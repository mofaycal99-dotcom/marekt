"""Derive the dashboard bundle from the raw QSE feeds.

One symbol, three periods (daily / weekly / monthly), one JSON object carrying
every number the source dashboard shows. Nothing here talks to the network
except through Client.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import archive as _archive
from .client import (
    INVESTOR_TYPE,
    NATIONALITY,
    SECTOR_INDEX_CODES,
    Client,
    NotAvailable,
)
from .period import KINDS, Period, previous_daily, resolve

QATAR = timezone(timedelta(hours=3))
WEEKEND = {4, 5}


def _f(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _i(value) -> int | None:
    v = _f(value)
    return None if v is None else int(v)


def _one_year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def trading_days_back(client: Client, end: date, count: int) -> list[str]:
    """The `count` most recent trading dates up to and including `end`."""
    found: list[str] = []
    cursor, misses = end, 0
    while len(found) < count and misses < 30:
        if cursor.weekday() not in WEEKEND:
            iso = cursor.isoformat()
            if client.try_report("MarketSummary", iso) is not None:
                found.append(iso)
                misses = 0
            else:
                misses += 1
        cursor -= timedelta(days=1)
    found.reverse()
    return found


def previous_trading_day(client: Client, day: date) -> str | None:
    prev = previous_daily(client, day)
    return prev.isoformat() if prev else None


def index_series(client: Client, end: date, weeks: int = 52) -> list[dict]:
    """Daily QE Index closes over the trailing `weeks`, oldest first."""
    series = []
    cursor = end - timedelta(weeks=weeks)
    while cursor <= end:
        if cursor.weekday() not in WEEKEND:
            iso = cursor.isoformat()
            value = client.index_value(iso)
            if value is not None:
                series.append({"date": iso, "index": value})
        cursor += timedelta(days=1)
    return series


def share_history(
    client: Client, symbol: str, end: date, days: int = 180
) -> list[dict]:
    """Daily close and volume for one symbol, oldest first.

    Straight out of StocksSummary, one file per session, so it reaches back as
    far as the report tree does (verified to 2020-01-02).
    """
    series, cursor = [], end - timedelta(days=days)
    while cursor <= end:
        if cursor.weekday() not in WEEKEND:
            rows = client.try_report("StocksSummary", cursor.isoformat())
            if rows:
                row = next((r for r in rows if r["SYMBOL_CODE"] == symbol), None)
                if row:
                    series.append(
                        {
                            "date": cursor.isoformat(),
                            "close": _f(row["CLOSE_PRICE"]),
                            "high": _f(row["HIGH_PRICE"]),
                            "low": _f(row["LOW_PRICE"]),
                            "volume": _i(row["TRADES_VOLUME"]),
                            "value": _f(row["TRADES_VALUE"]),
                        }
                    )
        cursor += timedelta(days=1)
    return series


def intraday_from_archive(out: Path, symbol: str, session: str | None = None) -> dict:
    """Rebuild an intraday series from the tick archive.

    qe.com.qa publishes no intraday history, so this only covers sessions the
    archive was running for — but it is the same shape as the source dashboard's
    intraday panel, and it accumulates from the first day you run `watch`.

    The feed's Volume is cumulative for the session, so per-interval volume is
    the difference between consecutive ticks.
    """
    folder = out / "archive" / "live" / symbol
    if not folder.is_dir():
        return {"session": None, "points": [], "sessionsAvailable": []}
    available = sorted(p.stem for p in folder.glob("*.jsonl"))
    if not available:
        return {"session": None, "points": [], "sessionsAvailable": []}
    chosen = session if session in available else available[-1]

    points, previous = [], None
    for line in (folder / f"{chosen}.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            tick = json.loads(line)
        except json.JSONDecodeError:
            continue
        price, volume = tick.get("lastPrice"), tick.get("volume") or 0
        if price is None:
            continue
        stamp = (tick.get("feedTime") or "")[-8:-3]  # HH:MM
        points.append(
            {
                "time": stamp,
                "price": price,
                "cumulativeVolume": volume,
                "volume": max(volume - previous, 0) if previous is not None else volume,
            }
        )
        previous = volume
    return {"session": chosen, "points": points, "sessionsAvailable": available}


# ------------------------------------------------------------------- panels

def _market_cap_ranks(stocks: list[dict], live: dict[str, dict], symbol: str) -> dict:
    """Rank by shares-outstanding x close, overall and inside the sector.

    Market cap is not in the report files, so it is reconstructed from the live
    share count and the period's close.
    """
    caps = []
    for row in stocks:
        code = row["SYMBOL_CODE"]
        quote = live.get(code)
        if not quote or quote.get("CompType") != "COMP":
            continue
        shares, close = _f(quote["SubscribedShares"]), _f(row["CLOSE_PRICE"])
        if not shares or not close:
            continue
        caps.append({"symbol": code, "cap": shares * close, "sector": quote["SectorEN"]})
    caps.sort(key=lambda c: c["cap"], reverse=True)

    order = [c["symbol"] for c in caps]
    sector = live[symbol]["SectorEN"]
    peers = [c["symbol"] for c in caps if c["sector"] == sector]
    return {
        "capRankMarket": order.index(symbol) + 1 if symbol in order else None,
        "capRankMarketOf": len(order),
        "capRankSector": peers.index(symbol) + 1 if symbol in peers else None,
        "capRankSectorOf": len(peers),
    }


def _top5(rows: list[dict], data_type: str, value_key: str) -> list[dict]:
    """Top5.TVALUE means a different thing per DATA_TYPE — name it properly."""
    return [
        {
            "symbol": r["SYMBOL_CODE"],
            "name": r["SYMBOL_NAME_3"],
            "nameAr": r["SYMBOL_NAME"],
            "close": _f(r["CLOSE_PRICE"]),
            value_key: _f(r["TVALUE"]),
        }
        for r in rows
        if r["DATA_TYPE"] == data_type
    ]


def _shareholder_activity(rows: list[dict]) -> list[dict]:
    """Nationality x investor type x buy/sell, as the source table lays it out."""
    out = []
    for group in rows:
        entry = {
            "nationality": NATIONALITY.get(group["natgrp"], group["natgrp"]),
            "code": group["natgrp"],
            "totalBuyPct": _f(group.get("net_buy")),
            "totalSellPct": _f(group.get("net_sell")),
            "rows": [],
        }
        for by_type in group.get("Data", []):
            label = INVESTOR_TYPE.get(by_type["invtype"], by_type["invtype"])
            for cell in by_type.get("Data", []):
                entry["rows"].append(
                    {
                        "investorType": label,
                        "tradeType": cell["trade_type"],
                        "companies": _i(cell.get("companies")),
                        "tradedValue": _f(cell.get("traded_value")),
                        "tradedVolume": _i(cell.get("traded_volume")),
                        "tradedValuePct": _f(cell.get("prct")),
                    }
                )
        # Individuals before Institutions, Buy before Sell — the source order.
        entry["rows"].sort(
            key=lambda r: (r["investorType"] != "Individuals", r["tradeType"] != "Buy")
        )
        out.append(entry)
    order = ["Qatari", "GCC", "Arab", "Foreigners"]
    out.sort(key=lambda e: order.index(e["nationality"]) if e["nationality"] in order else 9)
    return out


def _ownership(rows: list[dict] | None, symbol: str) -> dict | None:
    if not rows:
        return None
    record = next((r for r in rows if r["symbol_code"] == symbol), None)
    if record is None:
        return None

    by_nationality: dict[str, float] = {}
    split = {"Institutions": 0.0, "Individuals": 0.0}
    detail = []
    for group in record.get("Data", []):
        label = NATIONALITY.get(group["natgrp"], group["natgrp"])
        total = 0.0
        for cell in group.get("Data", []):
            pct = _f(cell.get("natgrp_prcnt")) or 0.0
            total += pct
            split[INVESTOR_TYPE[cell["invtype"]]] += pct
            detail.append(
                {
                    "nationality": label,
                    "investorType": INVESTOR_TYPE[cell["invtype"]],
                    "holders": _i(cell.get("natgrp_count")),
                    "shares": _i(cell.get("natgrp_shares")),
                    "pct": pct,
                }
            )
        by_nationality[label] = round(total, 3)
    return {
        "byNationality": by_nationality,
        "institutionsPct": round(split["Institutions"], 3),
        "individualsPct": round(split["Individuals"], 3),
        "detail": detail,
    }


def _insider_trades(client: Client, period: Period) -> list[dict]:
    """InsiderTrades is daily-only, so aggregate it across the period."""
    totals: dict[tuple[str, str], dict] = {}
    for day in period.days or (period.end_iso,):
        for row in client.try_report("InsiderTrades", day) or []:
            insider = " ".join((row.get("NIN_NAME") or "").split())
            key = (row["SYMBOL_CODE"], insider)
            entry = totals.setdefault(
                key,
                {
                    "symbol": row["SYMBOL_CODE"],
                    "company": row["SYMBOL_NAME_3"],
                    "insider": insider,
                    "buy": 0,
                    "sell": 0,
                    "sessions": 0,
                },
            )
            entry["buy"] += _i(row.get("BUY")) or 0
            entry["sell"] += _i(row.get("SELL")) or 0
            entry["sessions"] += 1
    out = list(totals.values())
    out.sort(key=lambda r: -(r["buy"] + r["sell"]))
    return out


def _ownership_pair(client: Client, symbol: str, period: Period) -> dict:
    """Register at the period end, against the register before the period began.

    OwnershipPercentage is a point-in-time snapshot published daily only, so a
    weekly or monthly view compares the two ends of its own window.
    """
    # The register publishes later than the session summary, so the newest trading
    # day often has no register yet. Walk back to the most recent one that does and
    # label it with its real date, rather than showing an empty panel.
    current_day, current = None, None
    cursor = period.end
    for _ in range(6):
        iso = cursor.isoformat()
        rows = client.try_report("OwnershipPercentage", iso)
        if rows:
            current_day, current = iso, _ownership(rows, symbol)
            break
        earlier = previous_daily(client, cursor)
        if earlier is None:
            break
        cursor = earlier

    if current_day is None:
        return {"current": None, "previous": None, "currentDate": None, "previousDate": None}

    # Daily compares consecutive sessions; a longer period compares its two ends.
    anchor = date.fromisoformat(current_day) if period.kind == "daily" else period.start
    baseline = previous_daily(client, anchor)
    baseline_day, previous = None, None
    for _ in range(6):
        if baseline is None:
            break
        rows = client.try_report("OwnershipPercentage", baseline.isoformat())
        if rows:
            baseline_day, previous = baseline.isoformat(), _ownership(rows, symbol)
            break
        baseline = previous_daily(client, baseline)

    return {
        "current": current,
        "previous": previous,
        "currentDate": current_day,
        "previousDate": baseline_day,
    }


def _short_index_name(name: str) -> str:
    return name.replace("All Share ", "").replace(" Index", "").strip()


# -------------------------------------------------------------------- build

def build_period(
    client: Client,
    symbol: str,
    period: Period,
    live: dict[str, dict],
    *,
    weeks: int = 52,
) -> dict:
    """One tab's worth of data."""
    path = period.path
    stocks = client.try_report("StocksSummary", path)
    if stocks is None:
        raise NotAvailable(f"no StocksSummary at {path}")
    quote = next((r for r in stocks if r["SYMBOL_CODE"] == symbol), None)
    if quote is None:
        raise KeyError(f"{symbol} not in StocksSummary for {path}")

    snapshot = live[symbol]
    close = _f(quote["CLOSE_PRICE"])
    shares = _f(snapshot["SubscribedShares"])

    # PriceBook is live-only, so recover book value per share and re-apply it to
    # the period's close. Exact for the current session; drifts for older ones.
    live_pb = _f(snapshot["PriceBook"])
    bvps = (_f(snapshot["LastPrice"]) / live_pb) if live_pb else None

    year_ago = trading_days_back(client, _one_year_before(period.end), 1)
    year_ago_close = client.stock_close(symbol, year_ago[0]) if year_ago else None

    market = client.report("MarketSummary", path)[0]
    indices = client.report("IndicesSummary", path)
    general = next(r for r in indices if r["INDEX_CODE"] == "GNRI")
    sector_index = next(
        (r for r in indices if r["INDEX_CODE"] == snapshot["IndexCode"]), None
    )

    venture = client.try_report("VentureSummary", path) or []
    venture_volume = sum(_i(r.get("TRADES_VOLUME")) or 0 for r in venture)
    venture_value = sum(_f(r.get("TRADES_VALUE")) or 0.0 for r in venture)
    venture_trades = sum(_i(r.get("TRADES_COUNT")) or 0 for r in venture)

    series = index_series(client, period.end, weeks)
    closes = [p["index"] for p in series] or [_f(general["INDEX_CLOSING_VALUE"])]
    index_high, index_low = max(closes), min(closes)
    index_close = _f(general["INDEX_CLOSING_VALUE"])

    top5 = client.report("Top5", path)

    return {
        "period": {
            "kind": period.kind,
            "tab": period.tab,
            "label": period.label,
            "path": path,
            "start": period.start.isoformat(),
            "end": period.end_iso,
            "sessions": len(period.days) or 1,
        },
        "share": {
            "open": _f(quote["OPEN_PRICE"]),
            "high": _f(quote["HIGH_PRICE"]),
            "low": _f(quote["LOW_PRICE"]),
            "close": close,
            "previousClose": _f(quote["PREVIOUS_CLOSE_PRICE"]),
            "changeValue": _f(quote["CHANGE_VALUE"]),
            "changePct": _f(quote["CHANGE_PRCT"]),
            "volume": _i(quote["TRADES_VOLUME"]),
            "value": _f(quote["TRADES_VALUE"]),
            "trades": _i(quote["TRADES_COUNT"]),
            "high52": _f(quote["HIGH52"]),
            "low52": _f(quote["LOW52"]),
            "oneYearChangePct": (
                round((close / year_ago_close - 1) * 100, 3) if year_ago_close else None
            ),
            "oneYearAgo": (
                {"date": year_ago[0], "close": year_ago_close} if year_ago_close else None
            ),
            "priceToBook": round(close / bvps, 3) if bvps else None,
            "bookValuePerShare": round(bvps, 4) if bvps else None,
            "priceToBookIsApproximate": True,
            "dividendYieldPct": _f(snapshot["Yield"]),
            "cashDividend": _f(snapshot["CashDividend"]),
            "eps": _f(snapshot["EPS"]),
            "peRatio": _f(snapshot["PERatio"]),
            "sharesOutstanding": _i(snapshot["SubscribedShares"]),
            "marketCap": round(shares * close, 2) if shares and close else None,
            **_market_cap_ranks(stocks, live, symbol),
        },
        "index": {
            "name": "QE Index",
            "indexValue": index_close,
            "changeValue": _f(general["CHANGE_VALUE"]),
            "changePct": _f(general["CHANGE_PRCT"]),
            "volume": (_i(market["TRADES_VOLUME"]) or 0) + venture_volume,
            "tradedValue": round((_f(market["TRADES_VALUE"]) or 0) + venture_value, 3),
            "trades": (_i(market["TRADES_COUNT"]) or 0) + venture_trades,
            "mainVolume": _i(market["TRADES_VOLUME"]),
            "mainValue": _f(market["TRADES_VALUE"]),
            "ventureVolume": venture_volume,
            "ventureValue": round(venture_value, 3),
            "tradedStocks": _i(market["TRADED_STOCKS"]),
            "gainers": _i(market["GAINER_STOCKS"]),
            "losers": _i(market["LOSER_STOCKS"]),
            "marketCap": _f(market["QSE_MCAP"]),
            "high52": index_high,
            "low52": index_low,
            "pctFromHigh52": round((index_close / index_high - 1) * 100, 2),
            "pctFromLow52": round((index_close / index_low - 1) * 100, 2),
            "window": {
                "weeks": weeks,
                "sessions": len(series),
                "basis": "daily closes from MarketSummary.INDEX_VALUE",
            },
        },
        "comparison": [
            {
                "label": f"{snapshot['CompanyEN']} Share",
                "changePct": _f(quote["CHANGE_PRCT"]),
            },
            {"label": "QE Index", "changePct": _f(general["CHANGE_PRCT"])},
        ]
        + (
            [
                {
                    "label": _short_index_name(sector_index["INDEX_NAME"]) + " Index",
                    "changePct": _f(sector_index["CHANGE_PRCT"]),
                }
            ]
            if sector_index
            else []
        ),
        "sectorIndices": [
            {
                "code": r["INDEX_CODE"],
                "name": _short_index_name(r["INDEX_NAME"]),
                "value": _f(r["INDEX_CLOSING_VALUE"]),
                "changeValue": _f(r["CHANGE_VALUE"]),
                "changePct": _f(r["CHANGE_PRCT"]),
            }
            for code in SECTOR_INDEX_CODES
            for r in indices
            if r["INDEX_CODE"] == code
        ],
        "allIndices": [
            {
                "code": r["INDEX_CODE"],
                "name": r["INDEX_NAME"],
                "value": _f(r["INDEX_CLOSING_VALUE"]),
                "changeValue": _f(r["CHANGE_VALUE"]),
                "changePct": _f(r["CHANGE_PRCT"]),
            }
            for r in indices
        ],
        "topGainers": _top5(top5, "TOP5GAINER", "changePct"),
        "topLosers": _top5(top5, "TOP5LOSER", "changePct"),
        "topByValue": _top5(top5, "TOP5VALUE", "tradedValue"),
        "topByVolume": _top5(top5, "TOP5VOLUME", "tradedVolume"),
        "shareholderActivity": _shareholder_activity(
            client.try_report("InvestorActivity", path) or []
        ),
        "ownership": _ownership_pair(client, symbol, period),
        "insiderTrades": _insider_trades(client, period),
        "indexSeries": series,
    }


