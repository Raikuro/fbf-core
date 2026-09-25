"""Unit tests for Part 19 strategy selectors."""

from __future__ import annotations

from fbf.core.research.part19_strategies import (
    PART19_EXPERIMENT_A_GLIDEPATH_IDS,
    PART19_EXPERIMENT_A_STATIC_IDS,
    PART19_EXPERIMENT_A_STRATEGY_COUNT,
    PART19_EXPERIMENT_B_GLIDEPATH_IDS,
    PART19_EXPERIMENT_B_STATIC_IDS,
    PART19_EXPERIMENT_B_STRATEGY_COUNT,
    part19_experiment_a_strategies,
    part19_experiment_b_strategies,
)
from fbf.core.research.part20_strategies import part20_strategy_universe


def test_experiment_a_static_ids() -> None:
    """Experiment A static IDs match expected values."""
    assert PART19_EXPERIMENT_A_STATIC_IDS == (
        "static_060",
        "static_080",
        "static_100",
    )


def test_experiment_a_glidepath_ids() -> None:
    """Experiment A glidepath IDs match expected values."""
    assert len(PART19_EXPERIMENT_A_GLIDEPATH_IDS) == 24
    # Verify all are gp_* strings
    for gid in PART19_EXPERIMENT_A_GLIDEPATH_IDS:
        assert gid.startswith("gp_")


def test_experiment_a_strategy_count() -> None:
    """Experiment A strategy count is correct."""
    assert PART19_EXPERIMENT_A_STRATEGY_COUNT == 27


def test_experiment_a_selector_returns_27() -> None:
    """Experiment A selector returns exactly 27 strategies."""
    strategies = part19_experiment_a_strategies()
    assert len(strategies) == 27


def test_experiment_a_static_strategies() -> None:
    """Experiment A has exactly 3 static strategies: 60%, 80%, 100%."""
    strategies = part19_experiment_a_strategies()
    static_ids = [s.id for s in strategies if s.kind == "static"]
    assert static_ids == ["static_060", "static_080", "static_100"]
    for s in strategies:
        if s.kind == "static":
            assert s.equity_allocation is not None


def test_experiment_a_glidepath_strategies() -> None:
    """Experiment A has exactly 24 glidepath strategies."""
    strategies = part19_experiment_a_strategies()
    glide_ids = [s.id for s in strategies if s.kind == "glidepath"]
    assert len(glide_ids) == 24
    assert glide_ids == list(PART19_EXPERIMENT_A_GLIDEPATH_IDS)
    for s in strategies:
        if s.kind == "glidepath":
            assert s.start_equity is not None
            assert s.end_equity is not None
            assert s.slope is not None
            assert s.mode in ("passive", "active")


def test_experiment_a_subset_of_part20() -> None:
    """All Experiment A strategies exist in Part 20 universe."""
    part19_strategies = part19_experiment_a_strategies()
    part20_universe = part20_strategy_universe()
    part20_ids = {s.id for s in part20_universe}

    for s in part19_strategies:
        assert s.id in part20_ids, f"Part 19 Exp A strategy {s.id} not in Part 20 universe"


def test_experiment_a_ordering() -> None:
    """Experiment A strategies are in documented order."""
    strategies = part19_experiment_a_strategies()
    actual_ids = [s.id for s in strategies]
    expected_order = list(PART19_EXPERIMENT_A_STATIC_IDS) + list(PART19_EXPERIMENT_A_GLIDEPATH_IDS)
    assert actual_ids == expected_order


def test_experiment_a_no_part20_only_glidepaths() -> None:
    """Experiment A does not include Part 20-only glidepaths."""
    strategies = part19_experiment_a_strategies()
    part20_only_prefixes = ("gp_030_070_", "gp_020_060_")
    for s in strategies:
        if s.kind == "glidepath":
            assert not s.id.startswith(part20_only_prefixes), (
                f"Part 19 Exp A should not include Part 20-only glidepath {s.id}"
            )


# --- Experiment B Tests ---


def test_experiment_b_static_ids() -> None:
    """Experiment B static IDs match expected 21 values (0%-100% in 5% steps)."""
    expected = tuple(f"static_{pct:03d}" for pct in range(0, 105, 5))
    assert expected == PART19_EXPERIMENT_B_STATIC_IDS
    assert len(PART19_EXPERIMENT_B_STATIC_IDS) == 21


def test_experiment_b_glidepath_ids() -> None:
    """Experiment B glidepath IDs match Experiment A (24 glidepaths)."""
    assert PART19_EXPERIMENT_B_GLIDEPATH_IDS == PART19_EXPERIMENT_A_GLIDEPATH_IDS
    assert len(PART19_EXPERIMENT_B_GLIDEPATH_IDS) == 24


