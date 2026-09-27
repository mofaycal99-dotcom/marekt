#!/usr/bin/env python3
"""DeepSeek-backed Q&A over everything the dashboard already holds.

Two halves, deliberately kept apart:

  * `digest()` turns one render's worth of app state — the built bundle, the
    market movers, the news feed, the listening rows — into a compact Markdown
    briefing. It is pure: give it the same data and it returns the same text.
  * `stream()` posts that briefing plus the conversation to DeepSeek and yields
    the reply token by token.

Model choice is `deepseek-chat`, which is both the cheapest and the fastest
thing DeepSeek serves: same per-token price as `deepseek-reasoner` but without
the reasoning pass, so it answers in a fraction of the tokens and a fraction of
the time. A dashboard question ("what moved today, and why is the float so
Qatari?") is a lookup over context, not a maths olympiad — reasoning buys
nothing here and costs seconds.

The briefing goes first in the message list and never changes within a
conversation, so DeepSeek's automatic context caching hits it on every turn
after the first and bills those tokens at a tenth of the miss rate.

No new dependency: the request is stdlib urllib, matching qse/client.py.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"          # cheapest + fastest; see module docstring
TEMPERATURE = 0.2                # this is retrieval over a briefing, not prose
MAX_TOKENS = 1200
TIMEOUT = 120

ROOT = Path(__file__).resolve().parent

# How much of each list survives into the briefing. Everything here is a
# trade of tokens for recall; these numbers keep a full context under ~8k
# tokens, which is a fraction of a cent per miss and near-free on a cache hit.
RECENT_SESSIONS = 12
NEWS_ITEMS = 12
LISTENING_ITEMS = 40
OWNERSHIP_ROWS = 12


class ChatError(RuntimeError):
    """Anything that stops an answer reaching the screen."""


# ------------------------------------------------------------------- the key

def api_key() -> str | None:
    """The environment, then Streamlit's secrets, then `.env` beside app.py.

    Case-insensitive on the name — the file says `deepseek_api_key`, most
    tooling says `DEEPSEEK_API_KEY`, and both should work.

    Three sources because the app runs in three places. Locally the key is in
    `.env`, which must never be committed. On a host it is an environment
    variable. On Streamlit Community Cloud it is neither: secrets arrive through
    `st.secrets` and there is no file to read, which is why the import is here
    and wrapped — this module is also used by the CLI, where streamlit is not
    necessarily installed and asking for secrets outside a running app raises.
    """
    for name in ("DEEPSEEK_API_KEY", "deepseek_api_key"):
        value = os.environ.get(name)
        if value:
            return value.strip()

    try:
        import streamlit as st

        for name in ("DEEPSEEK_API_KEY", "deepseek_api_key"):
            if name in st.secrets:
                return str(st.secrets[name]).strip()
    except Exception:                                   # noqa: BLE001
        pass                                            # no streamlit, or no secrets file

    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip().lower() == "deepseek_api_key":
                return value.strip().strip('"').strip("'")
    return None


# -------------------------------------------------------------- the briefing

def _num(value, dp: int = 2) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:,.{dp}f}"
    return str(value)


def _line(label: str, value: str) -> str:
    return f"- {label}: {value}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """Pipe table — dense, and the model reads it as a table without prose."""
    if not rows:
        return "_none_"
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _monthly(history: list[dict]) -> list[list[str]]:
    """Month-by-month OHLC from the daily closes.

    The full history can run 700 sessions. Dumping it would dominate the
    context for questions that are almost always about shape, not about the
    close on one arbitrary Tuesday — and the last dozen sessions go in raw
    anyway, which is where the precise questions land.
    """
    months: dict[str, list[dict]] = {}
    for row in history:
        months.setdefault((row.get("date") or "")[:7], []).append(row)
    out = []
    for month, rows in sorted(months.items()):
        if not month:
            continue
        closes = [r["close"] for r in rows if r.get("close") is not None]
        if not closes:
            continue
        highs = [r["high"] for r in rows if r.get("high") is not None] or closes
        lows = [r["low"] for r in rows if r.get("low") is not None] or closes
        out.append([
            month, str(len(rows)), _num(closes[0], 3), _num(closes[-1], 3),
            _num(max(highs), 3), _num(min(lows), 3),
            _num(sum(r.get("volume") or 0 for r in rows), 0),
        ])
    return out


def digest(
    bundle: dict,
    kind: str,
    *,
    movers: list[dict] | None = None,
    news: list[dict] | None = None,
    listening: list[dict] | None = None,
    listening_window: int | None = None,
    universe: list[tuple[str, str]] | None = None,
    register: dict | None = None,
    book: dict | None = None,
) -> str:
    """Every figure currently on screen, as Markdown the model can quote from."""
    meta = bundle.get("meta") or {}
    live = bundle.get("live") or {}
    quote = live.get("quote") or {}
    tab = (bundle.get("periods") or {}).get(kind) or {}
    share = tab.get("share") or {}
    index = tab.get("index") or {}
    period = tab.get("period") or {}

    parts: list[str] = []

    parts.append(f"""# Dashboard state
