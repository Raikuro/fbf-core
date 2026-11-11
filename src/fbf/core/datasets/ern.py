"""ERN canonical dataset loader.

Reconstructs the runtime Dataset from canonical CSV sources:

- ``spx_tr_real.csv`` — S&P 500 TR real returns (ISO date format)
- ``bond_10y_tr_real.csv`` — 10-Year Bond Market real returns (ISO date format)
- ``cpi.csv`` — CPI levels (ISO date format, used for interest-rate inflation adjustment)

Source: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns`` sheet, extracted exactly
by ``tools/ern/extract_workbook_returns.py``. The workbook is the single source
of truth for production ERN data.

The loader owns all CSV-specific details: filenames, forward-projection
rules, and derived market state (ATH, underwater).  The dataset contains
raw ERN market/index data with no fee embedding; the 0.05% p.a. ERN
portfolio fee is applied at the portfolio/study level (expense_ratio).

The ATH/underwater state is computed from the CPI-adjusted real
total-return equity index per ERN's active-glidepath methodology. The
real-return equity levels are also used for portfolio simulation returns.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, Literal

from fbf.core.domain.model.dataset import Dataset

# ---------------------------------------------------------------------------
# Canonical CSV filenames
# ---------------------------------------------------------------------------

_EQUITY_CSV = "spx_tr_real.csv"
_BOND_CSV = "bond_10y_tr_real.csv"
_CPI_CSV = "cpi.csv"
_CAPE_CSV = "cape_shiller.csv"
_FFR_CSV = "ffr.csv"

_SOURCE_FILES = (_EQUITY_CSV, _BOND_CSV, _CPI_CSV, _CAPE_CSV, _FFR_CSV)

# ---------------------------------------------------------------------------
# First data point constants (index 1, 1871-02-01)
# ---------------------------------------------------------------------------

_EQUITY_BASE = Decimal("100")
_BOND_BASE = Decimal("100")

# The dataset is fee-free; expense ratios are applied by the execution layer.
# The base snapshot level is derived from the first workbook return so the
# first interval reproduces the workbook's February 1871 return exactly.

# ---------------------------------------------------------------------------
# Forward projection constants (SWR Toolbox v2.0 workbook, Parameters B787:B790)
# ---------------------------------------------------------------------------

_EQUITY_FORWARD_ANNUAL = Decimal("0.04")  # 4.0% real p.a. for first 120 months
_EQUITY_FORWARD_ANNUAL_AFTER = Decimal("0.055")  # 5.5% real p.a. after month 120
_BOND_FORWARD_ANNUAL = Decimal("0.025")  # 2.5% real p.a. for first 120 months
_BOND_FORWARD_ANNUAL_AFTER = Decimal("0.0225")  # 2.25% real p.a. after month 120
_FORWARD_PHASE_MONTHS = 120  # 10 years = 120 months
# Historical data boundary: actual observations through 2026-06 (per SWR Toolbox v2.0 workbook).
# Projection begins at 2026-07.
_HISTORICAL_END = datetime(2026, 7, 1)  # first forward month
_PROJECTION_END = datetime(2075, 12, 1)

InflationMode = Literal["zero", "constant"]
FfrFutureMode = Literal["fail", "constant_rate", "last_observed_at_cutoff"]


@dataclass(frozen=True)
class InflationProjectionPolicy:
    """Runtime policy for inflation beyond the historical cutoff.

    CPI observations themselves remain historical-only.  ``zero`` keeps the
    cumulative inflation index flat; ``constant`` compounds the configured
    annual rate at runtime.
    """

    mode: InflationMode = "zero"
    annual_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.mode not in ("zero", "constant"):
            raise ValueError("inflation mode must be 'zero' or 'constant'")
        if self.mode == "zero" and self.annual_rate != Decimal("0"):
            raise ValueError("zero inflation mode requires annual_rate == 0")
        if self.annual_rate <= Decimal("-1"):
            raise ValueError("inflation annual_rate must be greater than -1")


@dataclass(frozen=True)
class FfrFuturePolicy:
    """Runtime policy for FFR when a study extends beyond the cutoff."""

    mode: FfrFutureMode = "last_observed_at_cutoff"
    constant_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("fail", "constant_rate", "last_observed_at_cutoff"):
            raise ValueError(
                "ffr policy mode must be 'fail', 'constant_rate', or "
                "'last_observed_at_cutoff'"
            )
        if self.mode == "constant_rate" and self.constant_rate is None:
            raise ValueError("constant_rate FFR policy requires constant_rate")
        if self.mode != "constant_rate" and self.constant_rate is not None:
            raise ValueError(
                "constant_rate is only valid with the constant_rate FFR policy"
            )


@dataclass(frozen=True)
class ProjectionConfig:
    """Historical cutoff and runtime projection assumptions for ERN data."""

    historical_data_cutoff: date | None = None
    end_date: date | None = None
    phase_months: int = _FORWARD_PHASE_MONTHS
    equity_annual: Decimal = _EQUITY_FORWARD_ANNUAL
    equity_annual_after: Decimal = _EQUITY_FORWARD_ANNUAL_AFTER
    bond_annual: Decimal = _BOND_FORWARD_ANNUAL
    bond_annual_after: Decimal = _BOND_FORWARD_ANNUAL_AFTER
    inflation: InflationProjectionPolicy = field(default_factory=InflationProjectionPolicy)
    ffr: FfrFuturePolicy = field(default_factory=FfrFuturePolicy)

    def __post_init__(self) -> None:
        if self.phase_months < 0:
            raise ValueError("projection phase_months must be non-negative")
        for name, value in (
            ("equity_annual", self.equity_annual),
            ("equity_annual_after", self.equity_annual_after),
            ("bond_annual", self.bond_annual),
            ("bond_annual_after", self.bond_annual_after),
        ):
            if value <= Decimal("-1"):
                raise ValueError(f"projection.{name} must be greater than -1")


@dataclass(frozen=True)
class PreparedDatasetMetadata:
    """Effective, auditable metadata for a runtime-prepared ERN dataset."""

    historical_data_cutoff: date
    projection_start: date
    projection_end: date
    historical_snapshot_count: int
    projected_snapshot_count: int
    snapshot_count: int
    phase_months: int
    equity_annual: Decimal
    equity_annual_after: Decimal
    bond_annual: Decimal
    bond_annual_after: Decimal
    inflation_mode: InflationMode
    inflation_annual_rate: Decimal
    ffr_policy: FfrFutureMode
    ffr_constant_rate: Decimal | None
    legacy_mode: bool
    source_sha256: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation for persistence/reporting."""
        return {
            "historical_data_cutoff": self.historical_data_cutoff.isoformat(),
            "projection_start": self.projection_start.isoformat(),
            "projection_end": self.projection_end.isoformat(),
            "historical_snapshot_count": self.historical_snapshot_count,
            "projected_snapshot_count": self.projected_snapshot_count,
            "snapshot_count": self.snapshot_count,
            "phase_months": self.phase_months,
            "equity_annual": str(self.equity_annual),
            "equity_annual_after": str(self.equity_annual_after),
            "bond_annual": str(self.bond_annual),
            "bond_annual_after": str(self.bond_annual_after),
            "inflation_mode": self.inflation_mode,
            "inflation_annual_rate": str(self.inflation_annual_rate),
            "ffr_policy": self.ffr_policy,
            "ffr_constant_rate": (
                str(self.ffr_constant_rate)
                if self.ffr_constant_rate is not None
                else None
            ),
            "legacy_mode": self.legacy_mode,
            "source_sha256": dict(self.source_sha256),
        }


