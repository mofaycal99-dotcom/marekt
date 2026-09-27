#!/usr/bin/env python3
"""Offline checks for the derivation and render layers.

The raw rows below are verbatim captures from qe.com.qa for IGRD on 2026-08-13.
Most assertions are the figures printed on the source PDF dashboard, so this is
what pins the pipeline to the thing it reproduces. No network.

    python3 test_build.py
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from pathlib import Path as _Path

from qse import Client, NotAvailable, archive, build_period, render
from qse.period import Period, month_weeks

DAY, PREV, BEFORE, YEAR_AGO = "2026-08-13", "2026-08-12", "2026-08-11", "2025-08-13"

MARKET_WATCH = [
    {
        "Symbol": "IGRD", "CompanyEN": "Estithmar Holding", "CompanyAR": "استثمار القابضة",
        "CompType": "COMP", "SectorEN": "Industrials", "IndexCode": "QIND",
        "LastPrice": "4.231", "PriceBook": "3.633", "SubscribedShares": "4493329500",
        "Yield": "0.00", "CashDividend": "0.00", "EPS": "0.25", "PERatio": "16.65",
    },
    {
        "Symbol": "IQCD", "CompanyEN": "Industries Qatar", "CompanyAR": "صناعات قطر",
        "CompType": "COMP", "SectorEN": "Industrials", "IndexCode": "QIND",
        "LastPrice": "10.04", "PriceBook": "2.0", "SubscribedShares": "6050000000",
        "Yield": "0", "CashDividend": "0", "EPS": "0", "PERatio": "0",
    },
    {
        "Symbol": "QNBK", "CompanyEN": "QNB", "CompanyAR": "QNB",
        "CompType": "COMP", "SectorEN": "Banks & Financial Services", "IndexCode": "QBNK",
        "LastPrice": "16.0", "PriceBook": "1.7", "SubscribedShares": "9236428000",
        "Yield": "0", "CashDividend": "0", "EPS": "0", "PERatio": "0",
    },
]

STOCKS = {
    DAY: [
        {
            "SYMBOL_CODE": "IGRD", "SYMBOL_NAME_3": "Estithmar Holding",
            "SYMBOL_NAME": "استثمار القابضة", "TRADES_COUNT": 744,
            "TRADES_VOLUME": 6366286, "TRADES_VALUE": "27647060.943",
            "OPEN_PRICE": "4.360", "HIGH_PRICE": "4.420", "LOW_PRICE": "4.298",
            "CLOSE_PRICE": "4.330", "PREVIOUS_CLOSE_PRICE": "4.445",
            "HIGH52": "4.445", "LOW52": "3.435",
            "CHANGE_PRCT": "-2.587", "CHANGE_VALUE": "-0.115",
        },
        {"SYMBOL_CODE": "IQCD", "CLOSE_PRICE": "10.04"},
        {"SYMBOL_CODE": "QNBK", "CLOSE_PRICE": "16.00"},
    ],
    YEAR_AGO: [{"SYMBOL_CODE": "IGRD", "CLOSE_PRICE": "4.181"}],
}

MARKET_SUMMARY = {
    "DATE_TYPE": "Day", "INDEX_VALUE": 10020.84, "TRADED_STOCKS": 52.0,
    "TRADES_COUNT": 23564.0, "TRADES_VOLUME": 238081594.0,
    "TRADES_VALUE": "740865670.710", "GAINER_STOCKS": 24.0, "LOSER_STOCKS": 26.0,
    "QSE_MCAP": "601340435012.114",
}

INDICES = [
    ("GNRI", "General Index", 10020.84, "-34.760", "-0.350"),
    ("QBNK", "All Share Banks&Financial Services Index", 5059.44, "-7.820", "-0.150"),
    ("QCON", "All Share Consumer Goods&Services Index", 7897.93, "-19.670", "-0.250"),
    ("QIND", "All Share Industrials Index", 3837.52, "-61.720", "-1.580"),
    ("QINS", "All Share Insurance Index", 2743.57, "-19.680", "-0.710"),
    ("QREA", "All Share Real Estate Index", 1395.84, "5.520", "0.400"),
    ("QTLC", "All Share Telecoms Index", 2408.68, "5.830", "0.240"),
    ("QTRN", "All Share Transportation Index", 5370.36, "9.620", "0.180"),
]
INDICES_SUMMARY = [
    {
        "DATE_TYPE": "Day", "INDEX_CODE": code, "INDEX_NAME": name, "INDEX_NAME_2": name,
        "PRIORITY": 0, "INDEX_CLOSING_VALUE": value,
        "CHANGE_VALUE": change, "CHANGE_PRCT": pct,
    }
    for code, name, value, change, pct in INDICES
]

VENTURE = [
    {"SYMBOL_CODE": "TQES", "TRADES_COUNT": 58.0, "TRADES_VOLUME": 291542.0,
     "TRADES_VALUE": "608615.103"},
]

TOP5 = [
    ("TOP5GAINER", "BEMA", "Beema", "3.774", 5.5),
    ("TOP5LOSER", "IQCD", "Industries Qatar", "-2.995", 10.04),
    ("TOP5VALUE", "IQCD", "Industries Qatar", "100512872.387", 10.04),
    ("TOP5VOLUME", "BLDN", "Baladna", "44781237", 1.317),
]
TOP5_ROWS = [
    {
        "DATE_TYPE": "Day", "DATA_TYPE": kind, "SYMBOL_CODE": code,
        "SYMBOL_NAME": code, "SYMBOL_NAME_3": name, "TVALUE": tvalue,
        "CLOSE_PRICE": close,
    }
    for kind, code, name, tvalue, close in TOP5
]

# Qatari and GCC in full; Arab deliberately missing its Institutions/Sell leg,
# which is the shape that used to break the rowspan grid in the render layer.
INVESTOR_ACTIVITY = [
    {
        "natgrp": "QTR", "net_buy": 31.5, "net_sell": 75.983,
        "Data": [
            {"invtype": "I", "Data": [
                {"trade_type": "Sell", "companies": "52", "traded_value": "127748509.475",
                 "traded_volume": "64982404", "prct": 17.243},
                {"trade_type": "Buy", "companies": "50", "traded_value": "122832155.722",
                 "traded_volume": "60216900", "prct": 16.58}]},
            {"invtype": "C", "Data": [
                {"trade_type": "Buy", "companies": "42", "traded_value": "110534649.653",
                 "traded_volume": "51592666", "prct": 14.92},
                {"trade_type": "Sell", "companies": "36", "traded_value": "435182609.513",
                 "traded_volume": "119457475", "prct": 58.74}]},
        ],
    },
    {
        "natgrp": "ARB", "net_buy": 5.471, "net_sell": 5.028,
        "Data": [
            {"invtype": "I", "Data": [
                {"trade_type": "Buy", "companies": "47", "traded_value": "40310478.485",
                 "traded_volume": "22710053", "prct": 5.441},
                {"trade_type": "Sell", "companies": "51", "traded_value": "37138983.703",
                 "traded_volume": "21116291", "prct": 5.013}]},
            {"invtype": "C", "Data": [
                {"trade_type": "Buy", "companies": "1", "traded_value": "225225.000",
                 "traded_volume": "22500", "prct": 0.03}]},
        ],
    },
]

OWNERSHIP = {
    DAY: [{
        "symbol_code": "IGRD", "symbol_name_3": "Estithmar Holding",
        "Data": [
            {"natgrp": "GCC", "Data": [
                {"invtype": "I", "natgrp_count": "25", "natgrp_shares": "1373239", "natgrp_prcnt": "0.031"},
                {"invtype": "C", "natgrp_count": "14", "natgrp_shares": "11250762", "natgrp_prcnt": "0.250"}]},
            {"natgrp": "ARB", "Data": [
                {"invtype": "I", "natgrp_count": "263", "natgrp_shares": "34978213", "natgrp_prcnt": "0.778"}]},
            {"natgrp": "FRN", "Data": [
                {"invtype": "C", "natgrp_count": "145", "natgrp_shares": "138362146", "natgrp_prcnt": "3.079"},
                {"invtype": "I", "natgrp_count": "184", "natgrp_shares": "24010570", "natgrp_prcnt": "0.534"}]},
            {"natgrp": "QTR", "Data": [
                {"invtype": "C", "natgrp_count": "70", "natgrp_shares": "1170708231", "natgrp_prcnt": "26.054"},
                {"invtype": "I", "natgrp_count": "3807", "natgrp_shares": "3112646339", "natgrp_prcnt": "69.273"}]},
        ],
    }],
    # The session before the weekly window opens — a weekly register delta is
    # measured against this, not against the window's own first day.
    BEFORE: [{
        "symbol_code": "IGRD", "symbol_name_3": "Estithmar Holding",
        "Data": [
            {"natgrp": "QTR", "Data": [
                {"invtype": "C", "natgrp_count": "70", "natgrp_shares": "1", "natgrp_prcnt": "26.100"},
                {"invtype": "I", "natgrp_count": "3800", "natgrp_shares": "1", "natgrp_prcnt": "69.200"}]},
        ],
    }],
    PREV: [{
        "symbol_code": "IGRD", "symbol_name_3": "Estithmar Holding",
        "Data": [
            {"natgrp": "QTR", "Data": [
                {"invtype": "C", "natgrp_count": "70", "natgrp_shares": "1", "natgrp_prcnt": "26.070"},
                {"invtype": "I", "natgrp_count": "3800", "natgrp_shares": "1", "natgrp_prcnt": "69.244"}]},
            {"natgrp": "FRN", "Data": [
                {"invtype": "C", "natgrp_count": "145", "natgrp_shares": "1", "natgrp_prcnt": "3.083"},
                {"invtype": "I", "natgrp_count": "184", "natgrp_shares": "1", "natgrp_prcnt": "0.553"}]},
            {"natgrp": "GCC", "Data": [
                {"invtype": "C", "natgrp_count": "14", "natgrp_shares": "1", "natgrp_prcnt": "0.250"},
                {"invtype": "I", "natgrp_count": "25", "natgrp_shares": "1", "natgrp_prcnt": "0.029"}]},
            {"natgrp": "ARB", "Data": [
                {"invtype": "I", "natgrp_count": "263", "natgrp_shares": "1", "natgrp_prcnt": "0.769"}]},
        ],
    }],
}

INSIDERS = {
    DAY: [
        {"SYMBOL_CODE": "QEWS", "SYMBOL_NAME_3": "Nebras Energy",
         "NIN_NAME": "جهاز قطر للإستثمار          حكومة دولة قطر", "BUY": None, "SELL": 1290780},
    ],
    PREV: [
        # Same insider on the day before, to exercise period aggregation.
        {"SYMBOL_CODE": "QEWS", "SYMBOL_NAME_3": "Nebras Energy",
         "NIN_NAME": "جهاز قطر للإستثمار حكومة دولة قطر", "BUY": 500, "SELL": 1000},
    ],
}

KNOWN_DAYS = {DAY, PREV, BEFORE, YEAR_AGO}


class StubClient(Client):
    """Serves the captured rows instead of hitting the network."""

    def live(self, name):
        assert name == "MarketWatch"
        return MARKET_WATCH

    def market_state(self, symbol=None):
        return {"state": "Close", "lastUpdate": "13/08/2026 - 13:15:00", "quote": None}

    def company_logo(self, symbol):
        return None

    def report(self, name, period):
        rows = self.try_report(name, period)
        if rows is None:
            raise NotAvailable(f"{name} {period}")
        return rows

    def try_report(self, name, period):
        day = period.replace("/", "-")
        if name == "OwnershipPercentage":
            return OWNERSHIP.get(day)
        if name == "InsiderTrades":
            return INSIDERS.get(day)
        if day not in KNOWN_DAYS:
            return None
        if name == "StocksSummary":
            return STOCKS.get(day)
        if name == "MarketSummary":
            return [MARKET_SUMMARY]
        if day != DAY:
            return None
        return {
            "IndicesSummary": INDICES_SUMMARY,
            "VentureSummary": VENTURE,
            "Top5": TOP5_ROWS,
            "InvestorActivity": INVESTOR_ACTIVITY,
        }.get(name)


CHECKS: list[tuple[str, object, object]] = []


def check(label, actual, expected):
    CHECKS.append((label, actual, expected))


def _daily_period() -> Period:
    day = date.fromisoformat(DAY)
    return Period(
        kind="daily", path="2026/08/13", label="13 August 2026", tab="Daily",
        end=day, start=day, days=(DAY,),
    )


def _weekly_period() -> Period:
    """A two-session week, enough to prove period aggregation."""
    return Period(
        kind="weekly", path="2026/08/13", label="12–13 August 2026", tab="Weekly",
        end=date.fromisoformat(DAY), start=date.fromisoformat(PREV), days=(PREV, DAY),
    )


def main() -> int:
    client = StubClient()
    live = client.market_watch_by_symbol()
    tab = build_period(client, "IGRD", _daily_period(), live, weeks=52)
    s, x = tab["share"], tab["index"]

    # --- straight passthrough, as printed on the PDF
    check("open", s["open"], 4.36)
    check("high", s["high"], 4.42)
    check("low", s["low"], 4.298)
    check("close", s["close"], 4.33)
    check("previous close", s["previousClose"], 4.445)
    check("change", s["changeValue"], -0.115)
    check("change %", s["changePct"], -2.587)
    check("volume", s["volume"], 6366286)
    check("value", s["value"], 27647060.943)
    check("52w high", s["high52"], 4.445)
    check("52w low", s["low52"], 3.435)
    check("shares outstanding", s["sharesOutstanding"], 4493329500)

    # --- derived: this is where the PDF is reproduced rather than copied
    check("1-year change %", s["oneYearChangePct"], 3.564)
    check("price to book", s["priceToBook"], 3.718)
    check("market cap", s["marketCap"], 19456116735.0)
    # Ranks span whatever universe StocksSummary holds. This stub carries three
    # stocks (QNBK 147.8bn > IQCD 60.7bn > IGRD 19.5bn), so the market rank is
    # 3 of 3 and Industrials is 2 of 2 — the logic, not the live answer. Against
    # the real 54-stock universe it returns 7 of 54 and 2 of 10, as the PDF prints.
    check("cap rank, sector", (s["capRankSector"], s["capRankSectorOf"]), (2, 2))
    check("cap rank, market", (s["capRankMarket"], s["capRankMarketOf"]), (3, 3))

    check("QE Index", x["indexValue"], 10020.84)
    check("QE Index change %", x["changePct"], -0.35)
    check("volume incl. venture", x["volume"], 238081594 + 291542)
    check("value incl. venture", x["tradedValue"], round(740865670.710 + 608615.103, 3))
    check("gainers/losers", (x["gainers"], x["losers"]), (24, 26))

    # --- reshaping
    sectors = {i["code"]: i["changePct"] for i in tab["sectorIndices"]}
    check("sector count", len(sectors), 7)
    check("industrials %", sectors["QIND"], -1.58)
    check("real estate %", sectors["QREA"], 0.4)
    check("comparison rows", [c["changePct"] for c in tab["comparison"]],
          [-2.587, -0.35, -1.58])
    check("gainer uses changePct", tab["topGainers"][0]["changePct"], 3.774)
    check("value uses tradedValue", tab["topByValue"][0]["tradedValue"], 100512872.387)
    check("volume uses tradedVolume", tab["topByVolume"][0]["tradedVolume"], 44781237)

    qtr = tab["shareholderActivity"][0]
    check("activity nationality", qtr["nationality"], "Qatari")
    check("activity total buy", qtr["totalBuyPct"], 31.5)
    check("activity row order",
          [(r["investorType"][:4], r["tradeType"]) for r in qtr["rows"]],
          [("Indi", "Buy"), ("Indi", "Sell"), ("Inst", "Buy"), ("Inst", "Sell")])
    check("individuals buy %", qtr["rows"][0]["tradedValuePct"], 16.58)
    check("institutions sell %", qtr["rows"][3]["tradedValuePct"], 58.74)

    own = tab["ownership"]["current"]
    check("Qatari ownership", own["byNationality"]["Qatari"], 95.327)
    check("GCC ownership", own["byNationality"]["GCC"], 0.281)
    check("Arab ownership", own["byNationality"]["Arab"], 0.778)
    check("Foreign ownership", own["byNationality"]["Foreigners"], 3.613)
    check("institutions %", own["institutionsPct"], 29.383)
    check("individuals %", own["individualsPct"], 70.616)
    check("baseline is prior session", tab["ownership"]["previousDate"], PREV)
    check("previous institutions %", tab["ownership"]["previous"]["institutionsPct"], 29.403)

    check("insider name collapsed",
          tab["insiderTrades"][0]["insider"], "جهاز قطر للإستثمار حكومة دولة قطر")
    check("insider null buy becomes 0", tab["insiderTrades"][0]["buy"], 0)
    check("daily insider not aggregated", tab["insiderTrades"][0]["sell"], 1290780)

    # --- periods: weekly aggregates the daily-only files across its sessions
    weekly = build_period(client, "IGRD", _weekly_period(), live, weeks=52)
    check("weekly insider rows", len(weekly["insiderTrades"]), 1)
    check("weekly insider buy summed", weekly["insiderTrades"][0]["buy"], 500)
    check("weekly insider sell summed", weekly["insiderTrades"][0]["sell"], 1290780 + 1000)
    check("weekly insider sessions", weekly["insiderTrades"][0]["sessions"], 2)
    check("weekly register baseline", weekly["ownership"]["previousDate"], BEFORE)
    check("weekly baseline institutions %",
          weekly["ownership"]["previous"]["institutionsPct"], 26.1)
    check("weekly sessions", weekly["period"]["sessions"], 2)

    # --- week numbering, validated against the site for these months
    check("Aug 2026 W1 (month opens Saturday)",
          month_weeks(2026, 8)[1][0], date(2026, 8, 2))
    check("Aug 2026 W2 ends 13th", month_weeks(2026, 8)[2][-1], date(2026, 8, 13))
    check("Nov 2025 W1 (month opens Saturday)",
          month_weeks(2025, 11)[1][0], date(2025, 11, 2))
    check("Jul 2026 W1 is the partial lead week",
          month_weeks(2026, 7)[1], [date(2026, 7, 1), date(2026, 7, 2)])
    check("no Fri/Sat in any week",
          {d.weekday() for week in month_weeks(2026, 8).values() for d in week} & {4, 5},
          set())

    # --- render: three tabs, and the activity grid must stay rectangular
    bundle = {
        "meta": {
            "symbol": "IGRD", "name": "Estithmar Holding", "nameAr": "استثمار القابضة",
            "sector": "Industrials", "currency": "QAR", "market": "Qatar",
            "builtAt": "2026-08-13T13:20:00+03:00", "refreshSeconds": 1800,
            "defaultKind": "daily", "unavailable": {"monthly": "not closed yet"},
            "logo": None, "source": "test",
        },
        "live": {"state": "Close", "lastUpdate": "13/08/2026 - 13:15:00",
                 "indexValue": 10020.84, "changePct": -0.35, "quote": None},
        "periods": {"daily": tab, "weekly": weekly},
    }
    page = render(bundle)
    check("html renders", page.startswith("<!doctype html>") and len(page) > 8000, True)
    check("no unsubstituted css token", "$s1l" not in page, True)
    check("tab radios", page.count('class="tabradio"'), 2)
    check("daily radio checked", 'id="t-daily" data-kind="daily" checked' in page, True)
    check("monthly tab disabled", 'class="disabled"' in page, True)
    check("css tab rules", page.count(":checked~.panelset"), 2)
    check("self-refresh set", 'http-equiv="refresh" content="1800"' in page, True)
    check("activity grid rectangular", _activity_columns(page), {6})

    # A full-width panel must survive the narrow breakpoint. The responsive rule
    # used to force every panel to span 6, which silently halved the share graph
    # inside the Streamlit iframe (usable width there is under the breakpoint).
    spans = re.findall(r"--span:(\d+);--span-md:(\d+)", page)
    check("every panel declares both spans", len(spans) > 10, True)
    check("full-width panels stay full at md",
          {md for sp, md in spans if sp == "12"}, {"12"})
    check("other panels collapse to half at md",
          {md for sp, md in spans if sp != "12"}, {"6"})
    check("md rule reads the variable", "span var(--span-md,6)" in page, True)

    # ------------------------------------------------- streamlit chart specs
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("appmod", "app.py")
        appmod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(appmod)
    except Exception as exc:  # streamlit absent — the CLI does not need it
        print(f"  [skip] streamlit helpers ({type(exc).__name__})")
    else:
        check("brief abbreviates billions", appmod.whole(4493329500), "4,493,329,500")
        check("pct formats plainly", appmod.pct(-2.587), "-2.59%")
        check("signed keeps the sign", appmod.signed(-2.587), "-2.59%")
        check("signed marks gains", appmod.signed(3.564), "+3.56%")
        check("tone maps sign to class",
              (appmod.tone(1), appmod.tone(-1), appmod.tone(0)), ("up", "down", ""))
        check("missing values render as a dash",
              (appmod.money(None), appmod.whole(None), appmod.pct(None)), ("-", "-", "-"))
        # Palette must be the Excel values the source dashboard uses.
        check("excel palette", (appmod.BAR_BLUE, appmod.BAR_GRAY, appmod.RED, appmod.GREEN),
              ("#4472C4", "#A5A5A5", "#FF0000", "#00B050"))

        # The durable rule, learned three times: a bar or area whose y scale has an
        # explicit domain excluding zero MUST declare y2. Otherwise the implicit
        # baseline of zero sits outside the domain, Vega clips the geometry, and the
        # chart draws its axes with no data. It bit the price area, the log-scale
        # ownership bars and the zoomed institutions bars — so it is checked against
        # the real generated specs, not the source text.
        import pandas as _pd

        captured: list = []
        appmod.st.altair_chart = lambda chart, **kw: captured.append(chart.to_dict())

        appmod.price_and_volume(
            _pd.DataFrame({
                "date": _pd.to_datetime(["2026-08-10", "2026-08-11", "2026-08-12"]),
                "_price": [4.10, 4.30, 4.20], "_volume": [1, 2, 3],
                "_up": [True, True, False],
            }), "date", "T")
        appmod.ownership_chart(
            [{"Nationality": "Qatari", "When": "08-18", "pct": 95.3},
             {"Nationality": "GCC", "When": "08-18", "pct": 0.28}],
            ["Qatari", "GCC"], ["08-18"])
        appmod.institutions_chart(
            [{"When": "08-17", "pct": 29.403}, {"When": "08-18", "pct": 29.341}],
            ["08-17", "08-18"], "08-18")
        appmod.comparison_chart(
            [{"label": "Share", "changePct": -2.59},
             {"label": "QE Index", "changePct": 0.35}])

        def _layers(spec):
            return spec.get("layer", [spec])

        offenders = []
        for spec in captured:
            for layer in _layers(spec):
                mark = layer.get("mark")
                kind = mark.get("type") if isinstance(mark, dict) else mark
                if kind not in ("bar", "area"):
                    continue
                y = (layer.get("encoding") or {}).get("y") or {}
                domain = (y.get("scale") or {}).get("domain")
                if not isinstance(domain, list) or len(domain) != 2:
                    continue
                if domain[0] <= 0 <= domain[1]:
                    continue  # zero is inside the domain, baseline is legal
                if "y2" not in (layer.get("encoding") or {}):
                    offenders.append(f"{kind} domain={domain}")
        check("charts inspected", len(captured), 5)

        # Ticker: the seamless loop depends on emitting the item list exactly
        # twice and translating the track by exactly -50%. Any other pairing
        # makes it visibly snap back at the wrap.
        html_out: list = []
        appmod.st.html = lambda body, **kw: html_out.append(body)
        appmod.ticker_bar(
            {"state": "Open", "indexValue": 9848.10, "changePct": -0.45},
            [{"symbol": "IGRD", "price": 4.107, "changePct": -1.44},
             {"symbol": "QNBK", "price": 16.80, "changePct": 0.12}],
            [{"Headline": "Discloses <b>semi-annual</b> results",
              "PublishDate": "2026-08-12T19:41:43+03:00"}],
        )
        bar = html_out[-1]
        check("ticker emits two identical runs", bar.count('class="run"'), 2)
        one = bar.split('class="run"')[1]
        two = bar.split('class="run"')[2]
        check("both runs carry the same items",
              one.count('class="ti"'), two.count('class="ti"'))
        check("track translates by exactly half",
              "translateX(-50%)" in Path("app.py").read_text(encoding="utf-8"), True)
        check("duration scales with item count",
              int(re.search(r"animation-duration:(\d+)s", bar).group(1)), 30)
        check("headline is escaped",
              "&lt;b&gt;semi-annual&lt;/b&gt;" in bar, True)
        check("news badge present", 'class="news"' in bar, True)
        check("empty input renders nothing",
              (html_out.append("SENTINEL"), appmod.ticker_bar({}, [], []),
               html_out[-1])[2], "SENTINEL")
        check("every non-zero-based bar/area declares y2", offenders, [])

        # An arc needs both radii stated. Vega derives the outer radius from the
        # space left after the legend, so an innerRadius set close to that guess
        # renders a hairline ring rather than a donut.
        arc_src = Path("app.py").read_text(encoding="utf-8")
        for chunk in arc_src.split("mark_arc(")[1:]:
            head = chunk[:120]
            check("arc states innerRadius", "innerRadius" in head, True)
            check("arc states outerRadius", "outerRadius" in head, True)
            inner = int(re.search(r"innerRadius=(\d+)", head).group(1))
            outer = int(re.search(r"outerRadius=(\d+)", head).group(1))
            check("donut ring is thick enough to read", outer - inner >= 20, True)

    # ------------------------------------------------- news listening (real feed)
    import listening

    names = {"Qatar Fuel": "QFLS", "Qatari German Co. for Medical Devices": "QGMD",
             "Rayan": "MARK", "Al Meera Consumer Goods Company": "MERS"}
    index = listening.entity_index(names)
    check("short trading names are excluded from matching",
          any(k == "rayan" for k in index), False)
    check("QE index notice is not tagged as a company",
          listening.attribute("QE Index, QE Al Rayan Islamic Index Constituents", index), None)
    check("legal-name variant still resolves",
          listening.attribute(
              "The Qatari German For Medical Devices Company announces an agreement",
              index), "QGMD")
    check("exchange notice is market-wide",
          listening.attribute("Randomization of the Opening & Closing Time", index), None)

    check("procedural notices forced neutral",
          listening.classify("Randomization of the Opening & Closing Time"), "Neutral")
    check("index review forced neutral",
          listening.classify("FTSE Global Equity Index Series Semi Annual Review"), "Neutral")
    check("postponement reads negative",
          listening.classify("Postponed its EGM due to lack of quorum"), "Negative")
    check("profit growth reads positive",
          listening.classify("Half-year profit rises on growth"), "Positive")

    shaped = listening.feed(
        [{"Headline": "Qatar Fuel Co.: Postponed it's EGM", "Summary": "",
          "PublishDate": "2026-08-19T07:40:12+03:00", "IsBreakingNews": "N",
          "url": "https://www.qe.com.qa/displaynewsdetails?InfoID=46770"}],
        names,
    )
    check("row carries a real link",
          shaped[0]["url"], "https://www.qe.com.qa/displaynewsdetails?InfoID=46770")
    check("row keeps the real date and time",
          (shaped[0]["date"], shaped[0]["time"]), ("2026-08-19", "07:40"))
    check("no synthetic dataset left in the tree",
          Path("demo_social.py").exists(), False)

    # ---- register scan: archetypes and the graph -----------------------------
    # These run on the generated panel when it exists, and are skipped when it
    # does not — the panel is a local artefact, and a checkout without one is a
    # valid state rather than a failure.
    if (Path("out") / "synth" / "market.json").exists():
        from synth.discover import ARCHETYPES, analyse

        scan = analyse()
        graph, arche = scan["graph"], scan["archetypes"]
        holders = len(scan["names"])
        scanned = scan["scanned"]

        # Holders who enter or leave mid-panel are deliberately not scanned: a
        # correlation needs a full run of months. The dashboard reports them.
        check("the panel is wider than the scan", holders > scanned, True)
        check("scanned and excluded account for the register",
              scanned + scan["excluded"], holders)

        check("every scanned holder gets an archetype",
              sum(a["count"] for a in arche), scanned)
        check("no holder gets two archetypes",
              len({k for a in arche for k in a["holders"]}), scanned)
        check("archetype labels are all known",
              {a["label"] for a in arche} <= set(ARCHETYPES), True)
        check("archetype float shares sum to 100%",
              round(sum(a["pct"] for a in arche)), 100)
        check("empty archetypes are not rendered",
              all(a["count"] for a in arche), True)

        check("the graph carries every scanned holder",
              len(graph["nodes"]), scanned)
        # Positions are register figures now, not drawing coordinates. x is a
        # ratio on a log axis, so a zero or negative value would not merely look
        # wrong — Vega drops the point and the chart silently loses a holder.
        check("every holder has a plottable position",
              all(n["x"] > 0 and n["y"] >= 0 for n in graph["nodes"]), True)
        check("positions are the register's own figures",
              [round(n["x"], 6) for n in graph["nodes"][:3]],
              [round(scan["series"][n["nin"]][scan["months"][-1]]
                     / scan["series"][n["nin"]][scan["months"][0]], 6)
               for n in graph["nodes"][:3]])
        check("drawn edges never exceed those found",
              len(graph["edges"]) <= graph["edges_found"], True)
        # Thinning is per holder, so a holder that appears in many other
        # holders' strongest few keeps more than DEGREE_CAP edges — the cap
        # bounds what each node contributes, not what it ends up with. What must
        # hold is that dropping edges never breaks a group apart: the clusters
        # drawn have to be the clusters found, or the picture argues something
        # the scan did not.
        from synth.discover import components

        ids = [n["nin"] for n in graph["nodes"]]
        drawn = [{"a": e["a"], "b": e["b"]} for e in graph["edges"]]
        kept = [c for c in components(sorted(ids), drawn) if len(c) > 1]
        # Holders that never dealt land on exactly the same point, (1.0, 0.0),
        # so a position is no longer an identity — edges carry ids instead.
        check("every holder appears once in the graph", len(set(ids)), scanned)
        check("thinning never splits a group",
              sorted(len(c) for c in kept),
              sorted(len(c) for c in graph["clusters"]))
        # Thinning removing edges is a property of a dense graph, not an
        # invariant — a book with two links has nothing to thin. What must hold
        # either way is that no holder the scan linked ends up drawn alone.
        drawn_ends = {e["a"] for e in graph["edges"]} | {e["b"] for e in graph["edges"]}
        check("thinning never orphans a linked holder",
              all(n["nin"] in drawn_ends for n in graph["nodes"] if n["linked"]),
              True)
        check("linked flag matches the groups",
              sum(1 for n in graph["nodes"] if n["linked"]),
              sum(len(c) for c in graph["clusters"]))
        check("clusters and singletons account for everyone",
              sum(len(c) for c in graph["clusters"]) + len(graph["singles"]), scanned)
        # The chart names exactly the holders the findings name — so every label
        # can be looked up in the panel beside it, and nothing else is named.
        reported = {k for f in scan["findings"] for k in f["holders"]}
        check("the chart names exactly the reported holders",
              {n["nin"] for n in graph["nodes"] if n["tag"]}, reported)
        check("label offsets are one of the two the chart layers",
              sorted({n["dy"] for n in graph["nodes"] if n["tag"]}) in ([-14], [-14, 18]),
              True)
        # ---- register book: the reporting layer ------------------------------
        from synth import book as bk

        snaps = bk.snapshots(scan["series"], scan["names"], scan["months"])
        shares_total = scan["market"]["total_shares"]
        m_now, m_was = scan["months"][-1], scan["months"][-2]
        curr, prior = snaps[m_now], snaps[m_was]
        cmp_all = bk.compare(prior, curr, shares_total)

        check("every month has a snapshot", len(snaps), len(scan["months"]))
        check("a snapshot holds only live holders",
              all(len(snaps[m]) <= len(scan["names"]) for m in scan["months"]), True)
        check("the book is not static across the panel",
              len({len(snaps[m]) for m in scan["months"]}) > 1, True)

        rows_now = [r for r in cmp_all["all_rows"] if r["status"] != "left"]
        check("the comparison keeps every current holder", len(rows_now), len(curr))
        check("comparison shares reconcile to the snapshot",
              sum(r["shares_now"] for r in cmp_all["all_rows"]),
              sum(r["shares"] for r in curr))
        check("the total line reconciles to its rows",
              cmp_all["total"]["shares_now"],
              sum(r["shares_now"] for r in cmp_all["all_rows"]))
        check("excluding related parties removes exactly them",
              cmp_all["total"]["shares_now"] - cmp_all["total_ex_related"]["shares_now"],
              sum(r["shares"] for r in curr if r["related"]))

        # The point of the two-snapshot comparison: a holder in one month only.
        check("arrivals are absent from the earlier month",
              all(r["shares_was"] == 0
                  for r in cmp_all["all_rows"] if r["status"] == "entered"), True)
        check("departures are absent from the later month",
              all(r["shares_now"] == 0
                  for r in cmp_all["all_rows"] if r["status"] == "left"), True)
        check("holders that did not deal show no change",
              all(r["delta_shares"] == 0
                  for r in cmp_all["all_rows"]
                  if r["status"] == "held" and r["shares_was"] == r["shares_now"]),
              True)
        # A register where every holder moves every month is not a register.
        still = sum(1 for r in cmp_all["all_rows"]
                    if r["status"] == "held" and r["delta_shares"] == 0)
        check("most of the book is untouched in a month",
              still > len(rows_now) // 3, True)

        for name, keep in bk.CUTS.items():
            cut = bk.compare(prior, curr, shares_total, keep=keep)
            check(f"cut reconciles: {name}".lower(),
                  cut["total"]["shares_now"],
                  sum(r["shares"] for r in curr if keep(r)))
        check("the related-party cut is the three the PDF names",
              len([r for r in curr if r["related"]]),
              len(scan["market"]["related_parties"]))
        check("the long list is capped",
              len(bk.compare(prior, curr, shares_total, limit=bk.TOP_N)["rows"]),
              min(bk.TOP_N, len(cmp_all["all_rows"])))

        for label, key in bk.SEGMENTS.items():
            seg = bk.segment(prior, curr, key, shares_total)
            check(f"segment sums to the book: {label}".lower(),
                  sum(s["shares"] for s in seg), sum(r["shares"] for r in curr))
            check(f"segment holders sum to the book: {label}".lower(),
                  sum(s["holders"] for s in seg), len(curr))

        con = bk.concentration(curr, shares_total)
        check("concentration bands nest",
              con["top10"] <= con["top20"] <= con["top50"], True)

        watch = bk.watchlist(cmp_all, prior, curr, shares_total, (m_was, m_now))
        check("every watch item carries a rule and an action",
              all(i["rule"] and i["action"] and i["detail"] and i["title"]
                  and i["severity"] in ("high", "medium", "low") for i in watch),
              True)
        # A standing disclosed holding is a fact, not a thing to watch.
        over = [r for r in cmp_all["all_rows"]
                if r["pct_was"] >= 5 and r["pct_now"] >= 5
                and abs(r["delta_pp"]) < bk.STAKE_MOVE]
        check("a steady holder above the threshold is not re-flagged",
              any(r["name"] in i["title"] for r in over for i in watch), False)
        check("the executive snapshot is six tiles",
              len(bk.executive(prior, curr, cmp_all, shares_total, (m_was, m_now))), 6)

        def _signature(g) -> str:
            return hashlib.sha256(
                repr([(n["nin"], round(n["x"], 9), round(n["y"], 9))
                      for n in g["nodes"]]).encode()
            ).hexdigest()[:12]

        check("the layout is deterministic",
              _signature(analyse()["graph"]), _signature(graph))

    failed = [(k, a, e) for k, a, e in CHECKS if a != e]
    for label, actual, expected in CHECKS:
        mark = "ok  " if actual == expected else "FAIL"
        print(
            f"  [{mark}] {label:<38} {actual!r}"
            + ("" if actual == expected else f"   expected {expected!r}")
        )
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


def _activity_columns(page: str) -> set[int]:
    """Resolve the rowspans in the shareholders table into a column count per row.

    A nationality missing a Buy or Sell leg used to make a rowspan bleed into the
    next group and shift every following cell, so this asserts the grid stays
    rectangular rather than merely that the HTML parses.
    """
    block = page.split("Qatar Market Shareholders Activity")[1].split("</table>")[0]
    rows = re.findall(r"<tr>(.*?)</tr>", block.split("<tbody>")[1])
    widths = [0] * len(rows)
    for i, row in enumerate(rows):
        for cell in re.findall(r"<td[^>]*>", row):
            widths[i] += 1
            span = re.search(r'rowspan="(\d+)"', cell)
            for k in range(1, int(span.group(1)) if span else 1):
                if i + k < len(widths):
                    widths[i + k] += 1
    return set(widths)


if __name__ == "__main__":
    sys.exit(main())
