"""Differential validation: Numba executor vs Workbook Oracle.

Verifies that the NumbaSimulationExecutor produces results matching the
workbook SCR methodology for identical inputs through the real execution
architecture. The workbook oracle implements the exact formulas from
SWR_Toolbox_v2.0.xlsx for static allocations (ConstantAllocationPolicy +
FixedRealWithdrawalPolicy, FV=0).
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution.pipeline.executor import SimulationExecutor
from fbf.core.execution.pipeline.simulation import (
    ExperimentDefinition as EngineExperimentDefinition,
    SimulationResult,
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import (
    _index_series,
    _weights_by_class,
    evaluate_closed_form,
)
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.study.builder import build_initial_portfolio
from tests.unit.strategies.workbook_oracle_test_helper import (
    WorkbookOracleResult,
    compute_workbook_oracle_result,
    make_workbook_test_context,
)

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_NUMBA_EXECUTOR: SimulationExecutor = NumbaSimulationExecutor()

WEALTH_TOLERANCE = Decimal("0.01")


def _legacy_identity(w: Decimal) -> tuple[tuple[str, Decimal], ...]:
    """Canonical allocation identity for a legacy two-asset (equity, bond) split."""
    return (("bond", Decimal("1") - w), ("equity", w))


# --- Legacy helpers for cache tests (use horizon snapshots, not horizon+1) ---

def _make_dataset(n_months: int) -> Dataset:
    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: pe, _BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1.006")
        pb *= Decimal("1.002")
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly")


def _make_dataset_with_returns(
    n_months: int,
    eq_return: Decimal,
    bd_return: Decimal,
) -> Dataset:
    """Dataset with configurable constant monthly equity/bond returns."""
    pe = pb = Decimal("100")
    snapshots = []
    d = date(1900, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={_EQ: pe, _BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal("1") + eq_return
        pb *= Decimal("1") + bd_return
        d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly")


def _make_context(
    dataset: Dataset,
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
) -> SimulationContext:
    start = dataset[0].date
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR), dataset)
    return SimulationContext(
        experiment_name="test",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset.slice(start, horizon),
        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
    )


def _make_context_on_dataset(
    dataset: Dataset,
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
) -> SimulationContext:
    """Like ``_make_context`` but uses *dataset* directly, without slicing.

    Production reuses a single sliced ``Dataset`` object across every context
    that shares its ``(start_date, horizon)`` (see
    ``materialize_research_plan``), so cache-reuse tests must do the same:
    ``_make_context`` slices on every call and would mint a distinct dataset
    object per context.
    """
    start = dataset[0].date
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR), dataset)
    return SimulationContext(
        experiment_name="test",
        cohort=str(start),
        start_date=start,
        horizon_months=horizon,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        initial_portfolio=portfolio,
        dataset=dataset,
        allocation_policy=ConstantAllocationPolicy(Decimal(str(w))),
        withdrawal_policy=FixedRealWithdrawalPolicy(Decimal(str(r))),
    )


# --- Workbook oracle helpers ---

def _make_context_workbook(
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
) -> SimulationContext:
    """Create a context with horizon+1 snapshots for workbook validation."""
    return make_workbook_test_context(horizon, w, r)


def _run_numba(
    contexts: list[SimulationContext],
) -> list[tuple[bool, int | None, Decimal, int]]:
    definition = EngineExperimentDefinition(
        name="test",
        description="test",
        simulation_contexts=tuple(contexts),
    )
    numba_run = _NUMBA_EXECUTOR.execute(definition)

    results = []
    for r in numba_run.simulation_results:
        s = r.statistics
        results.append((
            s.success,
            s.failure_month,
            s.final_wealth.amount,
            s.months_simulated,
        ))
    return results


def _assert_matches_workbook(
    oracle: WorkbookOracleResult,
    numba: tuple[bool, int | None, Decimal, int],
    label: str,
) -> None:
    numba_ok, numba_fm, numba_fv, numba_months = numba

    assert numba_ok == oracle.success, (
        f"{label}: success mismatch ({numba_ok} vs {oracle.success})"
    )
    assert numba_fm == oracle.failure_month, (
        f"{label}: failure_month mismatch ({numba_fm} vs {oracle.failure_month})"
    )
    assert numba_months == oracle.months_simulated, (
        f"{label}: months_simulated mismatch ({numba_months} vs {oracle.months_simulated})"
    )
    if oracle.success:
        diff = abs(oracle.final_wealth - numba_fv)
        assert diff < WEALTH_TOLERANCE, (
            f"{label}: final_wealth diff {diff} exceeds tolerance {WEALTH_TOLERANCE} "
            f"(oracle={oracle.final_wealth}, numba={numba_fv})"
        )


class TestNumbaExecutorVsWorkbookOracle:
    """Test Numba executor against workbook oracle for static allocations."""

    def test_flat_market_single_context(self) -> None:
        ctx = _make_context_workbook(horizon=720, w=0.5, r=0.04)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        assert len(numba) == 1
        _assert_matches_workbook(oracle, numba[0], "flat_720m")

    def test_flat_market_multiple_horizons(self) -> None:
        contexts = [_make_context_workbook(horizon=h, w=0.6, r=0.03) for h in [12, 60, 360, 720]]
        numba = _run_numba(contexts)
        assert len(numba) == 4
        for i, h in enumerate([12, 60, 360, 720]):
            ctx = contexts[i]
            oracle = compute_workbook_oracle_result(ctx)
            _assert_matches_workbook(oracle, numba[i], f"multi_horizon_{h}m")

    def test_equity_only(self) -> None:
        ctx = _make_context_workbook(horizon=240, w=1.0, r=0.04)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "equity_only_240m")

    def test_bond_only(self) -> None:
        ctx = _make_context_workbook(horizon=240, w=0.0, r=0.02)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "bond_only_240m")

    def test_high_withdrawal_depletes(self) -> None:
        ctx = _make_context_workbook(horizon=120, w=0.5, r=0.20)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "high_withdrawal_depletes")

    def test_zero_withdrawal(self) -> None:
        ctx = _make_context_workbook(horizon=240, w=0.7, r=0.0)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "zero_withdrawal")

    def test_different_allocations(self) -> None:
        for w in [0.0, 0.25, 0.5, 0.75, 1.0]:
            ctx = _make_context_workbook(horizon=360, w=w, r=0.04)
            oracle = compute_workbook_oracle_result(ctx)
            numba = _run_numba([ctx])
            _assert_matches_workbook(oracle, numba[0], f"alloc_{w}")

    def test_different_rates(self) -> None:
        for r in [0.0, 0.02, 0.03, 0.04, 0.05, 0.08]:
            ctx = _make_context_workbook(horizon=360, w=0.6, r=r)
            oracle = compute_workbook_oracle_result(ctx)
            numba = _run_numba([ctx])
            _assert_matches_workbook(oracle, numba[0], f"rate_{r}")

    def test_grouping_derives_shorter_horizons(self) -> None:
        contexts = [
            _make_context_workbook(horizon=720, w=0.5, r=0.04),
            _make_context_workbook(horizon=360, w=0.5, r=0.04),
        ]
        numba = _run_numba(contexts)
        assert len(numba) == 2
        for i, h in enumerate([720, 360]):
            ctx = contexts[i]
            oracle = compute_workbook_oracle_result(ctx)
            _assert_matches_workbook(oracle, numba[i], f"group_{h}m")

    def test_ineligible_context_falls_back(self) -> None:
        from fbf.core.domain.policies import ConstantWithdrawalPolicy

        ds = _make_context_workbook(horizon=240, w=0.5, r=0.04).dataset
        start = ds[0].date
        eligible = _make_context_workbook(horizon=240, w=0.5, r=0.04)
        _ = SimulationContext(
            experiment_name="test",
            cohort="ineligible",
            start_date=start,
            horizon_months=240,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=eligible.initial_portfolio,
            dataset=ds,
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=ConstantWithdrawalPolicy(Decimal("40000")),
        )
        # Only test the eligible one against workbook oracle
        oracle = compute_workbook_oracle_result(eligible)
        numba = _run_numba([eligible])
        _assert_matches_workbook(oracle, numba[0], "eligible_in_mixed")


class TestNumbaExecutorRandomizedVsWorkbook:
    @pytest.mark.parametrize("seed", range(30))
    def test_random_trajectories(self, seed: int) -> None:
        rng = random.Random(seed)
        ew = rng.uniform(0.0, 1.0)
        wr = rng.uniform(0.0, 0.10)
        horizon = rng.choice([12, 60, 120, 240, 360, 720])
        ctx = _make_context_workbook(horizon=horizon, w=ew, r=wr)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], f"random_s{seed}")

    @pytest.mark.parametrize("seed", range(15))
    def test_random_multi_context_groups(self, seed: int) -> None:
        rng = random.Random(seed + 1000)
        ew = rng.uniform(0.2, 0.8)
        wr = rng.uniform(0.01, 0.06)
        horizons = sorted(rng.sample([12, 60, 120, 240, 360, 720], k=rng.randint(2, 4)))
        contexts = [_make_context_workbook(horizon=h, w=ew, r=wr) for h in horizons]
        numba = _run_numba(contexts)
        assert len(numba) == len(contexts)
        for i, h in enumerate(horizons):
            ctx = contexts[i]
            oracle = compute_workbook_oracle_result(ctx)
            _assert_matches_workbook(oracle, numba[i], f"random_group_s{seed}_h{h}")


class TestNumbaVsFastPathEquivalence:
    """The Numba workbook path and the Decimal fast path must agree.

    Guards against terminal-period drift: the Numba kernel must use the same
    number of periods (``horizon_months - 1``) and the same withdraw-then-grow
    order as ``fast_path`` (the canonical workbook implementation).
    """

    @pytest.mark.parametrize("horizon", [12, 60, 120, 240, 360, 720])
    @pytest.mark.parametrize("w", [0.0, 0.5, 1.0])
    def test_matches_fast_path(self, horizon: int, w: float) -> None:
        ctx = _make_context_workbook(horizon=horizon, w=w, r=0.04)
        numba_ok, numba_fm, numba_fv, numba_months = _run_numba([ctx])[0]
        fast = evaluate_closed_form(ctx).statistics

        assert numba_ok == fast.success
        assert numba_months == fast.months_simulated
        if fast.success:
            assert numba_fm is None
            assert fast.failure_month is None
            assert abs(numba_fv - fast.final_wealth.amount) < WEALTH_TOLERANCE

    @pytest.mark.parametrize("rate", [0.0, 0.01, 0.02, 0.05, 0.10])
    def test_matches_fast_path_rates(self, rate: float) -> None:
        ctx = _make_context_workbook(horizon=360, w=0.6, r=rate)
        numba_ok, _numba_fm, numba_fv, numba_months = _run_numba([ctx])[0]
        fast = evaluate_closed_form(ctx).statistics

        assert numba_ok == fast.success
        assert numba_months == fast.months_simulated
        if fast.success:
            assert abs(numba_fv - fast.final_wealth.amount) < WEALTH_TOLERANCE


def _wb_ctx(
    horizon: int,
    w: float,
    r: float,
    eq_return: float = 0.0,
    bd_return: float = 0.0,
) -> SimulationContext:
    """Workbook context with explicit constant asset returns and no fee.

    Fee is fixed at zero so these boundary tests isolate the terminal-period
    convention (order and count) from fee handling.
    """
    return make_workbook_test_context(
        horizon,
        w=w,
        r=r,
        equity_return=eq_return,
        bond_return=bd_return,
        fee_annual=0.0,
    )


class TestWorkbookConventionBoundaries:
    """Boundary behaviour of the workbook terminal convention.

    The workbook (``SWR_Toolbox_v2.0.xlsx`` ``Case Study``) withdraws before
    growing, for exactly ``horizon_months - 1`` periods, compounding the final
    period's return.  These cases pin the minimum horizon, exact depletion,
    withdrawal exceeding available wealth, and the terminal period.
    """

    def test_minimum_horizon_one_period(self) -> None:
        # horizon_months == 2 -> exactly one withdrawal and one growth period.
        ctx = _wb_ctx(horizon=2, w=0.5, r=0.05, eq_return=0.006, bd_return=0.002)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "min_horizon")

        v0 = Decimal("1000000")
        port_ret = Decimal("0.5") * Decimal("0.006") + Decimal("0.5") * Decimal("0.002")
        c = v0 * Decimal("0.05") / Decimal("12")
        expected = (v0 - c) * (Decimal("1") + port_ret)
        assert abs(oracle.final_wealth - expected) < WEALTH_TOLERANCE

    def test_terminal_period_growth_is_applied(self) -> None:
        # horizon_months == 3 -> two periods; the second period's return must be
        # compounded (withdraw-then-grow) rather than dropped.
        ctx = _wb_ctx(horizon=3, w=0.5, r=0.04, eq_return=0.01, bd_return=0.0)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "terminal_period")

        v0 = Decimal("1000000")
        g = Decimal("1") + Decimal("0.5") * Decimal("0.01")
        c = v0 * Decimal("0.04") / Decimal("12")
        expected = v0 * g**2 - c * (g + g**2)
        assert abs(oracle.final_wealth - expected) < WEALTH_TOLERANCE

    def test_exact_depletion_is_sustainable(self) -> None:
        # Zero returns and zero fee: rate = 12 / T drains the portfolio to
        # exactly zero on the final withdrawal, which is sustainable
        # (SCR == rate), not a shortfall.
        periods = 100
        ctx = _wb_ctx(horizon=periods + 1, w=0.5, r=0.12)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "exact_depletion")

        assert oracle.scr == Decimal("0.12")
        assert oracle.success is True
        assert oracle.final_wealth == Decimal("0")

    def test_exact_depletion_then_shortfall(self) -> None:
        # Same zero-return setup, but the horizon outlives the funds: the
        # portfolio hits exactly zero before the horizon and then fails.
        ctx = _wb_ctx(horizon=151, w=0.5, r=0.12)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "exact_depletion_shortfall")

        assert oracle.scr == Decimal("0.08")  # 12 / 150 periods
        assert oracle.success is False
        assert oracle.final_wealth == Decimal("0")
        assert oracle.failure_month == 151

    def test_withdrawal_exceeding_available_wealth(self) -> None:
        # Zero returns: rate far above the SCR depletes the portfolio early.
        ctx = _wb_ctx(horizon=101, w=0.5, r=0.30)
        oracle = compute_workbook_oracle_result(ctx)
        numba = _run_numba([ctx])
        _assert_matches_workbook(oracle, numba[0], "withdrawal_exceeds_wealth")

        assert oracle.success is False
        assert oracle.final_wealth == Decimal("0")
        assert oracle.failure_month == 101


class TestGrowthFactorCache:
    """Tests for the growth-factor cache in NumbaSimulationExecutor."""

    def test_identical_key_one_computation(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        executor.execute(defn)
        keys_before = list(executor.gf_cache.keys())
        assert len(keys_before) == 1

        executor.execute(defn)
        keys_after = list(executor.gf_cache.keys())
        assert len(keys_after) == 1
        assert keys_before == keys_after

    def test_same_start_date_reuses_cache(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        d1 = ds[0].date
        sliced = ds.slice(d1, 120)
        ctx1 = _make_context_on_dataset(sliced, horizon=120, w=0.5, r=0.04)
        defn1 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1,),
        )
        executor.execute(defn1)

        # Same dataset object across execute calls → same trajectory token.
        ctx2 = _make_context_on_dataset(sliced, horizon=120, w=0.5, r=0.04)
        defn2 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx2,),
        )
        executor.execute(defn2)

        assert len(executor.gf_cache) == 1
        assert (d1, _legacy_identity(Decimal("0.5")), id(sliced)) in executor.gf_cache

    def test_different_start_date_separate_entries(self) -> None:
        executor = NumbaSimulationExecutor()

        ds1 = _make_dataset(241)
        ctx1 = _make_context(ds1, horizon=120, w=0.5, r=0.04)
        defn1 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1,),
        )
        executor.execute(defn1)

        snapshots2 = [
            MarketSnapshot(
                date=date(2000, 1, 1),
                index_levels={_EQ: Decimal("100"), _BD: Decimal("100")},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            ),
            *[
                MarketSnapshot(
                    date=date(2000 + (m + 1) // 12, (m + 1) % 12 + 1, 1),
                    index_levels={
                        _EQ: Decimal("100") * Decimal("1.006") ** (m + 1),
                        _BD: Decimal("100") * Decimal("1.002") ** (m + 1),
                    },
                    inflation=Decimal("0"),
                    inflation_cumulative=Decimal("0"),
                    is_ath=True,
                    is_underwater=False,
                    running_ath=Decimal("100"),
                )
                for m in range(120)
            ],
        ]
        ds2 = Dataset(snapshots=snapshots2, frequency="monthly")
        ctx2 = _make_context(ds2, horizon=120, w=0.5, r=0.04)
        defn2 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx2,),
        )
        executor.execute(defn2)

        assert len(executor.gf_cache) == 2
        key1 = (date(1900, 1, 1), _legacy_identity(Decimal("0.5")), id(ctx1.dataset))
        key2 = (date(2000, 1, 1), _legacy_identity(Decimal("0.5")), id(ctx2.dataset))
        assert key1 in executor.gf_cache
        assert key2 in executor.gf_cache

    def test_different_weight_separate_entry(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        sliced = ds.slice(ds[0].date, 120)
        ctx_a = _make_context_on_dataset(sliced, horizon=120, w=0.3, r=0.04)
        defn_a = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_a,),
        )
        executor.execute(defn_a)

        ctx_b = _make_context_on_dataset(sliced, horizon=120, w=0.7, r=0.04)
        defn_b = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_b,),
        )
        executor.execute(defn_b)

        assert len(executor.gf_cache) == 2
        key_a = (ds[0].date, _legacy_identity(Decimal("0.3")), id(sliced))
        key_b = (ds[0].date, _legacy_identity(Decimal("0.7")), id(sliced))
        assert key_a in executor.gf_cache
        assert key_b in executor.gf_cache

    def test_same_weight_different_rate_same_cache(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        sliced = ds.slice(ds[0].date, 120)
        ctx_a = _make_context_on_dataset(sliced, horizon=120, w=0.5, r=0.03)
        defn_a = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_a,),
        )
        executor.execute(defn_a)

        ctx_b = _make_context_on_dataset(sliced, horizon=120, w=0.5, r=0.05)
        defn_b = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_b,),
        )
        executor.execute(defn_b)

        assert len(executor.gf_cache) == 1
        key = (ds[0].date, _legacy_identity(Decimal("0.5")), id(sliced))
        assert key in executor.gf_cache

    def test_cached_array_not_mutated(self) -> None:
        import numpy as np

        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        executor.execute(defn)

        key = (ds[0].date, _legacy_identity(Decimal("0.5")), id(ctx.dataset))
        arr1 = executor.gf_cache[key].copy()
        executor.execute(defn)
        arr2 = executor.gf_cache[key]

        np.testing.assert_array_equal(arr1, arr2)

    def test_executor_instances_isolated(self) -> None:
        exec_a = NumbaSimulationExecutor()
        exec_b = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        exec_a.execute(defn)

        assert len(exec_a.gf_cache) == 1
        assert len(exec_b.gf_cache) == 0

    def test_pass2_uses_precomputed_sample_context(self) -> None:
        """Regression: Pass 2 must not scan all contexts per GF key (O(n²))."""
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(721)
        # Create many contexts sharing the same GF key but different horizons.
        # The old O(n²) implementation would scan all contexts for each key.
        contexts = [_make_context(ds, horizon=h, w=0.5, r=0.04) for h in range(12, 252, 12)]
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=tuple(contexts),
        )

        executor.execute(defn)

        # Cross-horizon derivation shares one GF per identity-prefix cluster:
        # the longest-horizon context (240 months) is evaluated once and every
        # shorter horizon is derived from it.
        assert len(executor.gf_cache) == 1
        (gf_array,) = executor.gf_cache.values()
        assert len(gf_array) == 240  # max horizon - 1 for the dummy entry


class TestPriceFloatCache:
    """Tests for the dataset-level price float cache (R7.9)."""

    def test_same_start_date_reuses_prices(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        sliced = ds.slice(ds[0].date, 120)
        ctx1 = _make_context_on_dataset(sliced, horizon=120, w=0.5, r=0.04)
        ctx2 = _make_context_on_dataset(sliced, horizon=120, w=0.75, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Same dataset object → one materialised-price cache entry, shared
        # across allocations.
        assert len(executor._price_float_cache) == 1

    def test_different_start_dates_separate_entries(self) -> None:
        executor = NumbaSimulationExecutor()
        ds1 = _make_dataset(241)
        ctx1 = _make_context(ds1, horizon=120, w=0.5, r=0.04)
        # Second context with different dataset (different date)
        from datetime import timedelta
        ds2_shifted = _make_dataset(241)
        # Manually shift dates
        shifted_snaps = []
        for s in ds2_shifted.snapshots:
            shifted_snaps.append(MarketSnapshot(
                date=s.date + timedelta(days=365),
                index_levels=s.index_levels,
                inflation=s.inflation,
                inflation_cumulative=s.inflation_cumulative,
                is_ath=s.is_ath,
                is_underwater=s.is_underwater,
                running_ath=s.running_ath,
            ))
        ds2_shifted = Dataset(snapshots=shifted_snaps, frequency="monthly")
        ctx2 = _make_context(ds2_shifted, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Different start_dates → two price cache entries
        assert len(executor._price_float_cache) == 2

    def test_different_dataset_lengths_separate_entries(self) -> None:
        executor = NumbaSimulationExecutor()
        # Two datasets with same start_date but different lengths
        ds_short = _make_dataset(121)
        ds_long = _make_dataset(241)
        ctx1 = _make_context(ds_short, horizon=120, w=0.5, r=0.04)
        # Use ds_long but with a different start date to force separate price materialization
        from datetime import timedelta
        long_snaps = [
            MarketSnapshot(
                date=s.date + timedelta(days=365),
                index_levels=s.index_levels,
                inflation=s.inflation,
                inflation_cumulative=s.inflation_cumulative,
                is_ath=s.is_ath,
                is_underwater=s.is_underwater,
                running_ath=s.running_ath,
            )
            for s in ds_long.snapshots
        ]
        ds_long_shifted = Dataset(snapshots=long_snaps, frequency="monthly")
        ctx2 = _make_context(ds_long_shifted, horizon=240, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Different start_dates + different n_prices → two price cache entries
        assert len(executor._price_float_cache) == 2

    def test_cached_prices_not_mutated(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        executor.execute(defn)
        # Cache key is the dataset-identity token.
        key = id(ctx.dataset)
        arr1 = executor._price_float_cache[key].copy()
        executor.execute(defn)
        arr2 = executor._price_float_cache[key]
        np.testing.assert_array_equal(arr1, arr2)

    def test_executor_instances_isolated(self) -> None:
        exec_a = NumbaSimulationExecutor()
        exec_b = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        exec_a.execute(defn)
        assert len(exec_a._price_float_cache) == 1
        assert len(exec_b._price_float_cache) == 0

    def test_numerical_equivalence_with_old_path(self) -> None:
        """Price cache produces same GF as _materialize_float_series."""
        from fbf.core.execution.strategies.numba_kernel import (
            _compute_growth_factors_numpy,
            _materialize_float_series,
        )
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        executor.execute(defn)

        # Get cached prices — keyed by the dataset-identity token.
        key = id(ctx.dataset)
        prices_f = executor._price_float_cache[key]

        # Compute using old path
        weights = _weights_by_class(ctx)
        series = _index_series(ctx)
        asset_classes = tuple(series.keys())
        w_old, p_old, _ = _materialize_float_series(asset_classes, weights, series)
        gf_old = _compute_growth_factors_numpy(w_old, p_old, 120)

        # Compute using new path
        w_new = np.array([float(weights[ac]) for ac in asset_classes], dtype=np.float64)
        gf_new = _compute_growth_factors_numpy(w_new, prices_f, 120)

        np.testing.assert_array_equal(gf_old, gf_new)


class TestIndexSeriesCache:
    """Tests for the dataset-level _index_series cache (R7.10)."""

    def test_same_key_reuses_series(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        sliced = ds.slice(ds[0].date, 120)
        ctx1 = _make_context_on_dataset(sliced, horizon=120, w=0.5, r=0.04)
        ctx2 = _make_context_on_dataset(sliced, horizon=120, w=0.75, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Same dataset object → one index-series cache entry, shared across
        # allocations.
        assert len(executor._index_series_cache) == 1

    def test_different_start_dates_separate_entries(self) -> None:
        executor = NumbaSimulationExecutor()
        ds1 = _make_dataset(241)
        ctx1 = _make_context(ds1, horizon=120, w=0.5, r=0.04)
        from datetime import timedelta
        ds2_shifted = _make_dataset(241)
        shifted_snaps = [
            MarketSnapshot(
                date=s.date + timedelta(days=365),
                index_levels=s.index_levels,
                inflation=s.inflation,
                inflation_cumulative=s.inflation_cumulative,
                is_ath=s.is_ath,
                is_underwater=s.is_underwater,
                running_ath=s.running_ath,
            )
            for s in ds2_shifted.snapshots
        ]
        ds2_shifted = Dataset(snapshots=shifted_snaps, frequency="monthly")
        ctx2 = _make_context(ds2_shifted, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Different start_dates → two cache entries
        assert len(executor._index_series_cache) == 2

    def test_different_n_prices_separate_entries(self) -> None:
        executor = NumbaSimulationExecutor()
        # Two datasets with different start dates AND different lengths
        ds_short = _make_dataset(121)
        ds_long = _make_dataset(241)
        ctx1 = _make_context(ds_short, horizon=120, w=0.5, r=0.04)
        from datetime import timedelta
        long_snaps = [
            MarketSnapshot(
                date=s.date + timedelta(days=365),
                index_levels=s.index_levels,
                inflation=s.inflation,
                inflation_cumulative=s.inflation_cumulative,
                is_ath=s.is_ath,
                is_underwater=s.is_underwater,
                running_ath=s.running_ath,
            )
            for s in ds_long.snapshots
        ]
        ds_long_shifted = Dataset(snapshots=long_snaps, frequency="monthly")
        ctx2 = _make_context(ds_long_shifted, horizon=240, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Different start_dates + different n_prices → two cache entries
        assert len(executor._index_series_cache) == 2

    def test_cached_series_not_mutated(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        executor.execute(defn)
        key = id(ctx.dataset)
        series1 = executor._index_series_cache[key]
        # Make a copy of the first value
        first_vals = dict(series1.items())
        executor.execute(defn)
        series2 = executor._index_series_cache[key]
        for ac in first_vals:
            assert first_vals[ac] == series2[ac]

    def test_executor_instances_isolated(self) -> None:
        exec_a = NumbaSimulationExecutor()
        exec_b = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        exec_a.execute(defn)
        assert len(exec_a._index_series_cache) == 1
        assert len(exec_b._index_series_cache) == 0

    def test_numerical_equivalence_with_uncached(self) -> None:
        """Cached _index_series produces same values as uncached."""
        from fbf.core.execution.strategies.fast_path import _index_series
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx,),
        )
        executor.execute(defn)

        # Get cached series
        key = id(ctx.dataset)
        cached_series = executor._index_series_cache[key]

        # Compute uncached
        uncached_series = _index_series(ctx)

        for ac in cached_series:
            assert cached_series[ac] == uncached_series[ac]


class TestDatasetIdentityIsolation:
    """Regression: contexts built from *different* trajectories that share a
    start date and allocation must never share cached growth factors or
    materialised prices.

    Before the dataset-identity cache key, growth factors were keyed by
    ``(start_date, equity_allocation)``, so the first trajectory processed in a
    definition silently supplied growth factors for every later trajectory with
    the same start date.
    """

    @staticmethod
    def _contexts() -> tuple[SimulationContext, SimulationContext]:
        flat = _make_dataset_with_returns(121, Decimal("0"), Decimal("0"))
        grow = _make_dataset_with_returns(121, Decimal("0.006"), Decimal("0.002"))
        return (
            _make_context(flat, horizon=120, w=0.5, r=0.04),
            _make_context(grow, horizon=120, w=0.5, r=0.04),
        )

    def _alone(self, ctx: SimulationContext) -> SimulationResult:
        run = NumbaSimulationExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx,)
            )
        )
        return run.simulation_results[0]

    def test_isolated_in_declaration_order(self) -> None:
        ctx_flat, ctx_grow = self._contexts()
        alone_flat = self._alone(ctx_flat).statistics
        alone_grow = self._alone(ctx_grow).statistics

        together = NumbaSimulationExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx_flat, ctx_grow)
            )
        ).simulation_results

        assert together[0].statistics.final_wealth == alone_flat.final_wealth
        assert together[1].statistics.final_wealth == alone_grow.final_wealth
        assert alone_flat.final_wealth != alone_grow.final_wealth

    def test_isolated_in_reverse_order(self) -> None:
        ctx_flat, ctx_grow = self._contexts()
        alone_flat = self._alone(ctx_flat).statistics
        alone_grow = self._alone(ctx_grow).statistics

        together = NumbaSimulationExecutor().execute(
            EngineExperimentDefinition(
                name="t", description="t", simulation_contexts=(ctx_grow, ctx_flat)
            )
        ).simulation_results

        assert together[0].statistics.final_wealth == alone_grow.final_wealth
        assert together[1].statistics.final_wealth == alone_flat.final_wealth
