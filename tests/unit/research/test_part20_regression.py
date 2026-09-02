"""Part 20 regression tests — verify existing behaviour is unchanged.

These tests ensure that the Part 20 additions do not break existing
functionality.  All tests in this module must pass; any failure indicates
an implementation defect.
"""

from __future__ import annotations

from decimal import Decimal

from fbf.core.domain.policies.cape_regime import (
    CapeBinary,
    CapeRegime,
    classify_cape_binary,
    classify_cape_regime,
)
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy


class TestExistingGlidepathBehaviour:
    """Regression: existing glidepath behaviour must not change."""

    def test_passive_glidepath_basic(self) -> None:
        """Passive glidepath increases equity every period."""
        policy = GlidepathAllocationPolicy(
            start_equity=Decimal("0.6"),
            end_equity=Decimal("0.8"),
            slope=Decimal("0.002"),
            mode="passive",
        )
        assert policy.start_equity == Decimal("0.6")
        assert policy.end_equity == Decimal("0.8")
        assert policy.slope == Decimal("0.002")
        assert policy.mode == "passive"

    def test_active_glidepath_basic(self) -> None:
        """Active glidepath increases equity only when underwater."""
        policy = GlidepathAllocationPolicy(
            start_equity=Decimal("0.4"),
            end_equity=Decimal("1.0"),
            slope=Decimal("0.003"),
            mode="active",
        )
        assert policy.mode == "active"

    def test_invalid_mode_raises(self) -> None:
        """Invalid mode must raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="'passive' or 'active'"):
            GlidepathAllocationPolicy(
                start_equity=Decimal("0.6"),
                end_equity=Decimal("0.8"),
                slope=Decimal("0.002"),
                mode="invalid",
            )

    def test_negative_slope_raises(self) -> None:
        """Negative slope must raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="non-negative"):
            GlidepathAllocationPolicy(
                start_equity=Decimal("0.6"),
                end_equity=Decimal("0.8"),
                slope=Decimal("-0.002"),
                mode="passive",
            )


class TestExistingCapeRegimeBehaviour:
    """Regression: existing four-level CAPE regime must not change."""

    def test_below_15(self) -> None:
        assert classify_cape_regime(Decimal("10")) == CapeRegime.BELOW_15

    def test_moderate(self) -> None:
        assert classify_cape_regime(Decimal("17")) == CapeRegime.MODERATE

    def test_high(self) -> None:
        assert classify_cape_regime(Decimal("25")) == CapeRegime.HIGH

    def test_extreme(self) -> None:
        assert classify_cape_regime(Decimal("35")) == CapeRegime.EXTREME

    def test_boundary_15(self) -> None:
        assert classify_cape_regime(Decimal("15")) == CapeRegime.MODERATE

    def test_boundary_20(self) -> None:
        assert classify_cape_regime(Decimal("20")) == CapeRegime.HIGH

    def test_boundary_30(self) -> None:
        assert classify_cape_regime(Decimal("30")) == CapeRegime.EXTREME


class TestCapeBinaryCoexistsWithFourLevel:
    """Regression: binary and four-level models coexist correctly."""

    def test_both_models_classify_independently(self) -> None:
        """Each model classifies the same CAPE value independently."""
        cape = Decimal("25")
        four_level = classify_cape_regime(cape)
        binary = classify_cape_binary(cape)
        assert four_level == CapeRegime.HIGH
        assert binary == CapeBinary.HIGH

    def test_boundary_divergence_at_20(self) -> None:
        """At CAPE=20, the models deliberately disagree."""
        cape = Decimal("20")
        four_level = classify_cape_regime(cape)
        binary = classify_cape_binary(cape)
        assert four_level == CapeRegime.HIGH
        assert binary == CapeBinary.LOW


class TestPart20GridRegression:
    """Regression: Part 20 grid structure must remain correct."""

    def test_32_glidepaths(self) -> None:
        from tests.oracle.ern.constants import PART20_ALL_GLIDEPATHS

        assert len(PART20_ALL_GLIDEPATHS) == 32

    def test_320_grid_cells(self) -> None:
        from tests.oracle.ern.constants import PART20_GRID_CELLS

        assert PART20_GRID_CELLS == 320

    def test_part19_count_unchanged(self) -> None:
        from tests.oracle.ern.constants import PART19_GLIDEPATHS

        assert len(PART19_GLIDEPATHS) == 24

    def test_part20_count_unchanged(self) -> None:
        from tests.oracle.ern.constants import PART20_GLIDEPATHS

        assert len(PART20_GLIDEPATHS) == 8


class TestPart20YAMLRegression:
    """Regression: Part 20 YAML must parse correctly."""

    def test_yaml_loads(self) -> None:
        from pathlib import Path

        from fbf.core.study.builder import StudyConfiguration, load_yaml

        data = load_yaml(Path("examples/studies/ern_part20.yaml"))
        config = StudyConfiguration.from_yaml(data)
        assert config.dataset_identifier == "ern_swr_h720"
        assert config.allocation_policy_type == "GlidepathAllocationPolicy"

    def test_yaml_grid_dimensions(self) -> None:
        from pathlib import Path

        from fbf.core.study.builder import (
            StudyConfiguration,
            _build_unified_parameter_configs,
            load_yaml,
        )

        data = load_yaml(Path("examples/studies/ern_part20.yaml"))
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        assert len(configs) == 320
