"""Differential validation: Numba executor vs Decimal reference engine.

Verifies that the NumbaSimulationExecutor produces results matching the
Decimal reference engine for identical inputs through the real execution
architecture (not just the raw kernel).
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

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
