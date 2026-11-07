"""Published-ERN dataset fixture with the September 2016 cutoff.

The published-ERN historical replication target uses historical returns through
September 2016 and the article's forward assumptions: equity 6.6% real p.a.;
bonds 0% for the first 120 projection months, then 2.6% real p.a.

This module builds a runtime :class:`Dataset` from the frozen fixture in
``data/ern/published_2016``.  It is test infrastructure for the published-ERN
E2E and is not production data.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fbf.core.datasets.ern import _build_ern_dataset, _load_csv
from fbf.core.domain.model.dataset import Dataset

PUBLISHED_DATA_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "ern" / "published_2016"
)

PUBLISHED_HISTORICAL_END = datetime(2016, 10, 1)
PUBLISHED_PROJECTION_END = datetime(2075, 11, 1)
PUBLISHED_EQUITY_FORWARD_ANNUAL = Decimal("0.066")
PUBLISHED_BOND_FORWARD_ANNUAL = Decimal("0")
PUBLISHED_BOND_FORWARD_ANNUAL_AFTER = Decimal("0.026")
PUBLISHED_FORWARD_PHASE_MONTHS = 120


def load_published_ern_dataset(
    data_dir: Path = PUBLISHED_DATA_DIR,
) -> Dataset:
    """Load the published-ERN dataset through the shared dataset builder."""
    equity_returns = _load_csv(data_dir / "spx_tr_real.csv")
    bond_returns = _load_csv(data_dir / "bond_10y_tr_real.csv")
    return _build_ern_dataset(
        equity_returns,
        bond_returns,
        historical_end=PUBLISHED_HISTORICAL_END,
        projection_end=PUBLISHED_PROJECTION_END,
        equity_forward_annual=PUBLISHED_EQUITY_FORWARD_ANNUAL,
        equity_forward_annual_after=PUBLISHED_EQUITY_FORWARD_ANNUAL,
        bond_forward_annual=PUBLISHED_BOND_FORWARD_ANNUAL,
        bond_forward_annual_after=PUBLISHED_BOND_FORWARD_ANNUAL_AFTER,
        forward_phase_months=PUBLISHED_FORWARD_PHASE_MONTHS,
    )
