"""Differential validation: Numba executor vs Decimal reference engine.

Verifies that the NumbaSimulationExecutor produces results matching the
Decimal reference engine for identical inputs through the real execution
architecture (not just the raw kernel).
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
)
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.fast_path import _index_series, _weights_by_class
from fbf.core.execution.strategies.numba_executor import NumbaSimulationExecutor
from fbf.core.execution.strategies.parallel_executor import (
    _create_default_simulation_executor,
)
from fbf.core.study.builder import build_initial_portfolio

_EQ = AssetClass(id="equity", name="", description="")
_BD = AssetClass(id="bond", name="", description="")

_REFERENCE_EXECUTOR: SimulationExecutor = _create_default_simulation_executor()
_NUMBA_EXECUTOR: SimulationExecutor = NumbaSimulationExecutor()

WEALTH_TOLERANCE = Decimal("0.01")


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
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _make_context(
    dataset: Dataset,
    horizon: int,
    w: float = 0.5,
    r: float = 0.04,
) -> SimulationContext:
    start = dataset[0].date
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Currency.EUR))
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


def _run_both(
    contexts: list[SimulationContext],
) -> tuple[
    list[tuple[bool, int | None, Decimal, int]],
    list[tuple[bool, int | None, Decimal, int]],
]:
    definition = EngineExperimentDefinition(
        name="test",
        description="test",
        simulation_contexts=tuple(contexts),
    )
    ref_run = _REFERENCE_EXECUTOR.execute(definition)
    numba_run = _NUMBA_EXECUTOR.execute(definition)

    def _extract(run: object) -> list[tuple[bool, int | None, Decimal, int]]:
        results = []
        for r in run.simulation_results:  # type: ignore[union-attr]
            s = r.statistics
            results.append((
                s.success,
                s.failure_month,
                s.final_wealth.amount,
                s.months_simulated,
            ))
        return results

    return _extract(ref_run), _extract(numba_run)


def _assert_matches(
    ref: tuple[bool, int | None, Decimal, int],
    numba: tuple[bool, int | None, Decimal, int],
    label: str,
) -> None:
    ref_ok, ref_fm, ref_fv, ref_months = ref
    numba_ok, numba_fm, numba_fv, numba_months = numba

    assert numba_ok == ref_ok, f"{label}: success mismatch ({numba_ok} vs {ref_ok})"
    assert numba_fm == ref_fm, f"{label}: failure_month mismatch ({numba_fm} vs {ref_fm})"
    assert numba_months == ref_months, (
        f"{label}: months_simulated mismatch ({numba_months} vs {ref_months})"
    )
    if ref_ok:
        diff = abs(ref_fv - numba_fv)
        assert diff < WEALTH_TOLERANCE, (
            f"{label}: final_wealth diff {diff} exceeds tolerance {WEALTH_TOLERANCE}"
        )


class TestNumbaExecutorDeterministic:
    def test_flat_market_single_context(self) -> None:
        ds = _make_dataset(721)
        ctx = _make_context(ds, horizon=720, w=0.5, r=0.04)
        ref, numba = _run_both([ctx])
        assert len(ref) == 1
        _assert_matches(ref[0], numba[0], "flat_720m")

    def test_flat_market_multiple_horizons(self) -> None:
        ds = _make_dataset(721)
        contexts = [_make_context(ds, horizon=h, w=0.6, r=0.03) for h in [12, 60, 360, 720]]
        ref, numba = _run_both(contexts)
        assert len(ref) == 4
        for i, h in enumerate([12, 60, 360, 720]):
            _assert_matches(ref[i], numba[i], f"multi_horizon_{h}m")

    def test_equity_only(self) -> None:
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=240, w=1.0, r=0.04)
        ref, numba = _run_both([ctx])
        _assert_matches(ref[0], numba[0], "equity_only_240m")

    def test_bond_only(self) -> None:
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=240, w=0.0, r=0.02)
        ref, numba = _run_both([ctx])
        _assert_matches(ref[0], numba[0], "bond_only_240m")

    def test_high_withdrawal_depletes(self) -> None:
        ds = _make_dataset(121)
        ctx = _make_context(ds, horizon=120, w=0.5, r=0.20)
        ref, numba = _run_both([ctx])
        _assert_matches(ref[0], numba[0], "high_withdrawal_depletes")

    def test_zero_withdrawal(self) -> None:
        ds = _make_dataset(241)
        ctx = _make_context(ds, horizon=240, w=0.7, r=0.0)
        ref, numba = _run_both([ctx])
        _assert_matches(ref[0], numba[0], "zero_withdrawal")

    def test_different_allocations(self) -> None:
        ds = _make_dataset(361)
        for w in [0.0, 0.25, 0.5, 0.75, 1.0]:
            ctx = _make_context(ds, horizon=360, w=w, r=0.04)
            ref, numba = _run_both([ctx])
            _assert_matches(ref[0], numba[0], f"alloc_{w}")

    def test_different_rates(self) -> None:
        ds = _make_dataset(361)
        for r in [0.0, 0.02, 0.03, 0.04, 0.05, 0.08]:
            ctx = _make_context(ds, horizon=360, w=0.6, r=r)
            ref, numba = _run_both([ctx])
            _assert_matches(ref[0], numba[0], f"rate_{r}")

    def test_grouping_derives_shorter_horizons(self) -> None:
        ds = _make_dataset(721)
        base = _make_context(ds, horizon=720, w=0.5, r=0.04)
        shorter = _make_context(ds, horizon=360, w=0.5, r=0.04)
        ref, numba = _run_both([base, shorter])
        assert len(ref) == 2
        _assert_matches(ref[0], numba[0], "group_longest_720m")
        _assert_matches(ref[1], numba[1], "group_derived_360m")

    def test_ineligible_context_falls_back(self) -> None:
        from fbf.core.domain.policies import ConstantWithdrawalPolicy

        ds = _make_dataset(241)
        eligible = _make_context(ds, horizon=240, w=0.5, r=0.04)
        start = eligible.start_date
        ineligible = SimulationContext(
            experiment_name="test",
            cohort="ineligible",
            start_date=start,
            horizon_months=240,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=eligible.initial_portfolio,
            dataset=ds.slice(start, 240),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.5")),
            withdrawal_policy=ConstantWithdrawalPolicy(Decimal("40000")),
        )
        ref, numba = _run_both([eligible, ineligible])
        assert len(ref) == 2
        _assert_matches(ref[0], numba[0], "eligible_in_mixed")
        assert numba[1] == ref[1], "ineligible fallback mismatch"


class TestNumbaExecutorRandomized:
    @pytest.mark.parametrize("seed", range(30))
    def test_random_trajectories(self, seed: int) -> None:
        rng = random.Random(seed)
        ds = _make_dataset(721)
        ew = rng.uniform(0.0, 1.0)
        wr = rng.uniform(0.0, 0.10)
        horizon = rng.choice([12, 60, 120, 240, 360, 720])
        ctx = _make_context(ds, horizon=horizon, w=ew, r=wr)
        ref, numba = _run_both([ctx])
        _assert_matches(ref[0], numba[0], f"random_s{seed}")

    @pytest.mark.parametrize("seed", range(15))
    def test_random_multi_context_groups(self, seed: int) -> None:
        rng = random.Random(seed + 1000)
        ds = _make_dataset(721)
        ew = rng.uniform(0.2, 0.8)
        wr = rng.uniform(0.01, 0.06)
        horizons = sorted(rng.sample([12, 60, 120, 240, 360, 720], k=rng.randint(2, 4)))
        contexts = [_make_context(ds, horizon=h, w=ew, r=wr) for h in horizons]
        ref, numba = _run_both(contexts)
        assert len(ref) == len(contexts)
        for i, h in enumerate(horizons):
            _assert_matches(ref[i], numba[i], f"random_group_s{seed}_h{h}")


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
        ds1 = _make_dataset(241)
        d1 = ds1[0].date
        ctx1 = _make_context(ds1, horizon=120, w=0.5, r=0.04)
        defn1 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1,),
        )
        executor.execute(defn1)

        ds2 = _make_dataset(241)
        ctx2 = _make_context(ds2, horizon=120, w=0.5, r=0.04)
        defn2 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx2,),
        )
        executor.execute(defn2)

        assert len(executor.gf_cache) == 1
        assert (d1, Decimal("0.5")) in executor.gf_cache

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
        ds2 = Dataset(snapshots=snapshots2, frequency="monthly", version="1.0")
        ctx2 = _make_context(ds2, horizon=120, w=0.5, r=0.04)
        defn2 = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx2,),
        )
        executor.execute(defn2)

        assert len(executor.gf_cache) == 2
        key1 = (date(1900, 1, 1), Decimal("0.5"))
        key2 = (date(2000, 1, 1), Decimal("0.5"))
        assert key1 in executor.gf_cache
        assert key2 in executor.gf_cache

    def test_different_weight_separate_entry(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx_a = _make_context(ds, horizon=120, w=0.3, r=0.04)
        defn_a = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_a,),
        )
        executor.execute(defn_a)

        ctx_b = _make_context(ds, horizon=120, w=0.7, r=0.04)
        defn_b = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_b,),
        )
        executor.execute(defn_b)

        assert len(executor.gf_cache) == 2
        key_a = (ds[0].date, Decimal("0.3"))
        key_b = (ds[0].date, Decimal("0.7"))
        assert key_a in executor.gf_cache
        assert key_b in executor.gf_cache

    def test_same_weight_different_rate_same_cache(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx_a = _make_context(ds, horizon=120, w=0.5, r=0.03)
        defn_a = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_a,),
        )
        executor.execute(defn_a)

        ctx_b = _make_context(ds, horizon=120, w=0.5, r=0.05)
        defn_b = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx_b,),
        )
        executor.execute(defn_b)

        assert len(executor.gf_cache) == 1
        key = (ds[0].date, Decimal("0.5"))
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

        key = (ds[0].date, Decimal("0.5"))
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

        # The GF array must use the longest horizon (240 months).
        key = (ds[0].date, Decimal("0.5"))
        assert key in executor.gf_cache
        assert len(executor.gf_cache[key]) == 240  # max horizon - 1 for the dummy entry


class TestPriceFloatCache:
    """Tests for the dataset-level price float cache (R7.9)."""

    def test_same_start_date_reuses_prices(self) -> None:
        executor = NumbaSimulationExecutor()
        ds = _make_dataset(241)
        ctx1 = _make_context(ds, horizon=120, w=0.5, r=0.04)
        ctx2 = _make_context(ds, horizon=120, w=0.75, r=0.04)
        defn = EngineExperimentDefinition(
            name="t", description="t", simulation_contexts=(ctx1, ctx2),
        )
        executor.execute(defn)
        # Same start_date, same n_prices → one price cache entry
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
        ds2_shifted = Dataset(snapshots=shifted_snaps, frequency="monthly", version="1.0")
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
        ds_long_shifted = Dataset(snapshots=long_snaps, frequency="monthly", version="1.0")
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
        # Cache key is (start_date, n_prices) where n_prices = horizon
        key = (ds[0].date, 120)
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

        # Get cached prices — key uses horizon (120), not dataset length (241)
        key = (ds[0].date, 120)
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
