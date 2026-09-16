"""Canonical dataset loaders.

Provides ``load_canonical_dataset`` — the single entry point from a CSV
directory to a runtime ``Dataset``.  Each loader owns all CSV-specific
details: filenames, fee rules, forward-projection rules, and derived
market state.  The study builder does not know those details.

Canonical source: ERN SWR Toolbox Google Sheet, Asset Returns tab.
  https://docs.google.com/spreadsheets/d/1QGrMm6XSGWBVLI8I_DOAeJV5whoCnSdmaR8toQB2Jz8
"""

from __future__ import annotations

from pathlib import Path

from fbf.core.domain.model.dataset import Dataset


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
