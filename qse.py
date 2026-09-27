#!/usr/bin/env python3
"""Qatar Stock Exchange data CLI — stdlib only, no dependencies.

  ./qse.py dashboard IGRD --open        Daily/Weekly/Monthly dashboard, JSON + HTML
  ./qse.py watch IGRD --open            same, rebuilt every 30 minutes
  ./qse.py raw IGRD                     dump every feed verbatim
  ./qse.py render out/dashboard_IGRD.json
  ./qse.py series --from 2026-01-01     QE Index daily closes

Outputs land in ./out unless --out says otherwise. Historical report files are
cached under ./out/.cache, so re-runs are cheap and mostly offline.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError

from qse import Client, NotAvailable, build, index_series, render
from qse import archive as archive_mod
from qse.fetch import fetch_company, fetch_live, fetch_period
from qse.period import KINDS, resolve

ROOT = Path(__file__).resolve().parent
QATAR = timezone(timedelta(hours=3))


def _client(args) -> Client:
    cache = None if args.no_cache else Path(args.out) / ".cache"
    return Client(cache_dir=cache, pause=args.pause)


def _write_atomic(path: Path, text: str) -> Path:
    """Write via a temp file + rename.

    The page reloads itself from this exact path on the same cadence the watch
    loop rewrites it, so a plain write_text() (truncate, then write) leaves a
    window where the browser can read a half-written file. os.replace is atomic
    on the same filesystem, so a reader sees either the old page or the new one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
    return path


def _save_json(path: Path, payload) -> Path:
    return _write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=1))


def _now() -> str:
    return datetime.now(QATAR).strftime("%H:%M:%S")


def _build_once(args, client: Client) -> tuple[Path, dict]:
    """Build the bundle and write both files. Returns (html path, bundle)."""
    kinds = tuple(k for k in KINDS if k in args.periods)
    as_of = date.fromisoformat(args.date) if args.date else None
    out = Path(args.out)
    bundle = build(
        client,
        args.symbol,
        kinds=kinds,
        weeks=args.weeks,
        refresh_seconds=args.refresh,
        today=as_of,
        history_days=args.history_days,
        out=out,
        archive_ticks=not args.no_archive,
        archive_market=args.archive_market,
    )
    stem = f"dashboard_{args.symbol}" + (f"_{args.date}" if args.date else "")
    _save_json(out / f"{stem}.json", bundle)
    html_path = _write_atomic(out / f"{stem}.html", render(bundle))

    if not args.no_archive:
        # Ticks were written inside build(); only the periods are left.
        stored = dict(bundle["meta"].get("archived") or {})
        stored["periods"] = archive_mod.record_periods(
            out, args.symbol, bundle["periods"], force=args.archive_force
        )
        summary = ", ".join(f"{k} {len(v)}" for k, v in stored.items() if v)
        print(f"  archive  {summary or 'nothing new (tick already captured)'}")

    live = bundle.get("live") or {}
    for kind, tab in bundle["periods"].items():
        s = tab["share"]
        print(
            f"  {kind:<8} {tab['period']['label']:<26} "
            f"close {s['close']} ({s['changePct']:+.3f}%)  vol {s['volume']:,}"
        )
    for kind, reason in (bundle["meta"].get("unavailable") or {}).items():
        print(f"  {kind:<8} unavailable — {reason}")
    if live.get("state"):
        print(f"  market   {live['state']} · feed {live.get('lastUpdate')}")
    return html_path, bundle


def cmd_dashboard(args) -> None:
    client = _client(args)
    print(f"[{_now()}] building {args.symbol} …")
    try:
        html_path, _ = _build_once(args, client)
    except NotAvailable as exc:
        sys.exit(f"no data: {exc}")
    print(f"  -> {html_path}")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())


def cmd_watch(args) -> None:
    """Rebuild on an interval. The page reloads itself on the same cadence."""
    client = _client(args)
    interval = max(args.refresh, 60)
    stop = {"now": False}

    def _handle(_signum, _frame):
        stop["now"] = True
        print(f"\n[{_now()}] stopping.")

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    if getattr(args, "date", None):
        sys.exit("watch follows the live market; drop --date or use `dashboard` instead")
    print(
        f"[{_now()}] watching {args.symbol}, rebuilding every {interval // 60} min. "
        "Ctrl-C to stop."
    )
    first = True
    while not stop["now"]:
        started = time.monotonic()
        try:
            print(f"[{_now()}] rebuild")
            html_path, _ = _build_once(args, client)
            # Only historical files are cached; drop it so the next pass re-reads
            # today's report the moment the exchange publishes it.
            client.forget(f"/wp/trading_report_data/{date.today().isoformat().replace('-', '/')}")
            if first and args.open:
                webbrowser.open(html_path.resolve().as_uri())
                first = False
        except (URLError, TimeoutError) as exc:
            print(f"[{_now()}] network error, will retry: {exc}")
        except NotAvailable as exc:
            print(f"[{_now()}] no data: {exc}")

        remaining = interval - (time.monotonic() - started)
        while remaining > 0 and not stop["now"]:
            time.sleep(min(remaining, 1.0))
            remaining -= 1.0


