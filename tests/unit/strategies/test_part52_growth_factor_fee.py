"""Focused validation of the additive fee convention used by the Part 52 executor.

``Part52NumbaExecutor`` derives its growth factors by delegating to
``_compute_growth_factors_numpy`` and passing the context's ``expense_ratio`` as
``fee_annual`` (see ``part52_numba_executor.py``).  The documented convention is
additive: ``g_m = Σ_j w_j · P_{j,m}/P_{j,m-1} − fee/12``, not multiplicative
(``g_m · (1 − fee/12)``).  These tests derive the expected values by hand rather
than executing the kernel, so they independently pin the convention.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np

from fbf.core.execution.strategies.numba_kernel import _compute_growth_factors_numpy


def _equity_bond_prices() -> np.ndarray:
    """Two-asset prices: equity +5%/month, bond +1%/month."""
    return np.array(
        [
            [100.0, 105.0, 110.25],
            [100.0, 101.0, 102.01],
        ],
        dtype=np.float64,
    )


class TestPart52AdditiveFeeGrowthFactors:
    """The Part 52 growth factors subtract ``fee/12`` additively."""

    def test_fee_is_subtracted_monthly_additively(self) -> None:
        weights = np.array([0.75, 0.25], dtype=np.float64)
        fee_annual = float(Decimal("0.006"))

        gfs = _compute_growth_factors_numpy(
            weights, _equity_bond_prices(), horizon=2, fee_annual=fee_annual
        )

        weighted_return = 0.75 * 1.05 + 0.25 * 1.01
        expected = weighted_return - fee_annual / 12.0
        np.testing.assert_allclose(
            gfs, np.array([expected, expected]), rtol=0.0, atol=1e-12
        )

    def test_zero_fee_leaves_weighted_return(self) -> None:
        weights = np.array([0.75, 0.25], dtype=np.float64)

        gfs = _compute_growth_factors_numpy(
            weights, _equity_bond_prices(), horizon=2, fee_annual=0.0
        )

        expected = 0.75 * 1.05 + 0.25 * 1.01
        np.testing.assert_allclose(
            gfs, np.array([expected, expected]), rtol=0.0, atol=1e-12
        )
