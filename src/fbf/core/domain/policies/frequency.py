"""Withdrawal frequency enum — the single source of truth for withdrawal cadence.

``MONTHLY`` is the default and preserves existing behaviour exactly.
``ANNUAL`` produces one withdrawal event per year at the beginning of
the year (``period_index % 12 == 0``); all other months return zero
amounts.
"""

from __future__ import annotations

from enum import Enum


class WithdrawalFrequency(Enum):
    """Cadence at which a WithdrawalPolicy produces non-zero amounts.

    The simulation timeline remains monthly regardless of this setting.
    A MONTHLY policy produces 721 events for a 60-year horizon.
    An ANNUAL policy produces 61 events (T+1 convention, ``period_index % 12 == 0``).
    """

    MONTHLY = "monthly"
    ANNUAL = "annual"
