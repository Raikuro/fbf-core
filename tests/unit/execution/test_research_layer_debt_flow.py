"""Research-layer debt flow tests for Part 49 (K.7).

Verifies that debt parameters flow correctly from StudyConfiguration through
PlannedSimulationUnit to SimulationContext, and that the Part49WithdrawalPolicy
produces correct loan draw amounts.

These tests validate the research-layer plumbing, not the engine debt mechanics
(which are covered by K.4-K.6 tests).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.study.builder import StudyConfiguration
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import PlannedSimulationUnit, materialize_research_plan

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

EQUITY = AssetClass(id="equity", name="", description="")
BOND = AssetClass(id="bond", name="", description="")


def _make_dataset(n_months: int = 13) -> Dataset:
    """Create a minimal dataset with constant prices."""
    snapshots = []
    pe, pb = Decimal("100"), Decimal("50")
    d = date(2020, 1, 1)
    for _i in range(n_months + 1):
        snapshots.append(MarketSnapshot(
            date=d,
            index_levels={EQUITY: pe, BOND: pb},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=pe,
        ))
        d = date(d.year + (d.month // 12), (d.month % 12) + 1, 1)
    return Dataset(snapshots=snapshots, frequency="monthly", version="test")


def _make_experiment_def() -> ExperimentDefinition:
    """Create a minimal ExperimentDefinition."""
    dataset = _make_dataset()
    return ExperimentDefinition(
        name="test-part49",
        description="K.7 research layer test",
        dataset=dataset,
        horizon_months=13,
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        cohorts=(CohortSpecification(start_date=dataset[0].date),),
        allocation_policies=(ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),),
        withdrawal_policies=(Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),),
    )


def _make_portfolio() -> Portfolio:
    return Portfolio(holdings=(
        AssetHolding(asset_class=EQUITY, units=Decimal("5000")),
        AssetHolding(asset_class=BOND, units=Decimal("10000")),
    ))


def _make_cohort(dataset: Dataset) -> CohortSpecification:
    return CohortSpecification(start_date=dataset[0].date)


# ---------------------------------------------------------------------------
# StudyConfiguration debt parsing
# ---------------------------------------------------------------------------


class TestStudyConfigurationDebtParsing:
    """StudyConfiguration.from_yaml() must parse the optional debt section."""

    def test_debt_section_parsed(self) -> None:
        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_swr_h720"},
            "cohorts": {"horizon_years": [30]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            "debt": {
                "interest_rate": 0.05,
                "ltv_limit": 0.75,
                "loan_draw_rate": 0.01,
            },
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.debt_interest_rate == Decimal("0.05")
        assert config.debt_ltv_limit == Decimal("0.75")
        assert config.debt_loan_draw_rate == Decimal("0.01")

    def test_debt_section_absent(self) -> None:
        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_swr_h720"},
            "cohorts": {"horizon_years": [30]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.debt_interest_rate is None
        assert config.debt_ltv_limit is None
        assert config.debt_loan_draw_rate is None

    def test_debt_section_partial(self) -> None:
        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_swr_h720"},
            "cohorts": {"horizon_years": [30]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            "debt": {
                "interest_rate": 0.06,
            },
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.debt_interest_rate == Decimal("0.06")
        assert config.debt_ltv_limit is None
        assert config.debt_loan_draw_rate is None

    def test_debt_invalid_type(self) -> None:
        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_swr_h720"},
            "cohorts": {"horizon_years": [30]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            "debt": "invalid",
        }
        with pytest.raises(ValueError, match="debt must be a mapping"):
            StudyConfiguration.from_yaml(data)

    def test_debt_loan_draw_requires_interest_rate(self) -> None:
        """loan_draw_rate without interest_rate must be rejected."""
        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_swr_h720"},
            "cohorts": {"horizon_years": [30]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            "debt": {
                "loan_draw_rate": 0.01,
            },
        }
        with pytest.raises(ValueError, match="debt.interest_rate is required"):
            StudyConfiguration.from_yaml(data)

    def test_debt_interest_rate_without_ltv_valid(self) -> None:
        """interest_rate without ltv_limit is allowed (LTV check becomes no-op)."""
        data = {
            "metadata": {"name": "test"},
            "dataset": {"identifier": "ern_swr_h720"},
            "cohorts": {"horizon_years": [30]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.75],
            },
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            "debt": {
                "interest_rate": 0.06,
            },
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.debt_interest_rate == Decimal("0.06")
        assert config.debt_ltv_limit is None


# ---------------------------------------------------------------------------
# PlannedSimulationUnit debt fields
# ---------------------------------------------------------------------------


class TestPlannedSimulationUnitDebtFields:
    """PlannedSimulationUnit must carry debt parameters."""

    def test_debt_fields_default_none(self) -> None:
        dataset = _make_dataset()
        unit = PlannedSimulationUnit(
            cohort=_make_cohort(dataset),
            parameter_config=ParameterConfiguration(
                {"withdrawal_rate": 0.04, "horizon_years": 30}
            ),
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            initial_portfolio=_make_portfolio(),
            dataset=dataset,
        )
        assert unit.interest_rate is None
        assert unit.ltv_limit is None
        assert unit.loan_draw_rate is None

    def test_debt_fields_set(self) -> None:
        dataset = _make_dataset()
        unit = PlannedSimulationUnit(
            cohort=_make_cohort(dataset),
            parameter_config=ParameterConfiguration(
                {"withdrawal_rate": 0.04, "horizon_years": 30}
            ),
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            initial_portfolio=_make_portfolio(),
            dataset=dataset,
            interest_rate=Decimal("0.05"),
            ltv_limit=Decimal("0.75"),
            loan_draw_rate=Decimal("0.01"),
        )
        assert unit.interest_rate == Decimal("0.05")
        assert unit.ltv_limit == Decimal("0.75")
        assert unit.loan_draw_rate == Decimal("0.01")


# ---------------------------------------------------------------------------
# materialize_research_plan debt passthrough
# ---------------------------------------------------------------------------


class TestMaterializeResearchPlanDebt:
    """materialize_research_plan must pass debt parameters to units."""

    def test_debt_params_propagated(self) -> None:
        dataset = _make_dataset()
        exp_def = _make_experiment_def()
        cohorts = (_make_cohort(dataset),)
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.04, "horizon_years": 30}
        ),)

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=dataset,
            cohorts=cohorts,
            param_configs=param_configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=lambda pc: 13,
            policy_resolver=lambda pc: (
                ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
                Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            ),
            interest_rate=Decimal("0.05"),
            ltv_limit=Decimal("0.75"),
            loan_draw_rate=Decimal("0.01"),
        )
        unit = plan.units[0]
        assert unit.interest_rate == Decimal("0.05")
        assert unit.ltv_limit == Decimal("0.75")
        assert unit.loan_draw_rate == Decimal("0.01")

    def test_debt_params_none_when_omitted(self) -> None:
        dataset = _make_dataset()
        exp_def = _make_experiment_def()
        cohorts = (_make_cohort(dataset),)
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.04, "horizon_years": 30}
        ),)

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=dataset,
            cohorts=cohorts,
            param_configs=param_configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=lambda pc: 13,
            policy_resolver=lambda pc: (
                ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
                Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            ),
        )
        unit = plan.units[0]
        assert unit.interest_rate is None
        assert unit.ltv_limit is None
        assert unit.loan_draw_rate is None


# ---------------------------------------------------------------------------
# ResearchExecutor context translation
# ---------------------------------------------------------------------------


class TestResearchExecutorContextTranslation:
    """ResearchExecutor must pass debt params to SimulationContext."""

    def test_debt_params_in_context(self) -> None:
        from fbf.core.execution.executor import ResearchExecutor
        from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
        from fbf.core.execution.pipeline.executor import SimulationExecutor
        from fbf.core.execution.pipeline.runner import SimulationRunner

        dataset = _make_dataset()
        exp_def = _make_experiment_def()
        cohorts = (_make_cohort(dataset),)
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.04, "horizon_years": 30}
        ),)

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=dataset,
            cohorts=cohorts,
            param_configs=param_configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=lambda pc: 13,
            policy_resolver=lambda pc: (
                ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
                Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            ),
            interest_rate=Decimal("0.05"),
            ltv_limit=Decimal("0.75"),
            loan_draw_rate=Decimal("0.01"),
        )

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
            )
        )
        unit = plan.units[0]
        ctx = executor._create_context_for_unit(plan.experiment_definition, unit)
        assert isinstance(ctx, SimulationContext)
        assert ctx.interest_rate == Decimal("0.05")
        assert ctx.ltv_limit == Decimal("0.75")
        assert ctx.loan_draw_rate == Decimal("0.01")

    def test_debt_params_none_when_omitted(self) -> None:
        from fbf.core.execution.executor import ResearchExecutor
        from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
        from fbf.core.execution.pipeline.executor import SimulationExecutor
        from fbf.core.execution.pipeline.runner import SimulationRunner

        dataset = _make_dataset()
        exp_def = _make_experiment_def()
        cohorts = (_make_cohort(dataset),)
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.04, "horizon_years": 30}
        ),)

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=dataset,
            cohorts=cohorts,
            param_configs=param_configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=lambda pc: 13,
            policy_resolver=lambda pc: (
                ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
                Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            ),
        )

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
            )
        )
        unit = plan.units[0]
        ctx = executor._create_context_for_unit(plan.experiment_definition, unit)
        assert isinstance(ctx, SimulationContext)
        assert ctx.interest_rate is None
        assert ctx.ltv_limit is None
        assert ctx.loan_draw_rate is None


# ---------------------------------------------------------------------------
# Part49WithdrawalPolicy behaviour
# ---------------------------------------------------------------------------


class TestPart49WithdrawalPolicy:
    """Part49WithdrawalPolicy must compute both withdrawal and loan draw."""

    def _make_decision_context(
        self,
        sim_ctx: SimulationContext,
    ) -> DecisionContext:
        portfolio = sim_ctx.initial_portfolio
        dataset = sim_ctx.dataset
        equity_alloc = AllocationTarget(weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")})
        return DecisionContext(
            date=dataset[0].date,
            period_index=0,
            simulation_context=sim_ctx,
            portfolio=portfolio,
            current_allocation=Allocation(weights={EQUITY: Decimal("0.75"), BOND: Decimal("0.25")}),
            target_allocation=equity_alloc,
            market_snapshot=dataset[0],
            dataset=dataset,
        )

    def test_withdrawal_and_loan_draw(self) -> None:
        dataset = _make_dataset()
        policy = Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        portfolio = _make_portfolio()

        sim_ctx = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=dataset[0].date,
            horizon_months=13,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=policy,
            loan_draw_rate=Decimal("0.01"),
        )

        decision_ctx = self._make_decision_context(sim_ctx)
        decision = policy.decide(decision_ctx)

        # monthly_withdrawal = 1_000_000 * 0.04 / 12
        expected_withdrawal = Decimal("1000000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == expected_withdrawal
        # monthly_loan = 1_000_000 * 0.01 / 12
        expected_loan = Decimal("1000000") * Decimal("0.01") / Decimal("12")
        assert decision.loan_draw_amount == expected_loan

    def test_zero_loan_draw_when_no_rate(self) -> None:
        dataset = _make_dataset()
        policy = Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04"))
        portfolio = _make_portfolio()

        sim_ctx = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=dataset[0].date,
            horizon_months=13,
            initial_wealth=Money(Decimal("1000000"), Currency.EUR),
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
            withdrawal_policy=policy,
        )

        decision_ctx = self._make_decision_context(sim_ctx)
        decision = policy.decide(decision_ctx)

        expected_withdrawal = Decimal("1000000") * Decimal("0.04") / Decimal("12")
        assert decision.nominal_amount.amount == expected_withdrawal
        assert decision.loan_draw_amount == Decimal("0")


# ---------------------------------------------------------------------------
# Full pipeline integration (research-layer end-to-end)
# ---------------------------------------------------------------------------


class TestPart49ResearchLayerEndToEnd:
    """End-to-end: StudyConfiguration -> plan -> context -> pipeline execution."""

    def test_pipeline_executes_with_debt(self) -> None:
        from fbf.core.execution.executor import ResearchExecutor
        from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
        from fbf.core.execution.pipeline.executor import SimulationExecutor
        from fbf.core.execution.pipeline.runner import SimulationRunner

        dataset = _make_dataset()
        exp_def = _make_experiment_def()
        cohorts = (_make_cohort(dataset),)
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.04, "horizon_years": 30}
        ),)

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=dataset,
            cohorts=cohorts,
            param_configs=param_configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=lambda pc: 13,
            policy_resolver=lambda pc: (
                ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
                Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            ),
            interest_rate=Decimal("0.05"),
            ltv_limit=Decimal("0.75"),
            loan_draw_rate=Decimal("0.01"),
        )

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
            )
        )
        result = executor.execute(plan)
        assert len(result.experiment_result.simulation_results) == 1

        sim_result = result.experiment_result.simulation_results[0]
        debt_snapshots = [
            mr.debt_snapshot
            for mr in sim_result.timeline.monthly_results
            if mr.debt_snapshot is not None
        ]
        assert len(debt_snapshots) > 0
        assert debt_snapshots[-1].loan_balance > debt_snapshots[0].loan_balance

    def test_pipeline_no_debt_when_params_none(self) -> None:
        from fbf.core.execution.executor import ResearchExecutor
        from fbf.core.execution.pipeline.default_pipeline import create_default_pipeline
        from fbf.core.execution.pipeline.executor import SimulationExecutor
        from fbf.core.execution.pipeline.runner import SimulationRunner

        dataset = _make_dataset()
        exp_def = _make_experiment_def()
        cohorts = (_make_cohort(dataset),)
        param_configs = (ParameterConfiguration(
            {"withdrawal_rate": 0.04, "horizon_years": 30}
        ),)

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=dataset,
            cohorts=cohorts,
            param_configs=param_configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=lambda pc: 13,
            policy_resolver=lambda pc: (
                ConstantAllocationPolicy(equity_allocation=Decimal("0.75")),
                Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.04")),
            ),
        )

        executor = ResearchExecutor(
            simulation_executor=SimulationExecutor(
                simulation_runner=SimulationRunner(pipeline=create_default_pipeline())
            )
        )
        result = executor.execute(plan)
        sim_result = result.experiment_result.simulation_results[0]
        debt_snapshots = [
            mr.debt_snapshot
            for mr in sim_result.timeline.monthly_results
            if mr.debt_snapshot is not None
        ]
        assert len(debt_snapshots) == 0