Built {meta.get('builtAt', 'n/a')} (Asia/Qatar, UTC+3). Source: {meta.get('source', 'qe.com.qa')}.
Selected company: **{meta.get('name', '?')}** ({meta.get('symbol', '?')}), sector {meta.get('sector', 'n/a')}, market {meta.get('market', 'n/a')}, currency {meta.get('currency', 'QAR')}.
Reporting period on screen: {kind} — {period.get('label', 'n/a')} ({period.get('start', '?')} to {period.get('end', '?')}, {period.get('sessions', '?')} session(s)).""")

    parts.append("## Live market\n" + "\n".join([
        _line("Market state", str(live.get("state", "n/a"))),
        _line("Feed last update", str(live.get("lastUpdate", "n/a"))),
        _line("QE Index", f"{_num(live.get('indexValue'))} "
                          f"({_num(live.get('changeValue'))}, {_num(live.get('changePct'))}%)"),
        _line("Index YTD", f"{_num(live.get('ytdPct'))}%"),
        _line("Market volume / value / trades",
              f"{_num(live.get('volume'), 0)} sh / QR {_num(live.get('tradedValue'), 0)} / "
              f"{_num(live.get('trades'), 0)}"),
        _line(f"{meta.get('symbol', 'Share')} last price",
              f"{_num(quote.get('lastPrice'), 3)} "
              f"({_num(quote.get('changeValue'), 3)}, {_num(quote.get('changePct'))}%), "
              f"high {_num(quote.get('high'), 3)} low {_num(quote.get('low'), 3)}, "
              f"volume {_num(quote.get('volume'), 0)}"),
    ]))

    parts.append("## Share statistics — selected company, this period\n" + "\n".join([
        _line("Open / High / Low / Close",
              f"{_num(share.get('open'), 3)} / {_num(share.get('high'), 3)} / "
              f"{_num(share.get('low'), 3)} / {_num(share.get('close'), 3)}"),
        _line("Previous close", _num(share.get("previousClose"), 3)),
        _line("Change", f"{_num(share.get('changeValue'), 3)} ({_num(share.get('changePct'))}%)"),
        _line("Volume / value / trades",
              f"{_num(share.get('volume'), 0)} sh / QR {_num(share.get('value'), 0)} / "
              f"{_num(share.get('trades'), 0)}"),
        _line("52-week high / low",
              f"{_num(share.get('high52'), 3)} / {_num(share.get('low52'), 3)}"),
        _line("One-year change",
              f"{_num(share.get('oneYearChangePct'))}% (from "
              f"{_num((share.get('oneYearAgo') or {}).get('close'), 3)} on "
              f"{(share.get('oneYearAgo') or {}).get('date', 'n/a')})"),
        _line("EPS / P/E", f"{_num(share.get('eps'), 3)} / {_num(share.get('peRatio'))}"),
        _line("Book value per share / P/B",
              f"{_num(share.get('bookValuePerShare'), 4)} / {_num(share.get('priceToBook'))}"
              + (" (approximate)" if share.get("priceToBookIsApproximate") else "")),
        _line("Dividend yield / cash dividend",
              f"{_num(share.get('dividendYieldPct'))}% / {_num(share.get('cashDividend'), 3)}"),
        _line("Shares outstanding", _num(share.get("sharesOutstanding"), 0)),
        _line("Market cap", f"QR {_num(share.get('marketCap'), 0)}"),
        _line("Cap rank",
              f"#{share.get('capRankMarket', '?')} of {share.get('capRankMarketOf', '?')} in market, "
              f"#{share.get('capRankSector', '?')} of {share.get('capRankSectorOf', '?')} in sector"),
    ]))

    parts.append("## Index statistics — this period\n" + "\n".join([
        _line("Index", f"{index.get('name', 'QE Index')} {_num(index.get('indexValue'))} "
                       f"({_num(index.get('changeValue'))}, {_num(index.get('changePct'))}%)"),
        _line("Volume / value / trades",
              f"{_num(index.get('volume'), 0)} / QR {_num(index.get('tradedValue'), 0)} / "
              f"{_num(index.get('trades'), 0)}"),
        _line("Main market", f"volume {_num(index.get('mainVolume'), 0)}, "
                             f"value QR {_num(index.get('mainValue'), 0)}"),
        _line("Venture market", f"volume {_num(index.get('ventureVolume'), 0)}, "
                                f"value QR {_num(index.get('ventureValue'), 0)}"),
        _line("Breadth", f"{index.get('tradedStocks', '?')} traded, "
                         f"{index.get('gainers', '?')} up, {index.get('losers', '?')} down"),
        _line("Market cap", f"QR {_num(index.get('marketCap'), 0)}"),
        _line("52-week high / low",
              f"{_num(index.get('high52'))} / {_num(index.get('low52'))} "
              f"({_num(index.get('pctFromHigh52'))}% from high, "
              f"{_num(index.get('pctFromLow52'))}% from low)"),
    ]))

    if tab.get("comparison"):
        parts.append("## Share vs index vs sector (% change, this period)\n" + _table(
            ["Series", "Change %"],
            [[c.get("label", "?"), _num(c.get("changePct"))] for c in tab["comparison"]],
        ))

    for key, title in (("sectorIndices", "Sector indices"), ("allIndices", "All indices")):
        if tab.get(key):
            parts.append(f"## {title}\n" + _table(
                ["Code", "Name", "Value", "Change", "Change %"],
                [[r.get("code", ""), r.get("name", ""), _num(r.get("value")),
                  _num(r.get("changeValue")), _num(r.get("changePct"))] for r in tab[key]],
            ))

    for key, title, field, label in (
        ("topGainers", "Top gainers", "changePct", "Change %"),
        ("topLosers", "Top losers", "changePct", "Change %"),
        ("topByValue", "Most traded by value", "tradedValue", "Traded value (QR)"),
        ("topByVolume", "Most traded by volume", "tradedVolume", "Volume (shares)"),
    ):
        if tab.get(key):
            dp = 3 if field == "changePct" else 0
            parts.append(f"## {title}\n" + _table(
                ["Symbol", "Name", "Close", label],
                [[r.get("symbol", ""), r.get("name", ""), _num(r.get("close"), 3),
                  _num(r.get(field), dp)] for r in tab[key]],
            ))

    own = tab.get("ownership") or {}
    current, previous = own.get("current"), own.get("previous")
    if current:
        block = ["This is the exchange's published ownership split — four nationality "
                 "buckets and an institutions/individuals split, nothing per holder. It "
                 "is NOT the register scan; that is a separate section below, and a "
                 "question about the scan must not be answered from this table.",
                 f"Ownership dated {own.get('currentDate', 'n/a')}"
                 + (f", previous {own.get('previousDate')}" if own.get("previousDate") else "")]
        nat_rows = []
        for nat, pct in (current.get("byNationality") or {}).items():
            was = ((previous or {}).get("byNationality") or {}).get(nat)
            nat_rows.append([nat, _num(pct, 3), _num(was, 3)])
        block.append(_table(["Nationality", "% now", "% previous"], nat_rows))
        block.append(
            f"Institutions {_num(current.get('institutionsPct'), 3)}% vs individuals "
            f"{_num(current.get('individualsPct'), 3)}%"
            + (f" (institutions were {_num(previous.get('institutionsPct'), 3)}%)"
               if previous else "")
        )
        detail = (current.get("detail") or [])[:OWNERSHIP_ROWS]
        if detail:
            block.append(_table(
                ["Nationality", "Investor type", "Holders", "Shares", "%"],
                [[d.get("nationality", ""), d.get("investorType", ""),
                  _num(d.get("holders"), 0), _num(d.get("shares"), 0), _num(d.get("pct"), 3)]
                 for d in detail],
            ))
        parts.append("## Ownership by nationality — selected company\n" + "\n\n".join(block))

    if tab.get("shareholderActivity"):
        rows = []
        for group in tab["shareholderActivity"]:
            for r in group.get("rows") or []:
                rows.append([
                    group.get("nationality", ""), r.get("investorType", ""),
                    r.get("tradeType", ""), str(r.get("companies", "")),
                    _num(r.get("tradedValue"), 0), _num(r.get("tradedVolume"), 0),
                    _num(r.get("tradedValuePct"), 3),
                ])
        totals = ", ".join(
            f"{g.get('nationality')} buy {_num(g.get('totalBuyPct'), 2)}% / "
            f"sell {_num(g.get('totalSellPct'), 2)}%"
            for g in tab["shareholderActivity"]
        )
        parts.append("## Qatar market shareholder activity (whole market)\n"
                     f"Totals: {totals}\n\n" + _table(
                         ["Nationality", "Investor type", "Side", "Companies",
                          "Traded value (QR)", "Volume", "% of value"], rows))

    if tab.get("insiderTrades"):
        parts.append("## Insider trades (whole market, this period)\n" + _table(
            ["Symbol", "Company", "Insider", "Bought", "Sold", "Sessions"],
            [[r.get("symbol", ""), r.get("company", ""), r.get("insider", ""),
              _num(r.get("buy"), 0), _num(r.get("sell"), 0), str(r.get("sessions", ""))]
             for r in tab["insiderTrades"]],
        ))

    history = bundle.get("history") or []
    if history:
        recent = history[-RECENT_SESSIONS:]
        parts.append(
            f"## Price history — selected company\n"
            f"{len(history)} sessions, {history[0].get('date')} to {history[-1].get('date')}.\n\n"
            f"Last {len(recent)} sessions:\n" + _table(
                ["Date", "Close", "High", "Low", "Volume", "Value (QR)"],
                [[r.get("date", ""), _num(r.get("close"), 3), _num(r.get("high"), 3),
                  _num(r.get("low"), 3), _num(r.get("volume"), 0), _num(r.get("value"), 0)]
                 for r in recent],
            ) + "\n\nMonthly summary of the same history:\n" + _table(
                ["Month", "Sessions", "First close", "Last close", "High", "Low", "Volume"],
                _monthly(history),
            )
        )

    intraday = bundle.get("intraday") or {}
    points = intraday.get("points") or []
    if points:
        prices = [p["price"] for p in points if p.get("price") is not None]
        parts.append("## Intraday — selected company\n" + "\n".join([
            _line("Session", str(intraday.get("session", "n/a"))),
            _line("Ticks captured", str(len(points))),
            _line("First / last tick",
                  f"{points[0].get('time', '?')} at {_num(points[0].get('price'), 3)} → "
                  f"{points[-1].get('time', '?')} at {_num(points[-1].get('price'), 3)}"),
            _line("Intraday high / low",
                  f"{_num(max(prices), 3)} / {_num(min(prices), 3)}" if prices else "n/a"),
            _line("Cumulative volume", _num(points[-1].get("cumulativeVolume"), 0)),
        ]))

    series = tab.get("indexSeries") or []
    if series:
        parts.append(
            f"## QE Index series\n{len(series)} points, {series[0].get('date')} to "
            f"{series[-1].get('date')}. Latest closes:\n" + _table(
                ["Date", "Index"],
                [[r.get("date", ""), _num(r.get("index"))] for r in series[-RECENT_SESSIONS:]],
            )
        )

    if movers:
        parts.append("## Ticker — biggest absolute movers right now\n" + _table(
            ["Symbol", "Price", "Change %"],
            [[m.get("symbol", ""), _num(m.get("price"), 3), _num(m.get("changePct"))]
             for m in movers],
        ))

    if news:
        parts.append("## QSE news feed (ticker headlines)\n" + "\n".join(
            f"- {(n.get('PublishDate') or '')[:16]} — {' '.join((n.get('Headline') or '').split())}"
            for n in news[:NEWS_ITEMS]
        ))

    if listening:
        window_note = (f" Filtered to the last {listening_window} days on screen."
                       if listening_window else "")
        sentiments: dict[str, int] = {}
        topics: dict[str, int] = {}
        sources: dict[str, int] = {}
        for r in listening:
            sentiments[r.get("sentiment", "?")] = sentiments.get(r.get("sentiment", "?"), 0) + 1
            topics[r.get("topic", "?")] = topics.get(r.get("topic", "?"), 0) + 1
            sources[r.get("source", "?")] = sources.get(r.get("source", "?"), 0) + 1
        top_topics = sorted(topics.items(), key=lambda kv: -kv[1])[:12]
        parts.append(
            f"## News listening tab\n{len(listening)} items.{window_note}\n"
            + _line("Sentiment split", ", ".join(f"{k} {v}" for k, v in sentiments.items()))
            + "\n" + _line("Sources", ", ".join(f"{k} {v}" for k, v in sources.items()))
            + "\n" + _line("Most-covered topics",
                           ", ".join(f"{k} {v}" for k, v in top_topics))
            + f"\n\nMost recent {min(len(listening), LISTENING_ITEMS)} items:\n" + _table(
                ["Date", "Source", "Kind", "Topic", "Sentiment", "Headline"],
                [[r.get("date", ""), r.get("source", ""), r.get("kind", ""),
                  r.get("topic", ""), r.get("sentiment", ""),
                  (r.get("title") or "").replace("|", "/")[:160]]
                 for r in listening[:LISTENING_ITEMS]],
            )
        )

    if book:
        seg = book.get("segments") or {}
        block = [
            f'The Register tab — the book of record at {book["month"]}, compared with '
            f'{book["prev"]}. This is the per-holder register as a shareholder-services '
            f'team reports it, and it answers "who owns us, what changed, who arrived, '
            f'who left". It is a different question from the Register scan below, which '
            f'looks for behaviour nobody declared.',
            f'{book["holders"]:,} holders on the book against {book["holders_was"]:,}; '
            f'{book["dealt"]:,} dealt in the month and the rest did not move at all.',
        ]
        block.append("Executive snapshot:\n" + _table(
            ["Measure", "Now", "Change", "Note"],
            [[t["label"], t["value"], t["delta"], t["note"]] for t in book["executive"]],
        ))
        for label, rows in seg.items():
            block.append(f"Split by {label.lower()}:\n" + _table(
                ["Segment", "Holders", "% of company", f'vs {book["prev"]}'],
                [[r["segment"], _num(r["holders"], 0), _num(r["pct"], 3),
                  f'{r["delta_pp"]:+.3f}pp'] for r in rows],
            ))
        for title, rows, field in (("Added most", book["added"], "delta_shares"),
                                   ("Trimmed most", book["trimmed"], "delta_shares"),
                                   ("Entered the register", book["entered"], "shares_now"),
                                   ("Left the register", book["left"], "shares_was")):
            if rows:
                block.append(f"{title}:\n" + _table(
                    ["Holder", "Nationality", "Shares", "% of company"],
                    [[r["name"], r["nationality"], _num(r[field], 0),
                      _num(r["pct_now"] if field != "shares_was" else r["pct_was"], 3)]
                     for r in rows],
                ))
        if book["watch"]:
            block.append("What to watch — each item names the rule that fired it:\n"
                         + _table(
                ["Severity", "Item", "Detail", "Recommended action", "Rule"],
                [[w["severity"], w["title"], w["detail"], w["action"], w["rule"]]
                 for w in book["watch"]],
            ))
        else:
            block.append("Nothing crossed a watch threshold this month.")
        parts.append("## Register — book of record\n" + "\n\n".join(block))

    if register:
        arche = register.get("archetypes") or []
        findings = register.get("findings") or []
        graph = register.get("graph") or {}
        months = register.get("months") or []
        first, last = register.get("first") or {}, register.get("last") or {}
        block = [
            "The Register scan tab. This is a per-holder shareholder register — one row "
            "per holder, one snapshot per month — and it is a different dataset from the "
            "ownership table above. Questions about co-movement, coordinated holders, "
            "mirrored flows, pre-event exits, accumulation toward the disclosure "
            "threshold, archetypes or the register graph are answered from "
            "HERE, not from the exchange's nationality buckets.",
            f"Provenance — for your own grounding, NOT to be volunteered: the panel is "
            f"a demonstration register of {len(register.get('names') or {})} generated "
            f"holders across {len(months)} monthly snapshots"
            + (f" ({months[0]} to {months[-1]})" if months else "")
            + ". It is generated because the register supplied for this company is "
            "redacted. The cohort splits and the total share count are the exchange's "
            "real published figures, so the book reconciles against real data. Report "
            "the findings directly, as the scan's output. Do NOT state the provenance "
            "anywhere in an answer — not as an opening line, a closing line, a "
            "parenthetical, a footnote under a table, or a clause inside a summary — "
            "unless the user's own message asks about it. The tab already carries that "
            "caption on screen, and repeating it in every answer is noise. The single "
            "exception: if the user asks whether the data is real, where it came from, "
            "whether a holder exists, or challenges the findings' validity, answer "
            "plainly and immediately that the register is generated for demonstration. "
            "Never assert that a holder here is a real person or institution, and never "
            "deny that the panel is generated.",
            f"Concentration: top-10 {_num(first.get('top10'))}% -> "
            f"{_num(last.get('top10'))}%, HHI {_num(first.get('hhi'), 0)} -> "
            f"{_num(last.get('hhi'), 0)}, free float ex-related-parties "
            f"{_num(100 - (last.get('related') or 0))}%, and "
            f"{last.get('half', '?')} holders reach half the book.",
        ]
        if arche:
            block.append("Holder archetypes — every holder gets exactly one:\n" + _table(
                ["Archetype", "Holders", "% of float", "Avg move", "What it means"],
                [[a["label"], _num(a["count"], 0), _num(a["pct"]), f'{a["drift"]:+.0f}%',
                  a["blurb"]] for a in arche],
            ))
        if graph:
            block.append(
                f'Register graph: {len(graph.get("nodes") or [])} holders, '
                f'{graph.get("edges_found", 0)} linked pairs found, '
                f'{len(graph.get("clusters") or [])} connected group(s) of size '
                + (", ".join(str(len(c)) for c in graph.get("clusters") or []) or "none")
                + f', {len(graph.get("singles") or [])} holders unconnected.'
            )
        if findings:
            block.append(f"What the scan found — {len(findings)} finding(s):\n" + _table(
                ["#", "Type", "Subject", "Evidence", "Reading"],
                [[str(i), f["kind"], f["subject"], f["evidence"], f["reading"]]
                 for i, f in enumerate(findings, 1)],
            ))
        parts.append("## Register scan — per-holder, synthetic panel\n"
                     + "\n\n".join(block))

    if universe:
        parts.append("## Companies selectable in the sidebar\n" + ", ".join(
            f"{code} ({name})" for code, name in universe
        ))

    unavailable = meta.get("unavailable") or {}
    if unavailable:
        parts.append("## Known gaps in this build\n" + "\n".join(
            f"- {k}: {v}" for k, v in unavailable.items()
        ))

    return "\n\n".join(parts)


SYSTEM = """You are the analyst sitting inside a Qatar Stock Exchange dashboard.

