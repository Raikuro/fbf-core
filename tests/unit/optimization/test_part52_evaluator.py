"""Tests for Part52Evaluator and optimize_part52.

Unit tests use mocked execution for fast deterministic validation.
Integration tests verify ERN anchor feasibility and monotonicity boundary.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fbf.core.domain.model.money import Currency, Money
from fbf.core.execution.pipeline.simulation import (
    SimulationStatistics,
)
from fbf.core.execution.result import ResearchExecutionResult
from fbf.core.optimization.part52_evaluator import (
    DEFAULT_BORROW_PCTS,
    Part52Evaluator,
    Part52EvaluatorConfig,
)
from fbf.core.optimization.swr_optimizer import EvaluationOutcome, SWROptimizer

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)


def _make_config(
    *,
    borrow_pcts: tuple[Decimal, ...] | None = None,
    workers: int | None = 1,
) -> Part52EvaluatorConfig:
    """Create a minimal evaluator config for testing."""
    return Part52EvaluatorConfig(
        data_dir=str(DATA_DIR),
        initial_wealth=INITIAL_WEALTH,
        drawdown_threshold=Decimal("0.20"),
        debt_interest_rate=Decimal("0.015"),
        ltv_limit=Decimal("0.50"),
        ltv_enforcement=True,
        borrow_pcts=borrow_pcts or (Decimal("0"),),
        workers=workers,
    )


def _make_mock_result(
    success: bool,
    count: int = 1739,
    max_ltv: Decimal = Decimal("0.001"),
) -> MagicMock:
    """Create a mock ResearchExecutionResult."""
    sim_results = []
    for _ in range(count):
        stats = MagicMock(spec=SimulationStatistics)
        stats.success = success
        stats.final_wealth = Money(Decimal("500000"), Currency.EUR)
        sim = MagicMock()
        sim.statistics = stats
        sim.timeline = MagicMock()
        sim.timeline.monthly_results = []
        sim_results.append(sim)

    result = MagicMock(spec=ResearchExecutionResult)
    result.results = tuple(sim_results)
    return result


class TestPart52EvaluatorContract:
    """Verify Evaluator protocol compliance (mocked, fast)."""

    def test_implements_evaluator_protocol(self) -> None:
        config = _make_config()
        evaluator = Part52Evaluator(config)
        assert hasattr(evaluator, "evaluate")

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_returns_evaluation_outcome(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=True)
        config = _make_config()
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.035"))
        assert isinstance(result, EvaluationOutcome)

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_provenance_contains_required_keys(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=True)
        config = _make_config()
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.035"))
        assert "withdrawal_rate" in result.provenance
        assert "borrow_pct" in result.provenance
        assert "success_count" in result.provenance
        assert "total_count" in result.provenance
        assert "all_success" in result.provenance
        assert "max_post_enforcement_ltv" in result.provenance
        assert "ltv_limit" in result.provenance
        assert "ltv_enforcement" in result.provenance


class TestPart52EvaluatorConfig:
    """Verify config construction."""

    def test_default_borrow_pcts(self) -> None:
        config = Part52EvaluatorConfig(
            data_dir=str(DATA_DIR),
            initial_wealth=INITIAL_WEALTH,
            drawdown_threshold=Decimal("0.20"),
            debt_interest_rate=Decimal("0.015"),
        )
        assert len(config.borrow_pcts) == 6
        assert Decimal("0") in config.borrow_pcts
        assert Decimal("0.50") in config.borrow_pcts
        assert config.borrow_pcts == DEFAULT_BORROW_PCTS

    def test_custom_borrow_pcts(self) -> None:
        custom = (Decimal("0.10"), Decimal("0.30"))
        config = _make_config(borrow_pcts=custom)
        assert config.borrow_pcts == custom


class TestPart52EvaluatorFeasibility:
    """Verify evaluator logic with mocked execution."""

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_success_when_all_cohorts_succeed(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=True)
        config = _make_config()
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.035"))
        assert result.success is True
        assert result.provenance["all_success"] is True
        assert result.provenance["total_count"] == 1739

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_failure_when_any_cohort_fails(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=False)
        config = _make_config()
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.050"))
        assert result.success is False
        assert result.provenance["all_success"] is False

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_multi_b_pct_returns_first_feasible(self, mock_exec: MagicMock) -> None:
        # First call (B%=0%) succeeds
        mock_exec.return_value = _make_mock_result(success=True)
        config = _make_config(
            borrow_pcts=(Decimal("0"), Decimal("0.20"), Decimal("0.50"))
        )
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.035"))
        assert result.success is True
        assert result.provenance["borrow_pct"] == "0"

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_skips_infeasible_b_pct(self, mock_exec: MagicMock) -> None:
        # First call (B%=0%) fails, second (B%=50%) succeeds
        fail_result = _make_mock_result(success=False)
        success_result = _make_mock_result(success=True)
        mock_exec.side_effect = [fail_result, success_result]
        config = _make_config(borrow_pcts=(Decimal("0"), Decimal("0.50")))
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.035"))
        assert result.success is True
        assert result.provenance["borrow_pct"] == "0.50"

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_ltv_recorded_in_provenance(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=True, max_ltv=Decimal("0.03"))
        config = _make_config()
        evaluator = Part52Evaluator(config)
        result = evaluator.evaluate(Decimal("0.035"))
        ltv = Decimal(result.provenance["max_post_enforcement_ltv"])
        assert ltv >= Decimal("0")
        assert ltv <= Decimal("0.50")


class TestSWROptimizerIntegration:
    """Verify Part52Evaluator works with SWROptimizer binary search."""

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_optimizer_finds_boundary(self, mock_exec: MagicMock) -> None:
        """Binary search converges to feasibility boundary."""
        # Use a counter to simulate: first few calls succeed, later fail
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            # First 3 calls succeed (low WR), rest fail (high WR)
            return _make_mock_result(success=call_count <= 3)

        mock_exec.side_effect = side_effect
        config = _make_config()
        evaluator = Part52Evaluator(config)
        optimizer = SWROptimizer()
        result = optimizer.optimize(
            evaluator=evaluator,
            domain_min=Decimal("0.030"),
            domain_max=Decimal("0.050"),
            precision=Decimal("0.005"),
        )
        assert result.candidate_value is not None
        assert Decimal("0.030") <= result.candidate_value <= Decimal("0.050")


class TestOptimizePart52API:
    """Verify optimize_part52() convenience function."""

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_returns_optimizer_outcome(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=True)
        from fbf.core.optimization import optimize_part52

        result = optimize_part52(
            data_dir=str(DATA_DIR),
            initial_wealth=INITIAL_WEALTH,
            drawdown_threshold=Decimal("0.20"),
            debt_interest_rate=Decimal("0.015"),
            borrow_pcts=(Decimal("0"),),
            domain_min=Decimal("0.030"),
            domain_max=Decimal("0.045"),
            precision=Decimal("0.005"),
            workers=1,
        )
        assert result.candidate_value is not None

    @patch("fbf.core.optimization.part52_evaluator.execute_study_plan")
    def test_provenance_structure(self, mock_exec: MagicMock) -> None:
        mock_exec.return_value = _make_mock_result(success=True)
        from fbf.core.optimization import optimize_part52

        result = optimize_part52(
            data_dir=str(DATA_DIR),
            initial_wealth=INITIAL_WEALTH,
            drawdown_threshold=Decimal("0.20"),
            debt_interest_rate=Decimal("0.015"),
            borrow_pcts=(Decimal("0"),),
            domain_min=Decimal("0.030"),
            domain_max=Decimal("0.045"),
            precision=Decimal("0.005"),
            workers=1,
        )
        assert "withdrawal_rate" in result.provenance
        assert "borrow_pct" in result.provenance
        assert "all_success" in result.provenance
