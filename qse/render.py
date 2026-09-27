"""Render the dashboard bundle as a self-contained, theme-aware HTML page.

Panel-for-panel reproduction of the source Excel dashboard, with Daily / Weekly /
Monthly tabs and a self-refresh. No external assets, no CDN, no build step.

Chart choices follow the source deliberately, including the two that a chart
reviewer would object to — the zoomed institutional-ownership axis and the log
ownership axis. Both carry their scale on the page so the reader can see it.
"""

from __future__ import annotations

import html
import json
import math
from datetime import date

# Categorical slots (dataviz reference palette, validated all-pairs both modes).
SERIES = {"light": ("#2a78d6", "#eb6834"), "dark": ("#3987e5", "#d95926")}
UP, DOWN = "#0ca30c", "#d03b3b"  # status good / critical — always with a signed label

MONTHS = (
    "January February March April May June July "
    "August September October November December"
).split()

TAB_ORDER = ("daily", "weekly", "monthly")


# --------------------------------------------------------------- formatting

def _n(value, dp: int = 3) -> str:
    return "–" if value is None else f"{value:,.{dp}f}"


def _int(value) -> str:
    return "–" if value is None else f"{value:,.0f}"


def _pct(value, dp: int = 2) -> str:
    return "–" if value is None else f"{value:+.{dp}f}%"


def _plain_pct(value, dp: int = 2) -> str:
    return "–" if value is None else f"{value:.{dp}f}%"


def _sign(value) -> str:
    if value is None:
        return "flat"
    return "up" if value > 0 else "down" if value < 0 else "flat"


def _short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}-{MONTHS[d.month - 1][:3]}"


def _e(text) -> str:
    return html.escape(str(text), quote=True)


# ------------------------------------------------------------- html helpers

def _panel(title: str, body: str, *, span: int, note: str = "") -> str:
    sub = f'<p class="note">{_e(note)}</p>' if note else ""
    return (
        f'<section class="panel" style="--span:{span};--span-md:{12 if span >= 12 else 6}">'
        f"<h2>{_e(title)}</h2>{sub}{body}</section>"
    )


def _rows(rows: list[tuple[str, str, str]]) -> str:
    out = ['<table class="kv">']
    for label, value, tone in rows:
        cls = f' class="{tone}"' if tone else ""
        out.append(f"<tr><th>{_e(label)}</th><td{cls}>{value}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _table(headers: list[str], body: list[list[str]], *, right_from: int = 1) -> str:
    head = "".join(
        f'<th{" class=\"num\"" if i >= right_from else ""}>{_e(h)}</th>'
        for i, h in enumerate(headers)
    )
    out = []
    for row in body:
        cells = "".join(
            c if c.startswith("<td") else
            f'<td{" class=\"num\"" if i >= right_from else ""}>{c}</td>'
            for i, c in enumerate(row)
        )
        out.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(out)}</tbody></table>"


# ------------------------------------------------------------------ charts

