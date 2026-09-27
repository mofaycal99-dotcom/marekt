"""Persist every refresh to the filesystem, shaped by what actually changes.

Three stores, because the data has three different lifetimes:

    archive/live/index/YYYY-MM-DD.jsonl  one line per 5-minute tick, market-wide
    archive/live/<SYM>/YYYY-MM-DD.jsonl  one line per tick, that symbol's quote
    archive/market/YYYY-MM-DD.jsonl       every instrument per tick (opt-in)
    archive/periods/<SYM>/<kind>/*.json   one file per closed period, write-once

The index tick is split from the symbol tick because it is symbol-independent:
tracking ten companies should not store the same QE Index reading ten times. It
also keeps deduplication a last-line comparison, which is what makes it cheap.

The live logs are the point. qe.com.qa keeps daily/weekly/monthly reports back to
2020, so a period bundle can always be rebuilt — but it publishes no intraday
history at all, so a tick that isn't captured is gone. Period bundles are stored
write-once because a closed period never changes; re-storing them every refresh
would just churn identical bytes.

Everything is plain JSON / JSONL: no database, greppable, and pandas reads a
JSONL file in one line (`pd.read_json(path, lines=True)`).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

QATAR = timezone(timedelta(hours=3))

# Fields worth keeping per instrument in the market log — the ones that move.
MARKET_FIELDS = (
    "Symbol", "LastPrice", "Change", "PercentChange", "Volume", "Value",
    "Trades", "OpenPrice", "High", "Low", "BidPrice", "OfferPrice", "StateEN",
)


def _atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
    return path


def _append_line(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _last_feed_stamp(path: Path) -> str | None:
    """The feedTime of the final line, without reading the whole file.

    The window has to expand: a market-log line carries every instrument and
    runs to ~25 KB, so a fixed small tail read lands mid-record, parses nothing,
    and silently defeats deduplication.
    """
    if not path.exists() or (size := path.stat().st_size) == 0:
        return None
    with path.open("rb") as handle:
        window = 4096
        while True:
            window = min(window, size)
            handle.seek(size - window)
            chunk = handle.read(window)
            # A complete final line needs a newline before it, unless we have
            # read the whole file.
            if b"\n" in chunk.rstrip(b"\n") or window == size:
                break
            if window >= 1 << 22:  # 4 MB: give up rather than slurp the file
                return None
            window *= 4
    for line in reversed(chunk.decode("utf-8", errors="replace").strip().splitlines()):
        try:
            return _tick_key(json.loads(line).get("feedTime") or "")
        except json.JSONDecodeError:
            continue
    return None


def _tick_key(stamp: str) -> str:
    """The dedup key for a feed timestamp: precision truncated to the minute.

    The feed publishes the same 5-minute tick with a seconds field that flips
    between :02 and :03 (`10:22:02` and `10:22:03` are one tick, not two), so
    keying on the raw string records duplicates. The raw value is still stored.
    """
    return stamp[:-3] if len(stamp) > 3 and stamp[-3] == ":" else stamp


def _session_date(live: dict) -> str:
    """Bucket by the feed's own date, so a tick never lands in the wrong day."""
    stamp = (live or {}).get("lastUpdate") or ""
    if len(stamp) >= 10 and stamp[2] == "/" and stamp[5] == "/":
        day, month, year = stamp[:2], stamp[3:5], stamp[6:10]
        return f"{year}-{month}-{day}"
    return datetime.now(QATAR).date().isoformat()


# ------------------------------------------------------------------- writers

def _stamped(live: dict) -> dict:
    return {
        "feedTime": live["lastUpdate"],
        "capturedAt": datetime.now(QATAR).isoformat(timespec="seconds"),
        "state": live.get("state"),
    }


def record_index(root: Path, live: dict) -> Path | None:
    """Append the market-wide tick: index level, volume, value, trades."""
    if not live or not live.get("lastUpdate"):
        return None
    path = root / "live" / "index" / f"{_session_date(live)}.jsonl"
    if _last_feed_stamp(path) == _tick_key(live["lastUpdate"]):
        return None
    _append_line(
        path,
        _stamped(live)
        | {
            k: live.get(k)
            for k in ("indexValue", "changeValue", "changePct", "volume",
                      "tradedValue", "trades", "ytdPct")
        },
    )
    return path


