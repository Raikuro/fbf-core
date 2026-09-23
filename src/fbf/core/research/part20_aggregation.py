"""Part 20 aggregation — percentile SWR statistics and discrepancy classification.

Percentile-SWR semantics (resolved T2.1 decision):
- one observation per retirement-start cohort;
- each observation is that cohort's maximum sustainable/break-even SWR;
- percentiles are order statistics over the per-cohort distribution;
- CAPE conditioning is applied to the cohort population first;
- comparison uses article displayed-precision rounding (2-decimal percent).

Interpolation convention: not documented by ERN. The order statistic
``sorted[floor(p * n)]`` is the maximum SWR whose empirical failure rate
is at most ``p``.  Residual last-digit differences are classified under
the audit protocol rather than by tuning the convention.

Discrepancy protocol (audit §9, frozen):
- exact match → REPRODUCED;
- difference of exactly one display ULP → EXPLAINED DIFFERENCE;
- difference of two or more display ULPs → UNEXPLAINED DIFFERENCE;
- no observation → CAPABILITY GAP.

Quantum is driven by the anchor unit (percent → 0.01, percent_1dp → 0.1,
usd → 1).  UNEXPLAINED rows are recorded with full context, never failed
silently (audit §12.3 allows explicitly recorded unexplained results).

Part 19/20 shared abstraction: DEFERRED (T2.1 architecture decision).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

__all__ = [
    "swr_at_failure_probability",
    "percentile_swrs",
    "to_displayed_percent",
    "to_displayed_failure_percent",
    "DiscrepancyClassification",
    "classify_displayed_value",
    "unit_quantum",
    "AnchorComparison",
    "PART20_FAILURE_PROBABILITIES",
]

# Failsafe (0%), then 1%, 3%, 5%, 10%, 25% (Part 19 shares 10/25).
PART20_FAILURE_PROBABILITIES: tuple[Decimal, ...] = (
    Decimal("0"),
    Decimal("0.01"),
    Decimal("0.03"),
    Decimal("0.05"),
    Decimal("0.10"),
    Decimal("0.25"),
)

_PERCENT_QUANTUM = Decimal("0.01")
_ONE_DECIMAL_QUANTUM = Decimal("0.1")
_USD_QUANTUM = Decimal("1")

_UNIT_QUANTUMS: dict[str, Decimal] = {
    "percent": _PERCENT_QUANTUM,
    "percent_1dp": _ONE_DECIMAL_QUANTUM,
    "usd": _USD_QUANTUM,
}


def unit_quantum(unit: str) -> Decimal:
    """Display quantum for an anchor unit (raises for unknown units)."""
    try:
        return _UNIT_QUANTUMS[unit]
    except KeyError as exc:
        raise ValueError(f"unknown anchor unit {unit!r}") from exc


def swr_at_failure_probability(
    sorted_swrs: Sequence[Decimal],
    failure_probability: Decimal,
) -> Decimal:
    """Maximum SWR whose empirical failure rate is at most *failure_probability*.

    A cohort with break-even SWR *s* succeeds at withdrawal rate *w* iff
    *w <= s*.  With sorted ascending *s*, the number of failures at *w* is
    ``#{s_i < w}``.  The largest *w* with that count ``<= floor(p * n)`` is
    the order statistic at 0-based index ``floor(p * n)``.

    Raises ``ValueError`` for an empty sample or an invalid probability.
    """
    if not sorted_swrs:
        raise ValueError("sorted_swrs must be non-empty")
    if failure_probability < 0 or failure_probability > 1:
        raise ValueError(
            f"failure_probability must be in [0, 1], got {failure_probability}"
        )
    n = len(sorted_swrs)
    exact = failure_probability * Decimal(n)
    index = int(exact // Decimal("1"))
    if index >= n:
        index = n - 1
    if index < 0:
        index = 0
    return sorted_swrs[index]


def percentile_swrs(
    per_cohort_swrs: Sequence[Decimal],
    failure_probabilities: Sequence[Decimal] = PART20_FAILURE_PROBABILITIES,
) -> dict[Decimal, Decimal]:
    """Compute percentile SWRs from unsorted per-cohort break-even SWRs."""
    if not per_cohort_swrs:
        raise ValueError("per_cohort_swrs must be non-empty")
    ordered = sorted(per_cohort_swrs)
    return {
        p: swr_at_failure_probability(ordered, p) for p in failure_probabilities
    }


def to_displayed_percent(swr: Decimal) -> Decimal:
    """Round a SWR fraction to article displayed precision (2-decimal percent)."""
    return (swr * Decimal("100")).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_EVEN)


def to_displayed_failure_percent(rate: Decimal) -> Decimal:
    """Round a failure rate fraction to 1-decimal percent (Table 04)."""
    return (rate * Decimal("100")).quantize(_ONE_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class DiscrepancyClassification:
    """Single classification for one published comparison."""

    kind: str  # REPRODUCED | EXPLAINED DIFFERENCE | UNEXPLAINED DIFFERENCE | CAPABILITY GAP
    evidence: str

    def __post_init__(self) -> None:
        allowed = {
            "REPRODUCED",
            "EXPLAINED DIFFERENCE",
            "UNEXPLAINED DIFFERENCE",
            "CAPABILITY GAP",
        }
        if self.kind not in allowed:
            raise ValueError(f"invalid classification {self.kind!r}")


def _ordering_evidence() -> str:
    return (
        "ERNet: return → withdrawal → rebalance; "
        "FBF: withdrawal → rebalance → return "
        "(docs/research/ern_part20_replication.md §8.1/§8.2, "
        "ern_part20_e2e_audit.md §9 known candidates)"
    )


def _ath_evidence() -> str:
    return (
        "ERNet: nominal S&P 500 total-return ATH; "
        "FBF: real total-return underwater "
        "(ern_part20_e2e_audit.md §9; active-glidepath impact only)"
    )


def _cohort_evidence() -> str:
    return (
        "ERN 1,740 vs FBF 1,739 executable cohorts "
        "(ern_part20_replication.md §7.1; ern_part20_e2e_audit.md §9)"
    )


def _fee_evidence() -> str:
    return (
        "ERN 0.05%/yr fee omitted from the canonical baseline study YAML "
        "(expense_ratio defaults to 0)"
    )


def classify_displayed_value(
    observed: Decimal | None,
    published: Decimal,
    *,
    unit: str,
    strategy_kind: str | None,
    strategy_is_active: bool,
    calculation_path: str,
) -> DiscrepancyClassification:
    """Classify one published-vs-observed comparison under the audit protocol.

    *observed* and *published* are already in the anchor's display unit.
    ``strategy_kind``/``strategy_is_active`` may be ``None`` when no
    strategy context applies (never combined with a non-None observation).
    """
    if observed is None:
        return DiscrepancyClassification(
            "CAPABILITY GAP",
            f"no observation produced for this published cell; "
            f"calculation_path={calculation_path}",
        )
    if strategy_kind is None:
        raise ValueError(
            "strategy context is required when an observation is present "
            f"(calculation_path={calculation_path})"
        )
    quantum = unit_quantum(unit)
    if observed == published:
        return DiscrepancyClassification(
            "REPRODUCED",
            f"displayed value matches exactly ({observed}); "
            f"unit={unit}; calculation_path={calculation_path}",
        )
    delta = observed - published
    magnitude = abs(delta)
    if magnitude <= quantum:
        reasons: list[str] = [
            f"delta={delta} = one display ULP (quantum={quantum}, unit={unit})",
            _cohort_evidence(),
            _ordering_evidence(),
            _fee_evidence(),
        ]
        if strategy_kind == "glidepath" and strategy_is_active:
            reasons.append(_ath_evidence())
        reasons.append(
            "search/rounding: article last-digit convention undocumented "
            "(ern_part20_replication.md §14.1; T2.1 decision)"
        )
        return DiscrepancyClassification(
            "EXPLAINED DIFFERENCE",
            "; ".join(reasons)
            + f"; calculation_path={calculation_path}"
            + "; variant isolation pending Part 19/20 shared work "
            "(audit §10 variants not executed in T2.1 baseline)",
        )
    ulps = magnitude / quantum
    return DiscrepancyClassification(
        "UNEXPLAINED DIFFERENCE",
        f"delta={delta} spans {ulps} display ULPs (quantum={quantum}, unit={unit}); "
        f"published={published}, observed={observed}; "
        f"calculation_path={calculation_path}; "
        "§10 variant isolation not run in T2.1 baseline — "
        "requires follow-up investigation (audit §9/§14)",
    )


@dataclass(frozen=True, slots=True)
class AnchorComparison:
    """One published-vs-observed cell ready for the audit matrix."""

    experiment: str
    strategy_id: str
    metric: str
    horizon_years: int | None
    final_value_target: Decimal | None
    cape_regime: str
    published_percent: Decimal
    observed_percent: Decimal | None
    classification: DiscrepancyClassification
    cohort_count: int
    calculation_path: str
    unit: str = "percent"

    @property
    def absolute_difference_percent(self) -> Decimal | None:
        if self.observed_percent is None:
            return None
        return self.observed_percent - self.published_percent

    @property
    def identifying_context(self) -> str:
        """Full cell identity + path + evidence (for recorded unexplained rows)."""
        return (
            f"{self.format_row()} | path={self.calculation_path} | "
            f"n={self.cohort_count} | evidence={self.classification.evidence}"
        )

    def format_row(self) -> str:
        obs = (
            f"{self.observed_percent}"
            if self.observed_percent is not None
            else "n/a"
        )
        diff = self.absolute_difference_percent
        diff_s = f"{diff:+}" if diff is not None else "n/a"
        fv = (
            str(self.final_value_target)
            if self.final_value_target is not None
            else "n/a"
        )
        return (
            f"{self.experiment} | {self.strategy_id} | {self.metric} | "
            f"H={self.horizon_years} | FV={fv} | "
            f"{self.cape_regime} | pub={self.published_percent} | "
            f"obs={obs} | Δ={diff_s} | {self.unit} | "
            f"{self.classification.kind}"
        )