def cmd_raw(args) -> None:
    client = _client(args)
    out = Path(args.out) / "raw"
    written = fetch_live(client, out)
    for kind in args.periods:
        period = resolve(client, kind)
        if period is None:
            print(f"  ! {kind}: nothing published yet")
            continue
        print(f"dumping {kind} {period.path} …")
        written += fetch_period(client, period, out)
    if args.symbol:
        written += fetch_company(client, args.symbol, out)
    for path in written:
        print(f"  {path}")
    print(f"{len(written)} files")


def cmd_archive(args) -> None:
    manifest = Path(args.out) / "archive" / "manifest.json"
    if not manifest.exists():
        sys.exit(f"no archive yet at {manifest.parent}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    print(f"archive at {manifest.parent}  (updated {data['updatedAt']})")
    for store, size in data["bytes"].items():
        shown = f"{size:,} B" if size < 1024 else f"{size / 1024:,.1f} KB"
        print(f"  {store:<8} {shown:>12}")
    root = manifest.parent
    for stream, sessions in sorted(data["live"].items()):
        for session in sessions:
            path = root / "live" / stream / f"{session}.jsonl"
            ticks = sum(1 for _ in path.open(encoding="utf-8"))
            print(f"  live     {stream:<8} {session}  {ticks} ticks")
    for symbol, kinds in data["periods"].items():
        for kind, names in kinds.items():
            print(f"  period   {symbol} {kind:<8} {len(names):>3} stored  "
                  f"({names[0]} … {names[-1]})")


def cmd_render(args) -> None:
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    target = Path(args.output) if args.output else Path(args.bundle).with_suffix(".html")
    _write_atomic(target, render(bundle))
    print(target)
    if args.open:
        webbrowser.open(target.resolve().as_uri())


def cmd_series(args) -> None:
    client = _client(args)
    end = date.fromisoformat(args.to) if args.to else date.today()
    start = date.fromisoformat(getattr(args, "from"))
    weeks = max(int((end - start).days / 7) + 1, 1)
    series = [p for p in index_series(client, end, weeks) if p["date"] >= start.isoformat()]
    path = _save_json(Path(args.out) / f"qe_index_{start}_{end}.json", series)
    print(f"{len(series)} sessions -> {path}")


def _periods(value: str) -> list[str]:
    if value == "all":
        return list(KINDS)
    chosen = [p.strip() for p in value.split(",") if p.strip()]
    unknown = [p for p in chosen if p not in KINDS]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown period(s): {', '.join(unknown)}")
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default=str(ROOT / "out"), help="output dir (default ./out)")
    parser.add_argument("--no-cache", action="store_true", help="always refetch")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between requests")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_build_args(p):
        p.add_argument("symbol")
        p.add_argument(
            "--periods",
            type=_periods,
            default=list(KINDS),
            help="all (default), or a comma list of daily,weekly,monthly",
        )
        p.add_argument(
            "--date",
            help="as-of date YYYY-MM-DD (default today); daily pins to it, "
            "weekly/monthly resolve to the latest period closed on or before it",
        )
        p.add_argument("--weeks", type=int, default=52, help="index range lookback")
        p.add_argument(
            "--history-days",
            type=int,
            default=180,
            help="calendar days of daily close/volume for the share graph (0 disables)",
        )
        p.add_argument(
            "--refresh",
            type=int,
            default=1800,
            help="page self-refresh in seconds (0 disables); also the watch interval",
        )
        p.add_argument("--open", action="store_true", help="open the HTML when done")
        p.add_argument(
            "--no-archive",
            action="store_true",
            help="skip writing to out/archive (archiving is on by default)",
        )
        p.add_argument(
            "--archive-market",
            action="store_true",
            help="also log every instrument each tick (~1 MB per session)",
        )
        p.add_argument(
            "--archive-force",
            action="store_true",
            help="rewrite period bundles that are already archived",
        )

    p = sub.add_parser("dashboard", help="build the bundle and the tabbed HTML once")
    add_build_args(p)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("watch", help="rebuild on an interval (default every 30 min)")
    add_build_args(p)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("raw", help="dump every feed verbatim as JSON")
    p.add_argument("symbol", nargs="?", help="also dump this company's profile and news")
    p.add_argument("--periods", type=_periods, default=list(KINDS))
    p.set_defaults(func=cmd_raw)

    p = sub.add_parser("archive", help="show what the archive holds")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("render", help="re-render an existing bundle")
    p.add_argument("bundle")
    p.add_argument("-o", "--output")
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("series", help="QE Index daily closes over a range")
    p.add_argument("--from", required=True, dest="from")
    p.add_argument("--to")
    p.set_defaults(func=cmd_series)

    args = parser.parse_args()
    try:
        args.func(args)
    except URLError as exc:
        sys.exit(f"network error reaching qe.com.qa: {exc.reason}")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
