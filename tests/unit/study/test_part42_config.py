"""Tests for Part 42 configuration and grid (S3.5).

Validates that:
  - Part 42 YAML parses correctly as a StudyConfiguration
  - Grid dimensions match expected values
  - OMY parameters are correctly parsed
  - Backward-compatible (no OMY config = no OMY fields)
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fbf.core.study.builder import StudyConfiguration


class TestPart42YamlParsing:
    """Part 42 YAML must parse as a valid StudyConfiguration."""

    def _load_part42(self) -> dict:
        from fbf.core.study.builder import load_yaml

        return load_yaml(Path("examples/studies/ern_part42.yaml"))

    def test_parses_as_study_configuration(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert config.name == "ERN Part 42 — One More Year Syndrome"

    def test_dataset_identifier(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert config.dataset_identifier == "ern_swr_h720"

    def test_horizon_years(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert config.horizon_years == (30,)

    def test_equity_allocation_values(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert config.allocation_policy_values == (
            Decimal("0.25"),
            Decimal("0.5"),
            Decimal("0.75"),
            Decimal("0.9"),
            Decimal("1.0"),
        )

    def test_withdrawal_rate_values(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert len(config.withdrawal_policy_values) == 9
        assert config.withdrawal_policy_values[0] == Decimal("0.03")
        assert config.withdrawal_policy_values[-1] == Decimal("0.05")

    def test_omy_parameters_parsed(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert config.omy_contribution_amount == Decimal("5000")
        assert config.omy_equity_weight == Decimal("0.75")
        assert config.omy_bond_weight == Decimal("0.25")
        assert config.omy_original_initial_wealth == Decimal("2000000")

    def test_final_value_target(self) -> None:
        data = self._load_part42()
        config = StudyConfiguration.from_yaml(data)
        assert config.final_value_target_values == (Decimal("0.25"),)


class TestPart42GridDimensions:
    """Part 42 grid constants must match expected dimensions."""

    def test_grid_cell_count(self) -> None:
        from tests.oracle.ern.constants import (
            PART42_GRID_CELLS,
            PART42_HORIZON_COUNT,
            PART42_SWR_COUNT,
            PART42_WEIGHT_COUNT,
        )

        assert PART42_WEIGHT_COUNT == 5
        assert PART42_SWR_COUNT == 9
        assert PART42_HORIZON_COUNT == 1
        assert PART42_GRID_CELLS == 45

    def test_omy_parameters(self) -> None:
        from tests.oracle.ern.constants import (
            PART42_BOND_WEIGHT,
            PART42_CONTRIBUTION_MONTHLY,
            PART42_EQUITY_WEIGHT,
            PART42_ORIGINAL_INITIAL_WEALTH,
        )

        assert PART42_CONTRIBUTION_MONTHLY == 5000.0
        assert PART42_EQUITY_WEIGHT == 0.75
        assert PART42_BOND_WEIGHT == 0.25
        assert PART42_ORIGINAL_INITIAL_WEALTH == 2000000.0


class TestBackwardCompatibility:
    """StudyConfiguration without OMY params must still work."""

    def test_no_omy_fields(self) -> None:
        config = StudyConfiguration(
            name="test",
            description="test",
            version="1.0",
            dataset_identifier="test",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.75"),),
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.04"),),
            horizon_years=(30,),
        )
        assert config.omy_contribution_amount is None
        assert config.omy_equity_weight is None
        assert config.omy_bond_weight is None
        assert config.omy_original_initial_wealth is None

    def test_no_omy_in_yaml(self) -> None:
        from fbf.core.study.builder import load_yaml

        data = load_yaml(Path("examples/studies/ern_part20.yaml"))
        config = StudyConfiguration.from_yaml(data)
        assert config.omy_contribution_amount is None
        assert config.omy_equity_weight is None
