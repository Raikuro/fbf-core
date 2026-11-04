"""ERN Part 2 deterministic warm-up timing validation.

The Part 2 article's warm-up example assumes a constant 4% real annual return
and a withdrawal at the beginning of the first month. The published maximum
annual withdrawal rates are 3.92%, 4.12%, 4.33%, 4.79%, and 5.66%.

This test reproduces those values through the production application path by
running a synthetic constant-return dataset. Withdrawals are linear in the
withdrawal rate, so two executed rates determine the exact maximum rate for
each final-value target. The result pins the beginning-of-month withdrawal
convention used by the ERN cohort window.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from fbf.core.application import run_study
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution import ExecutionBackend, ExecutionOptions
from fbf.core.study import StudyConfiguration

_INITIAL_WEALTH = Decimal("1000000")
_ANNUAL_RETURN = Decimal("0.04")
_PROBE_RATES = (Decimal("0"), Decimal("0.04"))
_PUBLISHED_WARMUP = {
    (30, Decimal("0")): Decimal("5.66"),
    (30, Decimal("0.5")): Decimal("4.79"),
    (60, Decimal("0")): Decimal("4.33"),
    (60, Decimal("0.5")): Decimal("4.12"),
    (60, Decimal("1.0")): Decimal("3.92"),
}


def _next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _constant_return_dataset() -> Dataset:
    equity = AssetClass(id="equity", name="", description="")
    bond = AssetClass(id="bond", name="", description="")
    monthly_return = (_ANNUAL_RETURN + Decimal("1")) ** (
        Decimal("1") / Decimal("12")
    ) - Decimal("1")

    snapshots: list[MarketSnapshot] = []
    current = date(1871, 1, 31)
    level = Decimal("100")
    for _ in range(60 * 12 + 1):
        snapshots.append(
            MarketSnapshot(
                date=current,
                index_levels={equity: level, bond: level},
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=level,
            )
        )
        current = _next_month(current)
        level *= Decimal("1") + monthly_return

    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _warmup_config() -> StudyConfiguration:
    return StudyConfiguration(
        name="part2-warmup",
        description="",
        version="",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("1.0"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=_PROBE_RATES,
        horizon_years=(30, 60),
        final_value_target_values=(Decimal("0"),),
        expense_ratio=Decimal("0"),
        cohort_horizon_years=60,
        cohort_start_date=date(1871, 1, 31),
        cohort_end_date=date(1871, 1, 31),
    )


def test_warmup_matches_published_beginning_of_month_values() -> None:
    result = run_study(
        config=_warmup_config(),
        data_dir="unused",
        initial_wealth=Money(_INITIAL_WEALTH, Currency.EUR),
        options=ExecutionOptions(
            backend=ExecutionBackend.FAST,
            summary_only=True,
            workers=1,
        ),
        dataset=_constant_return_dataset(),
    )

    terminal_wealth: dict[tuple[Decimal, int], Decimal] = {}
    for unit, simulation in zip(
        result.plan.units,
        result.experiment_result.simulation_results,
        strict=True,
    ):
        rate = Decimal(str(unit.parameter_config.values["withdrawal_rate"]))
        horizon = int(unit.parameter_config.values["horizon_years"])
        terminal_wealth[(rate, horizon)] = simulation.statistics.final_wealth.amount

    for (horizon, target), published in _PUBLISHED_WARMUP.items():
        no_withdrawal = terminal_wealth[(Decimal("0"), horizon)]
        probe_withdrawal = terminal_wealth[(_PROBE_RATES[1], horizon)]
        withdrawal_cost = (no_withdrawal - probe_withdrawal) / _PROBE_RATES[1]
        maximum_rate = (
            (no_withdrawal - target * _INITIAL_WEALTH) / withdrawal_cost * Decimal("100")
        )
        rounded = maximum_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        assert rounded == published, (
            f"horizon={horizon}, target={target}: "
            f"FBF={maximum_rate}% -> {rounded}%, published={published}%"
        )
