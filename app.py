#!/usr/bin/env python3
"""QSE share dashboard — a standalone Streamlit app.

    streamlit run app.py

Everything is native Streamlit: metric tiles, Altair charts, dataframes. No
iframe, no HTML renderer, no CLI. The whole body refreshes every 5 minutes,
which is the rate qe.com.qa regenerates its feeds.

Layout rules this file follows, so sections read as sections:
  * one big title per section, in document order
  * tiles come in full rows of equal width, never a ragged remainder
  * charts sitting side by side are given the same explicit height, so a short
    table never leaves a hole beside a tall chart
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from qse import Client, NotAvailable, archive, build, index_series, render
from qse.client import Unreachable
from qse.period import KINDS, resolve

import assistant
import listening
import media
import voice

OUT = Path(__file__).resolve().parent / "out"
REFRESH_SECONDS = 300  # the feed's own cadence; anything faster returns identical bytes

# Excel theme colours, matched to the source dashboard.
INK = "#000000"
BLUE_TEXT = "#0070C0"      # panel headings
NAVY = "#1F3864"           # table header band and rules
HEADER_FILL = "#DCE6F1"    # light-blue column-header fill
ROW_ALT = "#F2F2F2"        # zebra row
BORDER = "#BFBFBF"
RED = "#FF0000"            # negative text
GREEN = "#00B050"          # positive text
AMBER = "#FFC000"          # unchanged badge
BAR_BLUE = "#4472C4"       # current period
BAR_GRAY = "#A5A5A5"       # prior period
BAR_RED = "#C00000"        # comparison columns
LINE = "#3B3B6D"           # intraday / price line

# The user asked for this layout and palette exactly, which is the case where
# custom CSS is warranted: an Excel-styled table with zebra rows, a navy header
# rule and blue panel titles has no native Streamlit equivalent.
st.html(
    f"""
    <style>
      /* The toolbar is minimal and transparent, so the ticker can sit at the very
         top. Keep just enough padding to clear the sidebar-collapse control. */
      [data-testid="stHeader"]{{height:2.1rem;background:transparent}}
      [data-testid="stToolbar"]{{right:.4rem}}
      .block-container{{padding:2.3rem 1.4rem 1rem;max-width:2000px}}
      .stMainBlockContainer [data-testid="stVerticalBlock"]{{gap:.35rem}}
      [data-testid="stHorizontalBlock"]{{gap:.7rem}}
      [data-testid="stElementToolbar"]{{display:none}}
      [data-testid="stCaptionContainer"] p{{font-size:.7rem;color:#595959}}

      .ptitle{{color:{BLUE_TEXT};font-weight:700;font-size:.95rem;
              border-bottom:2px solid {HEADER_FILL};padding-bottom:.15rem;
              margin:.35rem 0 .25rem}}
      .ctitle{{color:{BLUE_TEXT};font-weight:700;font-size:.82rem;text-align:center;
              border:1px solid {BORDER};border-bottom:none;padding:.2rem;
              background:#fff}}
      .unit{{text-align:right;font-size:.72rem;color:{INK};padding-right:.2rem}}

      table.xl{{width:100%;border-collapse:collapse;font-size:.74rem;
               font-variant-numeric:tabular-nums;table-layout:fixed}}
      table.xl th,table.xl td{{padding:.14rem .35rem;overflow:hidden;
                              text-overflow:ellipsis;white-space:nowrap}}
      /* Opt-out for label cells whose whole point is the words in them — the
         related-party total line names three companies and reads as
         "Total without ..." when clipped. */
      table.xl td.wrap{{white-space:normal;overflow:visible;
                        text-overflow:clip;min-width:13rem}}
      /* key/value panel: label left, figure right, zebra rows */
      table.kvx td.k{{text-align:left;color:{INK}}}
      table.kvx td.v{{text-align:right;font-weight:600}}
      table.kvx tr:nth-child(even) td{{background:{ROW_ALT}}}
      table.kvx tr.b td{{font-weight:700}}
      table.kvx tr.sec td{{color:{BLUE_TEXT};font-weight:700;
                          border-bottom:2px solid {HEADER_FILL};background:#fff}}

      /* bordered data table with a light-blue header and a navy rule */
      table.box{{border:1px solid {BORDER}}}
      table.box thead th{{background:{HEADER_FILL};color:{NAVY};font-weight:700;
                         text-align:center;border:1px solid {BORDER};
                         font-size:.72rem}}
      table.box thead th.l{{text-align:left}}
      table.box tbody tr:first-child td{{border-top:3px solid {NAVY}}}
      table.box tbody td{{border:1px solid #E6E6E6;text-align:right}}
      table.box tbody td.l{{text-align:left}}
      table.box tbody tr:nth-child(even) td{{background:{ROW_ALT}}}
      table.box tbody td.m{{text-align:center;vertical-align:middle;
                           font-weight:600;background:#fff}}

      .up{{color:{GREEN}}}.down{{color:{RED}}}
      .badge{{border:1px solid {BORDER};text-align:center;padding:.3rem .2rem;
             margin-bottom:.3rem;background:#fff}}
      .badge b{{display:block;font-size:1.05rem;line-height:1.1}}
      .badge span{{font-size:.68rem;color:#595959}}
      .logo img{{height:46px}}
      .demo a{{color:{BLUE_TEXT}}}
      .demo{{background:#FFF4CE;border:1px solid #E8C87A;color:#6B5314;
            font-size:.72rem;padding:.3rem .55rem;margin:.1rem 0 .5rem}}
      /* Sliding monitor bar. Two identical runs plus a -50% translate gives a
         seamless loop; hover pauses it so a headline can be read. */
      .ticker{{overflow:hidden;white-space:nowrap;border:1px solid {BORDER};
              background:{ROW_ALT};margin:0 0 .5rem;height:1.65rem;
              display:flex;align-items:center}}
      .ticker .tk{{display:flex;width:max-content;
                  animation-name:tkslide;animation-timing-function:linear;
                  animation-iteration-count:infinite}}
      .ticker:hover .tk{{animation-play-state:paused}}
      @keyframes tkslide{{from{{transform:translateX(0)}}
                         to{{transform:translateX(-50%)}}}}
      .ticker .run{{display:inline-flex;align-items:center}}
      .ticker .ti{{font-size:.74rem;padding:0 .85rem;border-right:1px solid #D9D9D9;
                  font-variant-numeric:tabular-nums;color:{INK}}}
      .ticker .ti b{{font-weight:700}}
      .ticker .dot{{display:inline-block;width:.42rem;height:.42rem;border-radius:50%;
                   margin-right:.35rem}}
      .ticker .news{{background:{NAVY};color:#fff;font-size:.62rem;font-weight:700;
                    padding:.05rem .3rem;margin-right:.4rem;letter-spacing:.05em}}
      .ticker .breaking{{background:{RED}}}
      .ticker .when{{color:#7F7F7F;font-size:.68rem}}
      @media (prefers-reduced-motion:reduce){{.ticker .tk{{animation:none}}}}
    </style>
    """
)


MIN_INTRADAY_TICKS = 6


# ------------------------------------------------------------------- loaders

@st.cache_resource
def get_client() -> Client:
    return Client(cache_dir=OUT / ".cache")


@st.cache_resource
def listed() -> list[tuple[str, str]]:
    rows = get_client().live("MarketWatch")
    return sorted(
        ((r["Symbol"], r["CompanyEN"]) for r in rows if r.get("CompType") == "COMP"),
        key=lambda s: s[1],
    )


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Building from qe.com.qa …")
def load(symbol: str, kinds: tuple[str, ...], history_days: int, archive_market: bool) -> dict:
    """Every figure for one symbol. The TTL is the refresh, so a widget click
    re-renders from cache instead of refetching the market."""
    bundle = build(
        get_client(),
        symbol,
        kinds=kinds,
        refresh_seconds=0,  # Streamlit owns the refresh
        history_days=history_days,
        out=OUT,
        archive_ticks=True,
        archive_market=archive_market,
    )
    archive.record_periods(OUT, symbol, bundle["periods"])
    return bundle


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def news_items(limit: int = 12) -> list[dict]:
    """Market-wide headlines, newest first.

    One 108 KB POST covering every listed company, ~18 months deep — not the
    six-item per-company page scrape, which cost 400 KB for one issuer.
    """
    try:
        return get_client().news_feed()[:limit]
    except Exception:  # noqa: BLE001 — the ticker must never break the page
        return []


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def movers(limit: int = 14) -> list[dict]:
    """Biggest absolute movers from the live feed, for the price ticker."""
    rows = get_client().live("MarketWatch")
    out = []
    for r in rows:
        if r.get("CompType") != "COMP":
            continue
        try:
            change = float(r.get("PercentChange") or 0)
            price = float(r.get("LastPrice") or 0)
        except (TypeError, ValueError):
            continue
        if not price:
            continue
        out.append({"symbol": r["Symbol"], "price": price, "changePct": change})
    out.sort(key=lambda r: -abs(r["changePct"]))
    return out[:limit]


# --------------------------------------------------------------- formatting

def money(value, dp: int = 3) -> str:
    return "-" if value is None else f"{value:,.{dp}f}"


def whole(value) -> str:
    return "-" if value is None else f"{value:,.0f}"


def pct(value, dp: int = 2) -> str:
    return "-" if value is None else f"{value:.{dp}f}%"


def signed(value, dp: int = 2) -> str:
    return "-" if value is None else f"{value:+.{dp}f}%"


def tone(value) -> str:
    if value is None:
        return ""
    return "up" if value > 0 else "down" if value < 0 else ""


def brief_int(value) -> str:
    """Compact large counts: 7.5M rather than 7,500,892."""
    if value is None:
        return "-"
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= cut:
            return f"{value / cut:,.1f}{suffix}"
    return f"{value:,.0f}"


def frame(rows) -> pd.DataFrame:
    return pd.DataFrame(rows if rows else [])


# ------------------------------------------------------------------- pieces

def panel_title(text: str) -> None:
    st.html(f'<div class="ptitle">{escape(text)}</div>')


def kv_panel(rows: list[tuple]) -> None:
    """Label/value rows. A row is (label, value, tone, kind) where kind is
    '' | 'b' (bold) | 'sec' (blue section separator)."""
    out = []
    for label, value, cls, kind in rows:
        row_cls = f' class="{kind}"' if kind else ""
        val_cls = f"v {cls}".strip()
        out.append(
            f'<tr{row_cls}><td class="k">{escape(label)}</td>'
            f'<td class="{val_cls}">{escape(value)}</td></tr>'
        )
    st.html(f'<table class="xl kvx">{"".join(out)}</table>')


def boxed(title: str, headers: list[str], rows: list[list[tuple[str, str]]]) -> None:
    """Titled table with a light-blue header and a navy rule under it.

    Cells are (text, css class); the first column is left-aligned.
    """
    head = "".join(
        f'<th class="{"l" if i == 0 else ""}">{escape(h)}</th>'
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{("l " if i == 0 else "") + cls}">{text}</td>'
            for i, (text, cls) in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    st.html(
        f'<div class="ctitle">{escape(title)}</div>'
        f'<table class="xl box"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


def badge(value: str, label: str, colour: str) -> str:
    return (
        f'<div class="badge"><b style="color:{colour}">{escape(value)}</b>'
        f"<span>{escape(label)}</span></div>"
    )


def ticker_bar(live: dict, quotes: list[dict], headlines: list[dict]) -> None:
    """A continuously sliding monitor bar: session state, movers, then headlines.

    Pure CSS animation — st.html ignores JavaScript, and a marquee needs none.
    The item list is emitted twice and the track translated by exactly -50%, which
    is what makes the loop seamless rather than snapping back. It pauses on hover
    so a headline can actually be read.
    """
    items: list[str] = []

    # Only chip the session state when we actually know it — a bar reading
    # "QSE unknown" and nothing else is clutter, not monitoring.
    state = live.get("state")
    if state:
        dot = GREEN if state == "Open" else "#7F7F7F"
        items.append(
            f'<i class="dot" style="background:{dot}"></i><b>QSE {escape(state)}</b>'
        )
    if live.get("indexValue") is not None:
        cls = tone(live.get("changePct"))
        items.append(
            f'<b>QE Index</b> {money(live["indexValue"], 2)} '
            f'<span class="{cls}">{signed(live.get("changePct"))}</span>'
        )

    for q in quotes:
        cls = tone(q["changePct"])
        arrow = "&#9650;" if q["changePct"] > 0 else "&#9660;" if q["changePct"] < 0 else "&#8212;"
        items.append(
            f'<b>{escape(q["symbol"])}</b> {money(q["price"])} '
            f'<span class="{cls}">{arrow} {abs(q["changePct"]):.2f}%</span>'
        )

    for item in headlines:
        head = " ".join((item.get("Headline") or "").split())
        if not head:
            continue
        stamp = (item.get("PublishDate") or "")[:16].replace("T", " ")
        breaking = str(item.get("IsBreakingNews") or "").upper() == "Y"
        badge_cls = "news breaking" if breaking else "news"
        label = "BREAKING" if breaking else "NEWS"
        items.append(
            f'<span class="{badge_cls}">{label}</span> {escape(head[:170])}'
            + (f' <span class="when">{escape(stamp)}</span>' if stamp else "")
        )

    if not items:
        return
    run = "".join(f'<span class="ti">{piece}</span>' for piece in items)
    # Duration scales with content so the apparent speed stays constant however
    # many items there are. ~4s per item works out around 65 px/s, which is
    # readable without a two-minute wait to see the last headline.
    seconds = max(len(items) * 4, 30)
    st.html(
        f'<div class="ticker"><div class="tk" style="animation-duration:{seconds}s">'
        f'<span class="run">{run}</span><span class="run" aria-hidden="true">{run}</span>'
        f"</div></div>"
    )


# ------------------------------------------------------------------- charts

def price_and_volume(data: pd.DataFrame, x: str, x_type: str) -> None:
    """Thin price line above, red/green volume columns below, one shared x."""
    lo, hi = float(data["_price"].min()), float(data["_price"].max())
    mid = (hi + lo) / 2 or 1.0
    floor = abs(mid) * 0.004
    if (hi - lo) < floor * 2:
        lo, hi = mid - floor, mid + floor
    pad = (hi - lo) * 0.14

    price = (
        alt.Chart(data)
        .mark_line(color=LINE, strokeWidth=1.4)
        .encode(
            x=alt.X(f"{x}:{x_type}", title=None, axis=None),
            y=alt.Y("_price:Q", title=None,
                    scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False),
                    axis=alt.Axis(format=",.2f", grid=True, tickCount=5)),
            tooltip=[alt.Tooltip(f"{x}:{x_type}", title="When"),
                     alt.Tooltip("_price:Q", title="Price", format=",.3f"),
                     alt.Tooltip("_volume:Q", title="Volume", format=",.0f")],
        )
        .properties(height=190)
    )
    volume = (
        alt.Chart(data)
        .mark_bar(size=2.5)
        .encode(
            x=alt.X(f"{x}:{x_type}", title=None,
                    axis=alt.Axis(labelFontSize=9, tickCount=8, grid=False)),
            y=alt.Y("_volume:Q", title=None, axis=alt.Axis(format="~s", tickCount=3)),
            color=alt.condition(alt.datum._up, alt.value(GREEN), alt.value(RED)),
            tooltip=[alt.Tooltip(f"{x}:{x_type}"),
                     alt.Tooltip("_volume:Q", title="Volume", format=",.0f")],
        )
        .properties(height=86)
    )
    st.altair_chart(price, width="stretch")
    st.altair_chart(volume, width="stretch")


def ownership_chart(records: list[dict], order: list[str], names: list[str]) -> None:
    """Grouped columns on a log axis — blue for the newer date, grey for the older."""
    st.altair_chart(
        alt.Chart(frame(records))
        .mark_bar()
        .encode(
            x=alt.X("Nationality:N", sort=order, title=None,
                    axis=alt.Axis(labelAngle=0, labelFontSize=10)),
            xOffset=alt.XOffset("When:N", sort=names),
            # A bar's implicit baseline is zero, which is -inf on a log axis; y2
            # pins the columns to the axis floor.
            y=alt.Y("pct:Q", title=None,
                    scale=alt.Scale(type="log", domain=[0.1, 100]),
                    axis=alt.Axis(values=[0.1, 1, 10, 100], format=".2f",
                                  labelExpr="format(datum.value,'.2f')+'%'")),
            y2=alt.datum(0.1),
            color=alt.Color("When:N", sort=names,
                            scale=alt.Scale(domain=names, range=[BAR_BLUE, BAR_GRAY]),
                            legend=alt.Legend(orient="bottom", title=None,
                                              labelFontSize=10, symbolSize=70)),
            tooltip=["Nationality", "When", alt.Tooltip("pct:Q", format=".3f")],
        )
        .properties(height=162),
        width="stretch",
    )


def institutions_chart(points: list[dict], names: list[str], newest: str) -> None:
    """Two columns on an axis zoomed to the data, as the source draws it.

    `names` is the x order (chronological); `newest` decides the colour, so the
    current period is blue and the prior one grey regardless of x position.
    """
    data = frame(points)
    lo, hi = data["pct"].min(), data["pct"].max()
    if hi == lo:
        lo, hi = lo - 0.01, hi + 0.01
    pad = (hi - lo) * 0.6
    bars = (
        alt.Chart(data)
        .mark_bar(size=64)
        .encode(
            x=alt.X("When:N", sort=names, title=None,
                    axis=alt.Axis(labelAngle=0, labelFontSize=10)),
            y=alt.Y("pct:Q", title=None,
                    scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False),
                    axis=alt.Axis(format=".3f",
                                  labelExpr="format(datum.value,'.3f')+'%'")),
            # A bar's implicit baseline is zero. On an axis zoomed to ~29.4% that
            # is far outside the domain, so Vega clips the geometry and the chart
            # renders its axes with nothing in them.
            y2=alt.datum(lo - pad),
            color=alt.Color(
                "When:N", sort=names, legend=None,
                scale=alt.Scale(
                    domain=[newest] + [n for n in names if n != newest],
                    range=[BAR_BLUE] + [BAR_GRAY] * max(len(names) - 1, 1),
                ),
            ),
            tooltip=["When", alt.Tooltip("pct:Q", format=".3f")],
        )
    )
    labels = bars.mark_text(dy=-7, fontSize=10).encode(
        text=alt.Text("pct:Q", format=".3f"),
        color=alt.condition(alt.datum.When == newest,
                            alt.value(BAR_BLUE), alt.value("#7F7F7F")),
    )
    st.altair_chart((bars + labels).properties(height=150), width="stretch")


def comparison_chart(rows: list[dict]) -> None:
    """Three dark-red columns against a zero line, each labelled."""
    data = frame(rows)
    data["short"] = data["label"].str.replace(" Share", " Share", regex=False)
    lo = min(float(data["changePct"].min()), 0.0)
    hi = max(float(data["changePct"].max()), 0.0)
    pad = max((hi - lo) * 0.22, 0.15)
    bars = (
        alt.Chart(data)
        .mark_bar(size=52)
        .encode(
            x=alt.X("short:N", sort=None, title=None,
                    axis=alt.Axis(labelAngle=0, labelFontSize=10, orient="top")),
            y=alt.Y("changePct:Q", title=None,
                    scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False),
                    axis=alt.Axis(format=".2f",
                                  labelExpr="format(datum.value,'.2f')+'%'")),
            color=alt.condition(alt.datum.changePct >= 0,
                                alt.value(GREEN), alt.value(BAR_RED)),
            tooltip=["label", alt.Tooltip("changePct:Q", format="+.3f")],
        )
    )
    # Two sign-filtered text layers, because dy is a mark property and cannot be
    # made conditional inside one encoding (yOffset is a grouping channel, not a
    # pixel offset).
    text = alt.Text("changePct:Q", format=".2f")
    above = (
        bars.mark_text(dy=-8, fontSize=10, color="#404040")
        .encode(text=text)
        .transform_filter(alt.datum.changePct >= 0)
    )
    below = (
        bars.mark_text(dy=12, fontSize=10, color="#404040")
        .encode(text=text)
        .transform_filter(alt.datum.changePct < 0)
    )
    st.altair_chart((bars + above + below).properties(height=250), width="stretch")


@st.cache_data(ttl=1800, show_spinner="Loading press coverage …")
def press_rows() -> list[dict]:
    """Real press articles for the watched entities, via Google News RSS."""
    return listening.from_media(media.multi({
        "Estithmar": "Estithmar Holding",
        "Elegancia": "Elegancia Qatar",
    }))


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Loading news feed …")
def listening_rows() -> list[dict]:
    """Real QSE disclosures, attributed to companies where the headline names one."""
    client = get_client()
    names: dict[str, str] = {}
    for row in client.report("StocksSummary", resolve(client, "daily").path):
        for key in ("SYMBOL_NAME_3", "SYMBOL_NAME_4"):
            if row.get(key):
                names[row[key]] = row["SYMBOL_CODE"]
    for row in client.live("MarketWatch"):
        if row.get("CompType") == "COMP":
            names.setdefault(row["CompanyEN"], row["Symbol"])
    return listening.feed(client.news_feed(), names)


SENTIMENT_COLOURS = {"Positive": GREEN, "Neutral": "#A5A5A5", "Negative": RED}


def social_tab() -> None:
    """The social-listening demo. Every figure here is synthetic — see
    demo_social.py. Labelled on screen so it cannot be mistaken for measurement."""
    controls = st.columns([1.1, 1.6, 1.6, 1.2], gap="medium")
    with controls[0]:
        window = st.segmented_control(
            "Window", [30, 90, 180], default=90, key="soc_window",
            format_func=lambda d: f"{d}d", label_visibility="collapsed",
        ) or 90
    rows = press_rows() + listening_rows()
    cutoff = (date.today() - timedelta(days=window)).isoformat()
    rows = [r for r in rows if r["date"] >= cutoff]
    with controls[1]:
        picked_src = st.multiselect(
            "Source", sorted({r["source"] for r in rows}),
            placeholder="All sources", label_visibility="collapsed",
        )
    with controls[2]:
        picked_topic = st.multiselect(
            "Topic", sorted({r["topic"] for r in rows}),
            placeholder="All topics", label_visibility="collapsed",
        )
    with controls[3]:
        picked_sent = st.segmented_control(
            "Sentiment", listening.SENTIMENT_ORDER, selection_mode="multi",
            key="soc_sent", label_visibility="collapsed",
        ) or []

    if picked_src:
        rows = [r for r in rows if r["source"] in picked_src]
    if picked_topic:
        rows = [r for r in rows if r["topic"] in picked_topic]
    if picked_sent:
        rows = [r for r in rows if r["sentiment"] in picked_sent]
    if not rows:
        st.info("No mentions match those filters.")
        return

    stats = listening.summarise(rows)

    # Watched entities first — that is the point of the tab.
    watched = [r for r in rows if r["priority"]]
    panel_title(f'Priority coverage — {" · ".join(listening.WATCH)}')
    if not watched:
        st.caption(
            f"No {' or '.join(listening.WATCH)} disclosures in the last {window} days. "
            "Widen the window, or see the note below on Elegancia."
        )
    else:
        boxed("", ["Date", "Entity", "Outlet", "Type", "Sentiment", "Headline", "Link"], [
            [
                (escape(f'{r["date"]} {r["time"]}'), ""),
                (escape(r["watch"]), ""),
                (escape(r["source"][:24]), ""),
                (escape(r.get("kind", "")), ""),
                (escape(r["sentiment"]),
                 "up" if r["sentiment"] == "Positive"
                 else "down" if r["sentiment"] == "Negative" else ""),
                (escape(r["title"][:110]), "l"),
                (f'<a href="{escape(r["url"])}" target="_blank" rel="noopener">open</a>'
                 if r["url"] else "-", ""),
            ]
            for r in sorted(watched, key=lambda r: (r["date"], r["time"]), reverse=True)
        ])
    press = sum(1 for r in watched if r.get("kind") == "Press")
    filed = len(watched) - press
    st.caption(
        f"{press} press article(s) from named outlets and {filed} exchange "
        "disclosure(s). Press coverage comes from Google News; disclosures come "
        "from the exchange, which only carries formal filings — a contract win "
        "written up by a newspaper never appears there."
    )

    panel_title(f"Whole market — last {window} days")
    kpi = st.columns(6, gap="small")
    for col, label, value, colour in (
        (kpi[0], "Mentions", whole(stats["total"]), INK),
        (kpi[1], "Positive", pct(stats["sentimentPct"]["Positive"], 1), GREEN),
        (kpi[2], "Neutral", pct(stats["sentimentPct"]["Neutral"], 1), "#7F7F7F"),
        (kpi[3], "Negative", pct(stats["sentimentPct"]["Negative"], 1), RED),
        (kpi[4], "Net sentiment", signed(stats["netSentiment"], 1),
         GREEN if stats["netSentiment"] >= 0 else RED),
        (kpi[5], "Priority articles", whole(stats["priority"]),
         BAR_BLUE if stats["priority"] else "#7F7F7F"),
    ):
        with col:
            st.html(badge(value, label, colour))

    volume_col, mix_col = st.columns([3, 2], gap="medium")
    with volume_col:
        st.html('<div class="ctitle">Mentions over time by sentiment</div>')
        daily = {}
        for r in rows:
            key = (r["date"], r["sentiment"])
            daily[key] = daily.get(key, 0) + 1
        series = frame([
            {"date": d, "sentiment": s, "mentions": n} for (d, s), n in daily.items()
        ])
        series["date"] = pd.to_datetime(series["date"])
        st.altair_chart(
            alt.Chart(series)
            .mark_bar()
            .encode(
                # Ordinal, not temporal: mark_bar on a continuous time scale gets
                # a sub-pixel width (46 bars rendered under 0.4px wide and looked
                # like an empty chart). A band scale gives each day real width.
                x=alt.X("yearmonthdate(date):O", title=None,
                        axis=alt.Axis(format="%d %b", labelOverlap="greedy",
                                      labelAngle=0, tickCount=8)),
                y=alt.Y("sum(mentions):Q", title=None, stack="zero"),
                color=alt.Color(
                    "sentiment:N", sort=list(listening.SENTIMENT_ORDER),
                    scale=alt.Scale(domain=list(listening.SENTIMENT_ORDER),
                                    range=[SENTIMENT_COLOURS[s]
                                           for s in listening.SENTIMENT_ORDER]),
                    legend=alt.Legend(orient="bottom", title=None, labelFontSize=10),
                ),
                tooltip=["yearmonthdate(date):T", "sentiment:N", "sum(mentions):Q"],
            )
            .properties(height=196),
            width="stretch",
        )
    with mix_col:
        st.html('<div class="ctitle">Share of voice by topic</div>')
        # 39 one-article slivers is not a chart. Keep the top few, fold the rest.
        ranked = list(stats["byTopic"].items())
        named = [(t, n) for t, n in ranked if t != listening.MARKET_WIDE]
        head, tail = named[:6], named[6:]
        buckets = head + ([("Other companies", sum(n for _, n in tail))] if tail else [])
        wide = stats["byTopic"].get(listening.MARKET_WIDE, 0)
        if wide:
            buckets.append((listening.MARKET_WIDE, wide))
        topics = frame([{"topic": t, "mentions": n} for t, n in buckets])
        st.altair_chart(
            alt.Chart(topics)
            # Both radii explicit. Vega derives the outer radius from the space
            # left after the legend, so a bottom legend shrank it to ~50 and the
            # innerRadius of 46 left a 4px ring instead of a donut.
            .mark_arc(innerRadius=44, outerRadius=82, stroke="#fff", strokeWidth=2)
            .encode(
                theta=alt.Theta("mentions:Q", stack=True),
                color=alt.Color("topic:N",
                                legend=alt.Legend(orient="right", title=None,
                                                  labelFontSize=10, symbolSize=70),
                                scale=alt.Scale(scheme="blues")),
                order=alt.Order("mentions:Q", sort="descending"),
                tooltip=["topic:N", "mentions:Q"],
            )
            .properties(height=196),
            width="stretch",
        )

    top_col, wide_col = st.columns(2, gap="medium")
    with top_col:
        st.html('<div class="ctitle">Most-mentioned companies</div>')
        named = [(k, v) for k, v in stats["byTopic"].items() if k != listening.MARKET_WIDE]
        boxed("", ["Company", "Articles", "Share"], [
            [(escape(k), ""), (whole(v), ""), (pct(v / stats["total"] * 100, 1), "")]
            for k, v in named[:8]
        ] or [[("-", ""), ("-", ""), ("-", "")]])
    with wide_col:
        st.html('<div class="ctitle">Coverage split</div>')
        wide = stats["byTopic"].get(listening.MARKET_WIDE, 0)
        boxed("", ["Scope", "Articles", "Share"], [
            [("Attributed to a company", ""), (whole(stats["attributed"]), ""),
             (pct(stats["attributed"] / stats["total"] * 100, 1), "")],
            [("Market-wide notices", ""), (whole(wide), ""),
             (pct(wide / stats["total"] * 100, 1), "")],
        ])
        st.caption(
            "Market-wide items are exchange notices — trading-hour changes, FTSE "
            "index reviews, market statistics — not unattributed company news."
        )

    st.html('<div class="ctitle">Articles — newest first</div>')
    latest = [r for r in listening.priority_first(rows) if not r["priority"]][:12]
    boxed("", ["Date", "Company", "Outlet", "Sentiment", "Headline", "Link"], [
        [
            (escape(f'{r["date"]} {r["time"]}'), ""),
            (escape(r["topic"]), ""),
            (escape(r["source"][:22]), ""),
            (escape(r["sentiment"]),
             "up" if r["sentiment"] == "Positive"
             else "down" if r["sentiment"] == "Negative" else ""),
            (escape(r["title"][:120]), "l"),
            (f'<a href="{escape(r["url"])}" target="_blank" rel="noopener">open</a>'
             if r["url"] else "-", ""),
        ]
        for r in latest
    ])
    st.download_button(
        "Articles CSV", frame(rows).to_csv(index=False).encode(),
        file_name="qse_news_listening.csv", mime="text/csv",
    )


# ------------------------------------------------------------------- sidebar

with st.sidebar:
    st.subheader("Dashboard")
    options = listed()
    labels = {code: f"{name} · {code}" for code, name in options}
    codes = [c for c, _ in options]
    symbol = st.selectbox(
        "Company", codes,
        index=codes.index("IGRD") if "IGRD" in codes else 0,
        format_func=lambda c: labels[c],
    )
    history_days = st.select_slider(
        "Price history", options=[30, 90, 180, 365, 730], value=180,
        format_func=lambda d: f"{d} days",
    )
    archive_market = st.toggle(
        "Archive all instruments", value=False,
        help="Logs every instrument each tick (~25 KB) instead of just this one.",
    )
    st.caption(
        f"Refreshes every {REFRESH_SECONDS // 60} min — the rate qe.com.qa "
        "regenerates its feeds."
    )
    if st.button("Refresh now", icon=":material/refresh:", width="stretch"):
        load.clear()
        st.rerun()


@st.fragment(run_every=REFRESH_SECONDS)
def dashboard() -> None:
    """Two macro columns, as the source dashboard is laid out: charts and tables
    on the left, the figure panels down the right."""
    try:
        bundle = load(symbol, KINDS, history_days, archive_market)
    except NotAvailable as exc:
        st.error(f"No data: {exc}")
        return

    meta, live = bundle["meta"], bundle.get("live") or {}
    history = frame(bundle.get("history"))
    intraday = bundle.get("intraday") or {}
    ticks = frame(intraday.get("points"))

    ticker_bar(live, movers(), news_items())

    left, right = st.columns([2, 1], gap="medium")

    # ------------------------------------------------------------ selectors
    with left:
        top = st.columns([2, 3, 2], gap="small")
        with top[0]:
            if meta.get("logo"):
                st.html(f'<div class="logo"><img src="{meta["logo"]}" alt=""></div>')
        with top[1]:
            has_intraday = len(ticks) >= MIN_INTRADAY_TICKS
            spans: dict[str, int] = {"1D": 0} if has_intraday else {}
            if not history.empty:
                history["date"] = pd.to_datetime(history["date"])
                for name, n in (("1M", 21), ("3M", 62), ("6M", 124), ("1Y", 248)):
                    if n < len(history):
                        spans[name] = n
                spans["Max"] = len(history)
            chosen = st.segmented_control(
                "Range", list(spans), default=list(spans)[0] if spans else None,
                key="range", label_visibility="collapsed",
            ) or (list(spans)[0] if spans else None)
        with top[2]:
            kind = st.segmented_control(
                "Reporting period", list(bundle["periods"]),
                default=meta["defaultKind"], key="period",
                label_visibility="collapsed", format_func=lambda k: k.capitalize(),
            )
    if not kind:
        st.info("Pick a reporting period.")
        return
    tab = bundle["periods"][kind]
    share, index = tab["share"], tab["index"]

    # ------------------------------------------- left: price, charts, tables
    with left:
        if not spans:
            st.info("No price history for this symbol.")
        else:
            if chosen == "1D":
                window = ticks.copy()
                window["_price"], window["_volume"] = window["price"], window["volume"]
                window["_up"] = window["price"].diff().fillna(0) >= 0
                x_field, x_type = "time", "O"
                total = window["_volume"].sum()
            else:
                window = history.tail(spans[chosen]).copy()
                window["_price"], window["_volume"] = window["close"], window["volume"]
                window["_up"] = window["close"].diff().fillna(0) >= 0
                x_field, x_type = "date", "T"
                total = window["_volume"].iloc[-1]
            st.html(
                f'<div class="unit" style="text-align:left;font-weight:700">'
                f"Volume (shares) : {total:,.0f}</div>"
            )
            price_and_volume(window, x_field, x_type)

        own = tab["ownership"]
        current, previous = own.get("current"), own.get("previous")
        own_col, inst_col = st.columns(2, gap="medium")
        order = ["Qatari", "GCC", "Arab", "Foreigners"]
        with own_col:
            st.html('<div class="ptitle" style="text-align:center">'
                    "Ownership Percentage by Nationality</div>")
            if not current:
                st.caption("No register published for this period.")
            else:
                now_label = own["currentDate"][5:]
                prev_label = (own.get("previousDate") or "")[5:] or "prev"
                names = [now_label, prev_label]
                records = []
                for nat in order:
                    if nat not in current["byNationality"]:
                        continue
                    records.append({"Nationality": nat, "When": now_label,
                                    "pct": current["byNationality"][nat]})
                    if previous and previous["byNationality"].get(nat) is not None:
                        records.append({"Nationality": nat, "When": prev_label,
                                        "pct": previous["byNationality"][nat]})
                ownership_chart(records, order, names)
        with inst_col:
            st.html('<div class="ptitle" style="text-align:center">'
                    f'Institutions Shares in {escape(meta["name"].split()[0])}</div>')
            if not current:
                st.caption("Not published.")
            else:
                pts = []
                if previous:
                    pts.append({"When": (own.get("previousDate") or "")[5:],
                                "pct": previous["institutionsPct"]})
                pts.append({"When": own["currentDate"][5:],
                            "pct": current["institutionsPct"]})
                institutions_chart(
                    pts, [p["When"] for p in pts], own["currentDate"][5:]
                )

        mover_cols = st.columns(4, gap="small")
        for column, key, title, header, field, fmt, cls in zip(
            mover_cols,
            ("topGainers", "topLosers", "topByValue", "topByVolume"),
            ("Top Gainers", "Top Losers", "Top By Value", "Top By Volume"),
            ("Change Value", "Change Value", "Traded Value (QR)", "Volume"),
            ("changePct", "changePct", "tradedValue", "tradedVolume"),
            ("{:.3f}", "{:.3f}", "{:,.0f}", "{:,.0f}"),
            ("up", "down", "", ""),
        ):
            with column:
                rows_ = tab[key]
                boxed(
                    title, ["Name", header],
                    [[(escape(r["name"]), ""), (fmt.format(r[field]), cls)]
                     for r in rows_] or [[("-", ""), ("-", "")]],
                )

        act_col, cmp_col = st.columns([3, 2], gap="medium")
        with act_col:
            st.html('<div class="ptitle" style="text-align:center">'
                    "Qatar Market Shareholders Activitiy</div>")
            head = "".join(
                f'<th class="{"l" if i == 0 else ""}">{escape(h)}</th>'
                for i, h in enumerate(
                    ["Nationality", "Type", "Transaction", "Traded Value (%)",
                     "Total Buy (%)", "Total Sale (%)"]
                )
            )
            body = []
            for group in tab["shareholderActivity"]:
                legs = group["rows"]
                for i, r in enumerate(legs):
                    cells = []
                    if i == 0:
                        cells.append(
                            f'<td class="l m" rowspan="{len(legs)}">'
                            f'{escape(group["nationality"])}</td>'
                        )
                    if r["tradeType"] == "Buy":
                        cells.append(
                            f'<td class="m" rowspan="2">{escape(r["investorType"])}</td>'
                        )
                    cells.append(f'<td class="l">{escape(r["tradeType"])}</td>')
                    cells.append(f'<td>{pct(r["tradedValuePct"])}</td>')
                    if i == 0:
                        cells.append(
                            f'<td class="m" rowspan="{len(legs)}">'
                            f'{pct(group["totalBuyPct"])}</td>'
                        )
                        cells.append(
                            f'<td class="m" rowspan="{len(legs)}">'
                            f'{pct(group["totalSellPct"])}</td>'
                        )
                    body.append(f"<tr>{''.join(cells)}</tr>")
            st.html(
                f'<table class="xl box"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table>'
            )
        with cmp_col:
            st.html('<div class="ptitle" style="text-align:center">'
                    f'{escape(meta["name"].split()[0])} Compared to Market &amp; Sector</div>')
            comparison_chart(tab["comparison"])

    # --------------------------------------------- right: the figure panels
    with right:
        panel_title(f'{meta["name"].split()[0]} Share Update {tab["period"]["label"]}')
        st.html(f'<div class="unit">{escape(meta["currency"])}</div>')
        kv_panel([
            ("Market", meta["market"], "", ""),
            ("Symbol", meta["symbol"], "", ""),
            ("Previous Close", money(share["previousClose"]), "", ""),
            ("Open", money(share["open"]), "", ""),
            ("Low", money(share["low"]), "", ""),
            ("High", money(share["high"]), "", ""),
            ("Closing", money(share["close"]), "", ""),
            ("Change +/-", money(share["changeValue"]), tone(share["changeValue"]), ""),
            ("Change %", signed(share["changePct"], 3), tone(share["changePct"]), ""),
            ("1-Year Change", signed(share["oneYearChangePct"]),
             tone(share["oneYearChangePct"]), ""),
            ("Price to book", money(share["priceToBook"]), "", ""),
            ("Dividend (Yield)",
             "-" if not share["cashDividend"]
             else f'{money(share["cashDividend"])} ({pct(share["dividendYieldPct"])})',
             "", ""),
            ("52 Weeks High", money(share["high52"]), "", ""),
            ("52 Weeks Low", money(share["low52"]), "", ""),
            ("Volume", whole(share["volume"]), "", ""),
            ("Value", money(share["value"]), "", ""),
            ("Number of shares", whole(share["sharesOutstanding"]), "", ""),
            ("Market Cap", whole(share["marketCap"]), "", "b"),
            ("Cap rank to QE Market", whole(share["capRankMarket"]), "", ""),
            ("Cap rank to Sector", whole(share["capRankSector"]), "", ""),
        ])
        panel_title("QE Index Update")
        kv_panel([
            ("QE Index", money(index["indexValue"]), tone(index["changePct"]), "b"),
            ("Volume", whole(index["volume"]), "", ""),
            ("Value", money(index["tradedValue"]), "", ""),
            ("Change +/-", money(index["changeValue"], 2), tone(index["changeValue"]), ""),
            ("Change %", signed(index["changePct"]), tone(index["changePct"]), ""),
            ("Lowest Value 52 Weeks", money(index["low52"]), "", ""),
            ("Highest Value 52 Weeks", money(index["high52"]), "", ""),
            ("% Change from Lowest Value", signed(index["pctFromLow52"]),
             tone(index["pctFromLow52"]), ""),
            ("% Change from Highest Value", signed(index["pctFromHigh52"]),
             tone(index["pctFromHigh52"]), ""),
        ])

        badge_col, ins_col = st.columns([1, 3], gap="small")
        with badge_col:
            unchanged = max(
                (index["tradedStocks"] or 0) - (index["gainers"] or 0)
                - (index["losers"] or 0), 0
            )
            st.html(
                badge(whole(index["gainers"]), "Gainers", GREEN)
                + badge(whole(index["losers"]), "Losers", RED)
                + badge(whole(unchanged), "Unchanged", AMBER)
            )
        with ins_col:
            insiders = tab["insiderTrades"]
            boxed(
                "Insider Trades", ["Company Name", "Insider Name", "Buy", "Sell"],
                [
                    [
                        (escape(r["company"]), ""),
                        (f'<span dir="rtl">{escape(r["insider"][:26])}</span>', ""),
                        (whole(r["buy"]) if r["buy"] else "0", "up" if r["buy"] else ""),
                        (whole(r["sell"]) if r["sell"] else "0",
                         "down" if r["sell"] else ""),
                    ]
                    for r in insiders[:6]
                ] or [[("-", ""), ("-", ""), ("-", ""), ("-", "")]],
            )

        boxed(
            "Indices Performance", ["Index", "%"],
            [[(escape(i["name"]), ""), (signed(i["changePct"]), tone(i["changePct"]))]
             for i in tab["sectorIndices"]],
        )

        with st.popover("Export", icon=":material/download:", width="stretch"):
            st.download_button(
                "Bundle JSON", json.dumps(bundle, ensure_ascii=False, indent=1),
                file_name=f"{symbol}_dashboard.json", mime="application/json",
                width="stretch",
            )
            st.download_button(
                "Price history CSV", history.to_csv(index=False).encode(),
                file_name=f"{symbol}_history.csv", mime="text/csv",
                disabled=history.empty, width="stretch",
            )
            st.download_button(
                "Intraday CSV", ticks.to_csv(index=False).encode(),
                file_name=f"{symbol}_intraday.csv", mime="text/csv",
                disabled=ticks.empty, width="stretch",
            )
            st.download_button(
                "Printable HTML", render(bundle),
                file_name=f"{symbol}_dashboard.html", mime="text/html", width="stretch",
            )
        st.caption(
            f'feed {live.get("lastUpdate") or "-"} · built {meta["builtAt"][11:19]} AST'
        )


# ------------------------------------------------------------------- chatbot

# (icon, card label, the question actually sent)
SUGGESTIONS = [
    ("monitoring", "How did the share do today?",
     "How did the selected company's share perform this period, against the QE Index "
     "and its sector index?"),
    ("pie_chart", "Who owns this company?",
     "Break down the exchange's published ownership split — by nationality, and "
     "institutions vs individuals. What changed since the previous reading?"),
    ("trending_up", "What moved the market?",
     "What were the biggest gainers and losers on the market this period, and what "
     "was the breadth?"),
    ("newspaper", "What is the news saying?",
     "Summarise the news listening feed — sentiment split, most-covered topics, and "
     "the headlines that matter most."),
    ("calculate", "Is it expensive?",
     "Walk through the valuation figures for this company — P/E, P/B, dividend "
     "yield, market cap and where it ranks."),
    ("schedule", "How has it traded lately?",
     "Walk through the recent price history for this company — the trend, the "
     "highest and lowest closes, and how volume behaved."),
    ("inventory", "What moved on the register?",
     "Using the Register tab: what changed on the shareholder register this month — "
     "who added, who trimmed, who entered, who left, and what should be watched?"),
    ("hub", "What did the register scan find?",
     "Summarise the register scan: the holder archetypes, and every finding with its "
     "evidence and what it implies for the shareholder base."),
]

CHAT_HISTORY_TURNS = 8  # what gets resent each turn; the briefing carries the facts

# Every rule is scoped under .st-key-chatwrap. The market dashboard's Excel styling
# is deliberate (see the palette block at the top of this file) and must not inherit
# any of this — which is also why the global "gap:.35rem" is relaxed only in here.
CHAT_CSS = """
<style>
  .st-key-chatwrap{max-width:50rem;margin:0 auto}
  .st-key-chatwrap [data-testid="stVerticalBlock"]{gap:.75rem}

  /* ---- header: a hairline and a whisper, not a toolbar ---- */
  .st-key-chathead{border-bottom:1px solid #ECEFF2;padding-bottom:.5rem;
                   margin-bottom:.4rem}
  /* the row wraps by default and both children stretch, which drops Clear onto
     its own line; pin the row and let only the caption take the slack */
  .st-key-chathead{flex-wrap:nowrap}
  .st-key-chathead>div:first-child{flex:1 1 auto;min-width:0}
  .st-key-chatclear{flex:0 0 auto;width:auto}
  .chatbrand{display:flex;align-items:center;gap:.5rem;min-width:0}
  .chatbrand img{height:1.15rem;width:auto;border-radius:.15rem;flex-shrink:0}
  .cb-name{font-size:.85rem;font-weight:600;color:#1F3864;white-space:nowrap}
  .cb-sub{font-size:.72rem;color:#9AA2AA;overflow:hidden;text-overflow:ellipsis;
          white-space:nowrap}
  .st-key-chatclear button{border:none;background:transparent;color:#8A9199;
                           font-size:.75rem;padding:.15rem .4rem}
  .st-key-chatclear button:hover{color:#C00000;background:transparent}

  /* ---- empty state ---- */
  .st-key-chatempty h4{font-size:1.05rem;font-weight:600;color:#1F3864;
                       margin:.9rem 0 .25rem}
  .st-key-chatempty [data-testid="stCaptionContainer"] p{font-size:.78rem;
                       color:#77808A;line-height:1.55;max-width:34rem}

  /* ---- suggestion cards ---- */
  .st-key-suggestions{margin-top:.55rem}
  .st-key-suggestions button{width:100%;justify-content:flex-start;text-align:left;
        padding:.62rem .8rem;border-radius:.6rem;border:1px solid #E6EAEE;
        background:#fff;color:#3C444D;font-size:.82rem;font-weight:400;
        box-shadow:none;transition:border-color .15s,color .15s,background .15s}
  .st-key-suggestions button:hover{border-color:#0070C0;color:#0070C0;
                                   background:#F7FBFF}
  .st-key-suggestions button:focus{color:#0070C0;border-color:#0070C0}
  /* the button's inner flex row re-centres its own content, so left-aligning the
     button alone is not enough */
  .st-key-suggestions button>div{justify-content:flex-start;width:100%}

  /* ---- turns ---- */
  .st-key-chatwrap [data-testid="stChatMessage"]{background:transparent;padding:0;
        gap:0;margin:0 0 1.15rem}

  /* No avatars. They bought nothing and cost an indent: with one in place the
     answer started 34px right of the header, the input and the controls, so
     nothing in the column shared a left edge. The bubble marks the user turn. */
  .st-key-chatwrap [data-testid="stChatMessageAvatarUser"],
  .st-key-chatwrap [data-testid="stChatMessageAvatarAssistant"],
  .st-key-chatwrap [data-testid="stChatMessageAvatarCustom"]{display:none}

  /* The user turn hugs its own text and sits flush right. Without fit-content a
     two-word question renders as a 640px slab, and margin-left:auto is what
     actually pushes it over — flex-direction alone left it centred. */
  .st-key-chatwrap [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
        [data-testid="stChatMessageContent"]{background:#F4F7FA;
        border:1px solid #E7EDF2;border-radius:.8rem;
        padding:.45rem .8rem;width:fit-content;max-width:80%;
        margin-left:auto;margin-right:0;flex:0 1 auto}

  /* The answer is prose on the page, flush with the header and the composer. */
  .st-key-chatwrap [data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"]))
        [data-testid="stChatMessageContent"]{width:100%;flex:1 1 auto}

  .st-key-chatwrap [data-testid="stChatMessageContent"] p,
  .st-key-chatwrap [data-testid="stChatMessageContent"] li{font-size:.875rem;
        line-height:1.62;color:#2B3138}
  /* Do NOT touch the paragraph bottom margin here. Streamlit's stMarkdownContainer
     carries margin-bottom:-16px to cancel the paragraph's natural 1rem, so zeroing
     the paragraph leaves that negative margin uncancelled and collapses the
     container to 22.7-16=6.7px, after which the text paints outside its own
     bubble. Note also: never put an angle-bracket tag name in a comment in this
     block — st.html sanitizes its input and drops the entire style element. */
  .st-key-chatwrap [data-testid="stChatMessageContent"] strong{color:#1F3864}

  /* answers often come back as small tables — keep them in the same visual key
     as the dashboard's, but lighter */
  .st-key-chatwrap [data-testid="stChatMessageContent"] table{border-collapse:collapse;
        font-size:.79rem;font-variant-numeric:tabular-nums;margin:.5rem 0;width:auto}
  .st-key-chatwrap [data-testid="stChatMessageContent"] th{background:#F6F8FA;
        color:#1F3864;font-weight:600;text-align:left;
        padding:.28rem .6rem;border:1px solid #E6EAEE}
  .st-key-chatwrap [data-testid="stChatMessageContent"] td{padding:.26rem .6rem;
        border:1px solid #EDF0F3;color:#2B3138}

  /* ---- composer ---- */
  .st-key-composer [data-testid="stChatInput"]{border:1px solid #DFE5EB;
        border-radius:.85rem;background:#fff;box-shadow:0 1px 2px rgba(16,24,40,.04)}
  .st-key-composer [data-testid="stChatInput"]:focus-within{border-color:#0070C0;
        box-shadow:0 0 0 3px rgba(0,112,192,.10)}
  /* the inner shell carries its own grey fill and border from the Excel theme */
  .st-key-composer [data-testid="stChatInput"]>div{background:transparent;border:none}
  .st-key-composer [data-testid="stChatInputTextArea"]{font-size:.875rem;
        background:transparent}

  /* Arabic dictation is a first-class path here, so answers in Arabic have to
     read right-to-left rather than merely contain Arabic glyphs. */
  .st-key-chatwrap [class*="st-key-rtl"] p,
  .st-key-chatwrap [class*="st-key-rtl"] li{direction:rtl;text-align:right}
  .st-key-chatwrap [class*="st-key-rtl"] ul,
  .st-key-chatwrap [class*="st-key-rtl"] ol{padding-right:1.15rem;padding-left:0}

  /* voice controls read as an affordance under the box, not as a form */
  .st-key-tools{margin-top:.35rem}
  .st-key-voice_lang [data-testid="stSelectbox"]{height:auto}
  .st-key-voice_lang [data-testid="stSelectbox"]>div>div{border:1px solid #E6EAEE;
        background:#fff;border-radius:.5rem;min-height:2.05rem;height:2.05rem}
  .st-key-voice_lang input{font-size:.78rem;color:#77808A;height:2rem}
  .st-key-voice_lang svg{fill:#A8B0B8}
</style>
"""


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def chat_context(symbol: str, kind: str, history_days: int, archive_market: bool,
                 window: int) -> str:
    """The briefing the model answers from — every loader here is already cached
    by the two tabs above, so this costs a dict walk, not a fetch."""
    bundle = load(symbol, KINDS, history_days, archive_market)
    if kind not in bundle["periods"]:  # the selector can lag a symbol change
        kind = bundle["meta"]["defaultKind"]
    cutoff = (date.today() - timedelta(days=window)).isoformat()
    rows = [r for r in press_rows() + listening_rows() if r["date"] >= cutoff]
    rows.sort(key=lambda r: (r["date"], r.get("time") or ""), reverse=True)
    return assistant.digest(
        bundle, kind,
        movers=movers(), news=news_items(), listening=rows,
        listening_window=window, universe=listed(),
        register=register_panel(), book=book_digest(),
    )


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def book_digest() -> dict | None:
    """The register book, flattened for the briefing — latest month against prior."""
    panel = book_panel()
    if panel is None:
        return None
    from synth import book

    months, snaps = panel["months"], panel["snapshots"]
    total_shares = panel["total_shares"]
    month, prev_month = months[-1], months[-2]
    curr, prev = snaps[month], snaps[prev_month]
    whole = book.compare(prev, curr, total_shares)
    moved = book.what_moved(whole, (prev_month, month), total_shares)
    return {
        "month": month, "prev": prev_month,
        "holders": len(curr), "holders_was": len(prev),
        "dealt": sum(1 for r in whole["all_rows"]
                     if r["status"] == "held" and r["delta_shares"]),
        "executive": book.executive(prev, curr, whole, total_shares,
                                    (prev_month, month)),
        "segments": {label: book.segment(prev, curr, key, total_shares)
                     for label, key in book.SEGMENTS.items()},
        "added": moved["added"], "trimmed": moved["trimmed"],
        "entered": moved["entered"], "left": moved["left"],
        "watch": book.watchlist(whole, prev, curr, total_shares,
                                (prev_month, month)),
    }


ARABIC = re.compile(r"[\u0600-\u06FF]")


def rtl(text: str) -> bool:
    """Arabic present at all — enough to flip a chat turn right-to-left."""
    return bool(ARABIC.search(text or ""))


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def brand(symbol: str, history_days: int, archive_market: bool) -> tuple[str, str]:
    """Short company name and logo for the chat's own identity. The assistant is
    dressed as the company being analysed, not as the model behind it — which is
    also why the model name is not on screen."""
    try:
        meta = load(symbol, KINDS, history_days, archive_market)["meta"]
    except NotAvailable:
        return symbol, ""
    name = meta.get("name") or symbol
    return name.split()[0], meta.get("logo") or ""


def chat_tab() -> None:
    """Ask questions about everything on the other two tabs.

    Answers are grounded in a briefing built from the current render — no
    retrieval step, because the whole dashboard fits in one context window.
    """
    st.html(CHAT_CSS)

    key = assistant.api_key()
    if not key:
        st.error(
            "No DeepSeek key found. Add `deepseek_api_key=…` to `.env` beside `app.py`, "
            "then restart the app.",
            icon=":material/key_off:",
        )
        return

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    history = st.session_state.chat_messages

    with st.container(key="chatwrap"):
        # The wordmark identifies the chat in the header; the turn avatar stays a
        # plain mark, because most QSE logos are wide wordmarks and turn to mush
        # at avatar size.
        short, logo = brand(symbol, history_days, archive_market)
        head = st.container(horizontal=True, vertical_alignment="center", key="chathead")
        with head:
            mark = f'<img src="{logo}" alt="">' if logo else ""
            st.html(
                f'<div class="chatbrand">{mark}'
                f'<span class="cb-name">{escape(short)} chat</span>'
                f'<span class="cb-sub">· grounded in the live render '
                f'for {escape(symbol)}</span></div>'
            )
            if history:
                if st.button("Clear", width="content", key="chatclear"):
                    st.session_state.chat_messages = []
                    st.rerun()

        # Declared before the input so a fresh answer streams into place above the
        # box the user just typed in rather than below it.
        transcript = st.container()
        with transcript:
            for i, message in enumerate(history):
                with st.chat_message(message["role"]):
                    if rtl(message["content"]):
                        with st.container(key=f"rtl{i}"):
                            st.markdown(message["content"])
                    else:
                        st.markdown(message["content"])

        prompt = None
        opening = not history
        if opening:
            with st.container(key="chatempty"):
                st.markdown("#### What do you want to know?")
                st.caption(
                    "Answers come from the render you are looking at — prices, the "
                    "exchange's ownership split, market breadth, insider trades, the "
                    "news feed, and the per-holder register scan. Nothing is invented: "
                    "if a figure is not on the dashboard, you will be told so rather "
                    "than guessed at."
                )
            with st.container(key="suggestions"):
                columns = st.columns(2, gap="small")
                for i, (icon, label, question) in enumerate(SUGGESTIONS):
                    with columns[i % 2]:
                        if st.button(label, icon=f":material/{icon}:", key=f"sg{i}",
                                     width="stretch"):
                            prompt = question

        # Visual order is input-then-tools; execution order is the reverse, because
        # the transcript has to reach session state before st.chat_input mounts.
        composer = st.container(key="composer")
        tools = st.container(key="tools")
        with tools:
            row = st.container(horizontal=True, vertical_alignment="center", gap="small")
            with row:
                lang = st.selectbox(
                    "Dictation language", list(voice.LANGUAGES),
                    format_func=lambda code: voice.LANGUAGES[code],
                    label_visibility="collapsed", width=118, key="voice_lang",
                )
                heard = voice.mic(lang=lang, key="voice_mic")
        if heard.transcript:
            # Into the box, not straight to the model — a misheard ticker is easier
            # to fix before it becomes the question.
            st.session_state.chat_prompt = heard.transcript
        with composer:
            prompt = st.chat_input(
                "Ask about the market, the company, the register or the news …",
                submit_mode="disable", key="chat_prompt",
            ) or prompt

        if not prompt:
            return

        history.append({"role": "user", "content": prompt})
        kind = st.session_state.get("period") or "daily"
        window = st.session_state.get("soc_window") or 90
        # The model answers in the language it was asked in, so the prompt decides
        # the direction of both turns before a single token has come back.
        arabic = rtl(prompt)
        with transcript:
            with st.chat_message("user"):
                if arabic:
                    with st.container(key="rtl_live_q"):
                        st.markdown(prompt)
                else:
                    st.markdown(prompt)
            with st.chat_message("assistant"):
                answer_box = st.container(key="rtl_live_a") if arabic else st.container()
                try:
                    context = chat_context(symbol, kind, history_days, archive_market,
                                           window)
                    with answer_box:
                        answer = st.write_stream(assistant.stream(
                            context, history[-CHAT_HISTORY_TURNS:], key,
                        ))
                except NotAvailable as exc:
                    st.error(f"No data to answer from: {exc}", icon=":material/error:")
                    history.pop()
                    return
                except assistant.ChatError as exc:
                    st.error(str(exc), icon=":material/error:")
                    history.pop()
                    return

        history.append({"role": "assistant", "content": answer})
        if opening:
            st.rerun()  # retire the empty state now the conversation has started



# ------------------------------------------------------------------ register

# --------------------------------------------------------------- register book

SEVERITY_TONE = {
    "high":   ("#b00020", ":material/priority_high:"),
    "medium": ("#8a5a00", ":material/flag:"),
    "low":    ("#1b5e9c", ":material/info:"),
}


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Reading the register …")
def book_panel() -> dict | None:
    """Month-by-month snapshots of the register. None before it is generated."""
    if not (OUT / "synth" / "market.json").exists():
        return None
    from synth import book
    from synth.discover import load
    market, months, series, names = load()
    return {
        "market": market, "months": months,
        "snapshots": book.snapshots(series, names, months),
        "total_shares": market["total_shares"],
    }


def _delta_html(value: float, unit: str = "pp", dp: int = 2) -> str:
    colour = GREEN if value > 0 else RED if value < 0 else "#5a5a5a"
    return f'<span style="color:{colour}">{value:+.{dp}f}{unit}</span>'


def movers_table(title: str, rows: list[dict], field: str, when: str) -> None:
    """Five rows of who moved, in the house table style."""
    if not rows:
        st.caption(f"{title}: none in {when}.")
        return
    body = []
    for r in rows:
        shares = r["shares_now"] if field == "shares_now" else (
            r["shares_was"] if field == "shares_was" else r["delta_shares"])
        body.append([
            (escape(r["name"]), "l"),
            (escape(r["nationality"]), "l"),
            (brief_int(shares), "up" if shares > 0 else "down"),
            (f'{r["pct_now"] if field != "shares_was" else r["pct_was"]:.3f}%', ""),
        ])
    boxed(title, ["Holder", "Nat.", "Shares", "% of co."], body)


def _tone(delta, risk_on_rise: bool) -> str:
    """Red when a figure moved the way this KPI is monitored for, else green.

    Deliberately not "up is green". On a register half the KPIs are worse when
    they rise — concentration, HHI, related-party holding — and colouring by
    arithmetic sign would paint a book becoming more concentrated in green.
    """
    if delta is None or abs(delta) < 5e-3:
        return ""
    return "down" if ((delta > 0) == risk_on_rise) else "up"


def kpi_table(rows: list[dict]) -> None:
    from synth.book import LOOKBACKS
    spans = [span for _, span in LOOKBACKS]
    body = []
    for r in rows:
        dp = 0 if r["unit"] == "n" else 2
        cells = [(escape(r["label"]), "l wrap"),
                 (f'{r["value"]:,.{dp}f}' + ("%" if r["unit"] == "%" else ""), "b")]
        for span in spans:
            d = r[span]
            cells.append(("—" if d is None else f'{d:+,.{dp}f}'
                          + ("pp" if r["unit"] == "%" else ""),
                          _tone(d, r["risk_on_rise"])))
        body.append(cells)
    boxed("", ["KPI", "Now"] + [f"vs {s}" for s in spans], body)


def holdings_table(rows: list[dict], prev_month: str, month: str,
                   height: int = 340, key: str = "") -> pd.DataFrame:
    table = pd.DataFrame([
        {"#": i, "Holder": r["name"], "Nat.": r["nationality"],
         "Type": r["investor_type"], "Class": r["cls"],
         "Related": r["related"], "Board": r["board"],
         f"Shares {prev_month}": r["shares_was"] or None,
         f"% {prev_month}": r["pct_was"] or None,
         f"Shares {month}": r["shares_now"] or None,
         f"% {month}": r["pct_now"] or None,
         "Δ shares": r["delta_shares"] or None,
         "Diff": r["delta_pp"], "Status": r["status"]}
        for i, r in enumerate(rows, 1)
    ])
    st.dataframe(
        table, hide_index=True, height=height, key=key or None,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Class": st.column_config.TextColumn(
                width="small", help="P = passive, A = active"),
            "Related": st.column_config.CheckboxColumn(width="small"),
            "Board": st.column_config.CheckboxColumn(width="small"),
            f"Shares {prev_month}": st.column_config.NumberColumn(format="localized"),
            f"Shares {month}": st.column_config.NumberColumn(format="localized"),
            "Δ shares": st.column_config.NumberColumn(format="localized"),
            f"% {prev_month}": st.column_config.NumberColumn(format="%.3f%%"),
            f"% {month}": st.column_config.NumberColumn(format="%.3f%%"),
            "Diff": st.column_config.NumberColumn(format="%+.3fpp"),
        },
    )
    return table


def totals_row(view: dict, label: str, prev_month: str, month: str,
               ex_related: bool = True) -> None:
    """The two lines the client's own comparison file ends on.

    `ex_related` is dropped for the related-party cut itself, where excluding
    related parties from a related-party-only table leaves a row of zeros that
    reads as an error rather than as a tautology.
    """
    total, ex = view["total"], view["total_ex_related"]
    def line(name, t):
        return (f'<tr><td class="l wrap">{escape(name)}</td>'
                f'<td>{t["holders"]:,}</td>'
                f'<td>{t["shares_was"]:,}</td><td>{t["pct_was"]:.2f}%</td>'
                f'<td>{t["shares_now"]:,}</td><td>{t["pct_now"]:.2f}%</td>'
                f'<td class="{"up" if t["delta_pp"] >= 0 else "down"}">'
                f'{t["delta_pp"]:+.2f}pp</td></tr>')
    st.html(
        '<table class="xl box"><thead><tr><th class="l">Total</th><th>Holders</th>'
        f'<th>Shares {escape(prev_month)}</th><th>% {escape(prev_month)}</th>'
        f'<th>Shares {escape(month)}</th><th>% {escape(month)}</th><th>Diff</th>'
        "</tr></thead><tbody>"
        + line(label, total)
        + (line("Total without related parties", ex) if ex_related else "")
        + "</tbody></table>"
    )


# One palette for the splits, pinned by name so a segment is the same colour in
# its donut and its trend line. Vega assigns category colours in data order, and
# the donut carries one extra slice the line does not — without an explicit
# domain, Qatar is blue in one chart and red in the other.
SEGMENT_COLOURS = ["#1F3864", "#4472C4", "#8FAADC", "#C00000", "#00B050", "#7030A0"]
BELOW_FLOOR = "Below reporting floor"
BELOW_FLOOR_GREY = "#D9D9D9"


def split_block(title: str, rows: list[dict], frame_df, prev_month: str,
                month: str, height: int = 230) -> None:
    """One dimension: the table, its split at `month`, and its whole history."""
    names = [r["segment"] for r in rows]
    tone = alt.Scale(domain=names + [BELOW_FLOOR],
                     range=SEGMENT_COLOURS[:len(names)] + [BELOW_FLOOR_GREY])

    panel_title(title)
    table_col, pie_col, line_col = st.columns([1.15, 0.8, 1.15], gap="medium")

    with table_col:
        boxed("", ["Segment", "Holders", "Shares", "% of co.", f"vs {prev_month}"], [
            [(escape(r["segment"]), "l wrap"),
             (f'{r["holders"]:,}' + (f' ({r["holders_delta"]:+d})'
                                     if r["holders_delta"] else ""), ""),
             (brief_int(r["shares"]), ""),
             (f'{r["pct"]:.2f}%', "b"),
             (f'{r["delta_pp"]:+.2f}pp',
              "up" if r["delta_pp"] > 0 else "down" if r["delta_pp"] < 0 else "")]
            for r in rows
        ])

    with pie_col:
        # The segments cover the named holders only, so they stop short of 100%.
        # A pie asserts a whole, and rescaling to make one would quietly restate
        # every share. The gap is drawn instead, as the slice it actually is.
        residual = 100.0 - sum(r["pct"] for r in rows)
        slices = [{"segment": r["segment"], "pct": r["pct"]} for r in rows]
        if residual > 0.005:
            slices.append({"segment": BELOW_FLOOR, "pct": residual})
        st.altair_chart(
            alt.Chart(pd.DataFrame(slices))
            # outerRadius explicit: Vega derives it from whatever the legend
            # leaves, which shrinks the pie to a coin once the legend has five
            # rows. innerRadius stays 0 — a pie, not a ring.
            .mark_arc(innerRadius=0, outerRadius=80, stroke="#fff", strokeWidth=2)
            .encode(
                theta=alt.Theta("pct:Q", stack=True),
                color=alt.Color("segment:N", scale=tone,
                                legend=alt.Legend(orient="bottom", title=None,
                                                  columns=1, labelFontSize=10,
                                                  symbolSize=70)),
                order=alt.Order("pct:Q", sort="descending"),
                tooltip=["segment:N", alt.Tooltip("pct:Q", format=".2f",
                                                  title="% of company")],
            ).properties(height=height + 30),
            width="stretch",
        )
        st.caption(f"Split at {month}")

    with line_col:
        st.altair_chart(
            alt.Chart(frame_df).mark_line(strokeWidth=2).encode(
                x=alt.X("month:O", title=None,
                        axis=alt.Axis(labelAngle=-60, labelOverlap=True)),
                y=alt.Y("pct:Q", title="% of the company",
                        scale=alt.Scale(zero=False, type="symlog")),
                color=alt.Color("segment:N", scale=tone, title=None,
                                legend=alt.Legend(orient="bottom", columns=2)),
                tooltip=["month", "segment", alt.Tooltip("pct:Q", format=".3f")],
            ).properties(height=height)
        )


def register_book_tab() -> None:
    panel = book_panel()
    if panel is None:
        st.warning(
            "No register panel yet. It is generated locally — 250 holders across "
            "24 monthly snapshots, anchored to the published QSE cohort splits."
        )
        if st.button("Generate the register", type="primary",
                     icon=":material/build:", key="book_gen"):
            from synth.generate import run
            run()
            book_panel.clear()
            register_panel.clear()
            st.rerun()
        return

    from synth import book

    months, snaps = panel["months"], panel["snapshots"]
    total_shares = panel["total_shares"]

    head, pick, comp = st.columns([1.6, 1, 1], gap="medium")
    with head:
        st.markdown("#### Shareholder register — board pack")
    with pick:
        month = st.selectbox("Month", months, index=len(months) - 1, key="book_month")
    with comp:
        earlier = [m for m in months if m < month] or [month]
        prev_month = st.selectbox("Compared with", earlier, index=len(earlier) - 1,
                                  key="book_prev")

    curr, prev = snaps[month], snaps[prev_month]
    whole = book.compare(prev, curr, total_shares)
    moved = book.what_moved(whole, (prev_month, month), total_shares, top=50)
    watch = book.watchlist(whole, prev, curr, total_shares, (prev_month, month))
    now_m = book.metrics(curr, total_shares)

    st.caption(
        f"Register at {month} against {prev_month}. {len(curr):,} holders hold "
        f"{brief_int(now_m['shares'])} of {brief_int(total_shares)} shares in issue "
        f"({now_m['pct_registered']:.2f}%); the remainder sits in holdings below the "
        f"reporting floor. Every figure below is a number in the register or a "
        f"subtraction of two of them. The only section that applies judgement is "
        f"§9, and each item there names the rule that produced it."
    )

    # ------------------------------------------------- 1 executive snapshot
    panel_title("1 · Executive snapshot")
    with st.container(horizontal=True):
        for tile in book.executive(prev, curr, whole, total_shares,
                                   (prev_month, month)):
            st.metric(tile["label"], tile["value"], tile["delta"],
                      help=tile["note"], border=True)

    kpi_table(book.kpis(snaps, months, month, total_shares))
    st.caption(
        "Three lookbacks, because one month on a register is mostly noise — a "
        "single holder dealing moves a whole line. **Red marks movement in the "
        "direction that KPI is monitored for**, which is not the same as down: "
        "concentration, HHI and related-party holding are the ones that matter "
        "when they rise."
    )

    # --------------------------------------------------------- 2 top 200
    panel_title(f"2 · Top {book.TOP_N} holders")
    top = book.compare(prev, curr, total_shares, limit=book.TOP_N)
    table = holdings_table(top["rows"], prev_month, month, height=420, key="tbl_top")
    tail_pct = now_m["pct_registered"] - now_m["top200"]
    st.caption(
        f'The largest {min(book.TOP_N, len(top["all_rows"])):,} of '
        f'{len(top["all_rows"]):,} holders, covering {now_m["top200"]:.2f}% of the '
        f'company; the remaining names hold {tail_pct:.2f}%. Sort any column by '
        f'clicking it — Diff sorted ascending is the month\'s sellers.'
    )
    totals_row(top, f"Top {book.TOP_N}", prev_month, month)

    # ------------------------------------------- 3 local vs international
    split_block("3 · Local vs international",
                book.segment(prev, curr, book.SEGMENTS["Nationality"], total_shares),
                pd.DataFrame(book.segment_series(
                    snaps, months, book.SEGMENTS["Nationality"], total_shares)),
                prev_month, month)
    split_block("3b · By region",
                book.segment(prev, curr, book.SEGMENTS["Region"], total_shares),
                pd.DataFrame(book.segment_series(
                    snaps, months, book.SEGMENTS["Region"], total_shares)),
                prev_month, month)

    # ------------------------------------------------- 4 class P / A
    split_block("4 · By company class (P · A)",
                book.segment(prev, curr, book.SEGMENTS["Class"], total_shares),
                pd.DataFrame(book.segment_series(
                    snaps, months, book.SEGMENTS["Class"], total_shares)),
                prev_month, month)
    st.caption(
        "P is passive, A is active — carried on the register as a holder "
        "attribute, not inferred from how the holding moved. A rising active "
        "share means more of the book is being worked rather than held, which "
        "raises turnover and the odds of a stake being built quietly."
    )
    split_block("4b · By investor type",
                book.segment(prev, curr, book.SEGMENTS["Investor type"], total_shares),
                pd.DataFrame(book.segment_series(
                    snaps, months, book.SEGMENTS["Investor type"], total_shares)),
                prev_month, month)

    # ------------------------------------------------- 5 related parties
    panel_title("5 · Related parties")
    rel = book.compare(prev, curr, total_shares, keep=book.CUTS["Related parties"])
    holdings_table(rel["rows"], prev_month, month, height=160, key="tbl_rel")
    totals_row(rel, "Related parties", prev_month, month, ex_related=False)
    st.caption(
        "The three the client's own comparison file names in its "
        "\"Total Without Related Parties\" line — UCC, Infra Road and H'Collective "
        "— spelled out rather than hidden behind a flag only the system knows."
    )

    # -------------------------------------------------- 6 board members
    panel_title("6 · Board members")
    brd = book.compare(prev, curr, total_shares, keep=book.CUTS["Board members"])
    holdings_table(brd["rows"], prev_month, month, height=280, key="tbl_brd")
    totals_row(brd, "Board members", prev_month, month)
    st.caption(
        f'{now_m["n_board"]} directors on the register holding '
        f'{now_m["board"]:.3f}% of the company. Directors\' dealings are '
        "disclosable, so any movement here is a filing question before it is an "
        "ownership one. Names are generated for this panel."
    )

    # ---------------------------------------------------- 7 above 500K
    panel_title("7 · Holdings above 500K shares")
    big = book.compare(prev, curr, total_shares, keep=book.CUTS["Above 500K"],
                       limit=book.TOP_N)
    holdings_table(big["rows"], prev_month, month, height=340, key="tbl_500k")
    totals_row(big, "Above 500K", prev_month, month)
    st.caption(
        f'{now_m["n_above_500k"]:,} holders clear the 500,000-share floor and hold '
        f'{now_m["above_500k"]:.2f}% of the company between them. This is the cut '
        f"the client's own PDF publishes, reproduced with its two total lines."
    )

    # ----------------------------------------- 8 who entered and who left
    panel_title(f"8 · Who entered and who left — {prev_month} to {month}")
    ent, lef = st.columns(2, gap="medium")
    with ent:
        st.markdown(f'**Entered — {moved["entered_count"]} holder(s), '
                    f'{moved["entered_pct"]:+.3f}pp**')
        if moved["entered"]:
            holdings_table(moved["entered"], prev_month, month, height=240,
                           key="tbl_in")
        else:
            st.info(f"No holder joined the register in {month}.")
    with lef:
        st.markdown(f'**Left — {moved["left_count"]} holder(s), '
                    f'{-moved["left_pct"]:+.3f}pp**')
        if moved["left"]:
            holdings_table(moved["left"], prev_month, month, height=240,
                           key="tbl_out")
        else:
            st.info(f"No holder left the register in {month}.")

    add, trim = st.columns(2, gap="medium")
    with add:
        st.markdown("**Added most** — holders already on the book")
        holdings_table(moved["added"][:15], prev_month, month, height=240,
                       key="tbl_add")
    with trim:
        st.markdown("**Trimmed most** — holders already on the book")
        holdings_table(moved["trimmed"][:15], prev_month, month, height=240,
                       key="tbl_trim")
    st.caption(
        "Arrivals and departures are the one thing a single snapshot cannot show, "
        "which is why the comparison is against a named month rather than a period."
    )

    # -------------------------------------------- 9 month over month
    panel_title("9 · Month over month")
    tr = pd.DataFrame(book.trend(snaps, months, total_shares))
    view = tr.rename(columns={
        "month": "Month", "holders": "Holders", "entered": "In", "left": "Out",
        "dealt": "Dealt", "top10": "Top-10 %", "top20": "Top-20 %",
        "float_ex_related": "Float ex-rel %", "local": "Local %",
        "international": "Intl %", "passive": "Passive %", "active": "Active %",
        "related": "Related %", "board": "Board %", "hhi": "HHI",
        "n_above_500k": ">500K",
    })[["Month", "Holders", "In", "Out", "Dealt", "Top-10 %", "Top-20 %",
        "Float ex-rel %", "Local %", "Intl %", "Passive %", "Active %",
        "Related %", "Board %", "HHI", ">500K"]]
    st.dataframe(
        view.iloc[::-1], hide_index=True, height=380,
        column_config={
            c: st.column_config.NumberColumn(format="%.2f%%")
            for c in ("Top-10 %", "Top-20 %", "Float ex-rel %", "Local %",
                      "Intl %", "Passive %", "Active %", "Related %", "Board %")
        } | {"HHI": st.column_config.NumberColumn(format="%.0f")},
    )
    metric = st.selectbox(
        "Plot", ["Top-10 %", "Float ex-rel %", "Intl %", "Active %", "Related %",
                 "Holders", "HHI"], key="book_trend_metric")
    st.altair_chart(
        alt.Chart(view).mark_line(strokeWidth=2, color=BAR_BLUE, point=True).encode(
            x=alt.X("Month:O", title=None, axis=alt.Axis(labelAngle=-60)),
            y=alt.Y(f"{metric}:Q", title=metric, scale=alt.Scale(zero=False)),
            tooltip=["Month", metric],
        ).properties(height=240)
    )
    st.caption(
        "Newest first in the table, oldest first in the chart. Every row is one "
        "monthly snapshot of the register, so In / Out / Dealt reconcile against "
        "the holder tables above."
    )

    # ----------------------------------- 10 watch and recommended actions
    panel_title(f"10 · What to watch — {len(watch)} item(s)")
    if not watch:
        st.info(
            f"Nothing crossed a threshold between {prev_month} and {month}. "
            "Quiet months are the common case; try 2026-02 or 2024-11 on this panel."
        )
    else:
        for item in watch:
            colour, icon = SEVERITY_TONE[item["severity"]]
            with st.container(border=True):
                st.markdown(f'{icon} **{escape(item["title"])}**')
                st.caption(item["detail"])
                st.markdown(
                    f'<span style="color:{colour};font-size:.82rem">'
                    f'<b>Recommended action:</b> {escape(item["action"])}</span><br>'
                    f'<span style="color:#5a5a5a;font-size:.72rem">'
                    f'Rule: {escape(item["rule"])}</span>',
                    unsafe_allow_html=True,
                )
    st.caption(
        "The only section that applies judgement. Each item names the rule and the "
        "figure that tripped it, so a threshold you disagree with is one number to "
        "change rather than an opinion to argue with. The watchlist reports a change "
        "of state, never a standing fact: a holder that has been above 5% for two "
        "years is already disclosed and is not repeated here every month."
    )

    # --------------------------------------------------------- board pack
    panel_title("Export")
    full = pd.DataFrame([
        {"NIN": r["nin"], "Holder": r["name"], "Nationality": r["nationality"],
         "Bucket": r["bucket"], "Investor type": r["investor_type"],
         "Class": r["cls"], "Related party": r["related"],
         "Board member": r["board"],
         f"Shares {prev_month}": r["shares_was"], f"% {prev_month}": r["pct_was"],
         f"Shares {month}": r["shares_now"], f"% {month}": r["pct_now"],
         "Delta shares": r["delta_shares"], "Diff pp": r["delta_pp"],
         "Status": r["status"]}
        for r in whole["all_rows"]
    ])
    a, b, c = st.columns(3, gap="medium")
    with a:
        st.download_button(
            "Full register comparison (CSV)", full.to_csv(index=False),
            f"register-{month}-vs-{prev_month}.csv", "text/csv",
            icon=":material/download:", width="stretch")
    with b:
        st.download_button(
            "KPIs (CSV)",
            pd.DataFrame(book.kpis(snaps, months, month, total_shares)).to_csv(index=False),
            f"register-kpis-{month}.csv", "text/csv",
            icon=":material/download:", width="stretch")
    with c:
        st.download_button(
            "Month-over-month (CSV)", tr.to_csv(index=False),
            "register-trend.csv", "text/csv",
            icon=":material/download:", width="stretch")


# The register panel is synthetic (synth/generate.py) because the real thing is
# a per-holder register the exchange does not publish — the sample PDFs carry the
# schema but no values. Aggregates are anchored to figures qe.com.qa does publish,
# so the book reconciles against real data even though no holder in it is real.

# Archetype colours. The strip below doubles as the legend for the graph beside
# it, so these are the single source for both — a node and its card must never
# disagree about what colour a "Quiet accumulator" is.
ARCHETYPE_TONE = {
    "Quiet accumulator": "#8a5a00",
    "Coordinated":       "#7030A0",
    "Momentum chaser":   "#C00000",
    "Contrarian buyer":  "#00B050",
    "Exiting":           "#b00020",
    "Active trader":     "#5a5a5a",
    "Stable core":       "#1F3864",
}


def archetype_strip(rows: list[dict]) -> None:
    """One card per archetype: how many holders, how much float, which way."""
    cells = []
    for a in rows:
        colour = ARCHETYPE_TONE.get(a["label"], "#5a5a5a")
        cells.append(
            f'<div class="arch" style="border-top:3px solid {colour}">'
            f'<div class="arch-l">{escape(a["label"])}</div>'
            f'<div class="arch-n" style="color:{colour}">{a["count"]}'
            f'<span class="arch-u">holder{"" if a["count"] == 1 else "s"}</span></div>'
            f'<div class="arch-p">{a["pct"]:.1f}% of float · {a["drift"]:+.0f}% avg</div>'
            f'<div class="arch-b">{escape(a["blurb"])}</div>'
            "</div>"
        )
    st.html(
        "<style>"
        ".archrow{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 4px}"
        ".arch{flex:1 1 158px;min-width:158px;background:#F7F9FC;"
        "border:1px solid #BFBFBF;border-radius:3px;padding:7px 9px 8px}"
        ".arch-l{font-size:.74rem;font-weight:700;color:#1F3864;letter-spacing:.01em}"
        ".arch-n{font-size:1.55rem;font-weight:700;line-height:1.2}"
        ".arch-u{font-size:.66rem;font-weight:400;color:#5a5a5a;margin-left:4px}"
        ".arch-p{font-size:.70rem;color:#000;margin-bottom:3px}"
        ".arch-b{font-size:.68rem;color:#5a5a5a;line-height:1.32}"
        "</style>"
        f'<div class="archrow">{"".join(cells)}</div>'
    )


REPORTED = "Reported by the scan"
NOT_REPORTED = "Not reported"
REPORT_TONE = alt.Scale(domain=[REPORTED, NOT_REPORTED], range=[BAR_BLUE, "#9AA2AA"])


def _labelled(graph: dict):
    """Graph nodes as a frame, with the two figures the bar charts read."""
    d = pd.DataFrame(graph["nodes"])
    d["change"] = (d["x"] - 1.0) * 100.0
    d["flag"] = d["tag"].apply(lambda t: REPORTED if t else NOT_REPORTED)
    return d


def change_bars(graph: dict, n: int = 9) -> None:
    """Who grew and who shrank, as one ranked bar chart.

    This and the chart beside it replace a scatter that plotted the same two
    numbers against each other. The scatter was denser and, for anyone who does
    not read scatters for a living, worse: it asked the reader to decode two
    axes and a colour key before it said anything. Two ranked bars say the same
    thing in the form every finance reader already knows — a league table.
    """
    d = _labelled(graph)
    top = pd.concat([d.nlargest(n, "change"), d.nsmallest(n, "change")])
    st.altair_chart(
        alt.Chart(top).mark_bar().encode(
            y=alt.Y("name:N", title=None,
                    sort=alt.SortField("change", order="descending")),
            x=alt.X("change:Q", title="Change in holding over 24 months (%)",
                    axis=alt.Axis(format="+.0f")),
            color=alt.Color("flag:N", scale=REPORT_TONE, title=None,
                            legend=alt.Legend(orient="bottom")),
            tooltip=[alt.Tooltip("name:N", title="Holder"),
                     alt.Tooltip("cohort:N", title="Cohort"),
                     alt.Tooltip("change:Q", title="Change %", format="+.1f"),
                     alt.Tooltip("pct:Q", title="% of company", format=".3f"),
                     alt.Tooltip("archetype:N", title="Archetype")],
        ).properties(height=26 * len(top))
    )


def activity_bars(graph: dict, n: int = 12) -> None:
    """Who trades, ranked. The second axis of the old scatter, on its own."""
    d = _labelled(graph).nlargest(n, "y")
    st.altair_chart(
        alt.Chart(d).mark_bar().encode(
            y=alt.Y("name:N", title=None, sort=alt.SortField("y", order="descending")),
            x=alt.X("y:Q", title="Typical monthly movement (% of holding)"),
            color=alt.Color("flag:N", scale=REPORT_TONE, title=None,
                            legend=alt.Legend(orient="bottom")),
            tooltip=[alt.Tooltip("name:N", title="Holder"),
                     alt.Tooltip("cohort:N", title="Cohort"),
                     alt.Tooltip("y:Q", title="Monthly movement %", format=".2f"),
                     alt.Tooltip("pct:Q", title="% of company", format=".3f"),
                     alt.Tooltip("archetype:N", title="Archetype")],
        ).properties(height=26 * len(d))
    )


FINDING_TONE = {
    "Pre-event exit": ("#b00020", ":material/warning:"),
    "Mirrored flow": ("#8a5a00", ":material/swap_horiz:"),
    "Co-movement": ("#8a5a00", ":material/link:"),
    "Steady creep": ("#8a5a00", ":material/trending_up:"),
    "Price response": ("#1b5e9c", ":material/show_chart:"),
}


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Scanning the register …")
def register_panel() -> dict | None:
    """Analyse the synthetic register. None when it has not been generated yet."""
    if not (OUT / "synth" / "market.json").exists():
        return None
    from synth.discover import analyse
    return analyse()


def register_tab() -> None:
    panel = register_panel()
    if panel is None:
        st.warning(
            "No register panel yet. It is generated locally — 100 holders across "
            "24 monthly snapshots, anchored to the published QSE cohort splits."
        )
        if st.button("Generate the register", type="primary", icon=":material/build:"):
            from synth.generate import run
            run()
            register_panel.clear()
            st.rerun()
        return

    months = panel["months"]
    names, series = panel["names"], panel["series"]
    findings, market = panel["findings"], panel["market"]
    total = market["total_shares"]
    first, last = panel["first"], panel["last"]
    negative = {e["month"] for e in market["events"] if e["sentiment"] == "Negative"}

    st.caption(
        f"Synthetic register — {len(names)} named holders across {len(months)} monthly "
        f"snapshots ({months[0]} to {months[-1]}). Holder names and share counts are "
        f"generated; the cohort splits and the {brief_int(total)} total shares are the "
        "exchange's own published figures, so the book reconciles against real data. "
        "The detector is not told what was planted in it."
    )

    with st.container(horizontal=True):
        st.metric("Holders", len(names), border=True)
        st.metric("Findings", len(findings), border=True)
        st.metric(
            "Free float ex-related", f'{100 - last["related"]:.1f}%',
            f'{last["related"] - first["related"]:+.1f}pp related-party',
            delta_color="inverse", border=True,
        )
        st.metric(
            "Top-10 concentration", f'{last["top10"]:.1f}%',
            f'{last["top10"] - first["top10"]:+.1f}pp', border=True,
        )
        st.metric(
            "HHI", f'{last["hhi"]:,.0f}', f'{last["hhi"] - first["hhi"]:+,.0f}',
            delta_color="inverse", border=True,
            help="Herfindahl-Hirschman index over the register. Rising = concentrating.",
        )
        st.metric(
            "Half the book", f'{last["half"]} holders',
            f'{last["half"] - first["half"]:+d} vs {months[0]}', border=True,
            help="How few holders it takes to reach 50% of the shares on the register.",
        )

    panel_title("What kind of holders you have")
    archetype_strip(panel["archetypes"])
    st.caption(
        f'Every holder is classified, not only the flagged ones — the five detectors '
        f'describe the exceptions, this describes the book. Thresholds calibrate on '
        f'the register itself: the median holder moves {panel["norm"] * 100:.2f}% a '
        f'month after the common factor is removed, and "active" means 1.4x that, so '
        f'the same code reads a thin book and a liquid one the same way.'
    )

    from synth import book

    # ------------------------------------------------ 1 executive snapshot
    panel_title("1 · Executive snapshot")
    with st.container(horizontal=True):
        for tile in book.scan_executive(panel, total):
            st.metric(tile["label"], tile["value"], tile["delta"],
                      help=tile["note"], border=True)

    panel_title("2 · What kind of holders you have")
    archetype_strip(panel["archetypes"])
    st.caption(
        f'Every scanned holder is classified, not only the flagged ones — the '
        f'five detectors describe the exceptions, this describes the book. '
        f'Thresholds calibrate on the register itself: the median holder moves '
        f'{panel["norm"] * 100:.2f}% a month after the common factor is removed, '
        f'and "active" means 1.4x that, so the same code reads a thin book and a '
        f'liquid one the same way.'
    )

    # ------------------------------------------------------- 3 the two charts
    panel_title("3 · Who grew, who shrank, and who trades")
    grew, trades = st.columns([1, 1], gap="medium")
    with grew:
        st.markdown("**Biggest changes in holding** — 24 months")
        change_bars(panel["graph"])
    with trades:
        st.markdown("**Most actively traded holdings**")
        activity_bars(panel["graph"])
    st.caption(
        "Two league tables rather than one scatter. They carry the same two "
        "figures the scan works from — how much a holding changed over the panel, "
        "and how much it moves in an average month — but a ranked bar needs no "
        "decoding. Blue is a holder the scan reported; grey is one it did not, "
        "which is worth seeing: a holder can be the largest mover on the book and "
        "still be doing nothing a detector would call a pattern."
    )

    # ------------------------------------------------------- 4 the findings
    kinds = sorted({f["kind"] for f in findings})
    picked = st.pills("Finding type", kinds, selection_mode="multi",
                      key="reg_kind", label_visibility="collapsed") or kinds
    shown = [f for f in findings if f["kind"] in picked]

    panel_title(f"4 · What the scan found — {len(shown)} of {len(findings)}")
    cards, traj = st.columns([1, 1.1], gap="medium")
    with cards:
        with st.container(height=430):
            for f in shown:
                colour, icon = FINDING_TONE.get(f["kind"], ("#1b5e9c", ":material/info:"))
                with st.container(border=True):
                    st.markdown(f'{icon} **{f["subject"]}**')
                    st.caption(f'{f["kind"]} — {f["evidence"]}')
                    st.markdown(
                        f'<span style="color:{colour};font-size:.82rem">'
                        f'{escape(f["reading"])}</span>',
                        unsafe_allow_html=True,
                    )
            if not shown:
                st.info("No findings of that type.")

    with traj:
        labels = [f'{f["kind"]} — {f["subject"]}' for f in shown]
        if labels:
            choice = st.selectbox("Finding", labels, key="reg_focus",
                                  label_visibility="collapsed")
            focus = shown[labels.index(choice)]
            holders = focus["holders"][:6]   # a longer legend eats the plot area
        else:
            focus, holders = None, []

        if holders:
            rows = [
                {"month": m, "holder": names[k]["name"],
                 "pct": 100 * series[k][m] / total}
                for k in holders for m in months if m in series[k]
            ]
            frame_df = pd.DataFrame(rows)
            line = (
                alt.Chart(frame_df)
                .mark_line(point=False, strokeWidth=2)
                .encode(
                    x=alt.X("month:O", title=None,
                            axis=alt.Axis(labelAngle=-60, labelOverlap=True)),
                    y=alt.Y("pct:Q", title="% of shares outstanding",
                            scale=alt.Scale(zero=False)),
                    color=alt.Color("holder:N", title=None,
                                    legend=alt.Legend(orient="bottom", columns=2,
                                                      labelLimit=150, symbolLimit=6)),
                    tooltip=["month", "holder", alt.Tooltip("pct:Q", format=".3f")],
                )
            )
            layers = [line]
            if negative:
                marks = alt.Chart(pd.DataFrame({"month": sorted(negative)})).mark_rule(
                    color="#b00020", strokeDash=[4, 3], opacity=0.7
                ).encode(x="month:O")
                layers.insert(0, marks)
            st.altair_chart(alt.layer(*layers).properties(height=340))
            total_in = len(focus["holders"]) if focus else 0
            more = f" (plotting {len(holders)} of {total_in})" if total_in > len(holders) else ""
            st.caption(
                f"Pick a finding to plot the holders behind it. Dashed red rules "
                f"mark negative disclosures. {total_in} holder(s) in this "
                f"finding{more}."
            )
        else:
            st.info("Select a finding to plot the holders behind it.")

    # --------------------------------------------- 5 what moved in month X
    panel_title("5 · What the flagged holders did in a given month")
    month = st.selectbox("Month", months, index=len(months) - 1, key="scan_month")
    mv = book.scan_month(panel, month, total)
    if mv["rows"]:
        st.dataframe(
            pd.DataFrame([
                {"Holder": r["name"], "Flagged for": r["kinds"],
                 f"Shares {mv['prior'] or '—'}": r["shares_was"] or None,
                 f"Shares {month}": r["shares_now"],
                 "Δ shares": r["delta_shares"] or None,
                 "Δ %": r["delta_pct"] or None,
                 "% of company": r["pct"]}
                for r in mv["rows"]
            ]),
            hide_index=True, height=290,
            column_config={
                f"Shares {mv['prior'] or '—'}": st.column_config.NumberColumn(
                    format="localized"),
                f"Shares {month}": st.column_config.NumberColumn(format="localized"),
                "Δ shares": st.column_config.NumberColumn(format="localized"),
                "Δ %": st.column_config.NumberColumn(format="%+.2f%%"),
                "% of company": st.column_config.NumberColumn(format="%.3f%%"),
            },
        )
        st.caption(
            f'{mv["moved"]} of {len(mv["rows"])} flagged holders dealt in {month}. '
            f"A flagged holder that stands still for a month has not stopped being "
            f"flagged — the finding is about the run of months, not this one."
        )
    else:
        st.info(f"No flagged holder was on the register in {month}.")

    # --------------------------------- 6 what to watch, recommended actions
    watch = book.scan_watchlist(findings)
    panel_title(f"6 · What to watch — {len(watch)} item(s)")
    for item in watch:
        colour, icon = SEVERITY_TONE[item["severity"]]
        with st.container(border=True):
            st.markdown(f'{icon} **{escape(item["kind"])} — {escape(item["title"])}**')
            st.caption(item["detail"])
            st.markdown(
                f'<span style="color:{colour};font-size:.82rem">'
                f'<b>Recommended action:</b> {escape(item["action"])}</span>',
                unsafe_allow_html=True,
            )
    st.caption(
        "Severity is a business judgement, not a detector output, and it is set "
        "one line per finding type in synth/book.py rather than buried in this "
        "page. Accumulation and pre-event dealing rank highest because they are "
        "the two with a regulatory consequence."
    )

    panel_title("7 · Was the scan right?")
    truth_file = OUT / "synth" / "_ground_truth.json"
    if truth_file.exists():
        truth = json.loads(truth_file.read_text())
        blob = " ".join(f'{f["subject"]} {f["evidence"]}' for f in findings)
        rows = []
        for key, value in truth.items():
            wanted = value if isinstance(value, list) else [value]
            ok = all(w in blob for w in wanted)
            rows.append([
                (escape(key.replace("_", " ")), "l"),
                (escape(", ".join(wanted)), "l"),
                ("found" if ok else "missed", "up" if ok else "down"),
            ])
        boxed("", ["Planted behaviour", "Holder(s)", "Result"], rows)
        st.caption(
            "generate.py plants these; discover.py never reads the file. "
            "This is the check that the detectors work, not part of the scan."
        )

    panel_title("8 · Register snapshot")
    month = st.select_slider("Month", months, value=months[-1], key="reg_month",
                             label_visibility="collapsed")
    snap = sorted(panel["snapshots"][month], key=lambda r: -r["shares"])
    prev = months[months.index(month) - 1] if months.index(month) else None
    before = {r["nin"]: r["shares"] for r in panel["snapshots"][prev]} if prev else {}
    table = pd.DataFrame([
        {
            "#": i,
            "Holder": r["name"],
            "Nationality": r["nationality"],
            "Type": r["investor_type"],
            "Related party": r["related"],
            "Shares": r["shares"],
            "%": r["pct"],
            "Δ shares": r["shares"] - before[r["nin"]] if r["nin"] in before else None,
            "Δ %": (100 * (r["shares"] - before[r["nin"]]) / before[r["nin"]]
                    if r["nin"] in before and before[r["nin"]] else None),
        }
        for i, r in enumerate(snap, 1)
    ])
    st.dataframe(
        table, hide_index=True, height=360,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "Related party": st.column_config.CheckboxColumn(width="small"),
            "Shares": st.column_config.NumberColumn(format="localized"),
            "%": st.column_config.NumberColumn(format="%.3f%%"),
            "Δ shares": st.column_config.NumberColumn(format="localized"),
            "Δ %": st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )
    st.caption(
        f'{month} · {len(snap)} holders · top-10 {concentration_of(snap):.1f}% · '
        f'the exchange publishes only 7 nationality/type buckets for this company, '
        f'so none of the findings above are visible in its own reporting.'
    )


def concentration_of(rows: list[dict]) -> float:
    shares = sorted((r["shares"] for r in rows), reverse=True)
    return 100 * sum(shares[:10]) / sum(shares)


# --------------------------------------------------------------- demo notice
# A standing band, above the tabs so it is on screen whichever one is open, and
# sticky so it survives a long scroll through the register rather than leaving
# the page at the first swipe.
#
# The wording is scoped deliberately. "This data is simulated" as a blanket
# statement would be false on three of the five tabs — the market and news data
# is genuinely live from qe.com.qa — and a disclaimer that is wrong where the
# reader can check it is worse than none, because it teaches them to skip the
# part that is right.

st.html(
    """
    <style>
      /* Streamlit wraps every element in its own container, and this one is
         32px tall — shorter than the band itself, so a sticky band had no range
         to stick within and scrolled away with its wrapper. Collapsing the two
         wrappers makes the page-height vertical block the containing element,
         which is what sticky needs to span the whole scroll. */
      [data-testid="stElementContainer"]:has(> .stHtml > .demo-band),
      .stHtml:has(> .demo-band){display:contents}
      .demo-band{position:sticky;top:0;z-index:999;
                 margin:-2.3rem -1.4rem .9rem;
                 /* left padding clears the sidebar-collapse control, which sits
                    above this band and otherwise lands on the first words */
                 padding:.48rem 1.4rem .52rem 3rem;
                 background:#B00020;color:#fff;border-bottom:2px solid #7A0016;
                 font-size:.76rem;line-height:1.5}
      .demo-band b{letter-spacing:.07em}
      .demo-band .sep{opacity:.55;padding:0 .45rem}
      @media (max-width: 900px){ .demo-band{font-size:.7rem} }
    </style>
    <div class="demo-band">
      <b>DEMONSTRATION ONLY — NOT FOR DISTRIBUTION</b>
      <span class="sep">|</span>
      The shareholder register and every holder named on the Register and
      Register scan tabs are <b>simulated</b>. No figure on those tabs describes
      a real shareholder.
      <span class="sep">|</span>
      In production, register data will be encrypted in transit and at rest,
      privacy-certified, and reachable only by named authorised users.
    </div>
    """
)

tab_market, tab_social, tab_book, tab_register, tab_chat = st.tabs(
    ["Market dashboard", "News listening", "Register", "Register scan", "Ask the data"]
)
def safe(render, label: str) -> None:
    """Render one tab. A tab that raises must not blank the other three.

    Streamlit executes the script top to bottom, so an exception inside the
    first tab stops the run before the later ones are ever reached — losing the
    register scan and the assistant because qe.com.qa happened to be
    unreachable. Only the market and news tabs touch the network; catching here
    keeps the offline tabs usable.
    """
    try:
        render()
    except Unreachable as exc:
        # Not a bug and not worth a stack trace: the host this is deployed on
        # cannot route to qe.com.qa. Say so plainly, and point at the tabs that
        # do not need it — they are most of the app.
        st.warning(
            f"**{label} needs live data from qe.com.qa, and this server cannot "
            f"reach it.**\n\nThe exchange is not blocking anything — the host "
            f"running this app has no route to it. Nothing is wrong with the "
            f"data or the code.\n\n**Register** and **Register scan** work "
            f"normally: they run entirely on the register and never touch the "
            f"network.",
            icon=":material/cloud_off:",
        )
        with st.expander("Technical detail"):
            st.code(str(exc))
    except Exception as exc:                                # noqa: BLE001
        st.error(f"{label} could not be built: {type(exc).__name__} — {exc}")
        with st.expander("Details"):
            st.exception(exc)


with tab_market:
    safe(dashboard, "Market dashboard")
with tab_social:
    safe(social_tab, "News listening")
with tab_book:
    safe(register_book_tab, "Register")
with tab_register:
    safe(register_tab, "Register scan")
with tab_chat:
    safe(chat_tab, "Ask the data")