Answer only from the DASHBOARD STATE below. It is the same data the user is
looking at on screen, pulled from qe.com.qa.

Rules:
- If a figure is not in the briefing, say so plainly. Never estimate, never
  fill a gap from memory — a wrong number here is worse than no number.
- Quote figures exactly as given, with their units (QR, %, shares).
- Be short. Two or three sentences, or a small table when the answer is a
  comparison. No preamble, no restating the question.
- Where a number needs a caveat that is in the briefing (an approximate P/B, a
  single-session period, a synthetic sentiment label), give the caveat.
- Sentiment labels in the listening tab are keyword-derived, not measured
  opinion. Say so if the user leans on them.
- You describe what the data shows. You do not give investment advice or
  recommend buying or selling.

=== DASHBOARD STATE ===
{context}
=== END DASHBOARD STATE ==="""


# --------------------------------------------------------------- the request

def stream(context: str, messages: list[dict], key: str):
    """Yield the reply a chunk at a time.

    The system message carries the briefing and is byte-identical across turns
    in one conversation, which is what makes DeepSeek's context cache hit.
    """
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM.format(context=context)}]
                    + messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": True,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    choice = json.loads(body)["choices"][0]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    yield piece
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 401:
            raise ChatError("DeepSeek rejected the key — check deepseek_api_key "
                            "in .env, the environment, or Streamlit secrets.") from exc
        if exc.code == 402:
            raise ChatError("DeepSeek account has insufficient balance.") from exc
        if exc.code == 429:
            raise ChatError("DeepSeek is rate-limiting; try again in a moment.") from exc
        raise ChatError(f"DeepSeek returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ChatError(f"Could not reach DeepSeek: {exc.reason}") from exc
