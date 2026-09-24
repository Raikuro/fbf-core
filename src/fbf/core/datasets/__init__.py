"""Dataset loaders and builders.

Provides:
- ``load_canonical_dataset`` — the single entry point from a CSV directory
  to a runtime ``Dataset``.
- ``build_prescribed_dataset`` — builds a Dataset from a prescribed
  deterministic ReturnSequence for research/experiment use.

Canonical source: ERN SWR Toolbox Google Sheet, Asset Returns tab.
  https://docs.google.com/spreadsheets/d/1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.return_sequence import ReturnSequence


def load_canonical_dataset(data_dir: Path) -> Dataset:
    """Load the standard ERN dataset from canonical CSV sources.

    Parameters
    ----------
    data_dir:
        Directory containing the canonical CSV files
        (``spx_tr_real.csv``, ``bond_10y_tr_real.csv``).

    Returns
    -------
    Dataset
        Immutable market observations ready for study planning and simulation.
    """
    from fbf.core.datasets.ern import load_ern_dataset

    return load_ern_dataset(data_dir)


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


__all__ = ["load_canonical_dataset", "build_prescribed_dataset"]
