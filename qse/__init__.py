"""Reverse-engineered access to Qatar Stock Exchange (qe.com.qa) market data.

No API key, no cookies, no session tokens — see ../API_REFERENCE.md.
"""

# CAUTION. `build` and `render` are both a submodule and a function in here, and
# which one `qse.build` resolves to depends on when the import system sets the
# parent package's attribute — it differs between Python versions, and on 3.14 the
# module wins where on 3.13 the function did. The deployed app failed with
# "'module' object is not callable" for exactly this reason.
#
# These re-exports are kept for compatibility, but nothing should rely on them:
# import the function from its own module, `from qse.build import build`.

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
