#!/usr/bin/env python3
"""
Regression tests for Part 20 corrected methodology.

Tests that protect:
1. CAPE classification using workbook-aligned Shiller CAPE (cape_shiller.csv)
2. Historical data boundary at 2026-06 (not 2016-10)
3. Key cohort outcomes
4. Corrected anchor cell results
"""

import json
import os
from decimal import Decimal
from pathlib import Path

os.environ["RUN_ERN_E2E"] = "1"

import pytest

from fbf.core.datasets import load_canonical_dataset
from fbf.core.execution import ExecutionOptions
from fbf.core.research.part20_aggregation import (
    to_displayed_failure_percent,
    to_displayed_percent,
)
from fbf.core.research.part20_audit_spec import load_part20_audit_spec
from fbf.core.research.part20_pipeline import (
    run_fixed_swr_grid,
    run_percentile_search,
)
from fbf.core.research.part20_planner import Part20ExecutionContext
from fbf.core.research.part20_strategies import part20_strategy_universe

DATA_DIR = Path("data/ern")
MANIFEST_PATH = Path("data/ern/cohort_manifest_part3.json")
AUDIT_SPEC_PATH = Path("tests/fixtures/ern_part20_e2e_audit.yaml")


class TestCorrectedMethodology:
    """Regression tests for the corrected Part 20 methodology."""

    @classmethod
    def setup_class(cls):
        """Set up shared test fixtures."""
        cls.spec = load_part20_audit_spec(AUDIT_SPEC_PATH)
        cls.strategies = part20_strategy_universe()
        cls.dataset = load_canonical_dataset(DATA_DIR)

        with open(MANIFEST_PATH) as f:
            cls.manifest = json.load(f)

        cls.ctx = Part20ExecutionContext.create(MANIFEST_PATH, cls.dataset)
        cls.ctx.spec = cls.spec
        cls.cache = {}

    def test_cape_classification_matches_workbook(self):
        """Verify CAPE classification matches workbook Shiller CAPE semantics.
        
        The workbook classifies 1997-2001 cohorts as HIGH/EXTREME (CAPE >= 20).
        Previously these were LOW/MODERATE in FBF's manifest.
        """
        # Check key cohorts that changed regime
        key_cohorts = {
            "1997-01-01": "HIGH",      # was MODERATE/LOW
            "1998-07-01": "EXTREME",   # was LOW
            "1998-12-01": "EXTREME",   # was LOW
            "2000-12-01": "EXTREME",   # was LOW
            "2001-01-01": "EXTREME",   # was LOW
            "2001-09-01": "HIGH",      # was LOW
        }

        for cohort_date, expected_regime in key_cohorts.items():
            entry = next(e for e in self.manifest["cohorts"] if e["cohort_date"] == cohort_date)
            assert entry["cape_available"] is True, f"Cohort {cohort_date} should have CAPE"
            assert entry["cape_regime"] == expected_regime, \
                f"Cohort {cohort_date}: expected {expected_regime}, got {entry['cape_regime']}"

            # Verify CAPE value is >= 20
            cape_val = entry["cape_value"]
            assert cape_val is not None and cape_val >= 20.0, \
                f"Cohort {cohort_date}: CAPE {cape_val} should be >= 20"

    def test_cape_high_count_increased(self):
        """Verify HIGH regime cohort count increased from ~330 to ~416."""
        high_count = sum(1 for e in self.manifest["cohorts"] if e.get("cape_regime") in ("HIGH", "EXTREME"))
        # Should be around 416 (was 330)
        assert high_count >= 400, f"Expected ~416 HIGH cohorts, got {high_count}"

    def test_historical_data_boundary_2026(self):
        """Verify dataset uses actual historical data through 2026-06, not projection from 2016-10.
        
        The dataset loader should not replace actual historical observations
        with synthetic projections for 2016-10 through 2026-06.
        """
        # The dataset should have actual (non-constant) returns for 2016-10 through 2026-06
        # Check that the equity returns in this period are not all the same constant value
        equity_returns = []
        bond_returns = []

        from datetime import date

        from fbf.core.domain.model.asset import AssetClass

        eq_asset = AssetClass(id="equity", name="", description="")
        bond_asset = AssetClass(id="bond", name="", description="")

        # Check monthly returns from 2016-10 to 2026-06
        current = date(2016, 10, 1)
        end = date(2026, 6, 1)

        eq_prev = None
        bond_prev = None

        eq_vals = []
        bond_vals = []

        while current <= end:
            # Get the snapshot for this date
            snapshots = [s for s in self.dataset.snapshots if s.date == current]
            assert len(snapshots) == 1, f"Missing snapshot for {current}"
            snap = snapshots[0]

            eq_vals.append(float(snap.index_levels[eq_asset]))
            bond_vals.append(float(snap.index_levels[bond_asset]))

            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        # Compute monthly returns
        eq_rets = [(eq_vals[i] / eq_vals[i-1] - 1) for i in range(1, len(eq_vals))]
        bond_rets = [(bond_vals[i] / bond_vals[i-1] - 1) for i in range(1, len(bond_vals))]

        # Returns should NOT be constant (projection would be constant)
        # Check variance - actual returns have variation
        eq_variance = sum((r - sum(eq_rets)/len(eq_rets))**2 for r in eq_rets) / len(eq_rets)
        bond_variance = sum((r - sum(bond_rets)/len(bond_rets))**2 for r in bond_rets) / len(bond_rets)

        assert eq_variance > 1e-8, "Equity returns 2016-2026 should be actual (variable), not projected (constant)"
        assert bond_variance > 1e-8, "Bond returns 2016-2026 should be actual (variable), not projected (constant)"

    def test_projection_starts_after_2026_06(self):
        """Verify forward projection only begins after 2026-06."""
        # Check that returns become constant after 2026-06 (projection period)
        from datetime import date

        from fbf.core.domain.model.asset import AssetClass

        eq_asset = AssetClass(id="equity", name="", description="")
        bond_asset = AssetClass(id="bond", name="", description="")

        # Get values for 2026-06, 2026-07, 2026-08, 2026-09
        dates = [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
        eq_vals = []
        bond_vals = []

        for d in dates:
            snapshots = [s for s in self.dataset.snapshots if s.date == d]
            assert len(snapshots) == 1
            eq_vals.append(float(snapshots[0].index_levels[eq_asset]))
            bond_vals.append(float(snapshots[0].index_levels[bond_asset]))

        # Compute returns for projection months (should be constant)
        eq_rets = [(eq_vals[i] / eq_vals[i-1] - 1) for i in range(1, len(eq_vals))]
        bond_rets = [(bond_vals[i] / bond_vals[i-1] - 1) for i in range(1, len(bond_vals))]

        # In projection, returns should be constant (or follow projection formula)
        # Just verify they're not wildly varying like actual returns
        # The equity projection is 6.6% annual = ~0.53% monthly
        # Bond projection is 0% for first 120 months
        assert abs(eq_rets[0] - eq_rets[1]) < 1e-6, "Equity projection returns should be constant"
        assert abs(eq_rets[1] - eq_rets[2]) < 1e-6, "Equity projection returns should be constant"
        assert abs(bond_rets[0] - bond_rets[1]) < 1e-6, "Bond projection returns should be constant (0%)"
        assert abs(bond_rets[1] - bond_rets[2]) < 1e-6, "Bond projection returns should be constant (0%)"

    def test_static_100_4pct_60y_corrected(self):
        """Test corrected static_100 @ 4% 60Y failure rate.
        
        With corrected methodology: ~28.4% (was 30.3%)
        Published: 33.5%
        """
        strat = next(s for s in self.strategies if s.id == "static_100")
        cells = run_fixed_swr_grid(
            self.ctx, (strat,), self.ctx.populations.high_dates,
            horizon_years=60,
            withdrawal_rates=(Decimal("0.04"),),
            final_value_target=Decimal("0"),
            population="HIGH",
            options=ExecutionOptions(workers=1, summary_only=True),
        )
        for c in cells:
            if c.strategy_id == "static_100" and c.withdrawal_rate == Decimal("0.04"):
                obs = to_displayed_failure_percent(c.failure_rate)
                # Corrected result: ~28.4% (51 ULP from 33.5%)
                assert abs(obs - Decimal("28.4")) < Decimal("0.2"), \
                    f"static_100 @ 4% 60Y: expected ~28.4%, got {obs}%"
                return
        pytest.fail("Cell not found")

    def test_gp_030_070_4pct_60y_corrected(self):
        """Test corrected gp_030_070 @ 4% 60Y failure rate.
        
        With corrected methodology (ERN projection from 2026-07): ~32.0%
        This is a significant improvement from the old 31.1% (14 ULP from 32.5%).
        Published: 32.5%
        """
        strat = next(s for s in self.strategies if s.id == "gp_030_070_0.00111_passive")
        cells = run_fixed_swr_grid(
            self.ctx, (strat,), self.ctx.populations.high_dates,
            horizon_years=60,
            withdrawal_rates=(Decimal("0.04"),),
            final_value_target=Decimal("0"),
            population="HIGH",
            options=ExecutionOptions(workers=1, summary_only=True),
        )
        for c in cells:
            if c.strategy_id == strat.id and c.withdrawal_rate == Decimal("0.04"):
                obs = to_displayed_failure_percent(c.failure_rate)
                # Corrected result: ~32.0% (5 ULP from 32.5%)
                assert abs(obs - Decimal("32.0")) < Decimal("0.2"), \
                    f"gp_030_070 @ 4% 60Y: expected ~32.0%, got {obs}%"
                return
        pytest.fail("Cell not found")

    def test_static_080_3p75_60y_corrected(self):
        """Test corrected static_080 @ 3.75% 60Y failure rate.
        
        With corrected methodology: ~19.2% (was 23.5%)
        Published: 5.5%
        """
        strat = next(s for s in self.strategies if s.id == "static_080")
        cells = run_fixed_swr_grid(
            self.ctx, (strat,), self.ctx.populations.high_dates,
            horizon_years=60,
            withdrawal_rates=(Decimal("0.0375"),),
            final_value_target=Decimal("0"),
            population="HIGH",
            options=ExecutionOptions(workers=1, summary_only=True),
        )
        for c in cells:
            if c.strategy_id == "static_080" and c.withdrawal_rate == Decimal("0.0375"):
                obs = to_displayed_failure_percent(c.failure_rate)
                assert abs(obs - Decimal("19.2")) < Decimal("0.3"), \
                    f"static_080 @ 3.75% 60Y: expected ~19.2%, got {obs}%"
                return
        pytest.fail("Cell not found")

    def test_key_cohort_outcomes(self):
        """Test that the four key cohorts succeed with actual 2016-2026 returns.
        
        With the corrected methodology (actual data through 2026-06), the four
        dot-com cohorts should succeed under static_100 @ 4% 60Y.
        """
        from dataclasses import replace

        from fbf.core.domain.model import Money
        from fbf.core.domain.model.money import Currency
        from fbf.core.domain.policies import FixedRealWithdrawalPolicy
        from fbf.core.execution import (
            BuiltStudy,
            ExecutionOptions,
            ExecutionStrategy,
            execute_study_plan,
        )
        from fbf.core.execution.result import ResearchExecutionResult
        from fbf.core.research.part20_planner import (
            ExperimentDefinition,
            ParameterConfiguration,
            PlannedSimulationUnit,
            ResearchPlan,
        )

        PART20_INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)

        key_cohorts = ["1998-07-01", "1998-12-01", "2000-12-01", "2001-01-01"]
        strat = next(s for s in self.strategies if s.id == "static_100")

        for cohort_date in key_cohorts:
            # Verify cohort is in HIGH population
            assert cohort_date in self.ctx.populations.high_dates, \
                f"Cohort {cohort_date} should be in HIGH population"

            effective = self.ctx.effective_horizon(cohort_date, 60 * 12 + 1)
            cohort = self.ctx.cohort_spec(cohort_date)
            unit_dataset = self.ctx.dataset_for(cohort_date, effective)
            portfolio = self.ctx.portfolio_for(cohort_date, effective)
            alloc = self.ctx.allocation_policy(strat)
            withdrawal = FixedRealWithdrawalPolicy(withdrawal_rate=Decimal("0.04"))

            pc = ParameterConfiguration(
                values={
                    "strategy_id": strat.id,
                    "withdrawal_rate": float(Decimal("0.04")),
                    "horizon_months": float(effective),
                    "requested_horizon_months": float(60 * 12 + 1),
                    "final_value_target": float(Decimal("0")),
                    "step": f"regression_{cohort_date}",
                    "unit_index": 0.0,
                }
            )

            unit = PlannedSimulationUnit(
                cohort=cohort,
                parameter_config=pc,
                allocation_policy=alloc,
                withdrawal_policy=withdrawal,
                initial_portfolio=portfolio,
                dataset=unit_dataset,
                horizon_months=effective,
                final_value_target=Decimal("0"),
            )

            plan = ResearchPlan(
                experiment_definition=ExperimentDefinition(
                    name=f"Regression {cohort_date}",
                    description="Cohort regression test",
                    dataset=self.dataset,
                    horizon_months=60 * 12 + 1,
                    initial_wealth=PART20_INITIAL_WEALTH,
                    cohorts=(cohort,),
                    allocation_policies=(alloc,),
                    withdrawal_policies=(withdrawal,),
                ),
                units=(unit,),
            )

            built = BuiltStudy(
                plan=plan,
                experiment_definition=plan.experiment_definition,
                cohorts=(cohort,),
                param_configs=(pc,),
            )

            opts = ExecutionOptions(workers=1, summary_only=True)
            effective_opts = replace(opts, strategy=ExecutionStrategy.SEQUENTIAL, summary_only=True, glidepath_gf_cache=self.ctx.glidepath_gf_cache)
            result: ResearchExecutionResult = execute_study_plan(built, effective_opts)

            sim_result = result.results[0]
            stats = sim_result.statistics

            # With actual 2016-2026 returns, these cohorts should SUCCEED
            assert stats.success is True, \
                f"Cohort {cohort_date} should succeed with actual historical returns (got final_wealth={stats.final_wealth})"

            # Final wealth should be substantial (not depleted)
            assert stats.final_wealth is not None
            final_val = float(stats.final_wealth.amount)
            assert final_val > 100000, \
                f"Cohort {cohort_date} final wealth ${final_val:,.0f} should be substantial (>$100K)"

    def test_experiment_a_b_unaffected(self):
        """Verify Experiments A and B (30Y/60Y percentile) are largely unaffected.
        
        The historical boundary change primarily affects 60Y horizons with
        post-1966 cohorts. Experiments A and B should remain stable.
        """
        strat = next(s for s in self.strategies if s.id == "static_075")

        # Experiment A: 60Y, failsafe
        pop_dates = self.ctx.populations.high_dates
        results = run_percentile_search(
            self.ctx, (strat,), pop_dates,
            horizon_years=60,
            final_value_target=Decimal("0"),
            cape_regime="HIGH",
            options=ExecutionOptions(workers=1, summary_only=True),
            step_label="regression_exp_a",
            cache=self.cache,
        )
        result = results.get("static_075")
        assert result is not None
        failsafe = to_displayed_percent(result.failsafe)
        # Should remain ~3.28% (published 3.25%)
        assert abs(failsafe - Decimal("3.28")) < Decimal("0.05"), \
            f"Exp A static_075 failsafe: expected ~3.28%, got {failsafe}%"

        # Experiment B: 30Y, failsafe
        results = run_percentile_search(
            self.ctx, (strat,), pop_dates,
            horizon_years=30,
            final_value_target=Decimal("0"),
            cape_regime="HIGH",
            options=ExecutionOptions(workers=1, summary_only=True),
            step_label="regression_exp_b",
            cache=self.cache,
        )
        result = results.get("static_075")
        assert result is not None
        failsafe = to_displayed_percent(result.failsafe)
        # Should remain ~3.84% (published 3.82%)
        assert abs(failsafe - Decimal("3.84")) < Decimal("0.05"), \
            f"Exp B static_075 failsafe: expected ~3.84%, got {failsafe}%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
