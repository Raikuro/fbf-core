"""Part 19 strategy universe — Experiment A (Fixed 3.5% SWR).

Selects the 27 strategies used in Part 19 Experiment A from the
Part 20 strategy catalog:

* 3 static allocations: 60%, 80%, 100% equity
* 24 Part 19 glidepaths (6 start/end combos × 2 slopes × 2 modes)

No new strategy definitions; filters the existing Part 20 universe.
"""

from __future__ import annotations

from fbf.core.research.part20_strategies import Part20Strategy, part20_strategy_universe

__all__ = [
    "part19_experiment_a_strategies",
    "PART19_EXPERIMENT_A_STATIC_IDS",
    "PART19_EXPERIMENT_A_GLIDEPATH_IDS",
    "PART19_EXPERIMENT_A_STRATEGY_COUNT",
]

# The 3 static allocations used in Part 19 Experiment A (from the failure-rate charts)
PART19_EXPERIMENT_A_STATIC_IDS: tuple[str, ...] = (
    "static_060",
    "static_080",
    "static_100",
)

# The 24 Part 19 glidepath IDs (matching _PART19_GLIDEPATHS in part20_strategies.py)
PART19_EXPERIMENT_A_GLIDEPATH_IDS: tuple[str, ...] = (
    # 60% → 80%
    "gp_060_080_0.002_passive",
    "gp_060_080_0.003_passive",
    "gp_060_080_0.002_active",
    "gp_060_080_0.003_active",
    # 40% → 80%
    "gp_040_080_0.003_passive",
    "gp_040_080_0.004_passive",
    "gp_040_080_0.003_active",
    "gp_040_080_0.004_active",
    # 20% → 80%
    "gp_020_080_0.004_passive",
    "gp_020_080_0.005_passive",
    "gp_020_080_0.004_active",
    "gp_020_080_0.005_active",
    # 80% → 100%
    "gp_080_100_0.002_passive",
    "gp_080_100_0.003_passive",
    "gp_080_100_0.002_active",
    "gp_080_100_0.003_active",
    # 60% → 100%
    "gp_060_100_0.003_passive",
    "gp_060_100_0.004_passive",
    "gp_060_100_0.003_active",
    "gp_060_100_0.004_active",
    # 40% → 100%
    "gp_040_100_0.004_passive",
    "gp_040_100_0.005_passive",
    "gp_040_100_0.004_active",
    "gp_040_100_0.005_active",
)

PART19_EXPERIMENT_A_STRATEGY_COUNT = 27


def part19_experiment_a_strategies() -> tuple[Part20Strategy, ...]:
    """Return the 27 strategies for Part 19 Experiment A.

    Order: 3 static (60%, 80%, 100%) followed by 24 Part 19 glidepaths
    in the documented order from the article.
    """
    universe = part20_strategy_universe()
    selected_ids = set(PART19_EXPERIMENT_A_STATIC_IDS) | set(PART19_EXPERIMENT_A_GLIDEPATH_IDS)
    selected = tuple(s for s in universe if s.id in selected_ids)

    if len(selected) != PART19_EXPERIMENT_A_STRATEGY_COUNT:
        raise AssertionError(
            "Part 19 Experiment A strategy count "
            f"{len(selected)} != {PART19_EXPERIMENT_A_STRATEGY_COUNT}"
        )

    expected_order = PART19_EXPERIMENT_A_STATIC_IDS + PART19_EXPERIMENT_A_GLIDEPATH_IDS
    actual_ids = [s.id for s in selected]
    if actual_ids != list(expected_order):
        raise AssertionError(
            f"Part 19 Experiment A strategy order mismatch: {actual_ids} != {list(expected_order)}"
        )

    return selected
