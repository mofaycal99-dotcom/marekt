"""Daily / weekly / monthly report periods.

The trading-report tree files four period types under different path shapes:

    daily    /wp/trading_report_data/YYYY/MM/DD/
    weekly   /wp/trading_report_data/YYYY/MM/W<n>/
    monthly  /wp/trading_report_data/YYYY/MM/
    yearly   /wp/trading_report_data/YYYY/

Weekly and monthly only appear once the period has *closed*, and they carry 12 of
the 15 files — no OwnershipPercentage, no InsiderTrades, no MajorActivity. Those
three are reconstructed from the daily files inside the period.

Weeks run Sunday-Thursday and are numbered within the month, but a week that
straddles a month boundary is filed under the *later* month (2026/01/W1 closes on
2025-12-31). So the week index is only a starting guess: the period end is pinned
by matching the week's INDEX_VALUE to a daily close.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .client import Client

WEEKEND = {4, 5}  # Friday, Saturday
MONTH_NAMES = (
    "January February March April May June July "
    "August September October November December"
).split()

KINDS = ("daily", "weekly", "monthly")


@dataclass(frozen=True)
class Period:
    kind: str
    path: str  # path segment under /wp/trading_report_data/
    label: str  # human label for the tab body
    tab: str  # short label for the tab strip
    end: date  # last trading day inside the period
    start: date  # first trading day inside the period
    days: tuple[str, ...] = field(default=())  # ISO trading dates inside it

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()


# ------------------------------------------------------------------ calendar

def month_weeks(year: int, month: int) -> dict[int, list[date]]:
    """Week index -> trading dates, weeks rolling on Sunday.

    The counter only advances on a Sunday once at least one trading day has been
    emitted, so a month opening on Saturday still starts at W1.
    """
    weeks: dict[int, list[date]] = {}
    index, emitted = 1, False
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        current = date(year, month, day)
        if current.weekday() == 6 and emitted:
            index += 1
        if current.weekday() in WEEKEND:
            continue
        weeks.setdefault(index, []).append(current)
        emitted = True
    return weeks


def trading_days_between(client: Client, start: date, end: date) -> list[str]:
    """Trading dates in [start, end] that actually published a daily report."""
    days, cursor = [], start
    while cursor <= end:
        if cursor.weekday() not in WEEKEND:
            iso = cursor.isoformat()
            if client.try_report("MarketSummary", iso) is not None:
                days.append(iso)
        cursor += timedelta(days=1)
    return days


def _week_of(day: date) -> tuple[date, date]:
    """The Sunday-Thursday window containing `day`."""
    sunday = day - timedelta(days=(day.weekday() + 1) % 7)
    return sunday, sunday + timedelta(days=4)


# ------------------------------------------------------------- construction

def latest_daily(client: Client, today: date | None = None) -> Period | None:
    cursor = today or date.today()
    for _ in range(30):
        if cursor.weekday() not in WEEKEND:
            iso = cursor.isoformat()
            if client.try_report("MarketSummary", iso) is not None:
                return Period(
                    kind="daily",
                    path=iso.replace("-", "/"),
                    label=f"{cursor.day} {MONTH_NAMES[cursor.month - 1]} {cursor.year}",
                    tab="Daily",
                    end=cursor,
                    start=cursor,
                    days=(iso,),
                )
        cursor -= timedelta(days=1)
    return None


def _resolve_week_end(client: Client, year: int, month: int, index: int) -> date | None:
    """Pin a week's last trading day by matching its close to a daily close."""
    summary = client.try_report("MarketSummary", f"{year}/{month:02d}/W{index}")
    if not summary:
        return None
    target = float(summary[0]["INDEX_VALUE"])

    candidates = month_weeks(year, month).get(index, [])
    search = list(reversed(candidates))
    # Straddling weeks close in the previous month, so keep walking back.
    if candidates:
        cursor = candidates[0] - timedelta(days=1)
        for _ in range(10):
            if cursor.weekday() not in WEEKEND:
                search.append(cursor)
            cursor -= timedelta(days=1)

    for day in search:
        value = client.index_value(day.isoformat())
        if value is not None and abs(value - target) < 1e-6:
            return day
    return candidates[-1] if candidates else None


def latest_weekly(client: Client, today: date | None = None) -> Period | None:
    cursor = today or date.today()
    year, month = cursor.year, cursor.month
    for _ in range(4):  # walk back up to four months
        for index in sorted(month_weeks(year, month), reverse=True):
            end = _resolve_week_end(client, year, month, index)
            if end is None:
                continue
            start, _ = _week_of(end)
            return Period(
                kind="weekly",
                path=f"{year}/{month:02d}/W{index}",
                label=_span_label(start, end),
                tab="Weekly",
                end=end,
                start=start,
                days=tuple(trading_days_between(client, start, end)),
            )
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return None


def latest_monthly(client: Client, today: date | None = None) -> Period | None:
    cursor = today or date.today()
    year, month = cursor.year, cursor.month
    for _ in range(6):
        if client.try_report("MarketSummary", f"{year}/{month:02d}") is not None:
            first = date(year, month, 1)
            last = date(year, month, calendar.monthrange(year, month)[1])
            days = trading_days_between(client, first, last)
            if days:
                return Period(
                    kind="monthly",
                    path=f"{year}/{month:02d}",
                    label=f"{MONTH_NAMES[month - 1]} {year}",
                    tab="Monthly",
                    end=date.fromisoformat(days[-1]),
                    start=date.fromisoformat(days[0]),
                    days=tuple(days),
                )
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return None


def _span_label(start: date, end: date) -> str:
    if start.month == end.month:
        return (
            f"{start.day}–{end.day} {MONTH_NAMES[end.month - 1]} {end.year}"
        )
    return (
        f"{start.day} {MONTH_NAMES[start.month - 1]} – "
        f"{end.day} {MONTH_NAMES[end.month - 1]} {end.year}"
    )


def resolve(client: Client, kind: str, today: date | None = None) -> Period | None:
    return {
        "daily": latest_daily,
        "weekly": latest_weekly,
        "monthly": latest_monthly,
    }[kind](client, today)


def previous_daily(client: Client, day: date) -> date | None:
    cursor, misses = day - timedelta(days=1), 0
    while misses < 30:
        if cursor.weekday() not in WEEKEND:
            if client.try_report("MarketSummary", cursor.isoformat()) is not None:
                return cursor
            misses += 1
        cursor -= timedelta(days=1)
    return None
