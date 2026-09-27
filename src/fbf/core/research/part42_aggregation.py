"""Part 42 aggregation and anchor comparison.

Aggregates Part 42 experiment results into the published table formats
and compares against the transcribed anchors from the audit fixture.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from fbf.core.research.part42_pipeline import (
    Part42ExecutionContext,
    Part42FailsafeResult,
    Part42FixedSWRResult,
)

__all__ = [
    "AnchorComparison",
    "build_table01_aggregation",
    "build_table02_aggregation",
    "build_table03_aggregation",
    "build_table04_aggregation",
    "build_table05_aggregation",
    "compare_anchor",
    "structural_checks",
]


@dataclass(frozen=True, slots=True)
class AnchorComparison:
    """Comparison of one published anchor against FBF result."""

    table: int
    scenario: str
    decade: str | None
    condition: str | None
    metric: str
    published: Decimal | None
    observed: Decimal | None
    cohort_count: int
    unit: str
    classification: Classification

    def format_row(self) -> str:
        obs_str = f"{self.observed:.6f}" if self.observed is not None else "N/A"
        pub_str = f"{self.published:.6f}" if self.published is not None else "N/A"
        return (
            f"T{self.table} | {self.scenario:20s} | "
            f"{self.decade or '':10s} | "
            f"{self.condition or '':15s} | "
            f"pub={pub_str:>8s} obs={obs_str:>8s} | "
            f"{self.classification.kind}"
        )


@dataclass(frozen=True, slots=True)
class Classification:
    kind: str  # REPRODUCED, EXPLAINED DIFFERENCE, UNEXPLAINED DIFFERENCE, CAPABILITY GAP
    evidence: str = ""


def compare_anchor(anchor: Any, observed: Decimal | None, cohort_count: int) -> AnchorComparison:
    # Handle N/A (not applicable) published values - intentionally blank
    if anchor.published == "N/A":
        return AnchorComparison(
            table=anchor.table,
            scenario=anchor.scenario,
            decade=anchor.decade,
            condition=anchor.condition,
            metric=anchor.metric,
            published=None,
            observed=observed,
            cohort_count=cohort_count,
            unit=anchor.unit,
            classification=Classification("REPRODUCED", "Published value is N/A"),
        )

    if observed is None:
        return AnchorComparison(
            table=anchor.table,
            scenario=anchor.scenario,
            decade=anchor.decade,
            condition=anchor.condition,
            metric=anchor.metric,
            published=Decimal(anchor.published),
            observed=None,
            cohort_count=cohort_count,
            unit=anchor.unit,
            classification=Classification("CAPABILITY GAP", "No observed value produced"),
        )

    published = Decimal(anchor.published)
    diff = abs(observed - published)

    if anchor.unit == "usd":
        tolerance = Decimal("1")
    elif anchor.unit == "percent":
        tolerance = Decimal("0.1")
    elif anchor.unit == "percent_2dp":
        tolerance = Decimal("0.01")
    else:
        tolerance = Decimal("0.1")

    if diff <= tolerance:
        classification = Classification("REPRODUCED", f"diff={diff} <= tol={tolerance}")
    else:
        if diff <= tolerance * 3:
            classification = Classification(
                "UNEXPLAINED DIFF", f"diff={diff} > tol={tolerance} (2-3 ULP)")
        else:
            classification = Classification("UNEXPLAINED DIFF", f"diff={diff} > tol={tolerance}")

    return AnchorComparison(
        table=anchor.table,
        scenario=anchor.scenario,
        decade=anchor.decade,
        condition=anchor.condition,
        metric=anchor.metric,
        published=published,
        observed=observed,
        cohort_count=cohort_count,
        unit=anchor.unit,
        classification=classification,
    )


def structural_checks(state: Any) -> None:
    spec = state.spec
    manifest = state.manifest
    market_cohorts = sum(1 for e in manifest.cohorts if e.market_available)
    assert market_cohorts == spec.structural_counts.get("total_cohorts", 1739), (
        f"Manifest market cohorts: {market_cohorts} != spec: "
        f"{spec.structural_counts.get('total_cohorts')}"
    )

    cape_available = sum(1 for e in manifest.cohorts if e.market_available and e.cape_available)
    assert cape_available == spec.structural_counts.get("cape_available", 1485), (
        f"CAPE available: {cape_available} != spec: {spec.structural_counts.get('cape_available')}"
    )


def _compute_decade_failsafe(
    result: Part42FailsafeResult,
    ctx: Part42ExecutionContext,
    cohort_dates: list[str],
) -> dict[str, Decimal]:
    decade_swrs: dict[str, list[Decimal]] = defaultdict(list)

    for i, cohort_date in enumerate(cohort_dates):
        year = int(cohort_date[:4])
        decade = f"{year // 10 * 10}s"
        if i < len(result.per_cohort_swrs):
            decade_swrs[decade].append(result.per_cohort_swrs[i])

    decade_min = {}
    for decade, swrs in decade_swrs.items():
        if swrs:
            decade_min[decade] = min(swrs)
        else:
            decade_min[decade] = Decimal("0")

    all_swrs = [s for swrs in decade_swrs.values() for s in swrs]
    if all_swrs:
        decade_min["Min"] = min(all_swrs)
    else:
        decade_min["Min"] = Decimal("0")

    return decade_min


def _filter_cohorts_by_condition(
    cohort_dates: list[str],
    manifest: Any,
    condition: str,
    trajectory: Any = None,
) -> list[str]:
    """Filter cohort dates by the specified Table 01 condition."""
    if condition == "All":
        return cohort_dates

    filtered = []
    for cd in cohort_dates:
        entry = None
        for e in manifest.cohorts:
            if e.cohort_date == cd:
                entry = e
                break
        if entry is None:
            continue

        if condition == "Since_1926":
            year = int(cd[:4])
            if year >= 1926:
                filtered.append(cd)
        elif condition == "Since_1950":
            year = int(cd[:4])
            if year >= 1950:
                filtered.append(cd)
        elif condition == "CAPE_le_20":
            if entry.cape_value is not None and entry.cape_value <= Decimal("20"):
                filtered.append(cd)
        elif condition == "CAPE_gt_20":
            if entry.cape_value is not None and entry.cape_value > Decimal("20"):
                filtered.append(cd)
        elif condition == "SP500_High":
            # Within 10% of ATH at cohort start
            # Check if S&P 500 at cohort start is within 10% of running ATH
            if trajectory is not None and entry.cape_available:
                # Get the S&P 500 index level at cohort start
                try:
                    snapshot = trajectory.slice(date.fromisoformat(cd), 1)[0]
                    equity_asset = snapshot.index_levels.get("equity")
                    running_ath = snapshot.running_ath
                    if equity_asset is not None and running_ath is not None and running_ath > 0:
                        drawdown_pct = (running_ath - equity_asset) / running_ath
                        if drawdown_pct <= Decimal("0.10"):  # Within 10% of ATH
                            filtered.append(cd)
                except Exception:
                    pass
        elif condition == "Drdwn_0_10":
            if trajectory is not None:
                try:
                    snapshot = trajectory.slice(date.fromisoformat(cd), 1)[0]
                    equity_asset = snapshot.index_levels.get("equity")
                    running_ath = snapshot.running_ath
                    if equity_asset is not None and running_ath is not None and running_ath > 0:
                        drawdown_pct = (running_ath - equity_asset) / running_ath
                        # 0 < drawdown ≤ 10% (excludes exactly at ATH which is in SP500_High)
                        if Decimal("0") < drawdown_pct <= Decimal("0.10"):
                            filtered.append(cd)
                except Exception:
                    pass
        elif condition == "Drdwn_10_20":
            if trajectory is not None:
                try:
                    snapshot = trajectory.slice(date.fromisoformat(cd), 1)[0]
                    equity_asset = snapshot.index_levels.get("equity")
                    running_ath = snapshot.running_ath
                    if equity_asset is not None and running_ath is not None and running_ath > 0:
                        drawdown_pct = (running_ath - equity_asset) / running_ath
                        if Decimal("0.10") < drawdown_pct <= Decimal("0.20"):
                            filtered.append(cd)
                except Exception:
                    pass
        elif condition == "Drdwn_20_30":
            if trajectory is not None:
                try:
                    snapshot = trajectory.slice(date.fromisoformat(cd), 1)[0]
                    equity_asset = snapshot.index_levels.get("equity")
                    running_ath = snapshot.running_ath
                    if equity_asset is not None and running_ath is not None and running_ath > 0:
                        drawdown_pct = (running_ath - equity_asset) / running_ath
                        if Decimal("0.20") < drawdown_pct <= Decimal("0.30"):
                            filtered.append(cd)
                except Exception:
                    pass
        elif condition == "Drdwn_gt_30":
            if trajectory is not None:
                try:
                    snapshot = trajectory.slice(date.fromisoformat(cd), 1)[0]
                    equity_asset = snapshot.index_levels.get("equity")
                    running_ath = snapshot.running_ath
                    if equity_asset is not None and running_ath is not None and running_ath > 0:
                        drawdown_pct = (running_ath - equity_asset) / running_ath
                        if drawdown_pct > Decimal("0.30"):
                            filtered.append(cd)
                except Exception:
                    pass

    return filtered


def build_table02_aggregation(
    failsafe_results: dict[str, Part42FailsafeResult],
    ctx: Part42ExecutionContext,
    populations: dict[str, list[str]],
) -> dict[str, dict[str, Decimal]]:
    result = failsafe_results.get("A")
    if not result:
        return {}

    cohort_dates = []
    for cd in populations["ALL"]:
        if ctx.effective_horizon(cd, 12 + 30 * 12 + 1) >= 12 + 30 * 12 + 1:
            cohort_dates.append(cd)

    decade_min = _compute_decade_failsafe(result, ctx, cohort_dates)

    from fbf.core.research.part42_pipeline import PART42_INITIAL_WEALTH
    initial_wealth = PART42_INITIAL_WEALTH.amount

    table = {}
    for decade in [
        "1920s", "1930s", "1940s", "1950s", "1960s",
        "1970s", "1980s", "1990s", "2000s", "Min",
    ]:
        swr = decade_min.get(decade, Decimal("0"))
        table[decade] = {"Baseline": (swr * initial_wealth).quantize(Decimal("1"))}
    return table


def build_table03_aggregation(
    failsafe_results: dict[str, Part42FailsafeResult],
    ctx: Part42ExecutionContext,
    populations: dict[str, list[str]],
) -> dict[str, dict[str, Decimal | None]]:
    results = {
        "Baseline": failsafe_results.get("A"),
        "Delay RE 1Y": failsafe_results.get("B"),
        "$5k/m contributions": failsafe_results.get("C"),
    }

    cohort_dates = {}
    for scenario, result in results.items():
        if result:
            dates = []
            for cd in populations["ALL"]:
                if ctx.effective_horizon(cd, 12 + 30 * 12 + 1) >= 12 + 30 * 12 + 1:
                    dates.append(cd)
            cohort_dates[scenario] = dates

    from fbf.core.research.part42_pipeline import PART42_INITIAL_WEALTH
    initial_wealth = PART42_INITIAL_WEALTH.amount

    table = {}
    all_decades = [
        "1920s", "1930s", "1940s", "1950s", "1960s",
        "1970s", "1980s", "1990s", "2000s", "Min", "Rel to Base",
    ]

    for decade in all_decades:
        row: dict[str, Decimal | None] = {}
        if decade == "Rel to Base":
            baseline_min_result = results["Baseline"]
            assert baseline_min_result is not None
            baseline_min = _compute_decade_failsafe(
                baseline_min_result, ctx, cohort_dates["Baseline"]
            ).get("Min", Decimal("0"))
            delay_min_result = results["Delay RE 1Y"]
            assert delay_min_result is not None
            delay_min = _compute_decade_failsafe(
                delay_min_result, ctx, cohort_dates["Delay RE 1Y"]
            ).get("Min", Decimal("0"))
            contrib_min_result = results["$5k/m contributions"]
            assert contrib_min_result is not None
            contrib_min = _compute_decade_failsafe(
                contrib_min_result, ctx, cohort_dates["$5k/m contributions"]
            ).get("Min", Decimal("0"))
            # Include baseline column in Rel to Base row as N/A (None)
            row["Baseline"] = None
            if baseline_min > 0:
                row["Delay RE 1Y"] = (
            (delay_min / baseline_min - 1) * 100
        ).quantize(Decimal("0.01"))
                row["$5k/m contributions"] = (
            (contrib_min / baseline_min - 1) * 100
        ).quantize(Decimal("0.01"))
            else:
                row["Delay RE 1Y"] = Decimal("0")
                row["$5k/m contributions"] = Decimal("0")
        else:
            for scenario in [
                "Baseline", "Delay RE 1Y", "$5k/m contributions",
            ]:
                result = results[scenario]
                assert result is not None
                decade_min = _compute_decade_failsafe(
                    result, ctx, cohort_dates[scenario]
                ).get(decade, Decimal("0"))
                row[scenario] = (decade_min * initial_wealth).quantize(Decimal("1"))
        table[decade] = row
    return table


def build_table04_aggregation(
    failsafe_results: dict[str, Part42FailsafeResult],
    ctx: Part42ExecutionContext,
    populations: dict[str, list[str]],
) -> dict[str, dict[str, Decimal | None]]:
    results = {
        "30Y Baseline": failsafe_results.get("A"),
        "30Y Delay RE 1Y": failsafe_results.get("B"),
        "30Y $5k/m contr.": failsafe_results.get("C"),
        "50Y Baseline": failsafe_results.get("D"),
        "50Y Delay RE 1Y": failsafe_results.get("E_delay"),
        "50Y $5k/m contr.": failsafe_results.get("E_contrib"),
    }

    cohort_dates = {}
    for scenario, result in results.items():
        if result:
            dates = []
            horizon = 30 if "30Y" in scenario else 50
            for cd in populations["ALL"]:
                if ctx.effective_horizon(cd, 12 + horizon * 12 + 1) >= 12 + horizon * 12 + 1:
                    dates.append(cd)
            cohort_dates[scenario] = dates

    from fbf.core.research.part42_pipeline import PART42_INITIAL_WEALTH
    initial_wealth = PART42_INITIAL_WEALTH.amount

    table = {}
    all_decades = [
        "1920s", "1930s", "1940s", "1950s", "1960s",
        "1970s", "1980s", "1990s", "2000s", "Min", "Rel to Base",
    ]
    for decade in all_decades:
        row: dict[str, Decimal | None] = {}
        if decade == "Rel to Base":
            base50_result = results["50Y Baseline"]
            assert base50_result is not None
            base50 = _compute_decade_failsafe(
                base50_result, ctx, cohort_dates["50Y Baseline"]
            ).get("Min", Decimal("0"))
            delay50_result = results["50Y Delay RE 1Y"]
            assert delay50_result is not None
            delay50 = _compute_decade_failsafe(
                delay50_result, ctx, cohort_dates["50Y Delay RE 1Y"]
            ).get("Min", Decimal("0"))
            contrib50_result = results["50Y $5k/m contr."]
            assert contrib50_result is not None
            contrib50 = _compute_decade_failsafe(
                contrib50_result, ctx, cohort_dates["50Y $5k/m contr."]
            ).get("Min", Decimal("0"))
            row["50Y Delay RE 1Y"] = ((delay50 / base50 - 1) * 100).quantize(Decimal("0.01"))
            row["50Y $5k/m contr."] = ((contrib50 / base50 - 1) * 100).quantize(Decimal("0.01"))
            # Include baseline columns in Rel to Base row as N/A (None)
            row["30Y Baseline"] = None
            row["50Y Baseline"] = None
        else:
            for scenario in [
                "30Y Baseline", "30Y Delay RE 1Y", "30Y $5k/m contr.",
                "50Y Baseline", "50Y Delay RE 1Y", "50Y $5k/m contr.",
            ]:
                result = results[scenario]
                assert result is not None
                decade_min = _compute_decade_failsafe(
                    result, ctx, cohort_dates[scenario]
                ).get(decade, Decimal("0"))
                row[scenario] = (decade_min * initial_wealth).quantize(Decimal("1"))
        table[decade] = row
    return table


def build_table05_aggregation(
    failsafe_results: dict[str, Part42FailsafeResult],
    ctx: Part42ExecutionContext,
    populations: dict[str, list[str]],
) -> dict[str, dict[str, Decimal | None]]:
    results = {
        "30Y Baseline": failsafe_results.get("A"),
        "30Y Delay RE 1Y": failsafe_results.get("B"),
        "30Y $5k/m contr.": failsafe_results.get("C"),
        "50Y Baseline": failsafe_results.get("D"),
        "50Y Delay RE 1Y": failsafe_results.get("E_delay"),
        "50Y $5k/m contr.": failsafe_results.get("E_contrib"),
        "50Y+SS Baseline": failsafe_results.get("F_baseline"),
        "50Y+SS Delay RE 1Y": failsafe_results.get("F_delay"),
        "50Y+SS $5k/m contr.": failsafe_results.get("F_contrib"),
        "2-year delay": failsafe_results.get("G_2yr"),
    }

    cohort_dates = {}
    for scenario, result in results.items():
        if result:
            dates = []
            horizon = 30 if "30Y" in scenario else 50
            for cd in populations["ALL"]:
                if ctx.effective_horizon(cd, 12 + horizon * 12 + 1) >= 12 + horizon * 12 + 1:
                    dates.append(cd)
            cohort_dates[scenario] = dates

    from fbf.core.research.part42_pipeline import PART42_INITIAL_WEALTH
    initial_wealth = PART42_INITIAL_WEALTH.amount

    table = {}
    all_decades = [
        "1920s", "1930s", "1940s", "1950s", "1960s",
        "1970s", "1980s", "1990s", "2000s", "Min", "Rel to Base",
    ]

    for decade in all_decades:
        row: dict[str, Decimal | None] = {}
        if decade == "Rel to Base":
            base30_result = results["30Y Baseline"]
            assert base30_result is not None
            base30 = _compute_decade_failsafe(
                base30_result, ctx, cohort_dates["30Y Baseline"]
            ).get("Min", Decimal("0"))
            base50_result = results["50Y Baseline"]
            assert base50_result is not None
            base50 = _compute_decade_failsafe(
                base50_result, ctx, cohort_dates["50Y Baseline"]
            ).get("Min", Decimal("0"))
            base_ss_result = results["50Y+SS Baseline"]
            assert base_ss_result is not None
            base_ss = _compute_decade_failsafe(
                base_ss_result, ctx, cohort_dates["50Y+SS Baseline"]
            ).get("Min", Decimal("0"))

            delay30_result = results["30Y Delay RE 1Y"]
            assert delay30_result is not None
            delay30 = _compute_decade_failsafe(
                delay30_result, ctx, cohort_dates["30Y Delay RE 1Y"]
            ).get("Min", Decimal("0"))
            delay50_result = results["50Y Delay RE 1Y"]
            assert delay50_result is not None
            delay50 = _compute_decade_failsafe(
                delay50_result, ctx, cohort_dates["50Y Delay RE 1Y"]
            ).get("Min", Decimal("0"))
            delay_ss_result = results["50Y+SS Delay RE 1Y"]
            assert delay_ss_result is not None
            delay_ss = _compute_decade_failsafe(
                delay_ss_result, ctx, cohort_dates["50Y+SS Delay RE 1Y"]
            ).get("Min", Decimal("0"))
            contrib30_result = results["30Y $5k/m contr."]
            assert contrib30_result is not None
            contrib30 = _compute_decade_failsafe(
                contrib30_result, ctx, cohort_dates["30Y $5k/m contr."]
            ).get("Min", Decimal("0"))
            contrib50_result = results["50Y $5k/m contr."]
            assert contrib50_result is not None
            contrib50 = _compute_decade_failsafe(
                contrib50_result, ctx, cohort_dates["50Y $5k/m contr."]
            ).get("Min", Decimal("0"))
            contrib_ss_result = results["50Y+SS $5k/m contr."]
            assert contrib_ss_result is not None
            contrib_ss = _compute_decade_failsafe(
                contrib_ss_result, ctx, cohort_dates["50Y+SS $5k/m contr."]
            ).get("Min", Decimal("0"))

            if base30 > 0:
                row["30Y Delay RE 1Y"] = ((delay30 / base30 - 1) * 100).quantize(Decimal("0.01"))
                row["30Y $5k/m contr."] = ((contrib30 / base30 - 1) * 100).quantize(Decimal("0.01"))
            if base50 > 0:
                row["50Y Delay RE 1Y"] = ((delay50 / base50 - 1) * 100).quantize(Decimal("0.01"))
                row["50Y $5k/m contr."] = ((contrib50 / base50 - 1) * 100).quantize(Decimal("0.01"))
            if base_ss > 0:
                row["50Y+SS Delay RE 1Y"] = (
                    (delay_ss / base_ss - 1) * 100
                ).quantize(Decimal("0.01"))
                row["50Y+SS $5k/m contr."] = (
                    (contrib_ss / base_ss - 1) * 100
                ).quantize(Decimal("0.01"))

            # Include baseline columns in Rel to Base row as N/A (None)
            row["30Y Baseline"] = None
            row["50Y Baseline"] = None
            row["50Y+SS Baseline"] = None
            # Include 2-year delay column as N/A (no corresponding baseline)
            row["2-year delay"] = None
        else:
            for scenario in [
                "30Y Baseline", "30Y Delay RE 1Y", "30Y $5k/m contr.",
                "50Y Baseline", "50Y Delay RE 1Y", "50Y $5k/m contr.",
                "50Y+SS Baseline", "50Y+SS Delay RE 1Y", "50Y+SS $5k/m contr.",
                "2-year delay",
            ]:
                result = results[scenario]
                assert result is not None
                decade_min = _compute_decade_failsafe(
                    result, ctx, cohort_dates[scenario]
                ).get(decade, Decimal("0"))
                row[scenario] = (decade_min * initial_wealth).quantize(Decimal("1"))
        table[decade] = row
    return table


def build_table01_aggregation(
    fixed_swr_results: dict[str, Part42FixedSWRResult],
    cohort_dates_by_experiment: dict[str, list[str]],
    manifest: Any,
    trajectory: Any,
) -> dict[str, dict[str, Decimal | None]]:
    """Build Table 01: Fixed 4% failure probabilities with all 11 conditioning columns."""
    table = {}

    scenario_map = {
        "A": "Baseline",
        "B": "Delay RE 1Y",
        "C": "$5k/m contributions",
        "D": "50Y Baseline",
        "E_delay": "Delay RE 1Y (50Y)",
        "E_contrib": "$5k/m contributions (50Y)",
        "F_baseline": "50Y Baseline + SocSec",
        "F_delay": "Delay RE 1Y (50Y+SocSec)",
        "F_contrib": "$5k/m contributions (50Y+SocSec)",
        "G_2yr": "2-year delay",
    }

    conditions = [
        "All", "Since_1926", "Since_1950",
        "CAPE_le_20", "CAPE_gt_20", "SP500_High",
        "Drdwn_0_10", "Drdwn_10_20", "Drdwn_20_30", "Drdwn_gt_30",
    ]

    for exp_id, result in fixed_swr_results.items():
        if exp_id not in scenario_map:
            continue
        scenario = scenario_map[exp_id]

        # Get all cohort dates for this experiment
        all_cohort_dates = cohort_dates_by_experiment.get(exp_id, [])

        # For each condition, filter cohorts and compute failure rate
        row: dict[str, Decimal | None] = {}
        for condition in conditions:
            if condition == "All":
                filtered_dates = all_cohort_dates
            else:
                filtered_dates = _filter_cohorts_by_condition(
                    all_cohort_dates, manifest, condition, trajectory
                )

            if not filtered_dates:
                row[condition] = Decimal("0")
                continue

            # Find indices of filtered cohorts in the original cohort list
            date_to_index = {cd: i for i, cd in enumerate(all_cohort_dates)}
            filtered_indices = [date_to_index[cd] for cd in filtered_dates if cd in date_to_index]

            if not filtered_indices:
                row[condition] = Decimal("0")
                continue

            # Count failures among filtered cohorts
            filtered_failures = sum(
                1 for idx in filtered_indices
                if idx < len(result.per_cohort_success) and not result.per_cohort_success[idx]
            )
            filtered_total = len(filtered_indices)

            if filtered_total == 0:
                row[condition] = Decimal("0")
            else:
                failure_pct = (
                    Decimal(filtered_failures) / Decimal(filtered_total) * 100
                ).quantize(Decimal("0.1"))
                row[condition] = failure_pct

        table[scenario] = row

    return table
