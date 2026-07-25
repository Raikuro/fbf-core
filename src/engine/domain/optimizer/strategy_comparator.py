"""StrategyComparator implementation for deterministic comparative analysis."""

from __future__ import annotations

from typing import Mapping, Sequence, Union, MutableMapping

from .types import (
    EvaluationResult,
    Evaluator,
    InvalidInputError,
    RankingRule,
    StrategyComparisonReport,
    GroupingDimension,
    EvaluationError,
)


class StrategyComparator:
    """
    Consumer component for comparative analytics.

    Produces deterministic, auditable comparative analytics between labelled strategies.
    Each strategy is an externally defined label that maps to a set of evaluation
    artefacts or to an abstract evaluator capable of materialising them.
    """

    def __init__(self, metrics: Sequence[str], ranking_rule: RankingRule):
        self._metrics = metrics
        self._ranking_rule = ranking_rule

    def compare(
        self,
        strategy_map: Mapping[str, Union[Sequence[EvaluationResult], Evaluator]],
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

        # Helper to materialise evaluations for a strategy label
        def _materialise(label: str, source) -> Sequence[EvaluationResult]:
            # Evaluator
            if hasattr(source, "get_evaluations") and callable(source.get_evaluations):
                try:
                    vals = source.get_evaluations(label)
                except Exception as exc:  # wrap any evaluator error
                    raise EvaluationError(str(exc)) from exc
                return vals

            # Assume it's an iterable of EvaluationResult
            if isinstance(source, Sequence):
                return source  # type: ignore[return-value]

            raise InvalidInputError("strategy source must be an Evaluator or a sequence of EvaluationResult")

        # Aggregation structures
        aggregated: MutableMapping[str, MutableMapping[str, MutableMapping[str, float]]] = {}
        provenance_map: MutableMapping[str, MutableMapping[str, Sequence[str]]] = {}
        diagnostics: MutableMapping[str, MutableMapping[str, str]] = {}

        for label, source in strategy_map.items():
            evaluations = _materialise(label, source)
            if not evaluations:
                raise InvalidInputError(f"no evaluations for label: {label}")

            # Determine grouping keys from evaluations
            for ev in evaluations:
                if group_by == "global":
                    gkey = "global"
                else:
                    # pick first provenance key if present, otherwise fall back to global
                    if ev.provenance:
                        # choose a canonical provenance key if exists
                        # use the first provenance mapping key as grouping key
                        gkey = next(iter(ev.provenance))
                    else:
                        gkey = "global"

                aggregated.setdefault(gkey, {})
                aggregated[gkey].setdefault(label, {})
                provenance_map.setdefault(gkey, {})
                provenance_map[gkey].setdefault(label, [])
                diagnostics.setdefault(gkey, {})

                # accumulate metrics (simple average across evaluations per label/group)
                for m in self._metrics:
                    val = ev.metrics.get(m)
                    if val is None:
                        # missing metric treated as 0.0 for aggregation
                        val = 0.0
                    # sum via storing cumulative and count in diagnostics keys
                    existing = aggregated[gkey][label].get(m)
                    if existing is None:
                        aggregated[gkey][label][m] = float(val)
                        # use diagnostics to track count
                        diagnostics[gkey][f"{label}:{m}:count"] = "1"
                    else:
                        aggregated[gkey][label][m] = existing + float(val)
                        diagnostics[gkey][f"{label}:{m}:count"] = str(int(diagnostics[gkey][f"{label}:{m}:count"]) + 1)

                # append provenance ids
                for prov_vals in ev.provenance.values():
                    provenance_map[gkey][label] = list(provenance_map[gkey][label]) + list(prov_vals)

        # Finalize averages and prepare ranking
        final_aggregated: MutableMapping[str, MutableMapping[str, MutableMapping[str, float]]] = {}
        ranking_map: MutableMapping[str, Sequence[str]] = {}

        for gkey, per_label in aggregated.items():
            final_aggregated[gkey] = {}
            # finalize averages
            for label, metrics_map in per_label.items():
                final_aggregated[gkey][label] = {}
                for m, total in metrics_map.items():
                    count = int(diagnostics[gkey].get(f"{label}:{m}:count", "1"))
                    final_aggregated[gkey][label][m] = total / count if count > 0 else 0.0

            # ranking: sort labels by primary metric descending, then tie_breakers, then label
            def sort_key(label_name: str):
                primary = final_aggregated[gkey][label_name].get(self._ranking_rule.primary_metric, 0.0)
                tie_values = [
                    final_aggregated[gkey][label_name].get(tb, 0.0) for tb in self._ranking_rule.tie_breakers
                ]
                # negative label for deterministic final tie-break (ascending label)
                return tuple([-primary] + [-v for v in tie_values] + [label_name])

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