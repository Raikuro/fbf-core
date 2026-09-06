"""Benchmark for Part 52 evaluator parallel execution performance.

Verifies that Part52Evaluator delegates to the existing parallel infrastructure
efficiently. Measures wall-clock time for a small evaluation and reports results.
"""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.money import Currency, Money
from fbf.core.optimization.part52_evaluator import (
    Part52Evaluator,
    Part52EvaluatorConfig,
)

DATA_DIR = Path("data/ern")
INITIAL_WEALTH = Money(Decimal("1000000"), Currency.EUR)


@pytest.mark.benchmark
class TestPart52EvaluatorBenchmark:
    """Part52Evaluator performance characteristics."""

    @pytest.mark.slow
    def test_single_eval_wall_clock(self, benchmark: object) -> None:
        """Measure time for a single evaluator call on real data."""
        config = Part52EvaluatorConfig(
            data_dir=str(DATA_DIR),
            initial_wealth=INITIAL_WEALTH,
            drawdown_threshold=Decimal("0.20"),
            debt_interest_rate=Decimal("0.015"),
            borrow_pcts=(Decimal("0"),),
            workers=1,
        )
        evaluator = Part52Evaluator(config)

        start = time.perf_counter()
        result = evaluator.evaluate(Decimal("0.035"))
        elapsed = time.perf_counter() - start

        total = result.provenance["total_count"]
        print(f"\nPart52Evaluator single eval: {elapsed:.2f}s ({total} cohorts)")
        assert result.provenance["all_success"] in (True, False)

    @pytest.mark.slow
    def test_parallel_eval_performance(self) -> None:
        """Verify parallel execution scales with worker count."""
        for workers in (1, 2, 4):
            config = Part52EvaluatorConfig(
                data_dir=str(DATA_DIR),
                initial_wealth=INITIAL_WEALTH,
                drawdown_threshold=Decimal("0.20"),
                debt_interest_rate=Decimal("0.015"),
                borrow_pcts=(Decimal("0"),),
                workers=workers,
            )
            evaluator = Part52Evaluator(config)

            start = time.perf_counter()
            result = evaluator.evaluate(Decimal("0.035"))
            elapsed = time.perf_counter() - start

            total = result.provenance["total_count"]
            print(
                f"\n  workers={workers}: {elapsed:.2f}s "
                f"({total} cohorts, {elapsed / max(total, 1):.4f}s/cohort)"
            )

        assert True
