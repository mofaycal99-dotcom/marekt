"""News listening from the real QSE feed — real articles, real links.

Replaces the synthetic demo dataset. Every row here is an actual exchange
disclosure from `POST /wp/mw_app/mw.php` `f=News`, with its real headline,
summary, publish date and a working link to `/displaynewsdetails?InfoID=…`.

Two things are *derived* rather than reported, and both are labelled as such in
the UI so nobody reads them as measurement:

* **Sentiment** is a transparent keyword rule (see POSITIVE/NEGATIVE below). It
  is not a model and not a measured signal — it is a demo stand-in for what a
  licensed listening platform would score.
* **Company attribution** matches the headline against listed-company names.
  Roughly a third of items are genuinely market-wide — trading-hour changes,
  FTSE index reviews, exchange-level statistics — and those are tagged
  "Market-wide" rather than forced onto a ticker.

What this is *not*: social media. There is no X, Instagram or blog content here,
because inventing posts and attributing them to real outlets would be fabricating
sources. Those channels need a licensed platform.
"""

from __future__ import annotations

import re

# Watched entities, matched on the headline and summary independently of the
# ticker index. Elegancia and the Estithmar divisions are not separately listed
# instruments, so ticker matching alone would miss them entirely.
WATCH = {
    "Estithmar": ("estithmar",),
    "Elegancia": ("elegancia",),
}

# A watched entity's ticker, where it has one. A watch match beats name matching,
# so an Estithmar headline cannot be stolen by another issuer's generic name.
WATCH_SYMBOL = {"Estithmar": "IGRD"}

# Single-token names that are ordinary business words, not identifiers. QIGD
# trades as "The Investors", which normalises to "investors" and matched the word
# in "will hold its investors relation conference call" — tagging an Estithmar
# disclosure as Qatari Investors Group.
GENERIC = {
    "investors", "general", "national", "united", "gulf", "commercial",
    "international", "islamic", "holding", "industries", "insurance", "medical",
    "electronic", "consumer", "cement", "fuel", "bank", "qatar", "qatari",
}

SOURCE = "QSE disclosure"
DOMAIN = "qe.com.qa"
MARKET_WIDE = "Market-wide"
SENTIMENT_ORDER = ("Positive", "Neutral", "Negative")

# Corporate boilerplate that differs between the feed's legal names and the
# report files' trading names: "The Qatari German For Medical Devices Company"
# vs "Qatari German Co. for Medical Devices".
NOISE = re.compile(
    r"\b(q\.?p\.?s\.?c|q\.?s\.?c|p\.?j\.?s\.?c|w\.?l\.?l|company|companies|"
    r"co|corp|corporation|ltd|limited|group|holding|holdings|the|for|and|"
    r"public|shareholding)\b",
    re.I,
)

POSITIVE = (
    "profit", "profits", "growth", "grew", "rise", "rises", "rose", "increase",
    "increased", "higher", "award", "awarded", "wins", "won", "signs", "signing",
    "agreement", "partnership", "expansion", "expands", "inaugurat", "launch",
    "opens", "opening", "dividend", "record", "upgrade", "endorses", "approves",
    "completes", "acquisition", "investment",
)
NEGATIVE = (
    "loss", "losses", "decline", "declined", "decrease", "decreased", "lower",
    "fell", "drop", "dropped", "miss", "missed", "postpone", "postponed",
    "delay", "delayed", "lack of quorum", "resign", "resignation", "penalty",
    "fine", "fined", "suspend", "suspended", "cancel", "cancelled", "terminate",
    "lawsuit", "dispute", "downgrade", "warning", "deficit",
)


# Exchange housekeeping notices carry positive/negative words incidentally
# ("Randomization of the Opening & Closing Time" hits "opening"). These are
# procedural, so they are forced to Neutral before the keyword rule runs.
PROCEDURAL = (
    "randomization", "randomisation", "index series", "semi annual review",
    "semi-annual review", "constituents", "trading hours", "opening & closing",
    "opening and closing", "index review", "market holiday", "circuit breaker",
    "tick size", "settlement cycle",
)


