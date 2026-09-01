"""Tests for the shared CLI builders module.

Focuses on the equity/bond asset model contract: the initial portfolio built by
``build_initial_portfolio`` must reference the same ``AssetClass`` identities
that the dataset loader and ``cli.policies.ConstantAllocationPolicy`` produce,
so the real engine can price and rebalance the initial holdings.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.study.builder import build_initial_portfolio


def _loader_asset(asset_id: str) -> AssetClass:
    """Mimic ``_snapshot_from_dict`` in ``infrastructure/persistence/context.py``.

    The dataset loader constructs indexed assets with empty ``name`` /
    ``description`` so they round-trip from JSON ``index_levels`` keys.
    """
    return AssetClass(id=asset_id, name="", description="")


def _make_context(portfolio: Portfolio) -> DecisionContext:
    snapshot = MarketSnapshot(
        date=date(2020, 1, 1),
        index_levels={
            _loader_asset("equity"): Decimal("100"),
            _loader_asset("bond"): Decimal("50"),
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    dataset = Dataset(snapshots=(snapshot,), frequency="monthly", version="1.0")
    dummy = _loader_asset("equity")
    dummy_alloc = Allocation(weights={dummy: Decimal("1")})
    dummy_target = AllocationTarget(weights={dummy: Decimal("1")})
    return DecisionContext(
        date=date(2020, 1, 1),
        period_index=0,
        simulation_context=object(),
        portfolio=portfolio,
        current_allocation=dummy_alloc,
        target_allocation=dummy_target,
        market_snapshot=snapshot,
        dataset=dataset,
    )


def test_build_initial_portfolio_uses_equity_and_bond_holdings() -> None:
    initial_wealth = Money(Decimal("1000000"), Money.ZERO.currency)
    portfolio = build_initial_portfolio(initial_wealth)

    holdings = {h.asset_class.id: h for h in portfolio.holdings}
    assert set(holdings) == {"equity", "bond"}
    assert holdings["equity"].asset_class == _loader_asset("equity")
    assert holdings["bond"].asset_class == _loader_asset("bond")
    assert holdings["equity"].units == initial_wealth.amount * Decimal("0.5")
    assert holdings["bond"].units == initial_wealth.amount * Decimal("0.5")


def test_build_initial_portfolio_assets_equal_snapshot_keys() -> None:
    """Holding assets must be dict-key equal to the loader's snapshot keys."""
    initial_wealth = Money(Decimal("500000"), Money.ZERO.currency)
    portfolio = build_initial_portfolio(initial_wealth)

    snapshot_keys = {_loader_asset("equity"), _loader_asset("bond")}
    assert {h.asset_class for h in portfolio.holdings} == snapshot_keys
    assert all(h.asset_class in snapshot_keys for h in portfolio.holdings)


def test_build_initial_portfolio_does_not_use_synthetic_initial_asset() -> None:
    initial_wealth = Money(Decimal("1000000"), Money.ZERO.currency)
    portfolio = build_initial_portfolio(initial_wealth)

    assert "initial" not in {h.asset_class.id for h in portfolio.holdings}


def test_constant_allocation_policy_targets_loader_aligned_assets() -> None:
    policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Money.ZERO.currency))
    decision = policy.decide(_make_context(portfolio))

    assert decision.allocation_target.weights == {
        _loader_asset("equity"): Decimal("0.75"),
        _loader_asset("bond"): Decimal("0.25"),
    }


def test_constant_allocation_policy_assets_present_in_snapshot() -> None:
    """The target assets must exist in the dataset snapshot keys (priceable)."""
    policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.6"))
    portfolio = build_initial_portfolio(Money(Decimal("1000000"), Money.ZERO.currency))
    decision = policy.decide(_make_context(portfolio))

    snapshot_keys = {_loader_asset("equity"), _loader_asset("bond")}
    assert set(decision.allocation_target.weights) == snapshot_keys


