"""Part 20 grid structure tests.

Validates that the Part 20 study definition produces exactly the expected
parameter space: 32 glidepaths x 9 SWR x 2 horizons = 576 grid cells.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

_PART20_YAML = Path("examples/studies/ern_part20.yaml")


def _load_part20_config() -> StudyConfiguration:
    from fbf.core.study.builder import load_yaml

    data = load_yaml(_PART20_YAML)
    return StudyConfiguration.from_yaml(data)


def _load_part20_raw() -> dict[str, Any]:
    from fbf.core.study.builder import load_yaml

    return load_yaml(_PART20_YAML)


class TestPart20GridStructure:
    """Part 20 grid dimensions and parameter space."""

    def test_32_glidepath_configurations(self) -> None:
        config = _load_part20_config()
        assert config.explicit_configurations is not None
        assert len(config.explicit_configurations) == 32

    def test_5_swr_values(self) -> None:
        config = _load_part20_config()
        assert len(config.withdrawal_policy_values) == 5
        expected = (0.03, 0.0325, 0.035, 0.0375, 0.04)
        assert config.withdrawal_policy_values == tuple(Decimal(str(v)) for v in expected)

    def test_horizons_exactly_30_and_60(self) -> None:
        config = _load_part20_config()
        assert config.horizon_years == (30, 60)

    def test_320_grid_cells(self) -> None:
        config = _load_part20_config()
        configs = _build_unified_parameter_configs(config)
        # 32 glidepaths x 5 SWR x 2 horizons = 320
        assert len(configs) == 320

    def test_no_accidental_cartesian_expansion(self) -> None:
        """Glidepath parameters must NOT be crossed with each other."""
        config = _load_part20_config()
        configs = _build_unified_parameter_configs(config)
        # Each glidepath config is a fixed tuple; only SWR and horizon vary.
        # So there should be exactly 9 x 2 = 18 configs per glidepath.
        seen_glidepaths: set[tuple[float, float, float, str]] = set()
        for pc in configs:
            key = (
                float(pc.values["start_equity"]),
                float(pc.values["end_equity"]),
                float(pc.values["slope"]),
                str(pc.values["mode"]),
            )
            seen_glidepaths.add(key)
        # Exactly 32 unique glidepath tuples
        assert len(seen_glidepaths) == 32

    def test_part19_glidepaths_present(self) -> None:
        config = _load_part20_config()
        configs = _build_unified_parameter_configs(config)
        seen = {
            (pc.values["start_equity"], pc.values["end_equity"],
             pc.values["slope"], pc.values["mode"])
            for pc in configs
        }
        # 60% -> 80%, slope 0.002, passive
        assert (0.6, 0.8, 0.002, "passive") in seen
        # 40% -> 100%, slope 0.005, active
        assert (0.4, 1.0, 0.005, "active") in seen

    def test_part20_additions_are_exactly_eight(self) -> None:
        """The 8 Part 20 additions are exactly as specified."""
        from tests.oracle.ern.constants import PART20_GLIDEPATHS

        assert len(PART20_GLIDEPATHS) == 8
        config = _load_part20_config()
        configs = _build_unified_parameter_configs(config)
        seen = {
            (pc.values["start_equity"], pc.values["end_equity"],
             pc.values["slope"], pc.values["mode"])
            for pc in configs
        }
        for gp in PART20_GLIDEPATHS:
            assert gp in seen, f"Part 20 glidepath {gp} not found in grid"

    def test_part20_additions_are_passive_only(self) -> None:
        from tests.oracle.ern.constants import PART20_GLIDEPATHS

        for start, end, _slope, mode in PART20_GLIDEPATHS:
            assert mode == "passive", (
                f"Part 20 glidepath ({start}->{end}) must be passive, got {mode}"
            )

    def test_part20_additions_slopes(self) -> None:
        from tests.oracle.ern.constants import PART20_GLIDEPATHS

        expected_slopes = {0.00111, 0.002, 0.003, 0.004}
        actual_slopes = {slope for _, _, slope, _ in PART20_GLIDEPATHS}
        assert actual_slopes == expected_slopes

    def test_part20_additions_start_end_pairs(self) -> None:
        from tests.oracle.ern.constants import PART20_GLIDEPATHS

        pairs = {(start, end) for start, end, _, _ in PART20_GLIDEPATHS}
        assert pairs == {(0.3, 0.7), (0.2, 0.6)}

    def test_each_glidepath_crosses_10_combinations(self) -> None:
        """Each glidepath should produce 5 SWR x 2 horizons = 10 configs."""
        config = _load_part20_config()
        configs = _build_unified_parameter_configs(config)
        from collections import Counter

        gp_counts: Counter[tuple[float, float, float, str]] = Counter()
        for pc in configs:
            key = (
                float(pc.values["start_equity"]),
                float(pc.values["end_equity"]),
                float(pc.values["slope"]),
                str(pc.values["mode"]),
            )
            gp_counts[key] += 1
        for gp, count in gp_counts.items():
            assert count == 10, f"Glidepath {gp} has {count} configs, expected 10"


class TestPart20Constants:
    """Tests for the Part 20 constants module."""

    def test_part19_count(self) -> None:
        from tests.oracle.ern.constants import PART19_GLIDEPATHS

        assert len(PART19_GLIDEPATHS) == 24

    def test_part20_count(self) -> None:
        from tests.oracle.ern.constants import PART20_GLIDEPATHS

        assert len(PART20_GLIDEPATHS) == 8

    def test_combined_count(self) -> None:
        from tests.oracle.ern.constants import PART20_ALL_GLIDEPATHS

        assert len(PART20_ALL_GLIDEPATHS) == 32

    def test_grid_cell_count(self) -> None:
        from tests.oracle.ern.constants import PART20_GRID_CELLS

        assert PART20_GRID_CELLS == 320

    def test_swr_values(self) -> None:
        from tests.oracle.ern.constants import PART20_SWR

        assert len(PART20_SWR) == 5
        assert PART20_SWR[0] == 0.03
        assert PART20_SWR[-1] == 0.04

    def test_horizons(self) -> None:
        from tests.oracle.ern.constants import PART20_HORIZONS

        assert PART20_HORIZONS == [30, 60]


class TestPart20YAMLStructure:
    """Tests for the YAML file structure."""

    def test_dataset_identifier(self) -> None:
        data = _load_part20_raw()
        assert data["dataset"]["identifier"] == "ern_swr_h720"

    def test_allocation_policy_type(self) -> None:
        data = _load_part20_raw()
        assert data["allocation_policy"]["type"] == "GlidepathAllocationPolicy"

    def test_configurations_list_exists(self) -> None:
        data = _load_part20_raw()
        assert "configurations" in data["allocation_policy"]
        assert isinstance(data["allocation_policy"]["configurations"], list)

    def test_withdrawal_policy_type(self) -> None:
        data = _load_part20_raw()
        assert data["withdrawal_policy"]["type"] == "FixedRealWithdrawalPolicy"

    def test_final_value_target(self) -> None:
        data = _load_part20_raw()
        assert data["final_value_target"] == [0.0]