def _normalise(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    text = NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def entity_index(names: dict[str, str]) -> dict[str, str]:
    """name -> symbol, normalised and long enough to be distinctive.

    Short trading names are dropped: MarketWatch calls MARK "Rayan", which
    otherwise matches "QE Al Rayan Islamic Index" and mis-tags an index notice
    as company news.
    """
    index: dict[str, str] = {}
    for raw, symbol in names.items():
        key = _normalise(raw)
        if len(key) < 6:
            continue
        if " " not in key and key in GENERIC:
            continue  # a lone generic word is not an identifier
        index.setdefault(key, symbol)
    return index


def attribute(headline: str, index: dict[str, str]) -> str | None:
    """Longest matching company name wins; None means market-wide."""
    text = _normalise(headline)
    best: tuple[int, str] | None = None
    for key, symbol in index.items():
        if key and key in text and (best is None or len(key) > best[0]):
            best = (len(key), symbol)
    return best[1] if best else None


def classify(text: str) -> str:
    """Keyword sentiment. Deliberately simple, and labelled as such in the UI."""
    low = (text or "").lower()
    if any(term in low for term in PROCEDURAL):
        return "Neutral"
    neg = sum(1 for w in NEGATIVE if w in low)
    pos = sum(1 for w in POSITIVE if w in low)
    if neg > pos:
        return "Negative"
    if pos > neg:
        return "Positive"
    return "Neutral"


def feed(rows: list[dict], names: dict[str, str]) -> list[dict]:
    """Shape the real news feed into listening rows, newest first."""
    index = entity_index(names)
    out = []
    for row in rows:
        headline = " ".join((row.get("Headline") or "").split())
        if not headline:
            continue
        summary = " ".join((row.get("Summary") or "").split())
        blob = (headline + " " + summary).lower()
        watched = [label for label, terms in WATCH.items()
                   if any(term in blob for term in terms)]
        # A watch hit is authoritative; fall back to name matching otherwise.
        symbol = next(
            (WATCH_SYMBOL[label] for label in watched if label in WATCH_SYMBOL),
            None,
        ) or attribute(headline, index)
        out.append({
            "kind": "Disclosure",
            "priority": bool(watched),
            "watch": ", ".join(watched),
            "date": (row.get("PublishDate") or "")[:10],
            "time": (row.get("PublishDate") or "")[11:16],
            "source": SOURCE,
            "domain": DOMAIN,
            "topic": symbol or MARKET_WIDE,
            "sentiment": classify(headline + " " + summary),
            "breaking": str(row.get("IsBreakingNews") or "").upper() == "Y",
            "title": headline,
            "summary": summary,
            "url": row.get("url") or "",
        })
    return out


def priority_first(rows: list[dict]) -> list[dict]:
    """Watched entities first, then everything else — each newest first."""
    return sorted(
        rows,
        key=lambda r: (not r["priority"], r["date"], r["time"]),
        reverse=False,
    )[::1] if False else (
        sorted([r for r in rows if r["priority"]],
               key=lambda r: (r["date"], r["time"]), reverse=True)
        + sorted([r for r in rows if not r["priority"]],
                 key=lambda r: (r["date"], r["time"]), reverse=True)
    )


def from_media(items: list[dict]) -> list[dict]:
    """Shape Google News items into the same row schema as the disclosures."""
    out = []
    for item in items:
        stamp = item.get("published")
        out.append({
            "priority": True,  # media queries are the watched entities by definition
            "watch": item.get("entity", ""),
            "date": stamp.date().isoformat() if stamp else "",
            "time": stamp.strftime("%H:%M") if stamp else "",
            "source": item.get("outlet") or "Media",
            "domain": "news.google.com",
            "topic": item.get("entity", ""),
            "sentiment": classify(item["title"]),
            "breaking": False,
            "title": item["title"],
            "summary": "",
            "url": item.get("url", ""),
            "kind": "Press",
        })
    return [r for r in out if r["date"]]


def summarise(rows: list[dict]) -> dict:
    total = len(rows) or 1
    by_sentiment = {s: sum(1 for r in rows if r["sentiment"] == s) for s in SENTIMENT_ORDER}
    by_topic: dict[str, int] = {}
    for r in rows:
        by_topic[r["topic"]] = by_topic.get(r["topic"], 0) + 1
    return {
        "total": len(rows),
        "bySentiment": by_sentiment,
        "sentimentPct": {s: n / total * 100 for s, n in by_sentiment.items()},
        "netSentiment": (by_sentiment["Positive"] - by_sentiment["Negative"]) / total * 100,
        "byTopic": dict(sorted(by_topic.items(), key=lambda kv: -kv[1])),
        "attributed": sum(1 for r in rows if r["topic"] != MARKET_WIDE),
        "priority": sum(1 for r in rows if r["priority"]),
        "byWatch": {
            label: sum(1 for r in rows if label in (r["watch"] or ""))
            for label in WATCH
        },
        "companies": len({r["topic"] for r in rows if r["topic"] != MARKET_WIDE}),
    }