def _columns(items: list[tuple[str, float | None]]) -> str:
    """Vertical columns around a zero line — the source's comparison chart."""
    values = [v for _, v in items if v is not None] or [0.0]
    top, bottom = max(max(values), 0.0), min(min(values), 0.0)
    pad = max((top - bottom) * 0.18, 0.2)
    top, bottom = top + pad, bottom - pad

    width, height = 340, 200
    left, right, head, foot = 46, 8, 16, 34
    plot_h = height - head - foot
    scale = lambda v: head + (top - v) / (top - bottom) * plot_h  # noqa: E731
    zero = scale(0.0)
    slot = (width - left - right) / len(items)
    bar_w = min(slot * 0.42, 46)

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        'preserveAspectRatio="xMidYMid meet">'
    ]
    ticks = _nice_ticks(bottom, top, 5)
    for tick in ticks:
        y = scale(tick)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{left - 7}" y="{y:.1f}" text-anchor="end" '
            f'dominant-baseline="middle">{tick:.2f}%</text>'
        )
    parts.append(
        f'<line class="axis" x1="{left}" y1="{zero:.1f}" x2="{width - right}" '
        f'y2="{zero:.1f}"/>'
    )

    for i, (label, value) in enumerate(items):
        cx = left + slot * (i + 0.5)
        parts.append(
            f'<text class="cat" x="{cx:.1f}" y="{height - foot + 15}" '
            f'text-anchor="middle">{_e(_wrap_label(label))}</text>'
        )
        if value is None:
            continue
        y = scale(value)
        fill = UP if value > 0 else DOWN if value < 0 else "var(--baseline)"
        parts.append(
            f'<rect class="bar" x="{cx - bar_w / 2:.1f}" y="{min(y, zero):.1f}" '
            f'width="{bar_w:.1f}" height="{max(abs(y - zero), 1.5):.1f}" rx="4" '
            f'fill="{fill}" data-tip="{_e(label)} · {_pct(value)}">'
            f"<title>{_e(label)}: {_pct(value)}</title></rect>"
        )
        ly = y - 6 if value >= 0 else y + 14
        parts.append(
            f'<text class="val" x="{cx:.1f}" y="{ly:.1f}" text-anchor="middle">'
            f"{_pct(value)}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _wrap_label(label: str) -> str:
    return label.replace(" Index", "").replace(" Share", "")


def _nice_ticks(low: float, high: float, count: int) -> list[float]:
    span = high - low
    if span <= 0:
        return [low]
    raw = span / max(count - 1, 1)
    magnitude = 10 ** _floor_log10(raw)
    for factor in (1, 2, 2.5, 5, 10):
        step = magnitude * factor
        if step >= raw:
            break
    for _ in range(3):
        ticks = _walk(low, high, step)
        if len(ticks) >= 3:
            return ticks
        step /= 2  # a "nice" step can still be too coarse for a narrow span
    return _walk(low, high, step)


def _walk(low: float, high: float, step: float) -> list[float]:
    start = step * (int(low / step) - (1 if low % step else 0))
    ticks, value = [], start
    while value <= high + step * 0.001:
        if value >= low - step * 0.001:
            ticks.append(round(value, 10))
        value += step
    return ticks


def _floor_log10(value: float) -> int:
    return 0 if not value else math.floor(math.log10(abs(value)))


def _line(points: list[tuple[str, float]], *, unit: str = "%", dp: int = 3) -> str:
    """Small line chart on a zoomed axis, exactly as the source draws it.

    The axis min/max are printed so the zoom is visible rather than implied — a
    0.02pp move should not read as a cliff without the reader knowing the scale.
    """
    if not points:
        return '<p class="note">No data.</p>'
    values = [v for _, v in points]
    low, high = min(values), max(values)
    if high == low:
        low, high = low - 0.01, high + 0.01
    pad = (high - low) * 0.35
    low, high = low - pad, high + pad

    width, height = 320, 170
    left, right, head, foot = 58, 12, 14, 26
    plot_h = height - head - foot
    plot_w = width - left - right
    scale = lambda v: head + (high - v) / (high - low) * plot_h  # noqa: E731
    step = plot_w / max(len(points) - 1, 1)
    xs = [left + step * i for i in range(len(points))]

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        'preserveAspectRatio="xMidYMid meet">'
    ]
    for tick in _nice_ticks(low, high, 5):
        y = scale(tick)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{left - 7}" y="{y:.1f}" text-anchor="end" '
            f'dominant-baseline="middle">{tick:.{dp}f}{unit}</text>'
        )
    path = " ".join(
        f"{'M' if i == 0 else 'L'}{x:.1f},{scale(v):.1f}"
        for i, (x, (_, v)) in enumerate(zip(xs, points))
    )
    parts.append(f'<path class="series" d="{path}"/>')
    for x, (label, value) in zip(xs, points):
        y = scale(value)
        parts.append(
            f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4.5" '
            f'data-tip="{_e(label)} · {value:.{dp}f}{unit}">'
            f"<title>{_e(label)}: {value:.{dp}f}{unit}</title></circle>"
        )
        parts.append(
            f'<text class="cat" x="{x:.1f}" y="{height - foot + 15}" '
            f'text-anchor="middle">{_e(label)}</text>'
        )

    # Label every point, anchored so the end points stay inside the frame and
    # nudged to the side of the line the series is not travelling on.
    for i, (x, (_, value)) in enumerate(zip(xs, points)):
        anchor = "start" if i == 0 else "end" if i == len(points) - 1 else "middle"
        offset = 4 if i == 0 else -4 if i == len(points) - 1 else 0
        rising = i > 0 and value >= points[i - 1][1]
        dy = -11 if rising or i == 0 else 19
        parts.append(
            f'<text class="val" x="{x + offset:.1f}" y="{scale(value) + dy:.1f}" '
            f'text-anchor="{anchor}">{value:.{dp}f}{unit}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _log_columns(
    categories: list[str], series: list[tuple[str, list[float | None]]]
) -> str:
    """Grouped columns on a log axis — the source's ownership chart.

    A log axis is the only way a 95% holding and a 0.28% holding share one frame;
    the trade-off is that bar *length* stops being proportional, so every column
    is labelled with its value.
    """
    flat = [v for _, vals in series for v in vals if v]
    if not flat:
        return '<p class="note">No register published.</p>'
    decades = _log_decades(min(flat), max(flat))
    low, high = decades[0], decades[-1]

    width, height = 560, 260
    left, right, head, foot = 54, 12, 26, 40
    plot_h = height - head - foot
    span = math.log10(high) - math.log10(low)
    log = lambda v: (math.log10(max(v, low)) - math.log10(low)) / span  # noqa: E731
    scale = lambda v: head + (1 - log(v)) * plot_h  # noqa: E731
    base = head + plot_h

    slot = (width - left - right) / len(categories)
    bar_w = min(slot / (len(series) + 1.2), 40)

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        'preserveAspectRatio="xMidYMid meet">'
    ]
    for decade in decades:
        y = scale(decade)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{left - 7}" y="{y:.1f}" text-anchor="end" '
            f'dominant-baseline="middle">{decade:g}%</text>'
        )
    parts.append(
        f'<line class="axis" x1="{left}" y1="{base:.1f}" x2="{width - right}" y2="{base:.1f}"/>'
    )

    for i, category in enumerate(categories):
        centre = left + slot * (i + 0.5)
        group_w = bar_w * len(series)
        parts.append(
            f'<text class="cat" x="{centre:.1f}" y="{base + 16}" text-anchor="middle">'
            f"{_e(category)}</text>"
        )
        for s, (name, values) in enumerate(series):
            value = values[i]
            if not value:
                continue
            x = centre - group_w / 2 + s * bar_w
            y = scale(value)
            parts.append(
                f'<rect class="bar" x="{x + 1:.1f}" y="{y:.1f}" width="{bar_w - 2:.1f}" '
                f'height="{max(base - y, 1.5):.1f}" rx="3" fill="var(--series-{s + 1})" '
                f'data-tip="{_e(category)} · {_e(name)} · {value:.2f}%">'
                f"<title>{_e(category)} — {_e(name)}: {value:.3f}%</title></rect>"
            )
            # Stagger the pair vertically: two labels over adjacent bars of the
            # same group would otherwise overlap at these bar widths.
            lift = 6 if s == 0 else 17
            parts.append(
                f'<text class="val small" x="{x + bar_w / 2:.1f}" y="{y - lift:.1f}" '
                f'text-anchor="middle">{value:.2f}%</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _log_decades(low: float, high: float) -> list[float]:
    start, stop = _floor_log10(low), _floor_log10(high) + 1
    return [10.0**e for e in range(start, stop + 1)]


def _legend(names: list[str]) -> str:
    keys = "".join(
        f'<span class="key"><i style="background:var(--series-{i + 1})"></i>{_e(n)}</span>'
        for i, n in enumerate(names)
    )
    return f'<div class="legend">{keys}</div>'


# ------------------------------------------------------------- panel bodies

def _axis_label(value: str) -> str:
    """Dates shorten to 05-Jan; intraday stamps are already HH:MM."""
    try:
        return _short_date(value)
    except (ValueError, TypeError):
        return str(value)


def _compact(value: float) -> str:
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= cut:
            return f"{value / cut:,.1f}{suffix}"
    return f"{value:,.0f}"


def _price_volume(
    points: list[dict],
    *,
    x_key: str,
    price_key: str,
    volume_key: str,
    price_dp: int = 3,
) -> str:
    """Price line above, volume columns below, on a shared x-axis.

    Two stacked plots rather than one chart with two y-scales: a dual axis invites
    the reader to infer a price/volume relationship from whatever the scales
    happen to be. Sharing x and separating y keeps the comparison to the only
    honest one — when volume arrived relative to the move.
    """
    series = [p for p in points if p.get(price_key) is not None]
    if len(series) < 2:
        return (
            '<p class="note">Not enough points yet — the intraday series builds up '
            "from the tick archive as <code>watch</code> runs.</p>"
        )

    prices = [p[price_key] for p in series]
    volumes = [p.get(volume_key) or 0 for p in series]
    low, high = min(prices), max(prices)
    # A flat or near-flat stretch on an auto-zoomed axis reads as a cliff, so the
    # band has a floor of +/-0.5% of the level.
    mid = (high + low) / 2 or 1.0
    floor = abs(mid) * 0.005
    if (high - low) < floor * 2:
        low, high = mid - floor, mid + floor
    pad = (high - low) * 0.12
    low, high = low - pad, high + pad
    vmax = max(volumes) or 1

    width, height = 940, 300
    left, right = 62, 12
    price_top, price_h = 14, 168
    vol_top, vol_h = 214, 62
    plot_w = width - left - right
    step = plot_w / max(len(series) - 1, 1)
    py = lambda v: price_top + (high - v) / (high - low) * price_h  # noqa: E731
    xs = [left + step * i for i in range(len(series))]

    parts = [
        f'<svg class="chart pv" viewBox="0 0 {width} {height}" role="img" '
        'preserveAspectRatio="xMidYMid meet">'
    ]
    for tick in _nice_ticks(low, high, 5):
        y = py(tick)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>'
            f'<text class="tick" x="{left - 7}" y="{y:.1f}" text-anchor="end" '
            f'dominant-baseline="middle">{tick:,.{price_dp}f}</text>'
        )

    path = " ".join(
        f"{'M' if i == 0 else 'L'}{x:.1f},{py(p[price_key]):.1f}"
        for i, (x, p) in enumerate(zip(xs, series))
    )
    base = price_top + price_h
    parts.append(
        f'<path class="area" d="{path} L{xs[-1]:.1f},{base:.1f} L{xs[0]:.1f},{base:.1f} Z"/>'
    )
    parts.append(f'<path class="series" d="{path}"/>')

    vol_base = vol_top + vol_h
    bar_w = max(min(step * 0.65, 9), 1.0)
    parts.append(
        f'<line class="axis" x1="{left}" y1="{vol_base:.1f}" '
        f'x2="{width - right}" y2="{vol_base:.1f}"/>'
    )
    parts.append(
        f'<text class="tick" x="{left - 7}" y="{vol_top + 6:.1f}" text-anchor="end">'
        f"{_compact(vmax)}</text>"
    )
    for x, point in zip(xs, series):
        volume = point.get(volume_key) or 0
        if volume <= 0:
            continue
        bar_h = volume / vmax * vol_h
        parts.append(
            f'<rect class="vol" x="{x - bar_w / 2:.1f}" y="{vol_base - bar_h:.1f}" '
            f'width="{bar_w:.1f}" height="{bar_h:.1f}" rx="1"/>'
        )

    # Thin the x labels, and enforce a pixel gap so the always-drawn final label
    # cannot land on top of the last regular tick.
    every = max(1, len(series) // 9)
    min_gap, drawn_at = 46.0, -1e9
    for i, (x, point) in enumerate(zip(xs, series)):
        final = i == len(series) - 1
        if (i % every and not final) or (x - drawn_at) < min_gap:
            if not final:
                continue
            # The final label wins; drop the one crowding it.
            if parts and parts[-1].startswith('<text class="cat"'):
                parts.pop()
        parts.append(
            f'<text class="cat" x="{x:.1f}" y="{height - 6}" text-anchor="middle">'
            f"{_e(_axis_label(point[x_key]))}</text>"
        )
        drawn_at = x

    for x, point in zip(xs, series):
        tip = (
            f"{_axis_label(point[x_key])} · {point[price_key]:,.{price_dp}f}"
            f" · vol {_compact(point.get(volume_key) or 0)}"
        )
        parts.append(
            f'<rect class="hit" x="{x - step / 2:.1f}" y="{price_top}" '
            f'width="{max(step, 2):.1f}" height="{vol_base - price_top:.1f}" '
            f'data-tip="{_e(tip)}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


MIN_INTRADAY_TICKS = 6

# Range buttons over the daily history, mirroring the source graph's affordance.
# Sessions, not calendar days: the tree only holds trading days.
HISTORY_RANGES = (("1M", 21), ("3M", 62), ("6M", 124), ("1Y", 248), ("Max", None))


def _history_ranges(history: list[dict]) -> str:
    """One pre-rendered chart per range, switched with CSS only.

    The page is static, so every range is drawn at build time and the radios just
    reveal one. No JavaScript, and no refetch — they are slices of one array.
    """
    available = [
        (label, span)
        for label, span in HISTORY_RANGES
        if span is None or span < len(history)
    ] or [("Max", None)]
    if available[-1][0] != "Max":
        available.append(("Max", None))
    default = available[-2][0] if len(available) > 1 else available[0][0]

    radios, labels, charts, rules = [], [], [], []
    for label, span in available:
        slug = label.lower()
        window = history if span is None else history[-span:]
        first, last = window[0], window[-1]
        move = (last["close"] / first["close"] - 1) * 100 if first["close"] else None
        radios.append(
            f'<input class="rgradio" type="radio" name="qse-range" id="r-{slug}"'
            f'{" checked" if label == default else ""}>'
        )
        labels.append(f'<label for="r-{slug}">{_e(label)}</label>')
        charts.append(
            f'<div id="rg-{slug}"><p class="glabel">Daily close · '
            f'{_e(_axis_label(first["date"]))} to {_e(_axis_label(last["date"]))} '
            f'<span class="of">{len(window)} sessions</span> '
            f'<span class="{_sign(move)}">{_pct(move)}</span></p>'
            + _price_volume(window, x_key="date", price_key="close", volume_key="volume")
            + "</div>"
        )
        rules.append(
            f"#r-{slug}:checked~.rangeset>#rg-{slug}{{display:block}}"
            f'#r-{slug}:checked~.ranges label[for="r-{slug}"]'
            "{background:var(--series-1);color:var(--surface);border-color:var(--series-1)}"
        )
    return (
        f"<style>{''.join(rules)}</style>"
        f'<div class="graph rangewrap">{"".join(radios)}'
        f'<div class="ranges">{"".join(labels)}</div>'
        f'<div class="rangeset">{"".join(charts)}</div></div>'
    )


def _graph_panel(bundle: dict) -> str:
    """The share graph: intraday when the archive has it, daily history always."""
    meta = bundle["meta"]
    intraday = bundle.get("intraday") or {}
    history = bundle.get("history") or []
    blocks = []

    ticks = intraday.get("points") or []
    if len(ticks) >= MIN_INTRADAY_TICKS:
        last = ticks[-1]
        blocks.append(
            '<div class="graph"><p class="glabel">Intraday · '
            f'{_e(_axis_label(intraday["session"]))} '
            f'<span class="of">{len(ticks)} ticks · last {_n(last["price"])} · '
            f'volume {_compact(last["cumulativeVolume"])}</span></p>'
            + _price_volume(ticks, x_key="time", price_key="price", volume_key="volume")
            + "</div>"
        )
    else:
        sessions = len(intraday.get("sessionsAvailable") or [])
        blocks.append(
            '<div class="graph"><p class="glabel">Intraday</p>'
            f'<p class="note">{len(ticks)} of {MIN_INTRADAY_TICKS} ticks needed — builds up '
            f"from the tick archive as <code>watch</code> runs, one point every 5 minutes "
            f"({sessions} session(s) captured). qe.com.qa publishes no intraday history, so "
            "it cannot be backfilled.</p></div>"
        )

    if len(history) >= 2:
        blocks.append(_history_ranges(history))

    return _panel(
        f'{meta["name"]} Share Graph',
        "".join(blocks),
        span=12,
        note=f'price and volume · {meta["currency"]}',
    )


def _quote_panel(bundle: dict, tab: dict) -> str:
    m, s = bundle["meta"], tab["share"]
    tone = _sign(s["changePct"])
    logo = (
        f'<img class="logo" src="{m["logo"]}" alt="{_e(m["name"])}">' if m.get("logo") else ""
    )
    head = (
        f'<div class="ident">{logo}'
        f'<div><span class="idrow"><b>Market</b> {_e(m["market"])}</span>'
        f'<span class="idrow"><b>Symbol</b> {_e(m["symbol"])}</span>'
        f'<span class="idrow cur">{_e(m["currency"])}</span></div></div>'
    )
    dividend = (
        "–"
        if not s["cashDividend"]
        else f'{_n(s["cashDividend"], 3)} ({_plain_pct(s["dividendYieldPct"])})'
    )
    return _panel(
        f'{m["name"]} Share Update',
        head
        + _rows(
            [
                ("Previous Close", _n(s["previousClose"]), ""),
                ("Open", _n(s["open"]), ""),
                ("Low", _n(s["low"]), ""),
                ("High", _n(s["high"]), ""),
                ("Closing", _n(s["close"]), "strong"),
                ("Change +/-", _n(s["changeValue"]), tone),
                ("Change %", _pct(s["changePct"], 3), tone),
                ("1-Year Change", _pct(s["oneYearChangePct"]), _sign(s["oneYearChangePct"])),
                ("Price to book", _n(s["priceToBook"]), ""),
                ("Dividend (Yield)", dividend, ""),
                ("52 Weeks High", _n(s["high52"]), ""),
                ("52 Weeks Low", _n(s["low52"]), ""),
                ("Volume", _int(s["volume"]), ""),
                ("Value", _n(s["value"]), ""),
                ("Number of shares", _int(s["sharesOutstanding"]), ""),
                ("Market Cap", _int(s["marketCap"]), ""),
                (
                    "Cap rank to QE Market",
                    f'{s["capRankMarket"]} <span class="of">of {s["capRankMarketOf"]}</span>',
                    "",
                ),
                (
                    "Cap rank to Sector",
                    f'{s["capRankSector"]} <span class="of">of {s["capRankSectorOf"]}</span>',
                    "",
                ),
            ]
        ),
        span=3,
        note=tab["period"]["label"],
    )


def _index_panel(tab: dict) -> str:
    x = tab["index"]
    return _panel(
        "QE Index Update",
        _rows(
            [
                ("QE Index", _n(x["indexValue"]), "strong"),
                ("Volume", _int(x["volume"]), ""),
                ("Value", _n(x["tradedValue"]), ""),
                ("Change +/-", _n(x["changeValue"], 2), _sign(x["changeValue"])),
                ("Change %", _pct(x["changePct"]), _sign(x["changePct"])),
                ("Lowest Value 52 Weeks", _n(x["low52"]), ""),
                ("Highest Value 52 Weeks", _n(x["high52"]), ""),
                ("% Change from Lowest Value", _pct(x["pctFromLow52"]), _sign(x["pctFromLow52"])),
                (
                    "% Change from Highest Value",
                    _pct(x["pctFromHigh52"]),
                    _sign(x["pctFromHigh52"]),
                ),
                ("Traded stocks", _int(x["tradedStocks"]), ""),
                ("Gainers / Losers", f'{x["gainers"]} / {x["losers"]}', ""),
                ("QSE Market Cap", _int(x["marketCap"]), ""),
            ]
        ),
        span=3,
        note=f'52-week range from {x["window"]["sessions"]} daily closes',
    )


def _comparison_panel(bundle: dict, tab: dict) -> str:
    items = [(c["label"], c["changePct"]) for c in tab["comparison"]]
    return _panel(
        f'{bundle["meta"]["name"]} Compared to Market & Sector',
        _columns(items),
        span=3,
        note=f'{tab["period"]["tab"].lower()} % change',
    )


def _indices_panel(tab: dict) -> str:
    rows = [
        [
            _e(i["name"]),
            f'<span class="{_sign(i["changePct"])}">{_pct(i["changePct"])}</span>',
        ]
        for i in tab["sectorIndices"]
    ]
    return _panel("Indices Performance", _table(["Index", "%"], rows), span=3)


def _movers_panel(tab: dict, key: str, title: str, column: str, value_key: str, fmt) -> str:
    rows = [[_e(r["name"]), fmt(r[value_key])] for r in tab[key]]
    return _panel(title, _table(["Name", column], rows), span=3)


def _activity_panel(tab: dict) -> str:
    rows = []
    for group in tab["shareholderActivity"]:
        cells = group["rows"]
        if not cells:
            continue
        # Span each investor-type cell over however many rows that type actually
        # has. A nationality can be missing a Buy or a Sell leg (GCC and Arab
        # institutions often are), and a hard-coded rowspan of 2 then bleeds into
        # the next nationality and shifts every cell after it.
        by_type: dict[str, list[dict]] = {}
        for r in cells:
            by_type.setdefault(r["investorType"], []).append(r)

        first = True
        for investor_type, legs in by_type.items():
            for j, r in enumerate(legs):
                row = []
                if first:
                    row.append(
                        f'<td class="grouped" rowspan="{len(cells)}">'
                        f'{_e(group["nationality"])}</td>'
                    )
                if j == 0:
                    row.append(
                        f'<td class="grouped" rowspan="{len(legs)}">'
                        f"{_e(investor_type)}</td>"
                    )
                row.append(f'<td>{_e(r["tradeType"])}</td>')
                row.append(f'<td class="num">{_plain_pct(r["tradedValuePct"], 3)}</td>')
                if first:
                    row.append(
                        f'<td class="num grouped" rowspan="{len(cells)}">'
                        f'{_plain_pct(group["totalBuyPct"])}</td>'
                    )
                    row.append(
                        f'<td class="num grouped" rowspan="{len(cells)}">'
                        f'{_plain_pct(group["totalSellPct"])}</td>'
                    )
                rows.append(row)
                first = False
    return _panel(
        "Qatar Market Shareholders Activity",
        _table(
            [
                "Nationality",
                "Type",
                "Transaction",
                "Traded Value (%)",
                "Total Buy (%)",
                "Total Sale (%)",
            ],
            rows,
            right_from=3,
        ),
        span=6,
        note="percentages are of total market traded value",
    )


def _institutions_panel(bundle: dict, tab: dict) -> str:
    own = tab["ownership"]
    current, previous = own.get("current"), own.get("previous")
    if not current:
        return _panel(
            f'Institutions Shares in {bundle["meta"]["name"]}',
            '<p class="note">No register published for this period.</p>',
            span=3,
        )
    points = []
    if previous and own.get("previousDate"):
        points.append((_short_date(own["previousDate"]), previous["institutionsPct"]))
    points.append((_short_date(own["currentDate"]), current["institutionsPct"]))
    delta = (
        round(current["institutionsPct"] - previous["institutionsPct"], 3)
        if previous
        else None
    )
    caption = (
        f'<p class="delta {_sign(delta)}">'
        f'{"–" if delta is None else f"{delta:+.3f} pp"} over the period</p>'
    )
    return _panel(
        f'Institutions Shares in {bundle["meta"]["name"]}',
        _line(points) + caption,
        span=3,
        note="axis is zoomed to the data — read the tick values",
    )


def _ownership_panel(tab: dict) -> str:
    own = tab["ownership"]
    current, previous = own.get("current"), own.get("previous")
    if not current:
        return _panel(
            "Ownership Percentage by Nationality",
            '<p class="note">No register published for this period.</p>',
            span=6,
        )
    order = ["Qatari", "GCC", "Arab", "Foreigners"]
    categories = [c for c in order if c in current["byNationality"]]
    now = [current["byNationality"].get(c) for c in categories]
    before = [(previous or {}).get("byNationality", {}).get(c) for c in categories]

    now_label = _short_date(own["currentDate"])
    before_label = _short_date(own["previousDate"]) if own.get("previousDate") else "prev"
    series = [(now_label, now)]
    if previous:
        series.append((before_label, before))

    return _panel(
        "Ownership Percentage by Nationality",
        _legend([name for name, _ in series]) + _log_columns(categories, series),
        span=6,
        note="logarithmic scale — bar heights are not proportional; read the labels",
    )


def _insider_panel(tab: dict) -> str:
    rows = []
    for r in tab["insiderTrades"]:
        rows.append(
            [
                _e(r["company"]),
                f'<span dir="rtl" class="ar">{_e(r["insider"])}</span>',
                _int(r["buy"]) if r["buy"] else "0",
                _int(r["sell"]) if r["sell"] else "0",
            ]
        )
    if not rows:
        rows = [["No insider trades reported", "", "", ""]]
    note = (
        "aggregated across the period's sessions"
        if tab["period"]["kind"] != "daily"
        else "this session, market-wide"
    )
    return _panel(
        "Insider Trades",
        _table(["Company", "Insider Name", "Buy", "Sell"], rows, right_from=2),
        span=6,
        note=note,
    )


# -------------------------------------------------------------------- shell

def _tab_body(bundle: dict, kind: str) -> str:
    tab = bundle["periods"][kind]
    panels = [
        _quote_panel(bundle, tab),
        _index_panel(tab),
        _comparison_panel(bundle, tab),
        _indices_panel(tab),
        _movers_panel(tab, "topGainers", "Top Gainers", "Change %", "changePct",
                      lambda v: f'<span class="up">{_pct(v, 3)}</span>'),
        _movers_panel(tab, "topLosers", "Top Losers", "Change %", "changePct",
                      lambda v: f'<span class="down">{_pct(v, 3)}</span>'),
        _movers_panel(tab, "topByValue", "Top By Value", "Traded Value (QR)",
                      "tradedValue", lambda v: _n(v, 0)),
        _movers_panel(tab, "topByVolume", "Top By Volume", "Volume", "tradedVolume", _int),
        _activity_panel(tab),
        _institutions_panel(bundle, tab),
        _ownership_panel(tab),
        _insider_panel(tab),
    ]
    return f'<div class="grid">{"".join(panels)}</div>'


CSS = """
:root{color-scheme:light;
 --plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --grid:#e1e0d9;--baseline:#c3c2b7;--ring:rgba(11,11,11,.10);--wash:rgba(11,11,11,.03);
 --series-1:$s1l;--series-2:$s2l;--up:$up;--down:$down;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--baseline:#383835;--ring:rgba(255,255,255,.10);--wash:rgba(255,255,255,.04);
 --series-1:$s1d;--series-2:$s2d;}}
:root[data-theme="dark"]{color-scheme:dark;
 --plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--baseline:#383835;--ring:rgba(255,255,255,.10);--wash:rgba(255,255,255,.04);
 --series-1:$s1d;--series-2:$s2d;}
*{box-sizing:border-box}
body{margin:0;padding:18px;background:var(--plane);color:var(--ink);
 font:13.5px/1.42 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1480px;margin:0 auto}
header.top{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;margin-bottom:12px}
header.top h1{font-size:19px;margin:0;font-weight:650;letter-spacing:-.01em}
.state{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink2);
 border:1px solid var(--ring);border-radius:999px;padding:3px 10px}
.state i{width:7px;height:7px;border-radius:50%;background:var(--muted)}
.state.open i{background:var(--up)}.state.closed i{background:var(--muted)}
.state.preopen i{background:#fab219}
.livequote{font-size:12px;color:var(--ink2);font-variant-numeric:tabular-nums}
.built{margin-left:auto;font-size:11.5px;color:var(--muted);text-align:right}
input.tabradio{position:absolute;opacity:0;width:1px;height:1px;margin:0}
nav.tabs{display:flex;gap:4px;margin:0 0 12px;border-bottom:1px solid var(--ring)}
nav.tabs label,nav.tabs span{font-size:13px;color:var(--ink2);padding:8px 15px;
 cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;
 border-radius:6px 6px 0 0;user-select:none}
nav.tabs label:hover{background:var(--wash);color:var(--ink)}
nav.tabs span.disabled{color:var(--muted);cursor:not-allowed}
input.tabradio:focus-visible+ input.tabradio,
input.tabradio:focus-visible~nav.tabs label{outline:none}
.panelset>div{display:none}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:11px;align-items:start}
.panel{grid-column:span var(--span);background:var(--surface);border:1px solid var(--ring);
 border-radius:9px;padding:11px 13px;min-width:0;overflow-x:auto}
.panel h2{font-size:11.5px;text-transform:uppercase;letter-spacing:.055em;color:var(--ink2);
 margin:0 0 2px;font-weight:650}
.panel .note{font-size:11px;color:var(--muted);margin:0 0 8px}
.ident{display:flex;align-items:center;gap:10px;padding-bottom:8px;margin-bottom:6px;
 border-bottom:1px solid var(--grid)}
.ident .logo{height:30px;width:auto;max-width:110px;object-fit:contain}
.idrow{display:block;font-size:11.5px;color:var(--ink2)}
.idrow b{font-weight:600;color:var(--muted);font-size:10.5px;text-transform:uppercase;
 letter-spacing:.04em;margin-right:5px}
.idrow.cur{color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
table.kv th{text-align:left;font-weight:400;color:var(--ink2);padding:2.5px 8px 2.5px 0;
 border:0;text-transform:none;letter-spacing:0;font-size:12.5px}
table.kv td{text-align:right;font-variant-numeric:tabular-nums;padding:2.5px 0;border:0}
thead th{text-align:left;font-weight:600;color:var(--muted);font-size:10.5px;
 text-transform:uppercase;letter-spacing:.04em;padding:0 6px 5px 0;
 border-bottom:1px solid var(--grid)}
tbody td{padding:3.5px 6px 3.5px 0;border-bottom:1px solid var(--grid)}
tbody tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.grouped{vertical-align:middle;border-right:1px solid var(--grid);font-weight:600}
.of{color:var(--muted);font-weight:400;font-size:11px}
.strong{font-weight:700}.up{color:var(--up)}.down{color:var(--down)}
.ar{color:var(--ink2);font-size:12px}
.delta{margin:6px 0 0;font-size:12px;font-variant-numeric:tabular-nums;text-align:center}
svg.chart{width:100%;height:auto;display:block;overflow:visible}
svg .axis{stroke:var(--baseline);stroke-width:1}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .cat{fill:var(--ink2);font-size:10.5px}
svg .tick{fill:var(--muted);font-size:10px;font-variant-numeric:tabular-nums}
svg .val{fill:var(--ink2);font-size:10.5px;font-variant-numeric:tabular-nums;font-weight:600}
svg .val.small{font-size:9.5px}
svg .bar{stroke:var(--surface);stroke-width:2;paint-order:stroke}
svg .bar:hover{filter:brightness(1.08)}
svg .series{fill:none;stroke:var(--series-1);stroke-width:2;stroke-linejoin:round}
svg .area{fill:var(--series-1);opacity:.10;stroke:none}
svg .vol{fill:var(--series-1);opacity:.45}
svg .hit{fill:transparent}
svg .hit:hover{fill:var(--ink);opacity:.045}
.graph{margin-bottom:8px}
.graph:last-child{margin-bottom:0}
.glabel{margin:2px 0 4px;font-size:11.5px;color:var(--ink2);font-weight:600}
.glabel .of{font-weight:400;color:var(--muted)}
input.rgradio{position:absolute;opacity:0;width:1px;height:1px;margin:0}
.ranges{display:flex;gap:5px;margin:2px 0 6px}
.ranges label{font-size:11px;color:var(--ink2);padding:2px 9px;cursor:pointer;
 border:1px solid var(--ring);border-radius:999px;user-select:none;line-height:1.5}
.ranges label:hover{background:var(--wash)}
.rangeset>div{display:none}
svg .dot{fill:var(--series-1);stroke:var(--surface);stroke-width:2}
.legend{display:flex;gap:14px;margin:0 0 4px;font-size:11px;color:var(--ink2)}
.legend .key{display:inline-flex;align-items:center;gap:5px}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
footer{margin-top:13px;color:var(--muted);font-size:11px}
#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;z-index:9;
 background:var(--ink);color:var(--surface);font-size:11.5px;padding:4px 8px;border-radius:5px;
 font-variant-numeric:tabular-nums;white-space:nowrap}
/* Narrow layouts collapse to two-up, but a panel that asked for the full row
   keeps it — the share graph is unreadable at half width, and the Streamlit
   iframe is usually under this breakpoint. */
@media (max-width:1240px){.panel{grid-column:span var(--span-md,6)}}
@media (max-width:720px){.panel{grid-column:span 12}}
"""

for _token, _value in (
    ("$s1l", SERIES["light"][0]),
    ("$s2l", SERIES["light"][1]),
    ("$s1d", SERIES["dark"][0]),
    ("$s2d", SERIES["dark"][1]),
    ("$up", UP),
    ("$down", DOWN),
):
    CSS = CSS.replace(_token, _value)


JS = """
(function(){
var tip=document.getElementById('tip');
document.addEventListener('mouseover',function(e){var t=e.target.closest('[data-tip]');
 if(!t)return;tip.textContent=t.getAttribute('data-tip');tip.style.opacity=1;});
document.addEventListener('mousemove',function(e){if(tip.style.opacity!=='1')return;
 tip.style.left=Math.min(e.clientX+12,innerWidth-tip.offsetWidth-8)+'px';
 tip.style.top=(e.clientY-30)+'px';});
document.addEventListener('mouseout',function(e){
 if(e.target.closest('[data-tip]'))tip.style.opacity=0;});

// Switching itself is pure CSS. This only remembers the choice so the tab
// survives the self-refresh.
var KEY='qse-tab';
var radios=[].slice.call(document.querySelectorAll('input.tabradio'));
var saved=null;try{saved=localStorage.getItem(KEY);}catch(e){}
radios.forEach(function(r){
 if(saved&&r.dataset.kind===saved)r.checked=true;
 r.addEventListener('change',function(){
  if(r.checked){try{localStorage.setItem(KEY,r.dataset.kind);}catch(e){}}
 });
});

// Countdown to the next rebuild, so a stale tab is obvious at a glance.
var secs=parseInt(document.body.dataset.refresh||'0',10);
var out=document.getElementById('countdown');
if(secs>0&&out){
 var left=secs;
 setInterval(function(){
  left--;
  if(left<0){out.textContent='reloading…';return;}
  var m=Math.floor(left/60),s=left%60;
  out.textContent='refresh in '+m+':'+(s<10?'0':'')+s;
 },1000);
}
})();
"""


def _state_class(state: str | None) -> str:
    if not state:
        return ""
    key = state.lower().replace("-", "").replace(" ", "")
    return {"open": "open", "preopen": "preopen", "close": "closed", "closed": "closed"}.get(
        key, ""
    )


def render(bundle: dict) -> str:
    meta, live = bundle["meta"], bundle.get("live") or {}
    kinds = [k for k in TAB_ORDER if k in bundle["periods"]]
    default = meta.get("defaultKind") or kinds[0]
    refresh = int(meta.get("refreshSeconds") or 0)

    # Tabs are pure CSS (hidden radios + sibling selectors) so switching works
    # with JavaScript disabled — this file gets emailed and opened from disk.
    radios, labels = [], []
    for kind in TAB_ORDER:
        available = kind in bundle["periods"]
        label = bundle["periods"][kind]["period"]["tab"] if available else kind.capitalize()
        reason = meta.get("unavailable", {}).get(kind, "")
        title = (
            bundle["periods"][kind]["period"]["label"]
            if available
            else f"not available — {reason}"
        )
        if available:
            radios.append(
                f'<input class="tabradio" type="radio" name="qse-period" id="t-{kind}" '
                f'data-kind="{kind}"{" checked" if kind == default else ""}>'
            )
            labels.append(
                f'<label for="t-{kind}" title="{_e(title)}">{_e(label)}</label>'
            )
        else:
            labels.append(
                f'<span class="disabled" title="{_e(title)}">{_e(label)}</span>'
            )

    bodies = "".join(
        f'<div id="tab-{kind}">{_tab_body(bundle, kind)}</div>' for kind in kinds
    )
    tab_rules = "".join(
        f"#t-{kind}:checked~.panelset>#tab-{kind}{{display:block}}"
        f'#t-{kind}:checked~nav.tabs label[for="t-{kind}"]'
        "{color:var(--ink);font-weight:650;border-bottom-color:var(--series-1)}"
        for kind in kinds
    )

    state = live.get("state")
    state_bits = ""
    if state:
        quote = live.get("quote") or {}
        price = quote.get("lastPrice")
        state_bits = (
            f'<span class="state {_state_class(state)}"><i></i>{_e(state)}</span>'
            f'<span class="livequote">QE {_n(live.get("indexValue"), 2)} '
            f'{_pct(live.get("changePct"))}'
            + (
                f' · {_e(meta["symbol"])} {_n(price, 3)} {_pct(quote.get("changePct"))}'
                if price
                else ""
            )
            + (f' · feed {_e(live["lastUpdate"])}' if live.get("lastUpdate") else "")
            + "</span>"
        )

    built = meta.get("builtAt", "")
    built_short = built[11:16] if len(built) > 16 else built
    meta_refresh = (
        f'<meta http-equiv="refresh" content="{refresh}">' if refresh > 0 else ""
    )
    caveats = (
        "Market cap and cap ranks are derived (shares outstanding x close). "
        "Price to book applies live book value per share to the period close. "
        f'QE Index 52-week range from '
        f'{bundle["periods"][default]["index"]["window"]["sessions"]} daily closes.'
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{meta_refresh}
<title>{_e(meta["name"])} Share Update</title>
<style>{CSS}</style><style>{tab_rules}</style></head>
<body data-default-kind="{default}" data-refresh="{refresh}">
<div id="tip" role="status"></div>
<div class="wrap">
<header class="top">
 <h1>{_e(meta["name"])} Share Update</h1>
 {state_bits}
 <span class="built">built {_e(built_short)} AST ·
  <span id="countdown">{"auto-refresh off" if refresh <= 0 else ""}</span></span>
</header>
<div class="grid">{_graph_panel(bundle)}</div>
<div class="tabwrap">{"".join(radios)}
<nav class="tabs">{"".join(labels)}</nav>
<div class="panelset">{bodies}</div>
</div>
<footer>
 <p>Source: qe.com.qa public feeds · {_e(meta["symbol"])} · {_e(meta["sector"])}.
 {_e(caveats)}</p>
</footer>
</div>
<script>{JS}</script>
<script type="application/json" id="bundle">{json.dumps(bundle, ensure_ascii=False)}</script>
</body></html>
"""