@dataclass(frozen=True)
class PreparedErnDataset:
    """A runtime Dataset plus its effective preparation metadata."""

    dataset: Dataset
    metadata: PreparedDatasetMetadata


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def _load_csv(path: Path) -> list[tuple[str, Decimal]]:
    """Load a canonical date,value CSV.

    Accepts both YYYY-MM-DD and DD-MM-YYYY formats for backward
    compatibility.  Dates are normalised to ``YYYY-MM-DD`` on load.
    """
    rows: list[tuple[str, Decimal]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Accept either header format
        assert header in (
            ["date", "value"],
            ["DD-MM-YYYY", "value"],
        ), f"Unexpected header: {header}"
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                raw_date = row[0].strip()
                # Normalise DD-MM-YYYY → YYYY-MM-DD
                if len(raw_date) == 10 and raw_date[2] == "-" and raw_date[5] == "-":
                    parts = raw_date.split("-")
                    if len(parts[0]) == 2 and len(parts[2]) == 4:
                        raw_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                rows.append((raw_date, Decimal(row[1].strip())))
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _build_ern_dataset(
    equity_returns: Sequence[tuple[str, Decimal]],
    bond_returns: Sequence[tuple[str, Decimal]],
    *,
    historical_end: datetime,
    projection_end: datetime,
    equity_forward_annual: Decimal,
    equity_forward_annual_after: Decimal,
    bond_forward_annual: Decimal,
    bond_forward_annual_after: Decimal,
    forward_phase_months: int,
    cpi_levels: Mapping[str, Decimal] | None = None,
    inflation_policy: InflationProjectionPolicy | None = None,
) -> Dataset:
    """Build an ERN dataset from historical return rows and projection rules.

    The first return row must be February 1871.  The base snapshot
    (1871-01-31) is derived from that return, so the first interval reproduces
    the workbook value exactly.  Historical returns are consumed through the
    month before ``historical_end``; projection begins at ``historical_end``.
    """
    from fbf.core.domain.model.asset import AssetClass
    from fbf.core.domain.model.market_snapshot import MarketSnapshot

    if len(equity_returns) != len(bond_returns):
        raise ValueError("Equity and bond return series must have equal length")
    if not equity_returns:
        raise ValueError("At least one historical return is required")
    if equity_returns[0][0] != "1871-02-01":
        raise ValueError(
            f"First historical return must be 1871-02-01, got {equity_returns[0][0]}"
        )

    eq_return_map: dict[str, Decimal] = dict(equity_returns)
    bond_return_map: dict[str, Decimal] = dict(bond_returns)
    cpi_map: Mapping[str, Decimal] = cpi_levels or {}

    eq_asset = AssetClass(id="equity", name="", description="")
    bond_asset = AssetClass(id="bond", name="", description="")

    snapshots: list[MarketSnapshot] = []

    _ONE = Decimal("1")

    def _append(
        date_str: str,
        eq: Decimal,
        bond: Decimal,
        running_ath_val: Decimal,
        is_ath_val: bool,
        is_uw_val: bool,
        *,
        inflation_value: Decimal = Decimal("0"),
        inflation_cumulative_value: Decimal | None = None,
    ) -> None:
        cpi_value = (
            inflation_cumulative_value
            if inflation_cumulative_value is not None
            else cpi_map.get(date_str, Decimal("0"))
        )
        snapshots.append(
            MarketSnapshot(
                date=date.fromisoformat(date_str),
                inflation=inflation_value,
                inflation_cumulative=cpi_value,
                is_ath=is_ath_val,
                is_underwater=is_uw_val,
                running_ath=running_ath_val,
                index_levels={
                    eq_asset: eq,
                    bond_asset: bond,
                },
            )
        )

    # Base snapshot (index 0, 1871-01-31), implied by the first workbook return.
    with localcontext() as base_context:
        base_context.prec = 50
        equity_base_snapshot = _EQUITY_BASE / (_ONE + equity_returns[0][1])
        bond_base_snapshot = _BOND_BASE / (_ONE + bond_returns[0][1])

    _append(
        "1871-01-31",
        equity_base_snapshot,
        bond_base_snapshot,
        equity_base_snapshot,
        False,
        True,
    )

    # First data point (index 1, 1871-02-01)
    eq_level = _EQUITY_BASE
    bond_level = _BOND_BASE
    running_ath = eq_level
    _append("1871-02-01", eq_level, bond_level, running_ath, True, False)

    # Historical period (1871-03 through the month before historical_end).
    # Each snapshot interval uses the return dated the same month as the
    # workbook row (e.g. the 1871-03-01 snapshot uses the 1871-03-01 return).
    current_date = datetime(1871, 3, 1)
    while current_date < historical_end:
        date_key = current_date.strftime("%Y-%m-%d")
        try:
            r_eq = eq_return_map[date_key]
            r_bond = bond_return_map[date_key]
        except KeyError as exc:
            raise ValueError(f"Missing ERN return for {date_key}") from exc

        eq_level *= (_ONE + r_eq)
        bond_level *= (_ONE + r_bond)

        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        _append(
            date_key,
            eq_level,
            bond_level,
            running_ath,
            is_ath,
            is_underwater,
        )

        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    # Forward projection.  Use the same extended precision as the workbook
    # oracle so the two implementations agree.
    with localcontext() as _projection_context:
        _projection_context.prec = 50
        eq_monthly_forward = (
            (_ONE + equity_forward_annual) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        eq_monthly_forward_after = (
            (_ONE + equity_forward_annual_after) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        bond_monthly_forward = (
            (_ONE + bond_forward_annual) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        bond_monthly_forward_after = (
            (_ONE + bond_forward_annual_after) ** (Decimal("1") / Decimal("12")) - _ONE
        )
        effective_inflation_policy = (
            inflation_policy
            if inflation_policy is not None
            else InflationProjectionPolicy()
        )
        if effective_inflation_policy.mode == "constant":
            monthly_inflation = (
                (_ONE + effective_inflation_policy.annual_rate)
                ** (Decimal("1") / Decimal("12"))
                - _ONE
            )
        else:
            monthly_inflation = Decimal("0")

    projection_start = historical_end.date()
    last_historical_date = _add_months(projection_start, -1)
    last_historical_cpi = cpi_map.get(last_historical_date.isoformat())
    if effective_inflation_policy.mode == "constant" and last_historical_cpi is None:
        raise ValueError(
            "Cannot apply constant inflation projection: no CPI observation at "
            f"historical cutoff {last_historical_date.isoformat()}"
        )
    projected_cpi_cumulative = last_historical_cpi or Decimal("0")

    months_into_projection = 0
    while current_date <= projection_end:
        if months_into_projection < forward_phase_months:
            eq_level *= (_ONE + eq_monthly_forward)
            bond_level *= (_ONE + bond_monthly_forward)
        else:
            eq_level *= (_ONE + eq_monthly_forward_after)
            bond_level *= (_ONE + bond_monthly_forward_after)

        projected_cpi_cumulative *= (_ONE + monthly_inflation)
        running_ath = max(running_ath, eq_level)
        is_ath = eq_level >= running_ath
        is_underwater = eq_level < running_ath

        _append(
            current_date.strftime("%Y-%m-%d"),
            eq_level,
            bond_level,
            running_ath,
            is_ath,
            is_underwater,
            inflation_value=monthly_inflation,
            inflation_cumulative_value=projected_cpi_cumulative,
        )

        months_into_projection += 1
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def load_cape_rows(data_dir: Path) -> list[tuple[str, Decimal]]:
    """Load historical Shiller CAPE observations for runtime manifest use."""
    return _load_csv(data_dir / _CAPE_CSV)


def _load_historical_series(data_dir: Path) -> tuple[
    list[tuple[str, Decimal]],
    list[tuple[str, Decimal]],
    list[tuple[str, Decimal]],
]:
    equity_returns = _load_csv(data_dir / _EQUITY_CSV)
    bond_returns = _load_csv(data_dir / _BOND_CSV)
    cpi_levels = _load_csv(data_dir / _CPI_CSV)
    if not equity_returns or not bond_returns or not cpi_levels:
        raise ValueError("ERN historical source series must not be empty")
    return equity_returns, bond_returns, cpi_levels


def _default_historical_cutoff(
    equity_returns: Sequence[tuple[str, Decimal]],
    bond_returns: Sequence[tuple[str, Decimal]],
    cpi_levels: Sequence[tuple[str, Decimal]],
) -> date:
    last_dates = [
        date.fromisoformat(equity_returns[-1][0]),
        date.fromisoformat(bond_returns[-1][0]),
        date.fromisoformat(cpi_levels[-1][0]),
    ]
    return min(last_dates)


def prepare_ern_dataset(
    data_dir: Path,
    *,
    config: ProjectionConfig | None = None,
    required_through: date | None = None,
    legacy_mode: bool = False,
) -> PreparedErnDataset:
    """Prepare an in-memory ERN dataset from historical sources.

    Historical observations remain in the canonical CSVs.  The cutoff is
    inclusive, projection starts in the following month, and the projection
    end is derived from ``required_through`` when it is supplied.  An explicit
    configured end may be later than required but never earlier.
    """
    equity_returns, bond_returns, cpi_levels = _load_historical_series(data_dir)
    effective_config = config or ProjectionConfig()

    default_cutoff = _default_historical_cutoff(
        equity_returns, bond_returns, cpi_levels
    )
    cutoff = effective_config.historical_data_cutoff or default_cutoff
    if cutoff > default_cutoff:
        raise ValueError(
            f"Historical data cutoff {cutoff.isoformat()} exceeds the latest "
            f"available historical observation {default_cutoff.isoformat()}"
        )
    if cutoff < date(1871, 2, 1):
        raise ValueError(
            "Historical data cutoff must be at least 1871-02-01 "
            "(the first return month)"
        )

    equity_map = dict(equity_returns)
    bond_map = dict(bond_returns)
    cpi_map = dict(cpi_levels)
    cutoff_key = cutoff.isoformat()
    if cutoff_key not in equity_map:
        raise ValueError(f"No equity return at historical cutoff {cutoff_key}")
    if cutoff_key not in bond_map:
        raise ValueError(f"No bond return at historical cutoff {cutoff_key}")
    if cutoff_key not in cpi_map:
        raise ValueError(f"No CPI observation at historical cutoff {cutoff_key}")

    projection_start = _next_month(cutoff)
    if effective_config.end_date is not None:
        projection_end = effective_config.end_date
        if required_through is not None and projection_end < required_through:
            raise ValueError(
                "Configured projection.end_date does not cover the requested "
                f"study horizon: end={projection_end.isoformat()}, "
                f"required={required_through.isoformat()}"
            )
    else:
        default_end = _PROJECTION_END.date()
        projection_end = (
            max(default_end, required_through)
            if required_through is not None
            else default_end
        )

    if projection_end < projection_start:
        raise ValueError(
            "Projection end must not precede the first projected month "
            f"({projection_start.isoformat()})"
        )

    historical_end = datetime(
        projection_start.year, projection_start.month, projection_start.day
    )
    projection_end_dt = datetime(
        projection_end.year, projection_end.month, projection_end.day
    )
    dataset = _build_ern_dataset(
        equity_returns,
        bond_returns,
        historical_end=historical_end,
        projection_end=projection_end_dt,
        equity_forward_annual=effective_config.equity_annual,
        equity_forward_annual_after=effective_config.equity_annual_after,
        bond_forward_annual=effective_config.bond_annual,
        bond_forward_annual_after=effective_config.bond_annual_after,
        forward_phase_months=effective_config.phase_months,
        cpi_levels=cpi_map,
        inflation_policy=effective_config.inflation,
    )

    historical_snapshot_count = sum(
        1 for snapshot in dataset if snapshot.date <= cutoff
    )
    projected_snapshot_count = len(dataset) - historical_snapshot_count
    metadata = PreparedDatasetMetadata(
        historical_data_cutoff=cutoff,
        projection_start=projection_start,
        projection_end=projection_end,
        historical_snapshot_count=historical_snapshot_count,
        projected_snapshot_count=projected_snapshot_count,
        snapshot_count=len(dataset),
        phase_months=effective_config.phase_months,
        equity_annual=effective_config.equity_annual,
        equity_annual_after=effective_config.equity_annual_after,
        bond_annual=effective_config.bond_annual,
        bond_annual_after=effective_config.bond_annual_after,
        inflation_mode=effective_config.inflation.mode,
        inflation_annual_rate=effective_config.inflation.annual_rate,
        ffr_policy=effective_config.ffr.mode,
        ffr_constant_rate=effective_config.ffr.constant_rate,
        legacy_mode=legacy_mode,
        source_sha256=tuple(
            (name, _sha256(data_dir / name))
            for name in _SOURCE_FILES
            if (data_dir / name).is_file()
        ),
    )
    return PreparedErnDataset(dataset=dataset, metadata=metadata)


def load_ern_dataset(data_dir: Path) -> Dataset:
    """Load the ERN dataset using canonical runtime defaults.

    This is the compatibility loader for callers that only need a ready
    dataset.  Study planning uses :func:`prepare_ern_dataset` so the projection
    end can be derived from the study's cohort and horizon requirements.
    """
    return prepare_ern_dataset(data_dir).dataset
