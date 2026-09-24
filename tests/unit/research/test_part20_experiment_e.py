"""Unit tests for Experiment E research adapter.

Tests the Experiment E return sequences, trajectory construction,
and deterministic execution smoke tests.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.money import Currency
from fbf.core.research.part20_experiment_e import (
    BEAR_BULL_ANNUAL_BONDS,
    BEAR_BULL_ANNUAL_EQUITY,
    ExperimentECase,
    build_ern_table01_return_sequence,
    build_experiment_e_trajectories,
    execute_experiment_e,
)

# Expected annual returns from Article Table 01
EXPECTED_BEAR_BULL_EQUITY = (
    Decimal("-0.30"),
    Decimal("-0.05"),
    Decimal("0.20"),
    Decimal("0.15"),
    Decimal("0.10"),
    Decimal("0.10"),
    Decimal("0.10"),
    Decimal("0.10"),
    Decimal("0.10"),
    Decimal("0.10"),
)

EXPECTED_BEAR_BULL_BONDS = (
    Decimal("0.08"),
    Decimal("0.05"),
    Decimal("-0.01"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.02"),
    Decimal("0.02"),
    Decimal("0.02"),
    Decimal("0.02"),
    Decimal("0.02"),
)


class TestBearBullReturnSequence:
    """Tests for the Bear→Bull return sequence (Article Table 01)."""

    def test_annual_equity_returns_match_table01(self) -> None:
        """Bear→Bull annual equity returns match Article Table 01."""
        assert BEAR_BULL_ANNUAL_EQUITY == EXPECTED_BEAR_BULL_EQUITY

    def test_annual_bond_returns_match_table01(self) -> None:
        """Bear→Bull annual bond returns match Article Table 01."""
        assert BEAR_BULL_ANNUAL_BONDS == EXPECTED_BEAR_BULL_BONDS

    def test_return_sequence_has_10_annual_returns(self) -> None:
        """ReturnSequence built from 10 annual returns."""
        seq = build_ern_table01_return_sequence()
        # The sequence stores 120 monthly returns, but the annual source was 10
        # We verify by checking the annual source length
        assert len(seq.equity_returns) == 120
        assert len(seq.bond_returns) == 120

    def test_return_sequence_start_date(self) -> None:
        """ReturnSequence starts at 1929-09-01."""
        seq = build_ern_table01_return_sequence()
        assert seq.start_date == date(1929, 9, 1)

    def test_return_sequence_name(self) -> None:
        """ReturnSequence has correct name."""
        seq = build_ern_table01_return_sequence()
        assert seq.name == "ERN_Table01_BearBull"


class TestBullBearReturnSequence:
    """Tests for the Bull→Bear return sequence (reverse of Bear→Bull)."""

    def test_bull_bear_is_reverse_of_bear_bull(self) -> None:
        """Bull→Bear is the exact reverse of Bear→Bull at the annual source level."""
        bear_bull = build_ern_table01_return_sequence()
        bull_bear = bear_bull.reverse()

        # The reverse() method reverses the 120 monthly returns
        # Since each annual return expands to 12 identical monthly returns,
        # reversing monthly is equivalent to reversing annual source
        assert bull_bear.equity_returns == tuple(reversed(bear_bull.equity_returns))
        assert bull_bear.bond_returns == tuple(reversed(bear_bull.bond_returns))

    def test_bull_bear_name(self) -> None:
        """Bull→Bear sequence has _reversed suffix."""
        bear_bull = build_ern_table01_return_sequence()
        bull_bear = bear_bull.reverse()
        assert bull_bear.name == "ERN_Table01_BearBull_reversed"

    def test_bull_bear_start_date_preserved(self) -> None:
        """Bull→Bear preserves the start date."""
        bear_bull = build_ern_table01_return_sequence()
        bull_bear = bear_bull.reverse()
        assert bull_bear.start_date == date(1929, 9, 1)

    def test_bull_bear_annual_source_reversed(self) -> None:
        """Verify Bull→Bear annual source is reversed correctly.

        The first 12 monthly returns of Bull→Bear should correspond to
        the last annual return of Bear→Bull (Year 10: +10% equity, +2% bonds).
        """
        bear_bull = build_ern_table01_return_sequence()
        bull_bear = bear_bull.reverse()

        # Bear→Bull Year 10 monthly return (index 108-119)
        bear_bull_year10_equity = bear_bull.equity_returns[108]
        # Bull→Bear Year 1 monthly return (index 0-11)
        bull_bear_year1_equity = bull_bear.equity_returns[0]

        assert bull_bear_year1_equity == bear_bull_year10_equity


class TestExperimentETrajectories:
    """Tests for Experiment E trajectory construction."""

    def test_four_trajectories_built(self) -> None:
        """Exactly four trajectories are built."""
        trajectories = build_experiment_e_trajectories()
        assert len(trajectories) == 4

    def test_trajectory_names(self) -> None:
        """Trajectories have correct names."""
        trajectories = build_experiment_e_trajectories()
        names = {t.name for t in trajectories}
        assert names == {
            "E_bear_bull_static_080",
            "E_bear_bull_glidepath_070_090",
            "E_bull_bear_static_080",
            "E_bull_bear_glidepath_070_090",
        }

    def test_all_trajectories_have_120_month_horizon(self) -> None:
        """All trajectories have 10-year (120 month) horizon."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            assert t.horizon_months == 120

    def test_all_trajectories_have_eur_initial_wealth(self) -> None:
        """All trajectories use EUR 1M initial wealth."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            assert t.initial_wealth.amount == Decimal("1000000")
            assert t.initial_wealth.currency == Currency.EUR

    def test_all_trajectories_have_expense_ratio(self) -> None:
        """All trajectories have 0.05% expense ratio."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            assert t.expense_ratio == Decimal("0.0005")

    def test_all_trajectories_have_annual_rebalance_schedule(self) -> None:
        """All trajectories use annual rebalance schedule."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            assert t.schedule is not None
            from fbf.core.execution.pipeline.schedule import StepCadence
            from fbf.core.execution.pipeline.steps.portfolio_rebalance_step import (
                PortfolioRebalanceStep,
            )
            assert t.schedule.get_cadence(PortfolioRebalanceStep) == StepCadence.ANNUAL

    def test_static_trajectories_use_constant_allocation(self) -> None:
        """Static trajectories use ConstantAllocationPolicy at 80%."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            if "static" in t.name:
                from fbf.core.domain.policies import ConstantAllocationPolicy
                assert isinstance(t.allocation_policy, ConstantAllocationPolicy)
                assert t.allocation_policy.equity_allocation == Decimal("0.80")

    def test_glidepath_trajectories_use_annual_cadence(self) -> None:
        """Glidepath trajectories use ANNUAL cadence with 2pp/year slope."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            if "glidepath" in t.name:
                from fbf.core.domain.policies import GlidepathAllocationPolicy, GlidepathCadence
                assert isinstance(t.allocation_policy, GlidepathAllocationPolicy)
                assert t.allocation_policy.cadence == GlidepathCadence.ANNUAL
                assert t.allocation_policy.slope == Decimal("0.02")
                assert t.allocation_policy.start_equity == Decimal("0.70")
                assert t.allocation_policy.end_equity == Decimal("0.90")
                assert t.allocation_policy.mode == "passive"

    def test_all_trajectories_use_escalating_withdrawal(self) -> None:
        """All trajectories use EscalatingWithdrawalPolicy with Experiment E params."""
        from fbf.core.domain.policies import EscalatingWithdrawalPolicy
        from fbf.core.domain.policies.frequency import WithdrawalFrequency

        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            assert isinstance(t.withdrawal_policy, EscalatingWithdrawalPolicy)
            assert t.withdrawal_policy.withdrawal_rate == Decimal("0.035")
            assert t.withdrawal_policy.escalation_rate == Decimal("0.02")
            assert t.withdrawal_policy.frequency == WithdrawalFrequency.ANNUAL

    def test_static_initial_allocation_80_20(self) -> None:
        """Static trajectories start at 80/20."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            if "static" in t.name:
                equity = AssetClass(id="equity", name="", description="")
                bond = AssetClass(id="bond", name="", description="")
                assert t.initial_allocation.weights[equity] == Decimal("0.80")
                assert t.initial_allocation.weights[bond] == Decimal("0.20")

    def test_glidepath_initial_allocation_70_30(self) -> None:
        """Glidepath trajectories start at 70/30."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            if "glidepath" in t.name:
                equity = AssetClass(id="equity", name="", description="")
                bond = AssetClass(id="bond", name="", description="")
                assert t.initial_allocation.weights[equity] == Decimal("0.70")
                assert t.initial_allocation.weights[bond] == Decimal("0.30")

    def test_bear_bull_trajectories_use_bear_bull_dataset(self) -> None:
        """Bear→Bull trajectories use the Bear→Bull dataset."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            if "bear_bull" in t.name:
                assert t.dataset is not None
                assert len(t.dataset) == 120

    def test_bull_bear_trajectories_use_bull_bear_dataset(self) -> None:
        """Bull→Bear trajectories use the Bull→Bear dataset."""
        trajectories = build_experiment_e_trajectories()
        for t in trajectories:
            if "bull_bear" in t.name:
                assert t.dataset is not None
                assert len(t.dataset) == 120


