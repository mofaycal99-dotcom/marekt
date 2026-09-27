"""HTTP access to qe.com.qa's data endpoints.

No cookies, no session, no CSRF token — see ../API_REFERENCE.md.

Historical reports are plain GETs against static files. The *live* feeds are
POSTs, because their static mirrors can freeze mid-session; see LIVE.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_plus

# The apex domain answers, but its certificate is issued for the www name only,
# so verification fails with "Hostname mismatch, certificate is not valid for
# 'qe.com.qa'". Every path below is served identically from www.
HOST = "https://www.qe.com.qa"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

# Live market-watch feeds (plain JSON, no for(;;); guard).
#
# Each has a POST endpoint and a static mirror. Prefer the POST: the static
# MarketWatch mirror is a snapshot that FREEZES mid-session. Measured on
# 2026-08-18, /wp/mw/data/MarketWatch.txt served IGRD at 4.126 / 330,768 from
# 11:07 to 13:39 while the session actually closed at 4.107 / 4,112,307 — the
# POST and the official report agreed on the latter to the digit. Index does not
# have this problem (all sources agree), but it goes through the same path for
# consistency. Neither needs cookies.
LIVE = {
    "MarketWatch": ("/wp/mw_app/mw.php", "f=MarketWatch", "/wp/mw/data/MarketWatch.txt"),
    "Index": ("/wp/mw_app/mw.php", "f=Index", "/wp/mw/data/Index.txt"),
    "Indices": ("/wp/mw_app/mw.php", "f=Indices", "/wp/mw/data/Indices.txt"),
}

# Daily trading-report files, all under /wp/trading_report_data/YYYY/MM/DD/
REPORTS = (
    "MarketSummary",
    "IndicesSummary",
    "Top5",
    "StocksSummary",
    "ETFsSummary",
    "BondsSummary",
    "GovernmentSukuksSummary",
    "CorporateBondsSummary",
    "CorporateSukukSummary",
    "TBillsSummary",
    "VentureSummary",
    "InvestorActivity",
    "OwnershipPercentage",
    "InsiderTrades",
    "MajorActivity",
)

SECTOR_INDEX_CODES = ("QBNK", "QCON", "QIND", "QINS", "QREA", "QTLC", "QTRN")
NATIONALITY = {"QTR": "Qatari", "GCC": "GCC", "ARB": "Arab", "FRN": "Foreigners"}
INVESTOR_TYPE = {"I": "Individuals", "C": "Institutions"}


def _num(value):
    """Feed numbers arrive as strings, sometimes empty, sometimes null."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class NotAvailable(Exception):
    """The endpoint returned 404 — usually a non-trading day."""


class Blocked(Exception):
    """Got a 200 that isn't data — WAF challenge or an error page."""


