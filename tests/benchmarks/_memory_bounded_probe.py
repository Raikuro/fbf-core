"""Isolated-process probe for bounded streaming execution memory.

Run as a script so each measurement starts from a fresh interpreter and its
peak RSS is not contaminated by previous measurements.
"""

from __future__ import annotations

import argparse
import gc
import json
import pickle
import resource
import tempfile
import time
from contextlib import suppress
from datetime import date
from decimal import Decimal
from pathlib import Path

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionStrategy,
    iter_execute_study_plan,
)
from fbf.core.persistence.studies.sqlite import (
    AllocationPolicyCodec,
    PersistenceReconstructionContext,
    SimulationResultCodec,
    SQLiteRepository,
    WithdrawalPolicyCodec,
)
from fbf.core.persistence.studies.sqlite.sqlite_repository import ExperimentIdentity
from fbf.core.study.builder import BuiltStudy, build_initial_portfolio
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, ResearchPlan

_EQUITY = AssetClass(id="equity", name="Equity", description="")
_BOND = AssetClass(id="bond", name="Bond", description="")
_WEALTH = Money(Decimal("1000000"), Currency.EUR)


class _DatasetLoader:
    def __init__(self, dataset: Dataset) -> None:
        self._dataset = dataset

    def load(self) -> Dataset:
        return self._dataset