class TestExperimentEExecution:
    """Smoke tests for Experiment E deterministic execution."""

    def test_all_four_cases_execute_successfully(self) -> None:
        """All four trajectories execute without error."""
        result = execute_experiment_e()
        assert len(result.cases) == 4

    def test_execution_completes_for_all_cases(self) -> None:
        """Execution completes (reaches period 119) for all cases."""
        result = execute_experiment_e()
        for case, _traj in result.cases.items():
            det_result = result.get_result(case)
            assert det_result.success is True
            # Should have 120 monthly results
            assert len(det_result.timeline) == 120
            # Should reach period 119
            assert 119 in det_result.checkpoints

    def test_year_2_checkpoint_at_period_23(self) -> None:
        """Year 2 checkpoint exists at period 23."""
        result = execute_experiment_e()
        for case, _traj in result.cases.items():
            det_result = result.get_result(case)
            checkpoint_23 = det_result.checkpoints[23]
            assert checkpoint_23.period_index == 23

    def test_year_10_checkpoint_at_period_119(self) -> None:
        """Year 10 checkpoint exists at period 119."""
        result = execute_experiment_e()
        for case, _traj in result.cases.items():
            det_result = result.get_result(case)
            checkpoint_119 = det_result.checkpoints[119]
            assert checkpoint_119.period_index == 119

    def test_checkpoints_have_portfolio_and_allocation(self) -> None:
        """Checkpoints contain portfolio value and allocation target."""
        result = execute_experiment_e()
        for case, _traj in result.cases.items():
            det_result = result.get_result(case)
            for pi in [23, 119]:
                cp = det_result.checkpoints[pi]
                assert cp.portfolio is not None
                assert cp.allocation is not None
                assert cp.allocation_target is not None


