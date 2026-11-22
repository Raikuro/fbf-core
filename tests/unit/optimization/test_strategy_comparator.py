"""Tests for StrategyComparator."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

import pytest

from fbf.core.domain.optimizer import (
    EvaluationResult,
    Evaluator,
    InvalidInputError,
    MetricDefinition,
    MetricDirection,
    RankingRule,
    StrategyComparator,
    StrategyComparisonReport,
)


def _metric(name: str, direction: MetricDirection) -> MetricDefinition:
    return MetricDefinition(name=name, direction=direction)


class MockEvaluator(Evaluator):
    """Mock evaluator for testing."""

    def __init__(self, results: Mapping[str, EvaluationResult]):
        self._results = results

    def get_evaluations(self, label: str) -> Sequence[EvaluationResult]:
        if label not in self._results:
            raise ValueError(f"Unknown label: {label}")
        # return a single-item sequence to simulate a single evaluation
        return [self._results[label]]


def test_strategy_comparator_initialization() -> None:
    """Test that StrategyComparator initializes correctly."""
    metrics = [
        _metric("sharpe_ratio", MetricDirection.MAXIMIZE),
        _metric("max_drawdown", MetricDirection.MINIMIZE),
    ]
    ranking_rule = RankingRule(primary_metric="sharpe_ratio", tie_breakers=["max_drawdown"])

    comparator = StrategyComparator(metrics=metrics, ranking_rule=ranking_rule)

    assert comparator._metrics == tuple(metrics)
    assert comparator._ranking_rule == ranking_rule


def test_strategy_comparator_empty_strategy_map() -> None:
    """Test that StrategyComparator raises InvalidInputError for empty strategy_map."""
    metrics = [_metric("sharpe_ratio", MetricDirection.MAXIMIZE)]
    ranking_rule = RankingRule(primary_metric="sharpe_ratio", tie_breakers=[])

    comparator = StrategyComparator(metrics=metrics, ranking_rule=ranking_rule)

    with pytest.raises(InvalidInputError, match="strategy_map cannot be empty"):
        comparator.compare({})


def test_strategy_comparator_empty_metrics() -> None:
    """Test that StrategyComparator raises InvalidInputError for empty metrics."""
    ranking_rule = RankingRule(primary_metric="sharpe_ratio", tie_breakers=[])

    comparator = StrategyComparator(metrics=[], ranking_rule=ranking_rule)

    with pytest.raises(InvalidInputError, match="metrics cannot be empty"):
        comparator.compare({"strategy1": MockEvaluator({})})


def test_strategy_comparator_basic_functionality() -> None:
    """Test basic StrategyComparator functionality with mock data."""
    # Create mock evaluation results
    results = {
        "strategy1": EvaluationResult(
            label="strategy1",
            metrics={"sharpe_ratio": Decimal("1.5"), "max_drawdown": Decimal("0.2")},
            provenance={
                "experiment1": ["unit1", "unit2"],
                "cohort": ["c1"],
                "parameter_config": ["p1"],
            },
        ),
        "strategy2": EvaluationResult(
            label="strategy2",
            metrics={"sharpe_ratio": Decimal("2.0"), "max_drawdown": Decimal("0.3")},
            provenance={"experiment1": ["unit3"], "cohort": ["c1"], "parameter_config": ["p2"]},
        ),
    }

    evaluator = MockEvaluator(results)
    strategy_map = {"strategy1": evaluator, "strategy2": evaluator}

    metrics = [
        _metric("sharpe_ratio", MetricDirection.MAXIMIZE),
        _metric("max_drawdown", MetricDirection.MINIMIZE),
    ]
    ranking_rule = RankingRule(primary_metric="sharpe_ratio", tie_breakers=["max_drawdown"])

    comparator = StrategyComparator(metrics=metrics, ranking_rule=ranking_rule)

    report = comparator.compare(strategy_map)

    # Verify report structure
    assert isinstance(report, StrategyComparisonReport)
    assert report.aggregated_metrics is not None
    assert report.ranking is not None
    assert report.provenance is not None
    assert report.ranking["global"] == ["strategy2", "strategy1"]


def test_strategy_comparator_deterministic_output() -> None:
    """Test that StrategyComparator produces deterministic output."""
    results = {
        "strategy1": EvaluationResult(
            label="strategy1",
            metrics={"sharpe_ratio": Decimal("1.5"), "max_drawdown": Decimal("0.2")},
            provenance={"experiment1": ["unit1"], "cohort": ["c1"], "parameter_config": ["p1"]},
        ),
    }

    evaluator = MockEvaluator(results)
    strategy_map = {"strategy1": evaluator}

    metrics = [_metric("sharpe_ratio", MetricDirection.MAXIMIZE)]
    ranking_rule = RankingRule(primary_metric="sharpe_ratio", tie_breakers=[])

    comparator = StrategyComparator(metrics=metrics, ranking_rule=ranking_rule)

    # Run comparison twice with same inputs
    report1 = comparator.compare(strategy_map)
    report2 = comparator.compare(strategy_map)

    # Results should be identical
    assert report1.aggregated_metrics == report2.aggregated_metrics
    assert report1.ranking == report2.ranking
    assert report1.provenance == report2.provenance


def test_strategy_comparator_invalid_label() -> None:
    """Test that StrategyComparator handles invalid labels correctly."""
    results = {
        "strategy1": EvaluationResult(
            label="strategy1",
            metrics={"sharpe_ratio": Decimal("1.5")},
            provenance={"experiment1": ["unit1"], "cohort": ["c1"], "parameter_config": ["p1"]},
        ),
    }

    evaluator = MockEvaluator(results)
    strategy_map = {"strategy1": evaluator}

    metrics = [_metric("sharpe_ratio", MetricDirection.MAXIMIZE)]
    ranking_rule = RankingRule(primary_metric="sharpe_ratio", tie_breakers=[])

    comparator = StrategyComparator(metrics=metrics, ranking_rule=ranking_rule)

    # This should work fine since we only have strategy1
    report = comparator.compare(strategy_map)
    assert isinstance(report, StrategyComparisonReport)


def test_maximize_primary_ranks_higher_values_first() -> None:
    results = {
        "low": [
            EvaluationResult(
                label="low",
                metrics={"m": Decimal("0.10")},
                provenance={},
            )
        ],
        "high": [
            EvaluationResult(
                label="high",
                metrics={"m": Decimal("0.30")},
                provenance={},
            )
        ],
    }
    comparator = StrategyComparator(
        metrics=[_metric("m", MetricDirection.MAXIMIZE)],
        ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]),
    )

    report = comparator.compare(results)

    assert report.ranking["global"] == ["high", "low"]


def test_minimize_primary_ranks_lower_values_first() -> None:
    results = {
        "low": [
            EvaluationResult(
                label="low",
                metrics={"m": Decimal("0.10")},
                provenance={},
            )
        ],
        "high": [
            EvaluationResult(
                label="high",
                metrics={"m": Decimal("0.30")},
                provenance={},
            )
        ],
    }
    comparator = StrategyComparator(
        metrics=[_metric("m", MetricDirection.MINIMIZE)],
        ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]),
    )

    report = comparator.compare(results)

    assert report.ranking["global"] == ["low", "high"]


def test_mixed_direction_primary_and_tie_breaker() -> None:
    results = {
        "low_drawdown": [
            EvaluationResult(
                label="low_drawdown",
                metrics={
                    "success_rate": Decimal("1"),
                    "max_drawdown": Decimal("0.10"),
                },
                provenance={},
            )
        ],
        "high_drawdown": [
            EvaluationResult(
                label="high_drawdown",
                metrics={
                    "success_rate": Decimal("1"),
                    "max_drawdown": Decimal("0.30"),
                },
                provenance={},
            )
        ],
    }
    comparator = StrategyComparator(
        metrics=[
            _metric("success_rate", MetricDirection.MAXIMIZE),
            _metric("max_drawdown", MetricDirection.MINIMIZE),
        ],
        ranking_rule=RankingRule(
            primary_metric="success_rate",
            tie_breakers=["max_drawdown"],
        ),
    )

    report = comparator.compare(results)

    assert report.ranking["global"] == ["low_drawdown", "high_drawdown"]


def test_measured_zero_and_negative_values_are_valid() -> None:
    results = {
        "positive": [
            EvaluationResult(
                label="positive",
                metrics={"value": Decimal("0.1")},
                provenance={},
            )
        ],
        "zero": [
            EvaluationResult(
                label="zero",
                metrics={"value": Decimal("0")},
                provenance={},
            )
        ],
        "negative": [
            EvaluationResult(
                label="negative",
                metrics={"value": Decimal("-0.1")},
                provenance={},
            )
        ],
        "unavailable": [
            EvaluationResult(
                label="unavailable",
                metrics={"value": None},
                provenance={},
            )
        ],
    }
    comparator = StrategyComparator(
        metrics=[_metric("value", MetricDirection.MAXIMIZE)],
        ranking_rule=RankingRule(primary_metric="value", tie_breakers=[]),
    )

    report = comparator.compare(results)

    assert report.ranking["global"] == [
        "positive",
        "zero",
        "negative",
        "unavailable",
    ]


def test_unavailable_values_sort_last_for_minimize_primary() -> None:
    results = {
        "measured": [
            EvaluationResult(
                label="measured",
                metrics={"m": Decimal("0.5")},
                provenance={},
            )
        ],
        "unavailable": [
            EvaluationResult(
                label="unavailable",
                metrics={"m": None},
                provenance={},
            )
        ],
    }
    comparator = StrategyComparator(
        metrics=[_metric("m", MetricDirection.MINIMIZE)],
        ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]),
    )

    report = comparator.compare(results)

    assert report.ranking["global"] == ["measured", "unavailable"]


def test_duplicate_metric_definitions_raise() -> None:
    comparator = StrategyComparator(
        metrics=[
            _metric("m", MetricDirection.MAXIMIZE),
            _metric("m", MetricDirection.MINIMIZE),
        ],
        ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]),
    )

    with pytest.raises(InvalidInputError, match="duplicate metric definition"):
        comparator.compare(
            {
                "s": [
                    EvaluationResult(
                        label="s",
                        metrics={"m": Decimal("1")},
                        provenance={},
                    )
                ]
            }
        )


def test_undeclared_ranking_metric_raises() -> None:
    comparator = StrategyComparator(
        metrics=[_metric("declared", MetricDirection.MAXIMIZE)],
        ranking_rule=RankingRule(primary_metric="missing", tie_breakers=[]),
    )

    with pytest.raises(InvalidInputError, match="not declared"):
        comparator.compare(
            {
                "s": [
                    EvaluationResult(
                        label="s",
                        metrics={"declared": Decimal("1")},
                        provenance={},
                    )
                ]
            }
        )


def test_duplicate_ranking_metrics_raise() -> None:
    comparator = StrategyComparator(
        metrics=[_metric("m", MetricDirection.MAXIMIZE)],
        ranking_rule=RankingRule(primary_metric="m", tie_breakers=["m"]),
    )

    with pytest.raises(InvalidInputError, match="duplicate ranking metric"):
        comparator.compare(
            {
                "s": [
                    EvaluationResult(
                        label="s",
                        metrics={"m": Decimal("1")},
                        provenance={},
                    )
                ]
            }
        )


def test_invalid_metric_direction_raises() -> None:
    with pytest.raises(InvalidInputError, match="invalid direction"):
        MetricDefinition(
            name="m",
            direction=cast(MetricDirection, "sideways"),
        )


def test_metric_definition_requires_name() -> None:
    with pytest.raises(InvalidInputError, match="non-empty"):
        MetricDefinition(name="  ", direction=MetricDirection.MAXIMIZE)


def test_unavailable_metrics_are_excluded_from_average() -> None:
    results = {
        "strategy1": (
            EvaluationResult(
                label="strategy1",
                metrics={
                    "success_rate": Decimal("1"),
                    "max_drawdown": Decimal("0.10"),
                },
                provenance={"parameter_config": ["p1"]},
            ),
            EvaluationResult(
                label="strategy1",
                metrics={
                    "success_rate": Decimal("1"),
                    "max_drawdown": None,
                },
                provenance={"parameter_config": ["p1"]},
            ),
            EvaluationResult(
                label="strategy1",
                metrics={
                    "success_rate": Decimal("1"),
                    "max_drawdown": Decimal("0.30"),
                },
                provenance={"parameter_config": ["p1"]},
            ),
        )
    }
    comparator = StrategyComparator(
        metrics=[
            _metric("success_rate", MetricDirection.MAXIMIZE),
            _metric("max_drawdown", MetricDirection.MINIMIZE),
        ],
        ranking_rule=RankingRule(
            primary_metric="success_rate",
            tie_breakers=["max_drawdown"],
        ),
    )

    report = comparator.compare(results)

    metrics = report.aggregated_metrics["global"]["strategy1"]
    assert metrics["success_rate"] == Decimal("1")
    assert metrics["max_drawdown"] == Decimal("0.20")


def test_all_unavailable_metrics_remain_none() -> None:
    results = {
        "strategy1": (
            EvaluationResult(
                label="strategy1",
                metrics={"success_rate": Decimal("1"), "max_drawdown": None},
                provenance={"parameter_config": ["p1"]},
            ),
        )
    }
    comparator = StrategyComparator(
        metrics=[
            _metric("success_rate", MetricDirection.MAXIMIZE),
            _metric("max_drawdown", MetricDirection.MINIMIZE),
        ],
        ranking_rule=RankingRule(
            primary_metric="success_rate",
            tie_breakers=["max_drawdown"],
        ),
    )

    report = comparator.compare(results)

    assert report.aggregated_metrics["global"]["strategy1"]["max_drawdown"] is None


def test_unavailable_tie_breaker_sorts_after_measured_values() -> None:
    results = {
        "unavailable": (
            EvaluationResult(
                label="unavailable",
                metrics={"success_rate": Decimal("1"), "max_drawdown": None},
                provenance={"parameter_config": ["p1"]},
            ),
        ),
        "drawdown_zero": (
            EvaluationResult(
                label="drawdown_zero",
                metrics={"success_rate": Decimal("1"), "max_drawdown": Decimal("0")},
                provenance={"parameter_config": ["p2"]},
            ),
        ),
        "drawdown_measured": (
            EvaluationResult(
                label="drawdown_measured",
                metrics={"success_rate": Decimal("1"), "max_drawdown": Decimal("0.20")},
                provenance={"parameter_config": ["p3"]},
            ),
        ),
    }
    comparator = StrategyComparator(
        metrics=[
            _metric("success_rate", MetricDirection.MAXIMIZE),
            _metric("max_drawdown", MetricDirection.MINIMIZE),
        ],
        ranking_rule=RankingRule(
            primary_metric="success_rate",
            tie_breakers=["max_drawdown"],
        ),
    )

    report = comparator.compare(results)

    assert report.ranking["global"] == [
        "drawdown_zero",
        "drawdown_measured",
        "unavailable",
    ]