def _persistence_context(dataset: Dataset) -> PersistenceReconstructionContext:
    return PersistenceReconstructionContext(
        dataset_loader=_DatasetLoader(dataset),
        policy_codecs={
            ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )


def _add_months(start: date, months: int) -> date:
    total = start.month - 1 + months
    return date(start.year + total // 12, total % 12 + 1, 1)


def _dataset(months: int) -> Dataset:
    snapshots = []
    equity = Decimal("100")
    bond = Decimal("100")
    for index in range(months):
        snapshots.append(
            MarketSnapshot(
                date=_add_months(date(1800, 1, 1), index),
                index_levels={_EQUITY: equity, _BOND: bond},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=equity,
            )
        )
        equity *= Decimal("1.005")
        bond *= Decimal("1.002")
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _plan(n_units: int, horizon: int, per_cohort: int) -> ResearchPlan:
    if n_units % per_cohort != 0:
        raise ValueError("--units must be divisible by --per-cohort")
    n_cohorts = n_units // per_cohort
    dataset = _dataset(n_cohorts + horizon)
    cohorts = tuple(
        CohortSpecification(start_date=_add_months(date(1800, 1, 1), i))
        for i in range(n_cohorts)
    )
    cohort_data = tuple(
        (
            dataset.slice(cohort.start_date, horizon),
            build_initial_portfolio(
                _WEALTH, dataset.slice(cohort.start_date, horizon)
            ),
        )
        for cohort in cohorts
    )
    experiment = ExperimentDefinition(
        name="memory-bounded-probe",
        description="memory bounded probe",
        dataset=dataset,
        horizon_months=horizon,
        initial_wealth=_WEALTH,
        cohorts=cohorts,
        allocation_policies=(ConstantAllocationPolicy(Decimal("0.6")),),
        withdrawal_policies=(FixedRealWithdrawalPolicy(Decimal("0.04")),),
    )
    units = tuple(
        PlannedSimulationUnit(
            cohort=cohorts[i // per_cohort],
            parameter_config=ParameterConfiguration(values={"index": i}),
            allocation_policy=ConstantAllocationPolicy(Decimal("0.6")),
            withdrawal_policy=FixedRealWithdrawalPolicy(Decimal("0.04")),
            initial_portfolio=cohort_data[i // per_cohort][1],
            dataset=cohort_data[i // per_cohort][0],
            horizon_months=horizon,
        )
        for i in range(n_units)
    )
    return ResearchPlan(experiment_definition=experiment, units=units)


def _peak_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _reset_peak_rss() -> None:
    with suppress(OSError):
        Path("/proc/self/clear_refs").write_text("5")


def _hwm_mb() -> float:
    try:
        with open("/proc/self/status") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return _peak_mb()


def _rss_mb() -> float:
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=int, required=True)
    parser.add_argument("--slice", type=int, required=True)
    parser.add_argument("--horizon", type=int, default=720)
    parser.add_argument("--materialize", type=int, default=1)
    parser.add_argument("--per-cohort", type=int, default=1)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    plan = _plan(args.units, args.horizon, args.per_cohort)
    built = BuiltStudy(
        plan=plan,
        experiment_definition=plan.experiment_definition,
        cohorts=plan.experiment_definition.cohorts,
        param_configs=(),
    )
    materialize = bool(args.materialize)
    options = ExecutionOptions(
        backend=ExecutionBackend.FAST,
        strategy=ExecutionStrategy.SEQUENTIAL,
        materialize_timeline=materialize,
        summary_only=not materialize,
    )
    persist_dir: tempfile.TemporaryDirectory[str] | None = None
    repo: SQLiteRepository | None = None
    attempt = None
    if args.persist:
        persist_dir = tempfile.TemporaryDirectory()
        repo = SQLiteRepository(str(Path(persist_dir.name) / "probe.db"))
        ctx = _persistence_context(plan.experiment_definition.dataset)
        experiment_id = repo.save_experiment(
            ExperimentIdentity(name="memory-probe", revision="v1"),
            plan.experiment_definition,
            ctx,
        )
        plan_id = repo.save_plan(plan, experiment_id, ctx)
        attempt = repo.begin_execution(plan_id, len(plan.units), ctx)

    gc.collect()
    baseline_peak = _peak_mb()
    baseline_rss = _rss_mb()
    _reset_peak_rss()

    started = time.perf_counter()
    totals = 0
    payload_bytes = 0
    payload_units = 0
    months = 0
    for chunk in iter_execute_study_plan(
        built, options, max_units_per_slice=args.slice
    ):
        totals += len(chunk.result.results)
        if payload_units == 0:
            result = chunk.result.results[0]
            payload_bytes = len(pickle.dumps(result))
            months = len(result.timeline.monthly_results)
            payload_units = 1
            del result
        if repo is not None and attempt is not None:
            attempt = repo.append_execution_slice(
                attempt.result_id,
                attempt.attempt_id,
                chunk.start_index,
                chunk.result.results,
                ctx,
            )
        del chunk
    elapsed = time.perf_counter() - started

    db_size_mb = 0.0
    if repo is not None and attempt is not None:
        attempt = repo.complete_execution(
            attempt.result_id, attempt.attempt_id, elapsed
        )
        db_path = Path(repo.db_path)
        db_size_mb = sum(
            path.stat().st_size
            for path in (db_path, Path(f"{db_path}-wal"))
            if path.exists()
        ) / 1048576.0

    gc.collect()
    print(
        json.dumps(
            {
                "units": args.units,
                "slice": args.slice,
                "horizon": args.horizon,
                "per_cohort": args.per_cohort,
                "materialize": materialize,
                "executed": totals,
                "baseline_peak_mb": round(baseline_peak, 1),
                "baseline_rss_mb": round(baseline_rss, 1),
                "peak_mb": round(_hwm_mb(), 1),
                "peak_delta_mb": round(_hwm_mb() - baseline_rss, 1),
                "final_rss_mb": round(_rss_mb(), 1),
                "payload_bytes_per_unit": payload_bytes,
                "payload_mib_per_unit": round(payload_bytes / 1048576, 4),
                "months": months,
                "persisted": args.persist,
                "persisted_units": (
                    attempt.completed_units if attempt is not None else 0
                ),
                "persisted_status": (
                    attempt.status if attempt is not None else None
                ),
                "persist_db_mb": round(db_size_mb, 2),
                "elapsed_seconds": round(elapsed, 3),
            }
        )
    )
    if persist_dir is not None:
        persist_dir.cleanup()


if __name__ == "__main__":
    main()
