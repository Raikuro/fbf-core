"""Additional tests required by RESEARCH_STRATEGYCOMPARATOR_IMPLEMENTATION_HANDOFF.md"""

from decimal import Decimal
from typing import Mapping, Sequence

import pytest

from engine.domain.optimizer import (
    EvaluationResult,
    Evaluator,
    EvaluationError,
    InvalidInputError,
    RankingRule,
    StrategyComparator,
)


class MockEvaluatorSeq(Evaluator):
    def __init__(self, results: Mapping[str, EvaluationResult]):
        self._results = results

    def get_evaluations(self, label: str) -> Sequence[EvaluationResult]:
        if label not in self._results:
            raise ValueError("unknown label")
        return [self._results[label]]


class RaisingEvaluator(Evaluator):
    def get_evaluations(self, label: str) -> Sequence[EvaluationResult]:
        raise ValueError("boom")


def test_group_by_cohort() -> None:
    results = {
        "s1": EvaluationResult(
            label="s1",
            metrics={"m": Decimal("1")},
            provenance={"cohort": ["c1"], "parameter_config": ["p1"]},
        ),
        "s2": EvaluationResult(
            label="s2",
            metrics={"m": Decimal("2")},
            provenance={"cohort": ["c2"], "parameter_config": ["p2"]},
        ),
    }

    eval1 = MockEvaluatorSeq(results)
    comparator = StrategyComparator(metrics=["m"], ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]))

    report = comparator.compare({"s1": eval1, "s2": eval1}, group_by="cohort")

    assert "c1" in report.aggregated_metrics
    assert "c2" in report.aggregated_metrics


def test_group_by_parameter_config() -> None:
    results = {
        "s1": EvaluationResult(
            label="s1",
            metrics={"m": Decimal("1")},
            provenance={"cohort": ["c1"], "parameter_config": ["p1"]},
        ),
        "s2": EvaluationResult(
            label="s2",
            metrics={"m": Decimal("3")},
            provenance={"cohort": ["c1"], "parameter_config": ["p2"]},
        ),
    }

    eval1 = MockEvaluatorSeq(results)
    comparator = StrategyComparator(metrics=["m"], ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]))

    report = comparator.compare({"s1": eval1, "s2": eval1}, group_by="parameter_config")

    assert "p1" in report.aggregated_metrics
    assert "p2" in report.aggregated_metrics


def test_missing_provenance_raises() -> None:
    results = {
        "s1": EvaluationResult(label="s1", metrics={"m": Decimal("1")}, provenance={}),
    }

    eval1 = MockEvaluatorSeq(results)
    comparator = StrategyComparator(metrics=["m"], ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]))

    with pytest.raises(InvalidInputError):
        comparator.compare({"s1": eval1}, group_by="cohort")


def test_decimal_aggregation_exactness() -> None:
    # two evaluations for same label and cohort; average should be exact Decimal
    ev1 = EvaluationResult(label="s", metrics={"m": Decimal("1.1")}, provenance={"cohort": ["c1"], "parameter_config": ["p1"]})
    ev2 = EvaluationResult(label="s", metrics={"m": Decimal("2.3")}, provenance={"cohort": ["c1"], "parameter_config": ["p1"]})

    comparator = StrategyComparator(metrics=["m"], ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]))

    report = comparator.compare({"s": [ev1, ev2]}, group_by="cohort")

    agg = report.aggregated_metrics["c1"]["s"]["m"]
    assert isinstance(agg, Decimal)
    assert agg == (Decimal("1.1") + Decimal("2.3")) / Decimal(2)


def test_deterministic_tiebreakers_and_label_tiebreak() -> None:
    # primary equal, tie-breaker differs
    ev1 = EvaluationResult(label="a", metrics={"p": Decimal("1"), "t": Decimal("2")}, provenance={"cohort": ["c1"], "parameter_config": ["p1"]})
    ev2 = EvaluationResult(label="b", metrics={"p": Decimal("1"), "t": Decimal("1")}, provenance={"cohort": ["c1"], "parameter_config": ["p1"]})
    ev3 = EvaluationResult(label="c", metrics={"p": Decimal("1"), "t": Decimal("1")}, provenance={"cohort": ["c1"], "parameter_config": ["p1"]})

    comparator = StrategyComparator(metrics=["p", "t"], ranking_rule=RankingRule(primary_metric="p", tie_breakers=["t"]))

    report = comparator.compare({"a": [ev1], "b": [ev2], "c": [ev3]}, group_by="cohort")

    ranking = report.ranking["c1"]
    # a should come first (t=2), then b and c tied on p and t, sorted by label ascending -> b then c
    assert ranking == ["a", "b", "c"]


def test_evaluator_error_wrapped() -> None:
    comparator = StrategyComparator(metrics=["m"], ranking_rule=RankingRule(primary_metric="m", tie_breakers=[]))
    with pytest.raises(EvaluationError):
        comparator.compare({"s": RaisingEvaluator()}, group_by="global")
