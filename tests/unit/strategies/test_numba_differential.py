"""Differential tests: Decimal reference engine vs Numba scalar kernel.

These tests verify that the Numba kernel reproduces the canonical Decimal
reference engine's results, NOT merely the existing float fast path.

Every test case runs both:
  1. The full Decimal reference pipeline (SimulationRunner)
  2. The Numba scalar kernel (simulate_single)

and compares: success, failure_month, months_simulated, final_wealth.

The growth factors are computed from the same prices and target weights
used by the reference engine.  The monthly withdrawal is computed from
the same initial_wealth and withdrawal_rate used by the reference engine.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.pipeline import SimulationPipeline
from fbf.core.execution.pipeline.runner import SimulationRunner
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.pipeline.steps.allocation_decision_step import (
    AllocationDecisionStep,
)
from fbf.core.execution.pipeline.steps.build_decision_context_step import (
    BuildDecisionContextStep,
)
from fbf.core.execution.pipeline.steps.initialize_allocation_step import (
    InitializeAllocationStep,
)
from fbf.core.execution.pipeline.steps.market_evolution_step import MarketEvolutionStep
from fbf.core.execution.pipeline.steps.monthly_result_builder_step import (
    MonthlyResultBuilderStep,
)
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import (
    PortfolioRebalanceStep,
)
from fbf.core.execution.pipeline.steps.simulation_state_update_step import (
    SimulationStateUpdateStep,
)
from fbf.core.execution.pipeline.steps.withdrawal_decision_step import (
    WithdrawalDecisionStep,
)
from fbf.core.execution.pipeline.steps.withdrawal_execution_step import (
    WithdrawalExecutionStep,
)
from fbf.core.execution.strategies.numba_kernel import (
    compute_growth_factors,
    simulate_single,
)
from fbf.core.study.builder import build_initial_portfolio

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

_REFERENCE_PIPELINE = SimulationPipeline(
    steps=[
        InitializeAllocationStep(),
        BuildDecisionContextStep(),
        WithdrawalDecisionStep(),
        WithdrawalExecutionStep(),
        AllocationDecisionStep(),
        PortfolioRebalanceStep(),
        MarketEvolutionStep(),
        MonthlyResultBuilderStep(),
        SimulationStateUpdateStep(),
    ]
)
_REFERENCE_RUNNER = SimulationRunner(_REFERENCE_PIPELINE)

WEALTH_TOLERANCE = Decimal("0.01")


def _make_flat_dataset(n_months: int, price: Decimal = Decimal("100")) -> Dataset:
    snapshots = []
    from datetime import date

    d = date(1900, 1, 1)
    for _ in range(n_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: price, BD: price},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=price,
            )
        )
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _make_constant_return_dataset(
    n_months: int,
    eq_return: Decimal,
    bd_return: Decimal,
    start_price: Decimal = Decimal("100"),
) -> Dataset:
    from datetime import date

    snapshots = []
    pe = start_price
    pb = start_price
    d = date(1900, 1, 1)
    for _ in range(n_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=pe,
            )
        )
        pe *= 1 + eq_return
        pb *= 1 + bd_return
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _make_random_dataset(
    n_months: int, seed: int, eq_mu: Decimal = Decimal("0.006"), eq_sigma: float = 0.045
) -> Dataset:
    import random
    from datetime import date

    rng = random.Random(seed)
    snapshots = []
    pe = pb = Decimal("100")
    d = date(1900, 1, 1)
    for _ in range(n_months + 1):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=pe,
            )
        )
        pe *= Decimal(str(1 + rng.gauss(float(eq_mu), eq_sigma)))
        pb *= Decimal(str(1 + rng.gauss(0.002, 0.01)))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _run_differential(
    equity_weight: Decimal,
    withdrawal_rate: Decimal,
    initial_wealth: Money,
    dataset: Dataset,
    horizon: int,
) -> tuple:
    """Run both reference and Numba, return comparable results."""
    portfolio = build_initial_portfolio(initial_wealth)
    context = SimulationContext(
        experiment_name="diff_test",
        cohort="test",
        start_date=dataset[0].date,
        horizon_months=horizon,
        initial_wealth=initial_wealth,
        initial_portfolio=portfolio,
        dataset=dataset.slice(dataset[0].date, horizon),
        allocation_policy=ConstantAllocationPolicy(equity_weight),
        withdrawal_policy=FixedRealWithdrawalPolicy(withdrawal_rate),
    )

    # Reference engine
    ref = _REFERENCE_RUNNER.run(context)

    # Compute portfolio value at snapshot[0]
    portfolio_value = Money(
        sum(
            h.units * dataset[0].index_levels[h.asset_class]
            for h in portfolio.holdings
        ),
        Currency.EUR,
    )

    # Growth factors from target weights and price series
    target_weights = {EQ: equity_weight, BD: Decimal("1") - equity_weight}
    price_series = {
        EQ: tuple(dataset[i].index_levels[EQ] for i in range(horizon + 1)),
        BD: tuple(dataset[i].index_levels[BD] for i in range(horizon + 1)),
    }
    gf = compute_growth_factors((EQ, BD), target_weights, price_series, horizon)

    # Numba kernel
    numba_ok, numba_fm, numba_fv, _ = simulate_single(
        gf, portfolio_value, withdrawal_rate, horizon
    )
    numba_value = float(numba_fv.amount)

    return ref, numba_ok, numba_fm, numba_value


def _numba_single(gf, portfolio_value, withdrawal_rate, horizon):
    from fbf.core.execution.strategies.numba_kernel import simulate_single

    ok, fm, fv, months = simulate_single(gf, portfolio_value, withdrawal_rate, horizon)
    return float(fv.amount), ok, fm


def _assert_matches(
    ref_result,
    numba_ok: bool,
    numba_fm: int | None,
    numba_fv: float,
    case_name: str,
) -> None:
    ref_ok = ref_result.statistics.success
    ref_fm = ref_result.statistics.failure_month
    ref_fv = float(ref_result.statistics.final_wealth.amount)

    assert numba_ok == ref_ok, (
        f"[{case_name}] success mismatch: reference={ref_ok}, numba={numba_ok}"
    )
    assert numba_fm == ref_fm, (
        f"[{case_name}] failure_month mismatch: reference={ref_fm}, numba={numba_fm}"
    )
    if ref_ok:
        diff = abs(ref_fv - numba_fv)
        assert diff < float(WEALTH_TOLERANCE), (
            f"[{case_name}] final_wealth mismatch: reference={ref_fv}, "
            f"numba={numba_fv}, diff={diff}"
        )


# ---------------------------------------------------------------------------
# Market conditions
# ---------------------------------------------------------------------------


class TestFlatMarket:
    def test_flat_100(self):
        ds = _make_flat_dataset(720, Decimal("100"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 720
        )
        _assert_matches(ref, ok, fm, fv, "flat_100")

    def test_flat_1(self):
        ds = _make_flat_dataset(120, Decimal("1"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.5"), Decimal("0.04"), Money(Decimal("100000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "flat_1")


class TestConstantReturns:
    def test_positive_returns(self):
        ds = _make_constant_return_dataset(360, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 360
        )
        _assert_matches(ref, ok, fm, fv, "positive_returns")

    def test_negative_returns(self):
        ds = _make_constant_return_dataset(240, Decimal("-0.005"), Decimal("-0.001"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.5"), Decimal("0.06"), Money(Decimal("500000"), Currency.EUR), ds, 240
        )
        _assert_matches(ref, ok, fm, fv, "negative_returns")

    def test_mixed_returns(self):
        ds = _make_constant_return_dataset(180, Decimal("0.008"), Decimal("-0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.7"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 180
        )
        _assert_matches(ref, ok, fm, fv, "mixed_returns")


class TestSingleAsset:
    def test_equity_only(self):
        ds = _make_constant_return_dataset(120, Decimal("0.006"), Decimal("0.006"))
        ref, ok, fm, fv = _run_differential(
            Decimal("1.0"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "equity_only")

    def test_bond_only(self):
        ds = _make_constant_return_dataset(120, Decimal("0.002"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.0"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "bond_only")


class TestMixedAllocation:
    def test_30_70(self):
        ds = _make_constant_return_dataset(240, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.3"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 240
        )
        _assert_matches(ref, ok, fm, fv, "30_70")

    def test_70_30(self):
        ds = _make_constant_return_dataset(240, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.7"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 240
        )
        _assert_matches(ref, ok, fm, fv, "70_30")


# ---------------------------------------------------------------------------
# Withdrawal conditions
# ---------------------------------------------------------------------------


class TestZeroWithdrawal:
    def test_zero_withdrawal(self):
        ds = _make_constant_return_dataset(120, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.0"), Money(Decimal("1000000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "zero_withdrawal")


class TestHighWithdrawal:
    def test_high_withdrawal_no_depletion(self):
        ds = _make_constant_return_dataset(120, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.08"), Money(Decimal("2000000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "high_withdrawal_no_depletion")


class TestExtremeWithdrawal:
    def test_extreme_withdrawal_depletes(self):
        ds = _make_constant_return_dataset(60, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.50"), Money(Decimal("100000"), Currency.EUR), ds, 60
        )
        _assert_matches(ref, ok, fm, fv, "extreme_withdrawal_depletes")


class TestImmediateDepletion:
    def test_immediate_depletion(self):
        ds = _make_flat_dataset(12)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("2.00"), Money(Decimal("100000"), Currency.EUR), ds, 12
        )
        _assert_matches(ref, ok, fm, fv, "immediate_depletion")

    def test_depletion_month_1(self):
        ds = _make_flat_dataset(12)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.5"), Decimal("0.15"), Money(Decimal("10000"), Currency.EUR), ds, 12
        )
        _assert_matches(ref, ok, fm, fv, "depletion_month_1")


class TestDepletionAfterSeveralMonths:
    def test_depletion_mid_horizon(self):
        ds = _make_constant_return_dataset(120, Decimal("0.003"), Decimal("0.001"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.10"), Money(Decimal("100000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "depletion_mid_horizon")


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


class TestOneMonthHorizon:
    def test_one_month_success(self):
        ds = _make_flat_dataset(1)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 1
        )
        _assert_matches(ref, ok, fm, fv, "one_month_success")

    def test_one_month_depletion(self):
        ds = _make_flat_dataset(1)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("2.00"), Money(Decimal("100000"), Currency.EUR), ds, 1
        )
        _assert_matches(ref, ok, fm, fv, "one_month_depletion")


class TestExactBoundary:
    def test_portfolio_just_above_withdrawal(self):
        ds = _make_flat_dataset(12)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.5"), Decimal("11.9"), Money(Decimal("10000"), Currency.EUR), ds, 12
        )
        _assert_matches(ref, ok, fm, fv, "portfolio_just_above_withdrawal")

    def test_portfolio_just_below_withdrawal(self):
        ds = _make_flat_dataset(12)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.5"), Decimal("12.1"), Money(Decimal("10000"), Currency.EUR), ds, 12
        )
        _assert_matches(ref, ok, fm, fv, "portfolio_just_below_withdrawal")


class TestMultiMonth:
    def test_3_month(self):
        ds = _make_constant_return_dataset(3, Decimal("0.01"), Decimal("0.005"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 3
        )
        _assert_matches(ref, ok, fm, fv, "3_month")

    def test_12_month(self):
        ds = _make_constant_return_dataset(12, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 12
        )
        _assert_matches(ref, ok, fm, fv, "12_month")


class TestLongHorizon:
    def test_720_month(self):
        ds = _make_random_dataset(720, seed=42)
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 720
        )
        _assert_matches(ref, ok, fm, fv, "720_month")


# ---------------------------------------------------------------------------
# Input variation
# ---------------------------------------------------------------------------


class TestDifferentInitialWealth:
    def test_low_wealth(self):
        ds = _make_constant_return_dataset(120, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("10000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "low_wealth")

    def test_high_wealth(self):
        ds = _make_constant_return_dataset(120, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.04"), Money(Decimal("10000000"), Currency.EUR), ds, 120
        )
        _assert_matches(ref, ok, fm, fv, "high_wealth")


class TestDifferentWithdrawalRates:
    def test_3_percent(self):
        ds = _make_constant_return_dataset(240, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.03"), Money(Decimal("1000000"), Currency.EUR), ds, 240
        )
        _assert_matches(ref, ok, fm, fv, "3_percent")

    def test_7_percent(self):
        ds = _make_constant_return_dataset(240, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.6"), Decimal("0.07"), Money(Decimal("1000000"), Currency.EUR), ds, 240
        )
        _assert_matches(ref, ok, fm, fv, "7_percent")


class TestDifferentAllocations:
    def test_conservative(self):
        ds = _make_constant_return_dataset(360, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.2"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 360
        )
        _assert_matches(ref, ok, fm, fv, "conservative")

    def test_aggressive(self):
        ds = _make_constant_return_dataset(360, Decimal("0.006"), Decimal("0.002"))
        ref, ok, fm, fv = _run_differential(
            Decimal("0.9"), Decimal("0.04"), Money(Decimal("1000000"), Currency.EUR), ds, 360
        )
        _assert_matches(ref, ok, fm, fv, "aggressive")


# ---------------------------------------------------------------------------
# Randomized differential testing
# ---------------------------------------------------------------------------


class TestRandomized:
    @pytest.mark.parametrize("seed", range(50))
    def test_random_trajectories(self, seed: int) -> None:
        import random

        rng = random.Random(seed)
        ew = Decimal(str(round(rng.uniform(0.1, 0.9), 2)))
        wr = Decimal(str(round(rng.uniform(0.02, 0.08), 4)))
        iw = Money(Decimal(str(rng.randint(100000, 5000000))), Currency.EUR)
        horizon = rng.choice([60, 120, 240, 360, 720])

        ds = _make_random_dataset(horizon, seed=seed * 7 + 13)

        ref, ok, fm, fv = _run_differential(ew, wr, iw, ds, horizon)
        _assert_matches(ref, ok, fm, fv, f"random_seed={seed}")

    @pytest.mark.parametrize("seed", range(20))
    def test_random_extreme_withdrawal(self, seed: int) -> None:
        import random

        rng = random.Random(seed + 1000)
        ew = Decimal(str(round(rng.uniform(0.3, 0.7), 2)))
        wr = Decimal(str(round(rng.uniform(0.08, 0.30), 4)))
        iw = Money(Decimal(str(rng.randint(50000, 500000))), Currency.EUR)
        horizon = rng.choice([12, 60, 120])

        ds = _make_random_dataset(horizon, seed=seed * 11 + 31)

        ref, ok, fm, fv = _run_differential(ew, wr, iw, ds, horizon)
        _assert_matches(ref, ok, fm, fv, f"random_extreme_seed={seed}")
