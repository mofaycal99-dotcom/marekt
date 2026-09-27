"""Reverse-engineered access to Qatar Stock Exchange (qe.com.qa) market data.

No API key, no cookies, no session tokens — see ../API_REFERENCE.md.
"""

from . import archive
from .build import build, build_period, index_series, previous_trading_day, trading_days_back
from .client import Blocked, Client, NotAvailable
from .period import KINDS, Period, resolve
from .render import render

__all__ = [
    "Blocked",
    "archive",
    "Client",
    "KINDS",
    "NotAvailable",
    "Period",
    "build",
    "build_period",
    "index_series",
    "previous_trading_day",
    "render",
    "resolve",
    "trading_days_back",
]