class TestPart3DatasetIdentifier:
    """C6.1: Part 3 YAMLs must reference ern_swr_h720, not ern_cape_1871_2016."""

    PART3_YAML_FILES = [
        "ern_part3_expA.yaml",
        "ern_part3_expB.yaml",
        "ern_part3_expC.yaml",
        "ern_part3_expD.yaml",
        "ern_part3_replication.yaml",
    ]

    def _load_config(self, filename: str) -> dict:
        from fbf.core.study.builder import load_yaml

        return load_yaml(Path("examples/studies") / filename)

    def test_all_part3_use_ern_swr_h720(self) -> None:
        for filename in self.PART3_YAML_FILES:
            data = self._load_config(filename)
            assert data["dataset"]["identifier"] == "ern_swr_h720", (
                f"{filename} must reference ern_swr_h720"
            )

    def test_no_part3_references_ern_cape(self) -> None:
        for filename in self.PART3_YAML_FILES:
            data = self._load_config(filename)
            assert data["dataset"]["identifier"] != "ern_cape_1871_2016", (
                f"{filename} must not reference ern_cape_1871_2016"
            )

    def test_part3_parse_as_study_configuration(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        for filename in self.PART3_YAML_FILES:
            data = self._load_config(filename)
            config = StudyConfiguration.from_yaml(data)
            assert config.dataset_identifier == "ern_swr_h720", (
                f"{filename} parsed config must have ern_swr_h720"
            )

    def test_part3_replication_has_dual_final_value_targets(self) -> None:
        from decimal import Decimal

        from fbf.core.study.builder import StudyConfiguration

        data = self._load_config("ern_part3_replication.yaml")
        config = StudyConfiguration.from_yaml(data)
        assert config.final_value_target_values is not None
        assert Decimal("0.0") in config.final_value_target_values
        assert Decimal("0.5") in config.final_value_target_values

    def test_part3_expA_has_single_zero_target(self) -> None:
        from decimal import Decimal

        from fbf.core.study.builder import StudyConfiguration

        data = self._load_config("ern_part3_expA.yaml")
        config = StudyConfiguration.from_yaml(data)
        assert config.final_value_target_values == (Decimal("0.0"),)

    def test_part3_expBcd_have_single_half_target(self) -> None:
        from decimal import Decimal

        from fbf.core.study.builder import StudyConfiguration

        for filename in ["ern_part3_expB.yaml", "ern_part3_expC.yaml", "ern_part3_expD.yaml"]:
            data = self._load_config(filename)
            config = StudyConfiguration.from_yaml(data)
            assert config.final_value_target_values == (Decimal("0.5"),), (
                f"{filename} must have final_value_target = [0.5]"
            )


class TestNonPart3StudiesUnchanged:
    """C6.1: Non-Part-3 studies must remain untouched."""

    def test_ern_grid_uses_h720(self) -> None:
        from fbf.core.study.builder import load_yaml

        data = load_yaml(Path("examples/studies/ern_grid.yaml"))
        assert data["dataset"]["identifier"] == "ern_swr_h720"

    def test_no_study_references_ern_cape_as_dataset(self) -> None:
        import os

        from fbf.core.study.builder import load_yaml

        yaml_dir = Path("examples/studies")
        for filename in os.listdir(yaml_dir):
            if not filename.endswith(".yaml"):
                continue
            data = load_yaml(yaml_dir / filename)
            identifier = data.get("dataset", {}).get("identifier", "")
            assert identifier != "ern_cape_1871_2016", (
                f"{filename} must not use ern_cape_1871_2016 as dataset"
            )


class TestLoadYamlError:
    """Tests for load_yaml() error behaviour when PyYAML is unavailable."""

    def test_load_yaml_missing_pyyaml_error_message(self) -> None:
        """When PyYAML is not installed, load_yaml() raises RuntimeError with clear guidance."""
        import sys
        import unittest.mock
        from pathlib import Path

        from fbf.core.study.builder import load_yaml

        # Temporarily remove yaml from sys.modules to simulate missing PyYAML
        yaml_module = sys.modules.pop("yaml", None)
        try:
            with (
                unittest.mock.patch.dict(sys.modules, {"yaml": None}),
                pytest.raises(RuntimeError, match="PyYAML is not installed"),
            ):
                load_yaml(Path("/nonexistent.yaml"))
        finally:
            if yaml_module is not None:
                sys.modules["yaml"] = yaml_module
