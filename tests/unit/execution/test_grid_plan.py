"""Unit tests for plan materialization in ``research/domain/plan.py``.

Covers:
- ``materialize_research_plan`` per-unit horizons, per-parameter policies,
  canonical-trajectory prefix slices, and shared slice identity
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.decisions import AllocationDecision, WithdrawalDecision
from fbf.core.domain.policies.withdrawal_policy import WithdrawalPolicy
from fbf.core.study.internal.cohort.generator import CohortGenerator
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.experiment.definition import ExperimentDefinition
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration
from fbf.core.study.plan import (
    materialize_research_plan,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class StubAllocationPolicy(AllocationPolicy):
    def __init__(self, equity: Decimal) -> None:
        self.equity_allocation = equity

    def decide(self, context: object) -> AllocationDecision:
        asset = AssetClass(id="equity", name="", description="")
        bond = AssetClass(id="bond", name="", description="")
        return AllocationDecision(
            reason="stub",
            allocation_target=AllocationTarget(
                weights={
                    asset: self.equity_allocation,
                    bond: Decimal("1") - self.equity_allocation,
                }
            ),
        )


class StubWithdrawalPolicy(WithdrawalPolicy):
    def __init__(self, rate: Decimal) -> None:
        self.withdrawal_rate = rate

    def decide(self, context: object) -> WithdrawalDecision:
        return WithdrawalDecision(
            reason="stub",
            nominal_amount=Money(Decimal("0"), Currency.EUR),
            real_amount=Money(Decimal("0"), Currency.EUR),
        )


# ---------------------------------------------------------------------------
# Shared factories
# ---------------------------------------------------------------------------


def _make_asset() -> AssetClass:
    return AssetClass(id="equity", name="", description="")


def _make_snapshot(month: int) -> MarketSnapshot:
    asset = _make_asset()
    return MarketSnapshot(
        date=date(2000 + (month - 1) // 12, (month - 1) % 12 + 1, 1),
        index_levels={asset: Decimal("100.00")},
        inflation=Decimal("0.00"),
        inflation_cumulative=Decimal("0.00"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100.00"),
    )


def _make_dataset(num_months: int) -> Dataset:
    return Dataset(
        snapshots=tuple(_make_snapshot(m) for m in range(1, num_months + 1)),
        frequency="monthly",
        version="1.0",
    )


def _make_portfolio() -> Portfolio:
    asset = _make_asset()
    return Portfolio(holdings=(AssetHolding(asset_class=asset, units=Decimal("1000")),))


def _make_experiment_def(
    dataset: Dataset, cohorts: tuple[CohortSpecification, ...], horizon_months: int
) -> ExperimentDefinition:
    return ExperimentDefinition(
        name="grid-test",
        description="grid test experiment",
        dataset=dataset,
        horizon_months=horizon_months,
        initial_wealth=Money(Decimal("100000"), Currency.EUR),
        cohorts=cohorts,
        allocation_policies=(StubAllocationPolicy(Decimal("0.75")),),
        withdrawal_policies=(StubWithdrawalPolicy(Decimal("0.04")),),
    )


def _horizon_resolver(config: ParameterConfiguration, default_years: int = 5) -> int:
    if "horizon_years" in config.values:
        return int(config.get("horizon_years")) * 12
    return default_years * 12


def _policy_resolver(
    config: ParameterConfiguration,
    literal_alloc: AllocationPolicy,
    literal_withd: WithdrawalPolicy,
) -> tuple[AllocationPolicy, WithdrawalPolicy]:
    if "equity_allocation" in config.values:
        alloc: AllocationPolicy = StubAllocationPolicy(
            Decimal(str(config.get("equity_allocation")))
        )
    else:
        alloc = literal_alloc
    if "withdrawal_rate" in config.values:
        withd: WithdrawalPolicy = StubWithdrawalPolicy(
            Decimal(str(config.get("withdrawal_rate")))
        )
    else:
        withd = literal_withd
    return alloc, withd


# ---------------------------------------------------------------------------
# materialize_research_plan tests
# ---------------------------------------------------------------------------


class TestMaterializeResearchPlan:
    def test_horizon_axis_produces_correct_per_unit_horizons(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)
        cohorts = (cohorts[0], cohorts[1])
        configs = (
            ParameterConfiguration({"horizon_years": 3}),
            ParameterConfiguration({"horizon_years": 4}),
        )
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        assert len(plan) == 4
        by_horizon: dict[int, list[int]] = {}
        for unit in plan:
            assert unit.horizon_months is not None
            by_horizon.setdefault(unit.horizon_months, []).append(
                len(unit.dataset.snapshots)
            )
        assert sorted(by_horizon) == [36, 48]
        assert set(by_horizon[36]) == {36}
        assert set(by_horizon[48]) == {48}

    def test_parameter_values_drive_per_unit_policies(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)[:1]
        configs = (
            ParameterConfiguration({"equity_allocation": 0.75, "withdrawal_rate": 0.04}),
            ParameterConfiguration({"equity_allocation": 0.25, "withdrawal_rate": 0.05}),
        )
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        unit_75, unit_25 = plan.units
        alloc_75 = cast(StubAllocationPolicy, unit_75.allocation_policy)
        alloc_25 = cast(StubAllocationPolicy, unit_25.allocation_policy)
        withd_75 = cast(StubWithdrawalPolicy, unit_75.withdrawal_policy)
        withd_25 = cast(StubWithdrawalPolicy, unit_25.withdrawal_policy)
        assert alloc_75.equity_allocation == Decimal("0.75")
        assert alloc_25.equity_allocation == Decimal("0.25")
        assert withd_75.withdrawal_rate == Decimal("0.04")
        assert withd_25.withdrawal_rate == Decimal("0.05")

    def test_different_configs_are_distinct_policy_objects(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)[:1]
        configs = (
            ParameterConfiguration({"equity_allocation": 0.75}),
            ParameterConfiguration({"equity_allocation": 0.50}),
        )
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        assert plan.units[0].allocation_policy is not plan.units[1].allocation_policy

    def test_literal_policies_are_fallback_when_params_absent(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)[:1]
        configs = (ParameterConfiguration({"glidepath_duration": 5}),)
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.60"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.06"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        unit = plan.units[0]
        assert unit.allocation_policy is literal_alloc
        assert unit.withdrawal_policy is literal_withd
        assert unit.horizon_months == 60

    def test_shorter_horizons_are_prefix_slices_of_longest(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)[:1]
        configs = (
            ParameterConfiguration({"horizon_years": 3}),
            ParameterConfiguration({"horizon_years": 4}),
        )
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        short = plan.units[0]
        long_unit = plan.units[1]
        assert short.dataset.snapshots == long_unit.dataset.snapshots[:36]

    def test_units_share_slice_object_for_same_cohort_and_horizon(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)[:1]
        configs = (
            ParameterConfiguration({"horizon_years": 4, "equity_allocation": 0.75}),
            ParameterConfiguration({"horizon_years": 4, "equity_allocation": 0.25}),
        )
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        assert plan.units[0].dataset is plan.units[1].dataset

    def test_identity_remains_cohort_start_date_and_parameter_config(self) -> None:
        canonical = _make_dataset(60)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 48)[:2]
        configs = (
            ParameterConfiguration({"horizon_years": 4, "equity_allocation": 0.75}),
            ParameterConfiguration({"horizon_years": 3, "equity_allocation": 0.75}),
        )
        exp_def = _make_experiment_def(canonical, cohorts, 48)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        plan = materialize_research_plan(
            experiment_def=exp_def,
            canonical_trajectory=canonical,
            cohorts=cohorts,
            param_configs=configs,
            initial_portfolio=_make_portfolio(),
            horizon_resolver=_horizon_resolver,
            policy_resolver=lambda c: _policy_resolver(c, literal_alloc, literal_withd),
        )

        identities = {(u.cohort.start_date, u.parameter_config) for u in plan}
        assert len(identities) == len(plan.units)

    def test_infeasible_horizon_fails_clearly(self) -> None:
        canonical = _make_dataset(48)
        cohorts = CohortGenerator.generate_rolling_monthly(canonical, 36)[:1]
        # A cohort with only 48 months remaining but a 60-month request must fail.
        configs = (ParameterConfiguration({"horizon_years": 5}),)
        exp_def = _make_experiment_def(canonical, cohorts, 36)
        literal_alloc = StubAllocationPolicy(Decimal("0.75"))
        literal_withd = StubWithdrawalPolicy(Decimal("0.04"))

        with pytest.raises(ValueError, match="Insufficient dataset history"):
            materialize_research_plan(
                experiment_def=exp_def,
                canonical_trajectory=canonical,
                cohorts=cohorts,
                param_configs=configs,
                initial_portfolio=_make_portfolio(),
                horizon_resolver=_horizon_resolver,
                policy_resolver=lambda c: _policy_resolver(
                    c, literal_alloc, literal_withd
                ),
            )
