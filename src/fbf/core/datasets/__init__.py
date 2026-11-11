"""Dataset loaders and builders.

Provides:
- ``load_canonical_dataset`` — the single entry point from a CSV directory
  to a runtime ``Dataset``.
- ``build_prescribed_dataset`` — builds a Dataset from a prescribed
  deterministic ReturnSequence for research/experiment use.

Canonical production source: ``SWR_Toolbox_v2.0.xlsx``, ``Asset Returns``
sheet, extracted exactly by ``tools/ern/extract_workbook_returns.py``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.datasets.ern import (
    PreparedErnDataset,
    ProjectionConfig,
    prepare_ern_dataset,
)
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.return_sequence import ReturnSequence


def load_canonical_dataset(
    data_dir: Path,
    *,
    config: ProjectionConfig | None = None,
    required_through: date | None = None,
    legacy_mode: bool = False,
) -> Dataset:
    """Load the standard ERN dataset from canonical CSV sources.

    Parameters
    ----------
    data_dir:
        Directory containing the canonical CSV files
        (``spx_tr_real.csv``, ``bond_10y_tr_real.csv``, ``cpi.csv``).
    config:
        Optional historical cutoff and runtime projection rules.  When omitted,
        canonical runtime defaults are used.
    required_through:
        Latest snapshot date required by a study.  When supplied and no
        explicit projection end is configured, the projection is extended to
        cover it.
    legacy_mode:
        Record and use the explicitly selected legacy compatibility path.

    Returns
    -------
    Dataset
        Immutable market observations ready for study planning and simulation.
    """
    return prepare_ern_dataset(
        data_dir,
        config=config,
        required_through=required_through,
        legacy_mode=legacy_mode,
    ).dataset


def build_prescribed_dataset(
    seq: ReturnSequence,
    initial_equity_level: Decimal = Decimal("100"),
    initial_bond_level: Decimal = Decimal("100"),
) -> Dataset:
    """Build a Dataset from prescribed monthly returns.

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
    """
    from fbf.core.datasets.prescribed import build_prescribed_dataset as _build

    return _build(seq, initial_equity_level, initial_bond_level)


__all__ = [
    "load_canonical_dataset",
    "prepare_ern_dataset",
    "build_prescribed_dataset",
    "ProjectionConfig",
    "PreparedErnDataset",
]
