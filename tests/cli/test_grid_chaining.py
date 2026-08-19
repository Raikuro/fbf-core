"""Grid-study fast-path chaining: live report, CLI integration, validation.

Grid studies (``--fast-path`` on a plan with a ``horizon_years`` axis) reuse
each cohort's longest horizon as the single evaluation and derive the shorter
horizons as prefix paths.  These tests pin the instrumentation around that
behaviour:

- the live ``ChainedFastPathSimulationExecutor`` report matches the plan-level
  ``expected_chaining_report`` oracle,
- the CLI prints chaining and per-cell summaries for grid fast-path runs,
- Reference Chained is the sole reference execution strategy: every reference
  run (no flag, or ``--reference-chained``) routes through the chained
  Reference executor for chainable and single-horizon plans alike,
- F7 validation sampling is stratified so every horizon is covered.
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from cli.builders import (
    BuiltStudy,
    StudyConfiguration,
    build_initial_portfolio,
    build_study_plan,
)
from cli.fast_path import (
    FAST_PATH_VALIDATION_MAX_UNITS,
    ChainedFastPathSimulationExecutor,
    expected_chaining_report,
    select_validation_units,
)
from cli.policies import ConstantAllocationPolicy, FixedRealWithdrawalPolicy
from engine.domain.model.asset import AssetClass
from engine.domain.model.dataset import Dataset
from engine.domain.model.market_snapshot import MarketSnapshot
from engine.domain.model.money import Currency, Money
from infrastructure.execution.parallel_executor import sequential_execute
from infrastructure.execution.reference_chaining import (
    execute_reference_chained,
    expected_reference_chaining_report,
)
from infrastructure.persistence.codecs import DefaultDatasetResolver
from research.domain.cohort.generator import CohortGenerator
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.axis import ParameterAxis
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.parameter.engine import ParameterSweepEngine
from research.domain.parameter.types import ParameterScalar
from research.domain.plan import ResearchPlan, materialize_research_plan
from research.orchestration.result import ResearchExecutionResult

EQ = AssetClass(id="equity", name="", description="")
BD = AssetClass(id="bond", name="", description="")

_WEALTH = Money(Decimal("1000000"), Currency.EUR)

_SINGLE_HORIZON_YAML = """\
metadata:
  name: "Single Horizon Study"
dataset:
  identifier: "TEST_DATASET"
cohorts:
  horizon_years: [4]
allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [0.5]
withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.04]
"""


def _synthetic_dataset(n_months: int = 240, seed: int = 7) -> Dataset:
    rng = random.Random(seed)
    pe = pb = Decimal("100")
    snapshots = []
    d = date(2000, 1, 1)
    for _ in range(n_months):
        snapshots.append(
            MarketSnapshot(
                date=d,
                index_levels={EQ: pe, BD: pb},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        pe *= Decimal(str(1 + rng.gauss(0.006, 0.045)))
        pb *= Decimal(str(1 + rng.gauss(0.002, 0.01)))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="1.0")


def _parameter_configs(
    params_data: dict[str, list[ParameterScalar]],
) -> tuple[ParameterConfiguration, ...]:
    axes = [
        ParameterAxis(name=name, values=tuple(values))
        for name, values in params_data.items()
    ]
    return ParameterSweepEngine.cartesian_product(axes)


def build_grid_plan(
    dataset: Dataset,
    horizons: tuple[int, ...] = (2, 3, 4),
    cohorts: tuple[CohortSpecification, ...] | None = None,
) -> ResearchPlan:
    """Build a synthetic grid plan: one cohort set, one per-horizon config."""
    if cohorts is None:
        cohorts = CohortGenerator.generate_rolling_monthly(dataset, max(horizons) * 12)
    configs = _parameter_configs({"horizon_years": list(horizons)})
    alloc = ConstantAllocationPolicy(Decimal("0.5"))
    withdraw = FixedRealWithdrawalPolicy(Decimal("0.04"))
    exp_def = ExperimentDefinition(
        name="grid",
        description="grid test",
        dataset=dataset,
        horizon_months=max(horizons) * 12,
        initial_wealth=_WEALTH,
        cohorts=cohorts,
        allocation_policies=(alloc,),
        withdrawal_policies=(withdraw,),
    )
    return materialize_research_plan(
        experiment_def=exp_def,
        canonical_trajectory=dataset,
        cohorts=cohorts,
        param_configs=configs,
        initial_portfolio=build_initial_portfolio(_WEALTH),
        horizon_resolver=lambda c: int(c.get("horizon_years")) * 12,
        policy_resolver=lambda c: (alloc, withdraw),
    )


class TestGridChainingReport:
    def test_live_report_matches_expected_oracle(self) -> None:
        """The executor records exactly what the plan-level oracle predicts."""
        plan = build_grid_plan(_synthetic_dataset())
        expected = expected_chaining_report(plan)
        assert expected.chained_groups == len(plan.units) // len({u.parameter_config for u in plan})

        executor = ChainedFastPathSimulationExecutor(precision="float")
        sequential_execute(plan, simulation_executor=executor, summary_only=True)

        live = executor.chaining_report
        assert live is not None
        assert live == expected
        assert live.logical_units == len(plan.units)
        assert live.independent_evaluations == 0
        longest = max(h for h in (u.horizon_months for u in plan.units) if h is not None)
        assert live.longest_path_evaluations * longest == live.month_work

    def test_chained_grid_matches_reference_outcomes(self) -> None:
        """Derived shorter horizons reproduce reference success/failure."""
        plan = build_grid_plan(_synthetic_dataset())
        reference = sequential_execute(plan, summary_only=True).results
        chained = sequential_execute(
            plan,
            simulation_executor=ChainedFastPathSimulationExecutor(precision="float"),
            summary_only=True,
        ).results

        assert len(chained) == len(reference)
        for ref, got in zip(reference, chained, strict=True):
            assert ref.statistics.success == got.statistics.success
            assert ref.statistics.failure_month == got.statistics.failure_month


class TestGridValidationStratification:
    def test_sample_covers_every_horizon(self) -> None:
        """F7: multi-horizon grid validation samples each distinct horizon."""
        plan = build_grid_plan(_synthetic_dataset(), horizons=(2, 3, 4))
        sample = select_validation_units(plan)

        assert 0 < len(sample) <= FAST_PATH_VALIDATION_MAX_UNITS
        horizons = {u.horizon_months for u in sample}
        assert horizons == {24, 36, 48}

    def test_sampling_is_deterministic_for_grids(self) -> None:
        plan = build_grid_plan(_synthetic_dataset(), horizons=(2, 3, 4))
        assert select_validation_units(plan) == select_validation_units(plan)

    def test_stratified_sample_respects_horizon_shares(self) -> None:
        """With room to spare every horizon gets an equal share of the budget."""
        plan = build_grid_plan(_synthetic_dataset(), horizons=(1, 2, 3, 4))
        sample = select_validation_units(plan, max_units=8)
        counts: dict[int, int] = {}
        for unit in sample:
            horizon = unit.horizon_months
            assert horizon is not None
            counts[horizon] = counts.get(horizon, 0) + 1
        assert counts == {12: 2, 24: 2, 36: 2, 48: 2}


class TestGridCli:
    GRID_YAML = """\
metadata:
  name: "Grid Chaining Study"
dataset:
  identifier: "TEST_DATASET"
cohorts:
  horizon_years: [3, 4]
allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [0.5]
withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.04]
"""

    @pytest.fixture
    def mock_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from infrastructure.persistence.codecs import DefaultDatasetResolver

        def mock_resolve(self: DefaultDatasetResolver, identifier: str) -> Dataset:
            return _synthetic_dataset(500)

        monkeypatch.setattr(DefaultDatasetResolver, "resolve", mock_resolve)

    def test_fast_path_grid_prints_chaining_and_per_cell(
        self,
        tmp_path: Path,
        mock_dataset: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Grid fast-path runs report chaining and per-cell summaries."""
        from cli.main import main

        study_file = tmp_path / "grid.yaml"
        study_file.write_text(self.GRID_YAML, encoding="utf-8")
        rc = main(["run", "--fast-path", "--summary-only", "--no-persist", str(study_file)])
        out = capsys.readouterr().out

        assert rc == 0
        assert "Fast Path:" in out
        assert "Chained Groups:" in out
        assert "Longest Path:" in out
        assert "Month-Work:" in out
        assert "Per-Cell Results (grid):" in out
        assert "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=3" in out
        assert "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=4" in out

    def test_default_grid_uses_reference_chained_summary(
        self,
        tmp_path: Path,
        mock_dataset: None,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A grid run without any mode flag routes through Reference Chained and
        reports chaining coverage."""
        import infrastructure.execution.reference_chaining as rchain
        from cli.main import main

        monkeypatch.setattr(rchain, "parallel_execute", _make_fake_executor_result)

        study_file = tmp_path / "grid.yaml"
        study_file.write_text(self.GRID_YAML, encoding="utf-8")
        rc = main(["run", "--summary-only", "--no-persist", str(study_file)])
        out = capsys.readouterr().out

        assert rc == 0
        assert "Reference Chained:" in out
        assert "Chained Groups:" in out
        assert "Longest Path:" in out
        assert "Month-Work:" in out
        assert "Per-Cell Results (grid):" in out

    def test_default_single_horizon_plan_reports_chaining_summary(
        self,
        tmp_path: Path,
        mock_dataset: None,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A single-horizon plan without any mode flag still routes through
        Reference Chained (the sole reference strategy) and reports the chaining
        summary."""
        import infrastructure.execution.reference_chaining as rchain
        from cli.main import main

        monkeypatch.setattr(rchain, "parallel_execute", _make_fake_executor_result)

        study_file = tmp_path / "single.yaml"
        study_file.write_text(_SINGLE_HORIZON_YAML, encoding="utf-8")
        rc = main(["run", "--summary-only", "--no-persist", str(study_file)])
        out = capsys.readouterr().out

        assert rc == 0
        assert "Reference Chained:" in out
        assert "Chained Groups:" in out


class TestGridPerCellByteLayout:
    """The per-cell line for a 3-axis ERN grid keeps the historical layout.

    The generalized key derivation must keep ``equity_allocation``,
    ``withdrawal_rate``, ``horizon_years`` first in that order so existing
    machine-parseable output (and the ERN E2E parser) stays byte-identical.
    """

    GRID_YAML = """\
metadata:
  name: "Grid Three Axis Study"
dataset:
  identifier: "TEST_DATASET"
cohorts:
  horizon_years: [3, 4]
allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [0.5]
withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.04]
"""

    @pytest.fixture
    def mock_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from infrastructure.persistence.codecs import DefaultDatasetResolver

        def mock_resolve(self: DefaultDatasetResolver, identifier: str) -> Dataset:
            return _synthetic_dataset(500)

        monkeypatch.setattr(DefaultDatasetResolver, "resolve", mock_resolve)

    def test_three_axis_cell_lines_keep_historical_field_order(
        self,
        tmp_path: Path,
        mock_dataset: None,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cell keys keep the ERN-axes-first ordering for 3-axis grids."""
        import infrastructure.execution.reference_chaining as rchain
        from cli.main import main

        monkeypatch.setattr(rchain, "parallel_execute", _make_fake_executor_result)

        study_file = tmp_path / "three_axis.yaml"
        study_file.write_text(self.GRID_YAML, encoding="utf-8")
        rc = main(["run", "--summary-only", "--no-persist", str(study_file)])
        out = capsys.readouterr().out

        assert rc == 0
        cell_lines = [line for line in out.splitlines() if line.startswith("cell: ")]
        assert len(cell_lines) == 2
        for line in cell_lines:
            tokens = [token for token in line.split() if "=" in token]
            assert [t.split("=", 1)[0] for t in tokens[:3]] == [
                "equity_allocation",
                "withdrawal_rate",
                "horizon_years",
            ]
        assert "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=3" in out
        assert "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=4" in out


class TestGridCliReferenceChained:
    GRID_YAML = """\
metadata:
  name: "Grid Reference Chained Study"
dataset:
  identifier: "TEST_DATASET"
cohorts:
  horizon_years: [3, 4]
allocation_policy:
  type: "ConstantAllocationPolicy"
  equity_allocation: [0.5]
withdrawal_policy:
  type: "FixedRealWithdrawalPolicy"
  withdrawal_rate: [0.04]
"""

    @pytest.fixture
    def mock_dataset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from infrastructure.persistence.codecs import DefaultDatasetResolver

        def mock_resolve(self: DefaultDatasetResolver, identifier: str) -> Dataset:
            return _synthetic_dataset(500)

        monkeypatch.setattr(DefaultDatasetResolver, "resolve", mock_resolve)

    def test_reference_chained_grid_prints_chaining_and_per_cell(
        self,
        tmp_path: Path,
        mock_dataset: None,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--reference-chained grid runs report chaining + per-cell summaries."""
        import infrastructure.execution.reference_chaining as rchain
        from cli.main import main

        monkeypatch.setattr(rchain, "parallel_execute", _make_fake_executor_result)

        study_file = tmp_path / "grid.yaml"
        study_file.write_text(self.GRID_YAML, encoding="utf-8")
        rc = main(
            ["run", "--reference-chained", "--summary-only", "--no-persist", str(study_file)]
        )
        out = capsys.readouterr().out

        assert rc == 0
        assert "Reference Chained:" in out
        assert "Chained Groups:" in out
        assert "Longest Path:" in out
        assert "Month-Work:" in out
        assert "Per-Cell Results (grid):" in out
        assert "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=3" in out
        assert "cell: equity_allocation=0.5 withdrawal_rate=0.04 horizon_years=4" in out

    def test_reference_chained_reproduces_canonical_engine(self) -> None:
        """Reference Chained reproduces the canonical Decimal engine exactly on
        a representative multi-horizon grid.

        This is the key correctness contract of the sole reference strategy:
        executing the plan through ``execute_reference_chained`` (what a no-flag
        run dispatches) must equal ``sequential_execute`` with the canonical
        engine evaluated directly, field for field on every unit.
        """
        plan = build_grid_plan(_synthetic_dataset())
        assert (
            expected_reference_chaining_report(plan).derived_results > 0
        ), "fixture must be chaining-eligible"
        canonical = sequential_execute(plan, summary_only=True).results
        chained = execute_reference_chained(plan, max_workers=1, summary_only=True)
        chained_results = chained.experiment_result.simulation_results

        assert len(chained_results) == len(canonical)
        for ref, got in zip(canonical, chained_results, strict=True):
            assert ref.statistics.success == got.statistics.success
            assert ref.statistics.failure_month == got.statistics.failure_month
            assert ref.statistics.months_simulated == got.statistics.months_simulated
            assert ref.statistics.final_wealth == got.statistics.final_wealth

    def test_reference_chained_and_fast_path_rejected_together(
        self,
        tmp_path: Path,
        mock_dataset: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Combining the two execution-mode flags is rejected, not merged."""
        from cli.main import main

        study_file = tmp_path / "grid.yaml"
        study_file.write_text(self.GRID_YAML, encoding="utf-8")
        rc = main(
            [
                "run",
                "--reference-chained",
                "--fast-path",
                "--summary-only",
                "--no-persist",
                str(study_file),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 2
        assert "--reference-chained" in out
        assert "--fast-path" in out


def _make_fake_executor_result(plan: ResearchPlan, **kwargs: object) -> ResearchExecutionResult:
    """A fake ResearchExecutionResult whose statistics satisfy the per-cell block."""
    from datetime import date

    from engine.application.simulation import (
        ExperimentDefinition as EngineExperimentDefinition,
        ExperimentRun,
        SimulationResult,
        SimulationStatistics,
        SimulationTimeline,
    )
    from engine.application.simulation_context import SimulationContext

    results = tuple(
        SimulationResult(
            timeline=SimulationTimeline(monthly_results=()),
            statistics=SimulationStatistics(
                final_wealth=_WEALTH,
                max_drawdown=0.0,
                success=True,
                failure_month=None,
                months_simulated=48,
                execution_time_seconds=0.01,
            ),
        )
        for _ in plan.units
    )
    contexts = tuple(
        SimulationContext(
            experiment_name="fake",
            cohort="c",
            start_date=date(2000, 1, 1),
            horizon_months=48,
            initial_wealth=_WEALTH,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
        for unit in plan.units
    )
    engine_def = EngineExperimentDefinition(
        name=plan.experiment_definition.name,
        description="fake",
        simulation_contexts=contexts,
    )
    return ResearchExecutionResult(
        plan=plan,
        experiment_result=ExperimentRun(definition=engine_def, simulation_results=results),
    )


class TestFalsyArrayValuePreservation:
    """Declared array values are the actual policy even when falsy.

    ``build_study_plan`` builds policies from the declared value arrays; a
    legitimate explicit ``0.0`` (100% bonds / 0% withdrawal) must survive — it
    must not be replaced by any default via falsiness.
    """

    @staticmethod
    def _build(config_data: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> BuiltStudy:
        def mock_resolve(self: DefaultDatasetResolver, identifier: str) -> Dataset:
            return _synthetic_dataset()

        monkeypatch.setattr(DefaultDatasetResolver, "resolve", mock_resolve)
        config = StudyConfiguration.from_yaml(config_data)
        return build_study_plan(config, None, _WEALTH)

    def test_zero_allocation_value_in_array(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built = self._build(
            {
                "metadata": {"name": "zero-alloc"},
                "dataset": {"identifier": "TEST_DATASET"},
                "cohorts": {"horizon_years": [4]},
                "allocation_policy": {
                    "type": "ConstantAllocationPolicy",
                    "equity_allocation": [0.0],
                },
                "withdrawal_policy": {
                    "type": "FixedRealWithdrawalPolicy",
                    "withdrawal_rate": [0.04],
                },
            },
            monkeypatch,
        )
        for unit in built.plan.units:
            alloc = cast(ConstantAllocationPolicy, unit.allocation_policy)
            assert alloc.equity_allocation == Decimal("0.0")

    def test_zero_withdrawal_value_in_array(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built = self._build(
            {
                "metadata": {"name": "zero-withdraw"},
                "dataset": {"identifier": "TEST_DATASET"},
                "cohorts": {"horizon_years": [4]},
                "allocation_policy": {
                    "type": "ConstantAllocationPolicy",
                    "equity_allocation": [0.5],
                },
                "withdrawal_policy": {
                    "type": "FixedRealWithdrawalPolicy",
                    "withdrawal_rate": [0.0],
                },
            },
            monkeypatch,
        )
        for unit in built.plan.units:
            withdraw = cast(FixedRealWithdrawalPolicy, unit.withdrawal_policy)
            assert withdraw.withdrawal_rate == Decimal("0.0")