@dataclass
class Client:
    cache_dir: Path | None = None
    timeout: int = 30
    pause: float = 0.0  # seconds between live requests; be polite on big sweeps

    # ---------------------------------------------------------------- raw GET

    def post(self, path: str, body: str) -> bytes:
        """POST a form body. Used for the live feeds, which have no static
        equivalent that stays current — see LIVE."""
        req = urllib.request.Request(
            HOST + path,
            data=body.encode("ascii"),
            headers={
                "User-Agent": UA,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": HOST,
                "Referer": HOST + "/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def get(self, path: str, *, cacheable: bool = True) -> bytes:
        """GET a path on qe.com.qa, with an optional on-disk cache.

        Only historical files are worth caching; the caller marks live feeds
        with cacheable=False so they are always refetched.
        """
        cached = self._cache_path(path) if (cacheable and self.cache_dir) else None
        if cached and cached.exists():
            return cached.read_bytes()

        req = urllib.request.Request(
            HOST + path,
            headers={
                "User-Agent": UA,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": HOST + "/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotAvailable(path) from exc
            raise
        if self.pause:
            time.sleep(self.pause)

        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(body)
        return body

    def _cache_path(self, path: str) -> Path:
        assert self.cache_dir is not None
        return self.cache_dir / path.lstrip("/")

    def forget(self, prefix: str) -> int:
        """Drop cached files under `prefix`. Returns how many were removed.

        The watch loop calls this on today's report path so that the moment the
        exchange publishes the session, the next pass picks it up instead of
        serving a cached 404-shaped gap.
        """
        if not self.cache_dir:
            return 0
        target = self.cache_dir / prefix.lstrip("/")
        removed = 0
        if target.is_dir():
            for item in sorted(target.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink()
                    removed += 1
                else:
                    item.rmdir()
        elif target.is_file():
            target.unlink()
            removed = 1
        return removed

    # -------------------------------------------------------------- decoders

    @staticmethod
    def _as_json(body: bytes, path: str):
        text = body.decode("utf-8-sig", errors="replace").lstrip()
        # Anti-JSON-hijacking guard on /wp/trading_report_data/ responses.
        if text.startswith("for(;;);"):
            text = text[len("for(;;);") :].lstrip()
        if not text[:1] in "{[":
            raise Blocked(f"{path}: expected JSON, got {text[:120]!r}")
        return json.loads(text)

    # -------------------------------------------------------------- live feed

    def live(self, name: str) -> list[dict]:
        """MarketWatch / Index / Indices — returns the `rows` list.

        POST first, static mirror second, last-good snapshot third. The mirror is
        a real fallback rather than the primary source because it can be hours
        stale; the snapshot exists so a network blip does not fail a whole build,
        since the fundamentals in MarketWatch barely move day to day.
        """
        path, body, mirror = LIVE[name]
        snapshot = self._cache_path(mirror) if self.cache_dir else None
        payload = None
        try:
            payload = self._as_json(self.post(path, body), path)
        except (urllib.error.URLError, TimeoutError, Blocked, ValueError):
            try:
                payload = self._as_json(self.get(mirror, cacheable=False), mirror)
            except (urllib.error.URLError, TimeoutError, Blocked, ValueError):
                if snapshot and snapshot.exists():
                    payload = self._as_json(snapshot.read_bytes(), mirror)
                else:
                    raise
        rows = payload["rows"]
        if snapshot:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(json.dumps(payload).encode("utf-8"))
        return rows

    def market_watch_by_symbol(self) -> dict[str, dict]:
        return {row["Symbol"]: row for row in self.live("MarketWatch")}

    # ------------------------------------------------------- trading reports

    def report(self, name: str, period: str) -> list[dict]:
        """One trading-report file.

        `period` is either an ISO date (`2026-08-13`) or a report path segment
        (`2026/08/13`, `2026/08/W2`, `2026/07`, `2026`) — daily, weekly, monthly
        and yearly all live in the same tree. Raises NotAvailable when the
        period has not been published (non-trading day, or period still open).
        """
        if name not in REPORTS:
            raise KeyError(f"unknown report {name!r}; expected one of {REPORTS}")
        path = f"/wp/trading_report_data/{period.replace('-', '/')}/{name}.txt"
        return self._as_json(self.get(path), path)

    def try_report(self, name: str, period: str) -> list[dict] | None:
        try:
            return self.report(name, period)
        except (NotAvailable, Blocked):
            return None

    def index_value(self, period: str) -> float | None:
        """QE Index close for a period, or None if nothing was published."""
        rows = self.try_report("MarketSummary", period)
        return float(rows[0]["INDEX_VALUE"]) if rows else None

    def stock_close(self, symbol: str, period: str) -> float | None:
        rows = self.try_report("StocksSummary", period)
        if not rows:
            return None
        for row in rows:
            if row["SYMBOL_CODE"] == symbol:
                return float(row["CLOSE_PRICE"])
        return None

    # ------------------------------------------------------------ live state

    def market_state(self, symbol: str | None = None) -> dict:
        """Session state and the latest intraday numbers.

        The report files for the current session only publish after the close,
        so this is the only thing that moves during trading hours — it is what
        makes a 30-minute refresh worth doing.
        """
        try:
            index = self.live("Index")[0]
        except (urllib.error.URLError, TimeoutError, Blocked, NotAvailable):
            return {"state": None, "lastUpdate": None, "quote": None}

        state = {
            "state": index.get("State") or None,
            "lastUpdate": index.get("LastUpdate"),
            "indexValue": _num(index.get("LastPrice")),
            "changeValue": _num(index.get("Change")),
            "changePct": _num(index.get("PercentChange")),
            "volume": _num(index.get("Volume")),
            "tradedValue": _num(index.get("Value")),
            "trades": _num(index.get("Trades")),
            "ytdPct": _num(index.get("YTD")),
            "quote": None,
        }
        if symbol:
            row = self.market_watch_by_symbol().get(symbol)
            if row:
                state["quote"] = {
                    "symbol": symbol,
                    "lastPrice": _num(row.get("LastPrice")),
                    "changeValue": _num(row.get("Change")),
                    "changePct": _num(row.get("PercentChange")),
                    "volume": _num(row.get("Volume")),
                    "high": _num(row.get("High")),
                    "low": _num(row.get("Low")),
                }
        return state

    LOGO_MAX_BYTES = 80_000
    LOGO_HEIGHT = 64

    def news_feed(self, limit: int = 200) -> list[dict]:
        """Market-wide news, newest first — one POST, no page scraping.

        `POST /wp/mw_app/mw.php` with `f=News` returns ~200 items as plain JSON
        covering every listed company, about 18 months deep. This is the feed to
        use; the per-company `news()` scrape below is limited to six items and
        costs a 400 KB page render.

        Fields: InformationTypeDetailID, Headline, Summary, PublishDate,
        UpdatedDate, Image, IsBreakingNews, BreakingNewsDisplayDuration.

        Note IDs are not strictly chronological (46774 predates 46768), so sort
        on PublishDate rather than trusting the id order.
        """
        rows = self._as_json(self.post("/wp/mw_app/mw.php", "f=News"), "f=News")
        if not isinstance(rows, list):
            return []
        rows.sort(key=lambda r: r.get("PublishDate") or "", reverse=True)
        for row in rows:
            info_id = row.get("InformationTypeDetailID")
            if info_id:
                row["url"] = f"{HOST}/displaynewsdetails?InfoID={info_id}"
        return rows[:limit]

    def company_logo(self, symbol: str) -> str | None:
        """The company logo as a data URI, so the page stays self-contained.

        Some logos on the site are enormous (IGRD.jpg is 686 KB). Downscale with
        Pillow when it happens to be installed; otherwise embed only if the file
        is already small, and drop it rather than bloating the page.
        """
        try:
            body = self.get(f"/pps/companylogos/{symbol}.jpg")
        except (NotAvailable, urllib.error.URLError, TimeoutError):
            return None
        if body[:3] != b"\xff\xd8\xff":  # not a JPEG
            return None

        if len(body) > self.LOGO_MAX_BYTES:
            body = self._shrink(body) or b""
            if not body:
                return None
        return "data:image/jpeg;base64," + base64.b64encode(body).decode("ascii")

    @classmethod
    def _shrink(cls, body: bytes) -> bytes | None:
        try:
            from PIL import Image  # optional; everything else is stdlib
        except ImportError:
            return None
        import io

        with Image.open(io.BytesIO(body)) as image:
            image = image.convert("RGB")
            ratio = cls.LOGO_HEIGHT / image.height
            small = image.resize(
                (max(int(image.width * ratio), 1), cls.LOGO_HEIGHT), Image.LANCZOS
            )
            buffer = io.BytesIO()
            small.save(buffer, format="JPEG", quality=88, optimize=True)
        return buffer.getvalue()

    # ------------------------------------------------------ company profile

    def issue_information(self, symbol: str) -> dict:
        """Parse <CODE>_Issue_Information.xml into a dict."""
        path = f"/pps/dfiles/compprofile/{symbol}_Issue_Information.xml"
        root = ET.fromstring(self.get(path, cacheable=False).decode("utf-8"))
        info = root.find("./OutputMessage/Issuer_Information")
        if info is None:
            raise Blocked(f"{path}: no Issuer_Information")

        def rows(tag: str) -> list[dict]:
            return [
                {child.tag: (child.text or "").strip() for child in node}
                for node in info.findall(tag)
            ]

        weight = info.find("IndexWeight")
        index_weights = {}
        if weight is not None:
            for node in weight:
                index_weights[node.tag] = {
                    "value": (node.text or "").strip(),
                    "url": node.get("url"),
                }
        limits = info.find("Limits")
        return {
            "symbol": symbol,
            "historicalPrices": rows("HistPrice"),
            "indexWeights": index_weights,
            "limits": (
                {node.tag: (node.text or "").strip() for node in limits}
                if limits is not None
                else {}
            ),
            "majorHolders": rows("MajHolder"),
            "distributions": rows("Distribution"),
            "insiders": rows("Insiders"),
        }

    def news(self, symbol: str, information_type: str = "News") -> dict:
        """Scrape the 6 latest news items out of the company-profile HTML.

        There is no JSON API — the items are a URL-encoded XML blob inside a JS
        variable. See API_REFERENCE.md §3.

        `information_type` is sent as the site sends it, but qe.com.qa currently
        ignores it: Events / PressRelease / CorporateAction all return the same
        News items, always under a <News> tag.
        """
        path = (
            "/web/guest/company-profile?InformationCategory=Company"
            f"&InformationType={information_type}&CompanyCode={symbol}"
            "&FromLocalSite=N&MoreNewsTitle=1"
        )
        html = self.get(path, cacheable=False).decode("utf-8", errors="replace")

        marker = "request_NewsEventsOnQuoteDetailPage_responseXML = '"
        start = html.find(marker)
        if start == -1:
            raise Blocked(f"{path}: news variable not found")
        start += len(marker)
        blob = html[start : html.index("'", start)]

        outer = ET.fromstring(unquote_plus(blob))
        # ServletInnerXML usually holds real nested elements; some responses
        # deliver it as an escaped XML string instead. Handle both.
        inner = outer.find("./ServletInnerXML/OutputStructure")
        if inner is None:
            inner_text = (outer.findtext("ServletInnerXML") or "").strip()
            if not inner_text:
                return {
                    "symbol": symbol,
                    "informationType": information_type,
                    "totalRecords": None,
                    "returned": 0,
                    "items": [],
                }
            inner = ET.fromstring(inner_text)

        items = [
            {child.tag: (child.text or "").strip() for child in node}
            for node in inner.findall("./OutputMessage/News")
        ]
        for item in items:
            info_id = item.get("InformationTypeDetailID")
            if info_id:
                item["url"] = f"{HOST}/displaynewsdetails?InfoID={info_id}"
        return {
            "symbol": symbol,
            "informationType": information_type,
            "totalRecords": inner.findtext("./OutputMessage/TotalRecords"),
            "returned": len(items),
            "items": items,
        }
