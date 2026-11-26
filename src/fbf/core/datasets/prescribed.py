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

from datetime import date
from decimal import Decimal, DecimalException

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.return_sequence import ReturnSequence

__all__ = ["build_prescribed_dataset"]


def _validate_initial_level(level: object, asset_id: str) -> Decimal:
    """Validate an initial prescribed index level."""
    if not isinstance(level, Decimal):
        raise TypeError(f"Initial {asset_id} level must be a Decimal")
    if not level.is_finite():
        raise ValueError(f"Initial {asset_id} level must be finite")
    if level <= Decimal("0"):
        raise ValueError(f"Initial {asset_id} level must be strictly positive")
    return level


def _validate_generated_level(
    level: Decimal,
    asset_id: str,
    snapshot_date: date,
    return_index: int,
) -> None:
    """Validate a compounded prescribed index level."""
    location = (
        f"at {snapshot_date.isoformat()} (return index {return_index})"
    )
    if not level.is_finite():
        raise ValueError(
            f"Prescribed dataset {asset_id} level must be finite {location}"
        )
    if level <= Decimal("0"):
        raise ValueError(
            f"Prescribed dataset {asset_id} level must be strictly positive "
            f"{location}"
        )


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
        Starting index level for equity (default 100). Must be finite and
        strictly positive.
    initial_bond_level:
        Starting index level for bond (default 100). Must be finite and
        strictly positive.

    Returns
    -------
    Dataset
        Immutable dataset with 120 monthly snapshots ready for engine consumption.

    Notes
    -----
    The returned Dataset uses the same MarketSnapshot structure as the
    canonical ERN dataset, including ATH/underwater tracking derived
    from the prescribed equity trajectory.

    All generated equity and bond levels must remain finite and strictly
    positive because the execution engine consumes prices multiplicatively.
    """
    if len(seq.equity_returns) != 120 or len(seq.bond_returns) != 120:
        raise ValueError("ReturnSequence must contain exactly 120 monthly returns")

    eq_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    snapshots: list[MarketSnapshot] = []

    eq_level = _validate_initial_level(initial_equity_level, "equity")
    bond_level = _validate_initial_level(initial_bond_level, "bond")
    running_ath = eq_level

    current_date = seq.start_date

    for i in range(120):
        # Apply returns and validate the operational level path immediately.
        try:
            eq_level *= Decimal("1") + seq.equity_returns[i]
        except DecimalException as exc:
            raise ValueError(
                f"Prescribed dataset equity level must be finite "
                f"at {current_date.isoformat()} (return index {i})"
            ) from exc
        _validate_generated_level(eq_level, "equity", current_date, i)
        try:
            bond_level *= Decimal("1") + seq.bond_returns[i]
        except DecimalException as exc:
            raise ValueError(
                f"Prescribed dataset bond level must be finite "
                f"at {current_date.isoformat()} (return index {i})"
            ) from exc
        _validate_generated_level(bond_level, "bond", current_date, i)

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
