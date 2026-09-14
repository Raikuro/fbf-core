"""Canonical dataset loaders.

Provides ``load_canonical_dataset`` — the single entry point from a CSV
directory to a runtime ``Dataset``.  Each loader owns all CSV-specific
details: filenames, fee rules, forward-projection rules, and derived
market state.  The study builder does not know those details.
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
        (``sp500_tr_real_return.csv``, ``bond_10y_tr_real_return.csv``).

    Returns
    -------
    Dataset
        Immutable market observations ready for study planning and simulation.
    """
    from fbf.core.datasets.ern import load_ern_dataset

    return load_ern_dataset(data_dir)
