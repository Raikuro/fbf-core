"""StrategyComparator implementation for deterministic comparative analysis."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from decimal import Decimal
from typing import Any, cast

from .types import (
    EvaluationError,
    EvaluationResult,
    Evaluator,
    GroupingDimension,
    InvalidInputError,
    MetricDefinition,
    MetricDirection,
    RankingRule,
    StrategyComparisonReport,
)


class StrategyComparator:
    """
    Consumer component for comparative analytics.

    Produces deterministic, auditable comparative analytics between labelled strategies.
    Each strategy is an externally defined label that maps to a set of evaluation
    artefacts or to an abstract evaluator capable of materialising them.

    Ranking uses the explicit direction declared by each ``MetricDefinition``;
    the comparator never infers whether a metric is maximized or minimized.
    """

    def __init__(self, metrics: Sequence[MetricDefinition], ranking_rule: RankingRule):
        self._metrics = tuple(metrics)
        self._ranking_rule = ranking_rule

    def compare(
        self,
        strategy_map: Mapping[str, Sequence[EvaluationResult] | Evaluator],
        group_by: GroupingDimension = "global",
    ) -> StrategyComparisonReport:
        """
        Produces a deterministic report from the provided strategies.

        Args:
            strategy_map: Mapping from label to evaluator or evaluation results.

        Returns:
            StrategyComparisonReport: Immutable report containing aggregated metrics
                and ranking.

        Raises:
            InvalidInputError: If input validation fails.
        """
        # Input validation
        if not strategy_map:
            raise InvalidInputError("strategy_map cannot be empty")

        if not self._metrics:
            raise InvalidInputError("metrics cannot be empty")

        if group_by not in ("parameter_config", "cohort", "global"):
            raise InvalidInputError(f"invalid group_by: {group_by}")

        metric_directions: dict[str, MetricDirection] = {}
        for metric in self._metrics:
            if metric.name in metric_directions:
                raise InvalidInputError(
                    f"duplicate metric definition: {metric.name!r}"
                )
            metric_directions[metric.name] = metric.direction

        ranking_metrics = (
            self._ranking_rule.primary_metric,
            *self._ranking_rule.tie_breakers,
        )
        seen_ranking_metrics: set[str] = set()
        for metric_name in ranking_metrics:
            if metric_name in seen_ranking_metrics:
                raise InvalidInputError(
                    f"duplicate ranking metric: {metric_name!r}"
                )
            seen_ranking_metrics.add(metric_name)
            if metric_name not in metric_directions:
                raise InvalidInputError(
                    f"ranking metric {metric_name!r} is not declared in metrics"
                )

        # Helper to materialise evaluations for a strategy label
        def _materialise(label: str, source: Any) -> Sequence[EvaluationResult]:
            # Evaluator
            if hasattr(source, "get_evaluations") and callable(source.get_evaluations):
                try:
                    vals: Sequence[EvaluationResult] = source.get_evaluations(label)
                except Exception as exc:  # wrap any evaluator error
                    raise EvaluationError(str(exc)) from exc
                return vals

            # Assume it's an iterable of EvaluationResult
            if isinstance(source, Sequence):
                return cast(Sequence[EvaluationResult], source)

            raise InvalidInputError(
                "strategy source must be an Evaluator or a sequence of EvaluationResult"
            )

        # Aggregation structures (use Decimal for numeric sums)
        aggregated: MutableMapping[
            str, MutableMapping[str, MutableMapping[str, Decimal]]
        ] = {}
        provenance_map: MutableMapping[str, MutableMapping[str, Sequence[str]]] = {}
        diagnostics: MutableMapping[str, MutableMapping[str, str]] = {}
        counts: MutableMapping[str, MutableMapping[str, MutableMapping[str, int]]] = {}

        for label, source in strategy_map.items():
            evaluations = _materialise(label, source)
            if not evaluations:
                raise InvalidInputError(f"no evaluations for label: {label}")

            # Determine grouping keys from evaluations
            for ev in evaluations:
                if group_by == "global":
                    gkey = "global"
                elif group_by == "cohort":
                    ids = ev.provenance.get("cohort")
                    if not ids or len(ids) == 0:
                        raise InvalidInputError("missing cohort provenance for grouping")
                    if len(ids) != 1:
                        raise InvalidInputError(
                            "provenance['cohort'] must contain exactly one canonical identifier"
                        )
                    gkey = ids[0]
                elif group_by == "parameter_config":
                    ids = ev.provenance.get("parameter_config")
                    if not ids or len(ids) == 0:
                        raise InvalidInputError("missing parameter_config provenance for grouping")
                    if len(ids) != 1:
                        raise InvalidInputError(
                            "provenance['parameter_config'] must contain exactly one "
                            "canonical identifier"
                        )
                    gkey = ids[0]
                else:
                    raise InvalidInputError(f"invalid group_by: {group_by}")

                aggregated.setdefault(gkey, {})
                aggregated[gkey].setdefault(label, {})
                provenance_map.setdefault(gkey, {})
                provenance_map[gkey].setdefault(label, [])
                diagnostics.setdefault(gkey, {})
                counts.setdefault(gkey, {})
                counts[gkey].setdefault(label, {})

                # accumulate metrics (simple average across evaluations per label/group)
                for metric in self._metrics:
                    val = ev.metrics.get(metric.name)
                    if val is None:
                        # Unavailable metrics are excluded from the average;
                        # they are not numeric zero and must not affect the
                        # ranking of metrics that are actually observed.
                        continue
                    # ensure Decimal arithmetic
                    val_d = val if isinstance(val, Decimal) else Decimal(str(val))

                    existing = aggregated[gkey][label].get(metric.name)
                    if existing is None:
                        aggregated[gkey][label][metric.name] = val_d
                        counts[gkey][label][metric.name] = 1
                        diagnostics[gkey][f"{label}:{metric.name}:count"] = "1"
                    else:
                        aggregated[gkey][label][metric.name] = existing + val_d
                        counts[gkey][label][metric.name] = (
                            counts[gkey][label].get(metric.name, 1) + 1
                        )
                        diagnostics[gkey][f"{label}:{metric.name}:count"] = str(
                            counts[gkey][label][metric.name]
                        )

                # append provenance ids
                for prov_vals in ev.provenance.values():
                    provenance_map[gkey][label] = (
                        list(provenance_map[gkey][label]) + list(prov_vals)
                    )

        # Finalize averages and prepare ranking
        final_aggregated: MutableMapping[
            str, MutableMapping[str, MutableMapping[str, Decimal | None]]
        ] = {}
        ranking_map: MutableMapping[str, Sequence[str]] = {}

        for gkey, per_label in aggregated.items():
            final_aggregated[gkey] = {}
            # finalize averages
            for label, metrics_map in per_label.items():
                final_aggregated[gkey][label] = {}
                for m, total in metrics_map.items():
                    count = counts[gkey][label].get(m, 0)
                    final_aggregated[gkey][label][m] = (
                        (total / Decimal(count)) if count > 0 else None
                    )
                for metric in self._metrics:
                    if metric.name not in final_aggregated[gkey][label]:
                        final_aggregated[gkey][label][metric.name] = None

            # ranking: sort labels by primary metric direction, then tie_breakers,
            # then label
            def sort_key(label_name: str, *, _group_key: str = gkey) -> tuple[Any, ...]:
                def rank_component(metric_name: str) -> tuple[bool, Decimal]:
                    value = final_aggregated[_group_key][label_name].get(
                        metric_name
                    )
                    if value is None:
                        # Unavailable metrics sort after every measured value.
                        return (True, Decimal(0))
                    if metric_directions[metric_name] is MetricDirection.MAXIMIZE:
                        return (False, -value)
                    return (False, value)

                primary = rank_component(self._ranking_rule.primary_metric)
                tie_values = tuple(
                    rank_component(tb)
                    for tb in self._ranking_rule.tie_breakers
                )
                return (primary, *tie_values, label_name)

            sorted_labels = sorted(final_aggregated[gkey].keys(), key=sort_key)
            ranking_map[gkey] = sorted_labels

        # Build diagnostics mapping (human friendly)
        user_diagnostics: MutableMapping[str, MutableMapping[str, str]] = {}
        for gkey in diagnostics:
            user_diagnostics[gkey] = {}
            # sample sizes per label (derive from counts of first metric)
            for key in list(diagnostics[gkey].keys()):
                # keys like 'label:metric:count'
                user_diagnostics[gkey][key] = diagnostics[gkey][key]

        return StrategyComparisonReport(
            aggregated_metrics=final_aggregated,
            ranking=ranking_map,
            provenance=provenance_map,
            diagnostics=user_diagnostics,
        )
