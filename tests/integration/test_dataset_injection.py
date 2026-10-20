"""Dataset injection through the public application boundary."""

from __future__ import annotations

from decimal import Decimal

from fbf.core.application import run_study
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionBackend, ExecutionOptions
from fbf.core.study import StudyConfiguration
from tests.oracle.ern.published_dataset import load_published_ern_dataset


def test_run_study_uses_injected_published_dataset() -> None:
    dataset = load_published_ern_dataset()
    config = StudyConfiguration(
        name="published-injection-smoke",
        description="",
        version="",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.5"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.04"),),
        horizon_years=(30,),
        cohort_horizon_years=60,
        expense_ratio=Decimal("0.0005"),
    )
    result = run_study(
        config=config,
        data_dir="unused-data-dir",
        initial_wealth=Money(Decimal("1000000"), Currency.EUR),
        options=ExecutionOptions(
            backend=ExecutionBackend.REFERENCE,
            summary_only=True,
        ),
        dataset=dataset,
    )

    assert len(result.experiment_result.simulation_results) == 1739
    successes = sum(
        1 for item in result.experiment_result.simulation_results
        if item.statistics.success
    )
    assert round(100 * successes / 1739) == 95