def test_experiment_b_strategy_count() -> None:
    """Experiment B strategy count is correct."""
    assert PART19_EXPERIMENT_B_STRATEGY_COUNT == 45


def test_experiment_b_selector_returns_45() -> None:
    """Experiment B selector returns exactly 45 strategies."""
    strategies = part19_experiment_b_strategies()
    assert len(strategies) == 45


def test_experiment_b_static_strategies() -> None:
    """Experiment B has exactly 21 static strategies: 0%–100% in 5% steps."""
    strategies = part19_experiment_b_strategies()
    static_ids = [s.id for s in strategies if s.kind == "static"]
    assert static_ids == list(PART19_EXPERIMENT_B_STATIC_IDS)
    assert len(static_ids) == 21
    # Verify equity allocations are 0%, 5%, 10%, ..., 100%
    for i, s in enumerate(strategies):
        if s.kind == "static":
            expected_pct = i * 5
            assert s.id == f"static_{expected_pct:03d}"
            assert s.equity_allocation is not None
            # Check equity allocation value
            expected_alloc = expected_pct / 100
            assert float(s.equity_allocation) == expected_alloc


def test_experiment_b_glidepath_strategies() -> None:
    """Experiment B has exactly 24 glidepath strategies (same as Exp A)."""
    strategies = part19_experiment_b_strategies()
    glide_ids = [s.id for s in strategies if s.kind == "glidepath"]
    assert len(glide_ids) == 24
    assert glide_ids == list(PART19_EXPERIMENT_B_GLIDEPATH_IDS)
    for s in strategies:
        if s.kind == "glidepath":
            assert s.start_equity is not None
            assert s.end_equity is not None
            assert s.slope is not None
            assert s.mode in ("passive", "active")


def test_experiment_b_subset_of_part20() -> None:
    """All Experiment B strategies exist in Part 20 universe."""
    part19_strategies = part19_experiment_b_strategies()
    part20_universe = part20_strategy_universe()
    part20_ids = {s.id for s in part20_universe}

    for s in part19_strategies:
        assert s.id in part20_ids, f"Part 19 Exp B strategy {s.id} not in Part 20 universe"


def test_experiment_b_ordering() -> None:
    """Experiment B strategies are in documented order."""
    strategies = part19_experiment_b_strategies()
    actual_ids = [s.id for s in strategies]
    expected_order = list(PART19_EXPERIMENT_B_STATIC_IDS) + list(PART19_EXPERIMENT_B_GLIDEPATH_IDS)
    assert actual_ids == expected_order


def test_experiment_b_no_part20_only_glidepaths() -> None:
    """Experiment B does not include Part 20-only glidepaths."""
    strategies = part19_experiment_b_strategies()
    part20_only_prefixes = ("gp_030_070_", "gp_020_060_")
    for s in strategies:
        if s.kind == "glidepath":
            assert not s.id.startswith(part20_only_prefixes), (
                f"Part 19 Exp B should not include Part 20-only glidepath {s.id}"
            )


def test_experiment_b_is_strict_subset_of_part20() -> None:
    """Experiment B selector is a strict subset of the 53 Part 20 strategies."""
    part19_b = part19_experiment_b_strategies()
    part20 = part20_strategy_universe()

    part19_b_ids = {s.id for s in part19_b}
    part20_ids = {s.id for s in part20}

    assert part19_b_ids.issubset(part20_ids)
    assert len(part19_b_ids) == 45
    assert len(part20_ids) == 53
    assert part19_b_ids != part20_ids  # strict subset


def test_experiment_a_is_strict_subset_of_part20() -> None:
    """Experiment A selector is a strict subset of the 53 Part 20 strategies."""
    part19_a = part19_experiment_a_strategies()
    part20 = part20_strategy_universe()

    part19_a_ids = {s.id for s in part19_a}
    part20_ids = {s.id for s in part20}

    assert part19_a_ids.issubset(part20_ids)
    assert len(part19_a_ids) == 27
    assert part19_a_ids != part20_ids  # strict subset


def test_experiment_b_includes_experiment_a_static_plus_more() -> None:
    """Experiment B static strategies include Experiment A static plus more."""
    exp_a_static = set(PART19_EXPERIMENT_A_STATIC_IDS)
    exp_b_static = set(PART19_EXPERIMENT_B_STATIC_IDS)
    assert exp_a_static.issubset(exp_b_static)
    assert len(exp_b_static) > len(exp_a_static)


def test_experiment_b_includes_experiment_a_glidepaths() -> None:
    """Experiment B includes all Experiment A glidepaths."""
    exp_a_glide = set(PART19_EXPERIMENT_A_GLIDEPATH_IDS)
    exp_b_glide = set(PART19_EXPERIMENT_B_GLIDEPATH_IDS)
    assert exp_a_glide == exp_b_glide
