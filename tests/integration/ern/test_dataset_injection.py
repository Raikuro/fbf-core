"""Dataset injection through the public application boundary."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fbf.core.application import run_study
from fbf.core.datasets import load_canonical_dataset
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionBackend, ExecutionOptions
from fbf.core.study import StudyConfiguration


def test_run_study_uses_injected_canonical_dataset() -> None:
    """Injection smoke test against current canonical data, not 2016 vintage."""
    dataset = load_canonical_dataset(Path("data/inputs/ern"))
    config = StudyConfiguration(
        name="canonical-injection-smoke",
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
            backend=ExecutionBackend.FAST,
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