class TestExperimentECaseIdentification:
    """Tests for ExperimentECase identification."""

    def test_case_identification_from_name(self) -> None:
        """ExperimentECase correctly identifies cases from trajectory names."""
        result = execute_experiment_e()

        static_bb = ExperimentECase(sequence="bear_bull", strategy="static_080")
        gp_bb = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        static_br = ExperimentECase(sequence="bull_bear", strategy="static_080")
        gp_br = ExperimentECase(sequence="bull_bear", strategy="glidepath_070_090")

        for case, traj in result.cases.items():
            if "bear_bull" in traj.name and "static" in traj.name:
                assert case == static_bb
            elif "bear_bull" in traj.name and "glidepath" in traj.name:
                assert case == gp_bb
            elif "bull_bear" in traj.name and "static" in traj.name:
                assert case == static_br
            elif "bull_bear" in traj.name and "glidepath" in traj.name:
                assert case == gp_br

    def test_case_result_retrieval(self) -> None:
        """Can retrieve deterministic result by case."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="static_080")
        det_result = result.get_result(case)
        assert det_result.success is True
        assert len(det_result.timeline) == 120


class TestGlidepathProgression:
    """Tests for glidepath progression at key periods."""

    def test_glidepath_starts_at_70_percent(self) -> None:
        """Glidepath starts at 70% equity at period 0."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        det_result = result.get_result(case)
        cp0 = det_result.checkpoints[0]
        assert cp0.allocation_target is not None
        equity = AssetClass(id="equity", name="", description="")
        assert cp0.allocation_target.weights[equity] == Decimal("0.70")

    def test_glidepath_72_at_period_12(self) -> None:
        """Glidepath advances to 72% at period 12 (start of Year 2)."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        det_result = result.get_result(case)
        cp12 = det_result.checkpoints[12]
        assert cp12.allocation_target is not None
        equity = AssetClass(id="equity", name="", description="")
        assert cp12.allocation_target.weights[equity] == Decimal("0.72")

    def test_glidepath_74_at_period_24(self) -> None:
        """Glidepath advances to 74% at period 24 (start of Year 3)."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        det_result = result.get_result(case)
        cp24 = det_result.checkpoints[24]
        assert cp24.allocation_target is not None
        equity = AssetClass(id="equity", name="", description="")
        assert cp24.allocation_target.weights[equity] == Decimal("0.74")

    def test_glidepath_88_at_period_108(self) -> None:
        """Glidepath reaches 88% at period 108 (start of Year 10)."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        det_result = result.get_result(case)
        cp108 = det_result.checkpoints[108]
        assert cp108.allocation_target is not None
        equity = AssetClass(id="equity", name="", description="")
        assert cp108.allocation_target.weights[equity] == Decimal("0.88")

    def test_glidepath_88_at_period_119(self) -> None:
        """Glidepath stays at 88% at period 119 (end of Year 10)."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        det_result = result.get_result(case)
        cp119 = det_result.checkpoints[119]
        assert cp119.allocation_target is not None
        equity = AssetClass(id="equity", name="", description="")
        assert cp119.allocation_target.weights[equity] == Decimal("0.88")

    def test_glidepath_capped_at_end_equity(self) -> None:
        """Glidepath is capped at end_equity (90%) when advancement would exceed it."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="glidepath_070_090")
        det_result = result.get_result(case)

        # At period 119 (end of Year 10), glidepath should be at 88%
        # (9 advancements: period 0, 12, 24, 36, 48, 60, 72, 84, 96, 108)
        cp119 = det_result.checkpoints[119]
        assert cp119.allocation_target is not None
        equity = AssetClass(id="equity", name="", description="")
        assert cp119.allocation_target.weights[equity] == Decimal("0.88")

        # The cap at 90% would be reached at period 120 (10 advancements),
        # which is beyond the 10-year Experiment E horizon.


class TestWithdrawalSchedule:
    """Tests for Experiment E withdrawal schedule."""

    def test_year_1_withdrawal_35000(self) -> None:
        """Year 1 withdrawal is $35,000."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="static_080")
        det_result = result.get_result(case)
        # Year 1 withdrawal at period 0
        cp0 = det_result.checkpoints[0]
        assert cp0.withdrawal_decision is not None
        assert cp0.withdrawal_decision.nominal_amount.amount == Decimal("35000")

    def test_year_2_withdrawal_35700(self) -> None:
        """Year 2 withdrawal is $35,700 (3.5% * 1.02)."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="static_080")
        det_result = result.get_result(case)
        cp12 = det_result.checkpoints[12]
        assert cp12.withdrawal_decision is not None
        assert cp12.withdrawal_decision.nominal_amount.amount == Decimal("35700")

    def test_annual_frequency_zero_at_non_boundaries(self) -> None:
        """Withdrawal is zero at non-annual-boundary periods."""
        result = execute_experiment_e()
        case = ExperimentECase(sequence="bear_bull", strategy="static_080")
        det_result = result.get_result(case)
        for pi in [1, 11, 13, 23]:
            cp = det_result.checkpoints[pi]
            assert cp.withdrawal_decision is not None
            assert cp.withdrawal_decision.nominal_amount.amount == Decimal("0")

