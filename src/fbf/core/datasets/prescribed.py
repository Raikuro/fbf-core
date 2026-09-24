"""Prescribed dataset builder for deterministic return sequences.

This module provides the `build_prescribed_dataset()` function that adapts
a domain-layer `ReturnSequence` into the existing `Dataset` model consumed
by the simulation engine.

Dependency direction: this module imports `ReturnSequence` and `Dataset`.
No reverse dependency from domain to this module.

The prescribed Experiment E source data is annual, but the existing
simulation engine consumes monthly returns. The adapter expands each
annual return into 12 equal compounded monthly returns using the
documented assumption:

    monthly_return = (1 + annual_return) ** (1/12) - 1

IMPORTANT: This monthly series is an implementation adapter — it is NOT
claimed to be an article-published monthly series. Each 12-month block
compounds exactly to its source annual return.

Bull→Bear reversal occurs at the ANNUAL sequence level BEFORE monthly
expansion (handled by `ReturnSequence.reverse()`).
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.return_sequence import ReturnSequence

__all__ = ["build_prescribed_dataset"]


def build_prescribed_dataset(
    seq: ReturnSequence,
    initial_equity_level: Decimal = Decimal("100"),
    initial_bond_level: Decimal = Decimal("100"),
) -> Dataset:
    """Build a Dataset from prescribed monthly returns.

    Compounds index levels from prescribed monthly returns.
    Computes ATH/underwater state from equity trajectory.

    Parameters
    ----------
    seq:
        ReturnSequence containing 120 monthly equity and bond returns.
    initial_equity_level:
        Starting index level for equity (default 100).
    initial_bond_level:
        Starting index level for bond (default 100).

    Returns
    -------
    Dataset
        Immutable dataset with 120 monthly snapshots ready for engine consumption.

    Notes
    -----
    The returned Dataset uses the same MarketSnapshot structure as the
    canonical ERN dataset, including ATH/underwater tracking derived
    from the prescribed equity trajectory.
    """
    if len(seq.equity_returns) != 120 or len(seq.bond_returns) != 120:
        raise ValueError("ReturnSequence must contain exactly 120 monthly returns")

    eq_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    snapshots: list[MarketSnapshot] = []

    eq_level = initial_equity_level
    bond_level = initial_bond_level
    running_ath = eq_level

    current_date = seq.start_date

    for i in range(120):
        # Apply returns
        eq_level *= Decimal("1") + seq.equity_returns[i]
        bond_level *= Decimal("1") + seq.bond_returns[i]

        # Track ATH/underwater from equity trajectory
        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        snapshots.append(
            MarketSnapshot(
                date=current_date,
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=is_ath,
                is_underwater=is_underwater,
                running_ath=running_ath,
                index_levels={
                    eq_asset: eq_level,
                    bond_asset: bond_level,
                },
            )
        )

        # Advance to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")
