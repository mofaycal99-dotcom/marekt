"""Press coverage via Google News RSS — real articles from real outlets.

The QSE feed carries formal disclosures only: AGM notices, financial-statement
filings, index reviews. A contract win written up by Qatar Tribune never appears
there, which is why the listening tab needed a second source.

Google News RSS needs no key and no auth:

    https://news.google.com/rss/search?q=<query>&hl=en-US&gl=US&ceid=US:en

Each `<item>` gives a title, a publish date, the outlet name in `<source>`, and a
link. **The link is a Google redirect**, not the publisher's URL — Google encodes
the target in an opaque blob it changes periodically. It resolves correctly in a
browser, so it is fine to click, but do not expect to parse a domain out of it;
the outlet name comes from `<source>` instead.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

ENDPOINT = "https://news.google.com/rss/search"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
SOURCE = "Media"


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def search(query: str, *, limit: int = 40, timeout: int = 20) -> list[dict]:
    """Articles for one query, newest first. Returns [] rather than raising."""
    url = f"{ENDPOINT}?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "application/rss+xml, */*"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
        root = ET.fromstring(payload)
    except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError):
        return []

    items = []
    for node in root.iter("item"):
        title = _clean(node.findtext("title"))
        if not title:
            continue
        outlet_node = node.find("source")
        outlet = _clean(outlet_node.text if outlet_node is not None else "")
        # Google appends " - Outlet" to the title; drop the duplication.
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -(len(outlet) + 3)].strip()
        published = None
        raw_date = node.findtext("pubDate")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date).astimezone(timezone.utc)
            except (TypeError, ValueError):
                published = None
        items.append({
            "title": title,
            "url": _clean(node.findtext("link")),
            "outlet": outlet or "Unknown",
            "published": published,
            "query": query,
        })
    items.sort(key=lambda i: i["published"] or datetime.min.replace(tzinfo=timezone.utc),
               reverse=True)
    return items[:limit]


def multi(queries: dict[str, str], *, limit: int = 40) -> list[dict]:
    """Run several labelled queries and merge, de-duplicating by title.

    Wire agencies get syndicated, so the same story arrives from several outlets;
    keeping the first (newest) occurrence avoids a feed that looks padded.
    """
    seen: set[str] = set()
    merged: list[dict] = []
    for label, query in queries.items():
        for item in search(query, limit=limit):
            key = item["title"].lower()[:90]
            if key in seen:
                continue
            seen.add(key)
            merged.append(item | {"entity": label})
    merged.sort(key=lambda i: i["published"] or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True)
    return merged
