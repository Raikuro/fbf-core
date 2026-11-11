"""Test helpers for monkeypatching the runtime dataset preparation boundary."""

from __future__ import annotations

from decimal import Decimal

from fbf.core.datasets.ern import PreparedDatasetMetadata, PreparedErnDataset
from fbf.core.domain.model.dataset import Dataset


def prepared_dataset(dataset: Dataset) -> PreparedErnDataset:
    """Wrap a synthetic Dataset with plausible preparation metadata."""
    last = dataset.snapshots[-1].date
    return PreparedErnDataset(
        dataset=dataset,
        metadata=PreparedDatasetMetadata(
            historical_data_cutoff=last,
            projection_start=last,
            projection_end=last,
            historical_snapshot_count=len(dataset),
            projected_snapshot_count=0,
            snapshot_count=len(dataset),
            phase_months=120,
            equity_annual=Decimal("0.04"),
            equity_annual_after=Decimal("0.055"),
            bond_annual=Decimal("0.025"),
            bond_annual_after=Decimal("0.0225"),
            inflation_mode="zero",
            inflation_annual_rate=Decimal("0"),
            ffr_policy="last_observed_at_cutoff",
            ffr_constant_rate=None,
            legacy_mode=False,
        ),
    )