def build(
    client: Client,
    symbol: str,
    *,
    kinds: tuple[str, ...] = KINDS,
    weeks: int = 52,
    refresh_seconds: int = 1800,
    today: date | None = None,
    history_days: int = 180,
    out: Path | None = None,
    archive_ticks: bool = True,
    archive_market: bool = False,
) -> dict:
    """The whole dashboard: one bundle carrying every period tab."""
    live_rows = client.live("MarketWatch")
    live = {row["Symbol"]: row for row in live_rows}
    if symbol not in live:
        raise KeyError(f"{symbol} not in the live MarketWatch feed")
    snapshot = live[symbol]

    state = client.market_state(symbol)
    # Archive the tick here, not in the caller: the intraday series is read a few
    # lines below, so recording afterwards would leave this build's own tick out
    # of its own chart.
    archived: dict[str, list[str]] = {}
    if out is not None and archive_ticks:
        archived = _archive.record_ticks(
            out, symbol, state, market_rows=live_rows if archive_market else None
        )

    periods: dict[str, dict] = {}
    problems: dict[str, str] = {}
    for kind in kinds:
        period = resolve(client, kind, today)
        if period is None:
            problems[kind] = "no closed period published yet"
            continue
        try:
            periods[kind] = build_period(client, symbol, period, live, weeks=weeks)
        except (NotAvailable, KeyError) as exc:
            problems[kind] = str(exc)

    if not periods:
        raise NotAvailable(f"no periods available for {symbol}: {problems}")

    anchor = max(date.fromisoformat(t["period"]["end"]) for t in periods.values())
    history = share_history(client, symbol, anchor, history_days) if history_days else []
    intraday = (
        intraday_from_archive(out, symbol)
        if out is not None
        else {"session": None, "points": [], "sessionsAvailable": []}
    )

    return {
        "meta": {
            "symbol": symbol,
            "name": snapshot["CompanyEN"],
            "nameAr": snapshot["CompanyAR"],
            "sector": snapshot["SectorEN"],
            "sectorIndexCode": snapshot["IndexCode"],
            "currency": "QAR",
            "market": "Qatar",
            "builtAt": datetime.now(QATAR).isoformat(timespec="seconds"),
            "refreshSeconds": refresh_seconds,
            "defaultKind": next(iter(periods)),
            "unavailable": problems,
            "logo": client.company_logo(symbol),
            "archived": archived,
            "source": "qe.com.qa static feeds — see API_REFERENCE.md",
        },
        "live": state,
        "history": history,
        "intraday": intraday,
        "periods": periods,
    }