def record_quote(root: Path, symbol: str, live: dict) -> Path | None:
    """Append this symbol's tick. One file per symbol, so dedup stays exact.

    Deduplication is on the feed's own timestamp rather than the wall clock: the
    refresh interval and the feed's 5-minute cadence drift against each other, so
    polling on any schedule would otherwise record the same tick twice.
    """
    quote = live.get("quote") if live else None
    if not live or not live.get("lastUpdate") or not quote:
        return None
    path = root / "live" / symbol / f"{_session_date(live)}.jsonl"
    if _last_feed_stamp(path) == _tick_key(live["lastUpdate"]):
        return None
    _append_line(path, _stamped(live) | {k: v for k, v in quote.items() if k != "symbol"})
    return path


def record_market(root: Path, live: dict, rows: list[dict]) -> Path | None:
    """Append a full-market tick: every instrument, movement fields only.

    Opt-in — roughly 25 KB a tick, so about 1 MB a session.
    """
    if not live or not live.get("lastUpdate") or not rows:
        return None
    path = root / "market" / f"{_session_date(live)}.jsonl"
    if _last_feed_stamp(path) == _tick_key(live["lastUpdate"]):
        return None
    _append_line(
        path,
        {
            "feedTime": live["lastUpdate"],
            "capturedAt": datetime.now(QATAR).isoformat(timespec="seconds"),
            "state": live.get("state"),
            "instruments": [
                {k: row.get(k) for k in MARKET_FIELDS if row.get(k) not in (None, "")}
                for row in rows
            ],
        },
    )
    return path


def store_period(root: Path, symbol: str, tab: dict, *, force: bool = False) -> Path | None:
    """Write one closed period's figures. Skips a file that already exists."""
    period = tab["period"]
    name = period["path"].replace("/", "-")
    path = root / "periods" / symbol / period["kind"] / f"{name}.json"
    if path.exists() and not force:
        return None
    payload = dict(tab)
    payload["_archived"] = {
        "symbol": symbol,
        "capturedAt": datetime.now(QATAR).isoformat(timespec="seconds"),
    }
    return _atomic(path, json.dumps(payload, ensure_ascii=False, indent=1))


def write_manifest(root: Path) -> Path:
    """An index of what is on disk, so a consumer needs no directory walking."""
    live: dict[str, list[str]] = {}
    for path in sorted((root / "live").glob("*/*.jsonl")):
        live.setdefault(path.parent.name, []).append(path.stem)
    market = sorted(p.stem for p in (root / "market").glob("*.jsonl"))
    periods: dict[str, dict[str, list[str]]] = {}
    for path in sorted((root / "periods").glob("*/*/*.json")):
        sym, kind = path.parent.parent.name, path.parent.name
        periods.setdefault(sym, {}).setdefault(kind, []).append(path.stem)

    def _size(paths) -> int:
        return sum(p.stat().st_size for p in paths if p.exists())

    return _atomic(
        root / "manifest.json",
        json.dumps(
            {
                "updatedAt": datetime.now(QATAR).isoformat(timespec="seconds"),
                "live": live,
                "marketSessions": market,
                "periods": periods,
                "bytes": {
                    "live": _size((root / "live").glob("*/*.jsonl")),
                    "market": _size((root / "market").glob("*.jsonl")),
                    "periods": _size((root / "periods").glob("*/*/*.json")),
                },
                "layout": {
                    "live": "archive/live/{index|<SYMBOL>}/<session>.jsonl — one line per 5-min tick",
                    "market": "archive/market/<session>.jsonl — same, all instruments",
                    "periods": "archive/periods/<SYMBOL>/<kind>/<period>.json",
                },
            },
            ensure_ascii=False,
            indent=1,
        ),
    )


def record_ticks(
    out: Path,
    symbol: str,
    live: dict,
    *,
    market_rows: list[dict] | None = None,
) -> dict[str, list[str]]:
    """Write the live tick logs.

    Called *before* the intraday series is read, so the session being built is in
    its own chart. Doing it the other way round left the graph permanently one
    refresh cycle behind the header.
    """
    root = out / "archive"
    written: dict[str, list[str]] = {"index": [], "quote": [], "market": []}
    if not live:
        return written
    session = _session_date(live)
    if record_index(root, live):
        written["index"].append(session)
    if record_quote(root, symbol, live):
        written["quote"].append(f"{symbol}/{session}")
    if market_rows and record_market(root, live, market_rows):
        written["market"].append(session)
    if any(written.values()):
        write_manifest(root)
    return written


def record_periods(
    out: Path, symbol: str, periods: dict, *, force: bool = False
) -> list[str]:
    """Write each closed period's figures. Write-once unless forced."""
    root = out / "archive"
    written = []
    for tab in (periods or {}).values():
        stored = store_period(root, symbol, tab, force=force)
        if stored:
            written.append(f"{tab['period']['kind']}/{stored.stem}")
    if written:
        write_manifest(root)
    return written
