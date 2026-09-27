"""Dump the raw QSE feeds to disk as JSON, unmodified.

The point of keeping a raw layer is that build.py's derivations can be re-run
and argued with later without re-hitting the site.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .client import LIVE, REPORTS, Blocked, Client, NotAvailable


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def fetch_live(client: Client, out: Path) -> list[Path]:
    written = []
    for name in LIVE:
        written.append(_write(out / "live" / f"{name}.json", client.live(name)))
    return written


def fetch_period(client: Client, period, out: Path) -> list[Path]:
    """Every report file published for one period. Skips what 404s.

    Daily periods carry all 15 files; weekly and monthly carry 12 — no
    OwnershipPercentage, InsiderTrades or MajorActivity.
    """
    written = []
    folder = out / "reports" / period.kind / period.path.replace("/", "-")
    for name in REPORTS:
        rows = client.try_report(name, period.path)
        if rows is None:
            continue
        written.append(_write(folder / f"{name}.json", rows))
    written.append(
        _write(
            folder / "_period.json",
            {
                "kind": period.kind,
                "path": period.path,
                "label": period.label,
                "start": period.start.isoformat(),
                "end": period.end_iso,
                "tradingDays": list(period.days),
            },
        )
    )
    return written


def fetch_company(client: Client, symbol: str, out: Path) -> list[Path]:
    written = []
    base = out / "company" / symbol
    try:
        written.append(_write(base / "issue_information.json", client.issue_information(symbol)))
    except (NotAvailable, Blocked, ET.ParseError) as exc:
        print(f"  ! issue_information {symbol}: {exc}")
    # Only News is worth fetching — the InformationType param is ignored, so the
    # other three types come back identical.
    try:
        payload = client.news(symbol)
    except (NotAvailable, Blocked, ET.ParseError) as exc:
        print(f"  ! news {symbol}: {exc}")
    else:
        if payload["items"]:
            written.append(_write(base / "news.json", payload))
    return written
