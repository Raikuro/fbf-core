"""StrategyComparator implementation for deterministic comparative analysis."""

from __future__ import annotations

from typing import Any, Mapping, Sequence, Union, MutableMapping, cast
from decimal import Decimal

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

            raise InvalidInputError("strategy source must be an Evaluator or a sequence of EvaluationResult")

        # Aggregation structures (use Decimal for numeric sums)
        aggregated: MutableMapping[str, MutableMapping[str, MutableMapping[str, Decimal]]] = {}
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
                        raise InvalidInputError("provenance['cohort'] must contain exactly one canonical identifier")
                    gkey = ids[0]
                elif group_by == "parameter_config":
                    ids = ev.provenance.get("parameter_config")
                    if not ids or len(ids) == 0:
                        raise InvalidInputError("missing parameter_config provenance for grouping")
                    if len(ids) != 1:
                        raise InvalidInputError("provenance['parameter_config'] must contain exactly one canonical identifier")
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
                for m in self._metrics:
                    val = ev.metrics.get(m)
                    if val is None:
                        # missing metric treated as Decimal(0)
                        val_d = Decimal(0)
                    else:
                        # ensure Decimal arithmetic
                        if isinstance(val, Decimal):
                            val_d = val
                        else:
                            val_d = Decimal(str(val))

                    existing = aggregated[gkey][label].get(m)
                    if existing is None:
                        aggregated[gkey][label][m] = val_d
                        counts[gkey][label][m] = 1
                        diagnostics[gkey][f"{label}:{m}:count"] = "1"
                    else:
                        aggregated[gkey][label][m] = existing + val_d
                        counts[gkey][label][m] = counts[gkey][label].get(m, 1) + 1
                        diagnostics[gkey][f"{label}:{m}:count"] = str(counts[gkey][label][m])

                # append provenance ids
                for prov_vals in ev.provenance.values():
                    provenance_map[gkey][label] = list(provenance_map[gkey][label]) + list(prov_vals)

        # Finalize averages and prepare ranking
        final_aggregated: MutableMapping[str, MutableMapping[str, MutableMapping[str, Decimal]]] = {}
        ranking_map: MutableMapping[str, Sequence[str]] = {}

        for gkey, per_label in aggregated.items():
            final_aggregated[gkey] = {}
            # finalize averages
            for label, metrics_map in per_label.items():
                final_aggregated[gkey][label] = {}
                for m, total in metrics_map.items():
                    count = counts[gkey][label].get(m, 1)
                    final_aggregated[gkey][label][m] = (total / Decimal(count)) if count > 0 else Decimal(0)

            # ranking: sort labels by primary metric descending, then tie_breakers, then label
            def sort_key(label_name: str) -> tuple[Any, ...]:
                primary = final_aggregated[gkey][label_name].get(self._ranking_rule.primary_metric, Decimal(0))
                tie_values = [
                    final_aggregated[gkey][label_name].get(tb, Decimal(0)) for tb in self._ranking_rule.tie_breakers
                ]
                # negative numeric values to sort descending; label_name ascending as final tiebreak
                negs = [ -primary ] + [ -v for v in tie_values ]
                return tuple(negs + [label_name])

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