"""Experiment E research adapter — ERN Part 20 deterministic case study.

This module implements the Experiment E composition in the research layer,
using only the generic core capabilities implemented in Phases 1–3.

Experiment E is a 10-year deterministic mechanical case study from
ERN Part 20 Tables 01/05. It defines four trajectories:

1. Bear→Bull, Static 80% equity
2. Bear→Bull, 70→90% annual glidepath
3. Bull→Bear, Static 80% equity
4. Bull→Bear, 70→90% annual glidepath

All Experiment E-specific configuration lives here. No generic execution
mechanisms are introduced; the adapter composes existing core capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fbf.core.datasets import build_prescribed_dataset
from fbf.core.domain.model.allocation import AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.return_sequence import ReturnSequence, expand_annual_to_monthly
from fbf.core.domain.policies import (
    ConstantAllocationPolicy,
    EscalatingWithdrawalPolicy,
    GlidepathAllocationPolicy,
    GlidepathCadence,
)
from fbf.core.domain.policies.frequency import WithdrawalFrequency
from fbf.core.execution import (
    DeterministicResult,
    DeterministicTrajectory,
    execute_deterministic_trajectory,
)
from fbf.core.execution.pipeline.schedule import ExecutionSchedule, StepCadence
from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import PortfolioRebalanceStep

__all__ = [
    "ExperimentECase",
    "ExperimentEResult",
    "build_experiment_e_trajectories",
    "execute_experiment_e",
]


# ---------------------------------------------------------------------------
# Experiment E Return Sequences (Article Tables 01/05)
# ---------------------------------------------------------------------------

# Bear→Bull annual returns from Article Table 01
_BEAR_BULL_ANNUAL_EQUITY = (
    Decimal("-0.30"),  # Year 1
    Decimal("-0.05"),  # Year 2
    Decimal("0.20"),   # Year 3
    Decimal("0.15"),   # Year 4
    Decimal("0.10"),   # Year 5
    Decimal("0.10"),   # Year 6
    Decimal("0.10"),   # Year 7
    Decimal("0.10"),   # Year 8
    Decimal("0.10"),   # Year 9
    Decimal("0.10"),   # Year 10
)

_BEAR_BULL_ANNUAL_BONDS = (
    Decimal("0.08"),   # Year 1
    Decimal("0.05"),   # Year 2
    Decimal("-0.01"),  # Year 3
    Decimal("0.01"),   # Year 4
    Decimal("0.02"),   # Year 5
    Decimal("0.02"),   # Year 6
    Decimal("0.02"),   # Year 7
    Decimal("0.02"),   # Year 8
    Decimal("0.02"),   # Year 9
    Decimal("0.02"),   # Year 10
)


def build_ern_table01_return_sequence() -> ReturnSequence:
    """Build the Bear→Bull ReturnSequence from ERN Table 01.

    Expands the 10 annual returns to 120 monthly returns using the
    documented annual-to-monthly conversion:

        monthly_return = (1 + annual_return) ** (1/12) - 1

    The start date is 1929-09-01 (matching the article's 1929 start).

    Returns
    -------
    ReturnSequence
        120 monthly equity and bond returns for the Bear→Bull scenario.
    """
    equity_monthly = expand_annual_to_monthly(_BEAR_BULL_ANNUAL_EQUITY)
    bond_monthly = expand_annual_to_monthly(_BEAR_BULL_ANNUAL_BONDS)

    return ReturnSequence(
        equity_returns=equity_monthly,
        bond_returns=bond_monthly,
        start_date=date(1929, 9, 1),
        name="ERN_Table01_BearBull",
    )


# ---------------------------------------------------------------------------
# Experiment E Configuration Constants
# ---------------------------------------------------------------------------

_EXPERIMENT_E_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)
_EXPERIMENT_E_HORIZON_MONTHS = 120
_EXPERIMENT_E_EXPENSE_RATIO = Decimal("0.0005")  # 0.05% p.a.

# Initial allocations
_STATIC_80_INITIAL_ALLOCATION = AllocationTarget(
    weights={
        AssetClass(id="equity", name="", description=""): Decimal("0.80"),
        AssetClass(id="bond", name="", description=""): Decimal("0.20"),
    }
)

_GLIDEPATH_70_90_INITIAL_ALLOCATION = AllocationTarget(
    weights={
        AssetClass(id="equity", name="", description=""): Decimal("0.70"),
        AssetClass(id="bond", name="", description=""): Decimal("0.30"),
    }
)

# Withdrawal policy: 3.5% initial, 2% annual escalation, annual frequency
_EXPERIMENT_E_WITHDRAWAL = EscalatingWithdrawalPolicy(
    withdrawal_rate=Decimal("0.035"),
    escalation_rate=Decimal("0.02"),
    frequency=WithdrawalFrequency.ANNUAL,
)

# Annual rebalance schedule
_EXPERIMENT_E_SCHEDULE = ExecutionSchedule(
    {PortfolioRebalanceStep: StepCadence.ANNUAL}
)


# ---------------------------------------------------------------------------
# Experiment E Trajectory Construction
# ---------------------------------------------------------------------------

def build_experiment_e_trajectories() -> list[DeterministicTrajectory]:
    """Build the four Experiment E deterministic trajectories.

    Returns the four cases:
    1. Bear→Bull, Static 80%
    2. Bear→Bull, 70→90% annual glidepath
    3. Bull→Bear, Static 80%
    4. Bull→Bear, 70→90% annual glidepath

    Each trajectory uses the Experiment E parameters:
    - $1M initial wealth
    - 3.5% initial withdrawal, 2% annual escalation
    - Annual withdrawal frequency
    - Annual rebalance
    - 10-year horizon (120 months)
    - 0.05% annual expense ratio
    - Annual glidepath cadence for glidepath cases

    Returns
    -------
    list[DeterministicTrajectory]
        Four trajectories ready for deterministic execution.
    """
    # 1. Build Bear→Bull return sequence and dataset
    bear_bull_seq = build_ern_table01_return_sequence()
    bear_bull_ds = build_prescribed_dataset(bear_bull_seq)

    # 2. Build Bull→Bear by reversing the ANNUAL source sequence
    bull_bear_seq = bear_bull_seq.reverse()
    bull_bear_ds = build_prescribed_dataset(bull_bear_seq)

    # 3. 70→90% annual glidepath (2pp/year, passive)
    glidepath_70_90 = GlidepathAllocationPolicy(
        start_equity=Decimal("0.70"),
        end_equity=Decimal("0.90"),
        slope=Decimal("0.02"),      # 2pp per YEAR
        mode="passive",
        cadence=GlidepathCadence.ANNUAL,
    )

    # 4. Static 80%
    static_80 = ConstantAllocationPolicy(equity_allocation=Decimal("0.80"))

    return [
        # 1. Bear→Bull, Static 80%
        DeterministicTrajectory(
            name="E_bear_bull_static_080",
            initial_wealth=_EXPERIMENT_E_INITIAL_WEALTH,
            initial_allocation=_STATIC_80_INITIAL_ALLOCATION,
            dataset=bear_bull_ds,
            allocation_policy=static_80,
            withdrawal_policy=_EXPERIMENT_E_WITHDRAWAL,
            horizon_months=_EXPERIMENT_E_HORIZON_MONTHS,
            expense_ratio=_EXPERIMENT_E_EXPENSE_RATIO,
            schedule=_EXPERIMENT_E_SCHEDULE,
        ),
        # 2. Bear→Bull, 70→90% annual glidepath
        DeterministicTrajectory(
            name="E_bear_bull_glidepath_070_090",
            initial_wealth=_EXPERIMENT_E_INITIAL_WEALTH,
            initial_allocation=_GLIDEPATH_70_90_INITIAL_ALLOCATION,
            dataset=bear_bull_ds,
            allocation_policy=glidepath_70_90,
            withdrawal_policy=_EXPERIMENT_E_WITHDRAWAL,
            horizon_months=_EXPERIMENT_E_HORIZON_MONTHS,
            expense_ratio=_EXPERIMENT_E_EXPENSE_RATIO,
            schedule=_EXPERIMENT_E_SCHEDULE,
        ),
        # 3. Bull→Bear, Static 80%
        DeterministicTrajectory(
            name="E_bull_bear_static_080",
            initial_wealth=_EXPERIMENT_E_INITIAL_WEALTH,
            initial_allocation=_STATIC_80_INITIAL_ALLOCATION,
            dataset=bull_bear_ds,
            allocation_policy=static_80,
            withdrawal_policy=_EXPERIMENT_E_WITHDRAWAL,
            horizon_months=_EXPERIMENT_E_HORIZON_MONTHS,
            expense_ratio=_EXPERIMENT_E_EXPENSE_RATIO,
            schedule=_EXPERIMENT_E_SCHEDULE,
        ),
        # 4. Bull→Bear, 70→90% annual glidepath
        DeterministicTrajectory(
            name="E_bull_bear_glidepath_070_090",
            initial_wealth=_EXPERIMENT_E_INITIAL_WEALTH,
            initial_allocation=_GLIDEPATH_70_90_INITIAL_ALLOCATION,
            dataset=bull_bear_ds,
            allocation_policy=glidepath_70_90,
            withdrawal_policy=_EXPERIMENT_E_WITHDRAWAL,
            horizon_months=_EXPERIMENT_E_HORIZON_MONTHS,
            expense_ratio=_EXPERIMENT_E_EXPENSE_RATIO,
            schedule=_EXPERIMENT_E_SCHEDULE,
        ),
    ]


# ---------------------------------------------------------------------------
# Experiment E Execution and Result Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ExperimentECase:
    """Identifies one Experiment E case for result lookup."""

    sequence: str  # "bear_bull" or "bull_bear"
    strategy: str  # "static_080" or "glidepath_070_090"


@dataclass(frozen=True, slots=True)
class ExperimentEResult:
    """Container for Experiment E execution results.

    Holds the deterministic results for all four cases, keyed by
    ExperimentECase for easy lookup by Phase 5.
    """

    cases: dict[ExperimentECase, DeterministicTrajectory]

    def get(self, case: ExperimentECase) -> DeterministicTrajectory:
        """Get the trajectory for a specific case."""
        return self.cases[case]

    def get_result(self, case: ExperimentECase) -> DeterministicResult:
        """Execute and return the deterministic result for a case."""
        trajectory = self.get(case)
        return execute_deterministic_trajectory(trajectory)


def execute_experiment_e() -> ExperimentEResult:
    """Execute all four Experiment E trajectories.

    Returns
    -------
    ExperimentEResult
        Container with all four executed cases.
    """
    trajectories = build_experiment_e_trajectories()

    # Map trajectories to cases
    case_map: dict[ExperimentECase, DeterministicTrajectory] = {}
    for traj in trajectories:
        if "bear_bull" in traj.name and "static" in traj.name:
            case = ExperimentECase(sequence="bear_bull", strategy="static_080")
        elif "bear_bull" in traj.name and "glidepath" in traj.name:
            case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        elif "bull_bear" in traj.name and "static" in traj.name:
            case = ExperimentECase(sequence="bull_bear", strategy="static_080")
        elif "bull_bear" in traj.name and "glidepath" in traj.name:
            case = ExperimentECase(sequence="bull_bear", strategy="glidepath_070_090")
        else:
            raise ValueError(f"Unknown trajectory: {traj.name}")
        case_map[case] = traj

    return ExperimentEResult(cases=case_map)


# ---------------------------------------------------------------------------
# Export the return sequences for testing/verification
# ---------------------------------------------------------------------------

# The annual source sequences (for verification that Bull→Bear is the reverse)
BEAR_BULL_ANNUAL_EQUITY = _BEAR_BULL_ANNUAL_EQUITY
BEAR_BULL_ANNUAL_BONDS = _BEAR_BULL_ANNUAL_BONDS
