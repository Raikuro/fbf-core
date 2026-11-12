"""Tests for the shared CLI builders module.

Focuses on the equity/bond asset model contract: the initial portfolio built by
``build_initial_portfolio`` must reference the same ``AssetClass`` identities
that the dataset loader and ``cli.policies.ConstantAllocationPolicy`` produce,
so the real engine can price and rebalance the initial holdings.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fbf.core.domain.model.allocation import Allocation, AllocationTarget
from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.decision_context import DecisionContext
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Money
from fbf.core.domain.model.portfolio import Portfolio
from fbf.core.domain.policies import ConstantAllocationPolicy
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.study.builder import StudyConfiguration, build_initial_portfolio


def _loader_asset(asset_id: str) -> AssetClass:
    """Mimic ``_snapshot_from_dict`` in ``infrastructure/persistence/context.py``.

    The dataset loader constructs indexed assets with empty ``name`` /
    ``description`` so they round-trip from JSON ``index_levels`` keys.
    """
    return AssetClass(id=asset_id, name="", description="")


def _make_dataset() -> Dataset:
    snapshot = MarketSnapshot(
        date=date(2020, 1, 1),
        index_levels={
            _loader_asset("equity"): Decimal("1"),
            _loader_asset("bond"): Decimal("1"),
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    return Dataset(snapshots=(snapshot,), frequency="monthly")


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
    dataset = Dataset(snapshots=(snapshot,), frequency="monthly")
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
    portfolio = build_initial_portfolio(initial_wealth, _make_dataset())

    holdings = {h.asset_class.id: h for h in portfolio.holdings}
    assert set(holdings) == {"equity", "bond"}
    assert holdings["equity"].asset_class == _loader_asset("equity")
    assert holdings["bond"].asset_class == _loader_asset("bond")
    assert holdings["equity"].units == initial_wealth.amount * Decimal("0.5")
    assert holdings["bond"].units == initial_wealth.amount * Decimal("0.5")


def test_build_initial_portfolio_assets_equal_snapshot_keys() -> None:
    """Holding assets must be dict-key equal to the loader's snapshot keys."""
    initial_wealth = Money(Decimal("500000"), Money.ZERO.currency)
    portfolio = build_initial_portfolio(initial_wealth, _make_dataset())

    snapshot_keys = {_loader_asset("equity"), _loader_asset("bond")}
    assert {h.asset_class for h in portfolio.holdings} == snapshot_keys
    assert all(h.asset_class in snapshot_keys for h in portfolio.holdings)


def test_build_initial_portfolio_does_not_use_synthetic_initial_asset() -> None:
    initial_wealth = Money(Decimal("1000000"), Money.ZERO.currency)
    portfolio = build_initial_portfolio(initial_wealth, _make_dataset())

    assert "initial" not in {h.asset_class.id for h in portfolio.holdings}


def _make_priced_dataset(equity_price: Decimal, bond_price: Decimal) -> Dataset:
    snapshot = MarketSnapshot(
        date=date(2020, 1, 1),
        index_levels={
            _loader_asset("equity"): equity_price,
            _loader_asset("bond"): bond_price,
        },
        inflation=Decimal("0"),
        inflation_cumulative=Decimal("0"),
        is_ath=True,
        is_underwater=False,
        running_ath=Decimal("100"),
    )
    return Dataset(snapshots=(snapshot,), frequency="monthly")


@pytest.mark.parametrize(
    ("wealth", "equity_price", "bond_price"),
    [
        ("1000000", "1", "1"),
        ("1000000", "101.169089694984", "100.747178470726"),
        ("1234567.89", "101.169089694984", "100.747178470726"),
        ("500000.01", "77.3", "91.13"),
    ],
)
def test_build_initial_portfolio_value_equals_initial_wealth_exactly(
    wealth: str, equity_price: str, bond_price: str
) -> None:
    """Representable two-asset prices value the portfolio exactly at ``initial_wealth``.

    Execution derives the Numba withdrawal base from the initial portfolio value
    (``v0``) while the legacy policies use ``context.initial_wealth``.  Decimal
    division may round for arbitrary price pairs; Numba admission requires the
    two values to agree in float64 (see
    ``numba_executor._initial_value_equals_wealth``).
    """
    initial_wealth = Money(Decimal(wealth), Money.ZERO.currency)
    dataset = _make_priced_dataset(Decimal(equity_price), Decimal(bond_price))
    portfolio = build_initial_portfolio(initial_wealth, dataset)

    snapshot = dataset[0]
    value = sum(
        (h.units * snapshot.index_levels[h.asset_class] for h in portfolio.holdings),
        Decimal("0"),
    )
    assert value == initial_wealth.amount


def test_constant_allocation_policy_targets_loader_aligned_assets() -> None:
    policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))
    portfolio = build_initial_portfolio(
        Money(Decimal("1000000"), Money.ZERO.currency), _make_dataset()
    )
    decision = policy.decide(_make_context(portfolio))

    assert decision.allocation_target.weights == {
        _loader_asset("equity"): Decimal("0.75"),
        _loader_asset("bond"): Decimal("0.25"),
    }


def test_constant_allocation_policy_assets_present_in_snapshot() -> None:
    """The target assets must exist in the dataset snapshot keys (priceable)."""
    policy = ConstantAllocationPolicy(equity_allocation=Decimal("0.6"))
    portfolio = build_initial_portfolio(
        Money(Decimal("1000000"), Money.ZERO.currency), _make_dataset()
    )
    decision = policy.decide(_make_context(portfolio))

    snapshot_keys = {_loader_asset("equity"), _loader_asset("bond")}
    assert set(decision.allocation_target.weights) == snapshot_keys


def test_part3_parse_as_study_configuration() -> None:
    from fbf.core.study.builder import StudyConfiguration, load_yaml

    data = load_yaml(Path("examples/studies/ern_part3_replication.yaml"))
    StudyConfiguration.from_yaml(data)


def test_part3_replication_has_dual_final_value_targets() -> None:
    from decimal import Decimal

    from fbf.core.study.builder import StudyConfiguration, load_yaml

    data = load_yaml(Path("examples/studies/ern_part3_replication.yaml"))
    config = StudyConfiguration.from_yaml(data)
    assert config.final_value_target_values is not None
    assert Decimal("0.0") in config.final_value_target_values
    assert Decimal("0.5") in config.final_value_target_values




class TestLoadYamlError:
    """Tests for load_yaml() error behaviour when PyYAML is unavailable."""

    def test_load_yaml_missing_pyyaml_error_message(self) -> None:
        """When PyYAML is not installed, load_yaml() raises RuntimeError with clear guidance."""
        import sys
        import unittest.mock

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


class TestExplicitConfigurations:
    """Tests for the ``configurations`` (explicit) mode in StudyConfiguration."""

    BASE_YAML = {
        "metadata": {"name": "test-explicit", "description": "explicit config test"},
        "dataset": {"identifier": "ern_swr_h720"},
        "cohorts": {"horizon_years": [10, 20]},
        "allocation_policy": {
            "type": "ConstantAllocationPolicy",
        },
        "withdrawal_policy": {
            "type": "FixedRealWithdrawalPolicy",
            "withdrawal_rate": [0.04],
        },
    }

    def test_from_yaml_explicit_configurations_populated(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [
                    {"equity_allocation": "0.6"},
                    {"equity_allocation": "0.8"},
                ],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        assert config.explicit_configurations is not None
        assert len(config.explicit_configurations) == 2

    def test_mutual_exclusivity_rejects_configurations_with_axis(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [{"equity_allocation": "0.6"}],
                "equity_allocation": ["0.5", "0.7"],
            },
        }
        with pytest.raises(ValueError, match="mutually exclusive"):
            StudyConfiguration.from_yaml(data)

    def test_mutual_exclusivity_rejects_configurations_with_gp_axis(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "GlidepathAllocationPolicy",
                "configurations": [
                    {"start_equity": 0.8, "end_equity": 0.5, "slope": 0.01, "mode": "active"},
                ],
                "start_equity": ["0.8", "0.9"],
            },
        }
        with pytest.raises(ValueError, match="mutually exclusive"):
            StudyConfiguration.from_yaml(data)

    def test_build_configs_explicit_produces_correct_count(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [
                    {"equity_allocation": "0.6"},
                    {"equity_allocation": "0.8"},
                ],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        # 2 configs × 2 horizons × 1 withdrawal = 4
        assert len(configs) == 4

    def test_build_configs_explicit_cross_horizons(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "cohorts": {"horizon_years": [5, 10, 20]},
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [{"equity_allocation": "0.7"}],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        horizons = {pc.values["horizon_years"] for pc in configs}
        assert horizons == {5, 10, 20}

    def test_build_configs_explicit_cross_withdrawal(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "withdrawal_policy": {
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.03, 0.04],
            },
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [{"equity_allocation": "0.7"}],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        wrates = {pc.values["withdrawal_rate"] for pc in configs}
        assert wrates == {0.03, 0.04}

    def test_build_configs_explicit_cross_final_value_target(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [{"equity_allocation": "0.7"}],
            },
            "final_value_target": [0.0, 0.5],
        }
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        targets = {pc.values.get("final_value_target") for pc in configs}
        assert targets == {0.0, 0.5}

    def test_build_configs_explicit_preserves_all_policy_keys(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "GlidepathAllocationPolicy",
                "configurations": [
                    {
                        "start_equity": 0.8,
                        "end_equity": 0.5,
                        "slope": 0.01,
                        "mode": "active",
                    },
                ],
            },
            "cohorts": {"horizon_years": [10]},
        }
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        pc = configs[0]
        assert pc.values["start_equity"] == 0.8
        assert pc.values["end_equity"] == 0.5
        assert pc.values["slope"] == 0.01
        assert pc.values["mode"] == "active"
        assert pc.values["horizon_years"] == 10

    def test_from_yaml_empty_configurations_raises(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [],
            },
        }
        with pytest.raises(ValueError, match="must be a non-empty list"):
            StudyConfiguration.from_yaml(data)

    def test_from_yaml_empty_dict_configuration_raises(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [{}],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        with pytest.raises(ValueError, match="at least one parameter"):
            _build_unified_parameter_configs(config)

    def test_build_configs_cartesian_unchanged_when_no_explicit(self) -> None:
        """Regression: Cartesian product mode still works as before."""
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "equity_allocation": [0.6, 0.8],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        # 2 allocations × 2 horizons × 1 withdrawal = 4
        assert len(configs) == 4

    def test_representative_policies_use_first_explicit_config(self) -> None:
        from fbf.core.domain.policies import ConstantAllocationPolicy
        from fbf.core.study.builder import (
            StudyConfiguration,
            _representative_policies,
        )

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "ConstantAllocationPolicy",
                "configurations": [
                    {"equity_allocation": "0.3"},
                    {"equity_allocation": "0.9"},
                ],
            },
        }
        config = StudyConfiguration.from_yaml(data)
        alloc, _withdrawal = _representative_policies(config)
        # Representative policy should use first config (0.3)
        assert isinstance(alloc, ConstantAllocationPolicy)
        assert alloc.equity_allocation == Decimal("0.3")

    def test_representative_policies_use_first_explicit_gp_config(self) -> None:
        from fbf.core.domain.policies import GlidepathAllocationPolicy
        from fbf.core.study.builder import (
            StudyConfiguration,
            _representative_policies,
        )

        data = {
            **self.BASE_YAML,
            "allocation_policy": {
                "type": "GlidepathAllocationPolicy",
                "configurations": [
                    {"start_equity": 0.9, "end_equity": 0.4, "slope": 0.02, "mode": "active"},
                    {"start_equity": 0.7, "end_equity": 0.3, "slope": 0.01, "mode": "active"},
                ],
            },
            "cohorts": {"horizon_years": [10]},
        }
        config = StudyConfiguration.from_yaml(data)
        alloc, _withdrawal = _representative_policies(config)
        assert isinstance(alloc, GlidepathAllocationPolicy)
        assert alloc.start_equity == Decimal("0.9")
        assert alloc.end_equity == Decimal("0.4")


# ---------------------------------------------------------------------------
# Initial-wealth reconciliation regression
# ---------------------------------------------------------------------------


class TestInitialWealthReconciliation:
    """Portfolio value at the initial market snapshot must equal initial_wealth.

    Regression: build_initial_portfolio previously created units as
    ``initial_wealth * 0.5`` without dividing by the initial price, which
    produced a portfolio value of ~100× initial_wealth when index levels
    were ~100.
    """

    def test_portfolio_value_equals_initial_wealth(self) -> None:
        """portfolio_value_at_snapshot[0] == initial_wealth for any price level."""
        equity = _loader_asset("equity")
        bond = _loader_asset("bond")
        price_eq = Decimal("101.17")
        price_bd = Decimal("100.75")

        snapshot = MarketSnapshot(
            date=date(2020, 1, 1),
            index_levels={equity: price_eq, bond: price_bd},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=price_eq,
        )
        dataset = Dataset(snapshots=(snapshot,), frequency="monthly")

        initial_wealth = Money(Decimal("1000000"), Money.ZERO.currency)
        portfolio = build_initial_portfolio(initial_wealth, dataset)

        # Price the portfolio at the initial snapshot
        total = Decimal("0")
        for h in portfolio.holdings:
            price = snapshot.index_levels[h.asset_class]
            total += h.units * price

        assert total == initial_wealth.amount, (
            f"Portfolio value at snapshot[0] ({total}) != "
            f"initial_wealth ({initial_wealth.amount})"
        )

    def test_withdrawal_amount_computed_from_initial_wealth(self) -> None:
        """Part49WithdrawalPolicy monthly amounts must match ERN methodology.

        ERN Part 49: monthly_withdrawal = initial_wealth * rate / 12.
        This requires portfolio_value_at_snapshot[0] == initial_wealth.
        """
        from fbf.core.domain.model.decision_context import DecisionContext
        from fbf.core.domain.policies import ConstantAllocationPolicy
        from fbf.core.domain.policies.part49_withdrawal import Part49WithdrawalPolicy

        equity = _loader_asset("equity")
        bond = _loader_asset("bond")
        price_eq = Decimal("101.17")
        price_bd = Decimal("100.75")

        snapshot = MarketSnapshot(
            date=date(2020, 1, 1),
            index_levels={equity: price_eq, bond: price_bd},
            inflation=Decimal("0"),
            inflation_cumulative=Decimal("0"),
            is_ath=True,
            is_underwater=False,
            running_ath=price_eq,
        )
        dataset = Dataset(snapshots=(snapshot,), frequency="monthly")

        initial_wealth = Money(Decimal("1000000"), Money.ZERO.currency)
        portfolio = build_initial_portfolio(initial_wealth, dataset)

        policy = Part49WithdrawalPolicy(withdrawal_rate=Decimal("0.03"))
        alloc = ConstantAllocationPolicy(equity_allocation=Decimal("0.75"))

        # Build a minimal SimulationContext-like object for the policy
        sim_ctx = SimulationContext(
            experiment_name="test",
            cohort="test",
            start_date=date(2020, 1, 1),
            horizon_months=12,
            initial_wealth=initial_wealth,
            initial_portfolio=portfolio,
            dataset=dataset,
            allocation_policy=alloc,
            withdrawal_policy=policy,
            loan_draw_rate=Decimal("0.01"),
        )

        alloc_decision = alloc.decide(DecisionContext(
            date=date(2020, 1, 1),
            period_index=0,
            simulation_context=sim_ctx,
            portfolio=portfolio,
            current_allocation=Allocation(
                weights={equity: Decimal("0.75"), bond: Decimal("0.25")}
            ),
            target_allocation=AllocationTarget(
                weights={equity: Decimal("0.75"), bond: Decimal("0.25")}
            ),
            market_snapshot=snapshot,
            dataset=dataset,
        ))

        decision_ctx = DecisionContext(
            date=date(2020, 1, 1),
            period_index=0,
            simulation_context=sim_ctx,
            portfolio=portfolio,
            current_allocation=Allocation(
                weights={equity: Decimal("0.75"), bond: Decimal("0.25")}
            ),
            target_allocation=alloc_decision.allocation_target,
            market_snapshot=snapshot,
            dataset=dataset,
        )

        decision = policy.decide(decision_ctx)

        # ERN Part 49: 3% portfolio withdrawal + 1% loan draw = 4% total
        expected_monthly = initial_wealth.amount * Decimal("0.03") / Decimal("12")
        expected_loan = initial_wealth.amount * Decimal("0.01") / Decimal("12")
        # GAP-1 fix: nominal_amount is total spending (portfolio + loan)
        expected_nominal = expected_monthly + expected_loan

        assert decision.nominal_amount.amount == expected_nominal
        assert decision.loan_draw_amount == expected_loan


# ---------------------------------------------------------------------------
# Part 52 parameter-grid axes (S6.4A)
# ---------------------------------------------------------------------------


class TestPart52ParameterAxes:
    """Verify borrow_pct and drawdown_threshold participate in the Cartesian product."""

    BASE_YAML: dict[str, Any] = {
        "metadata": {"name": "test-part52-axes"},
        "dataset": {"identifier": "ern_swr_h720"},
        "cohorts": {"horizon_years": [10]},
        "allocation_policy": {
            "type": "ConstantAllocationPolicy",
            "equity_allocation": [0.75],
        },
        "withdrawal_policy": {
            "type": "Part52WithdrawalPolicy",
            "withdrawal_rate": [0.0358],
        },
        "debt": {
            "interest_rate": 0.015,
            "ltv_limit": 0.50,
        },
    }

    def _yaml(self, **overrides: Any) -> dict[str, Any]:
        """Return a copy of BASE_YAML with deep-merged overrides for ``debt``."""
        data = dict(self.BASE_YAML)
        if "debt" in overrides:
            debt = dict(self.BASE_YAML["debt"])
            debt.update(overrides.pop("debt"))
            overrides["debt"] = debt
        data.update(overrides)
        return data

    def test_scalar_borrow_pct_produces_one_element_axis(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        config = StudyConfiguration.from_yaml(self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "borrow_pct": 0.4108},
        ))
        configs = _build_unified_parameter_configs(config)
        assert len(configs) == 1
        assert configs[0].values["borrow_pct"] == 0.4108

    def test_list_borrow_pct_produces_multi_element_axis(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        config = StudyConfiguration.from_yaml(self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "borrow_pct": [0.1, 0.2, 0.4]},
        ))
        configs = _build_unified_parameter_configs(config)
        borrow_pcts = {pc.values["borrow_pct"] for pc in configs}
        assert borrow_pcts == {0.1, 0.2, 0.4}

    def test_scalar_drawdown_threshold_produces_one_element_axis(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        config = StudyConfiguration.from_yaml(self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "drawdown_threshold": 0.20},
        ))
        configs = _build_unified_parameter_configs(config)
        assert len(configs) == 1
        assert configs[0].values["drawdown_threshold"] == 0.20

    def test_list_drawdown_threshold_produces_multi_element_axis(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        config = StudyConfiguration.from_yaml(self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50,
                  "drawdown_threshold": [0.15, 0.20, 0.25]},
        ))
        configs = _build_unified_parameter_configs(config)
        thresholds = {pc.values["drawdown_threshold"] for pc in configs}
        assert thresholds == {0.15, 0.20, 0.25}

    def test_cartesian_product_includes_all_axes(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = self._yaml(
            withdrawal_policy={
                "type": "Part52WithdrawalPolicy",
                "withdrawal_rate": [0.0358, 0.0378],
            },
            debt={"interest_rate": 0.015, "ltv_limit": 0.50,
                  "borrow_pct": [0.1, 0.4],
                  "drawdown_threshold": [0.15, 0.20]},
        )
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        # 2 WR × 2 borrow_pct × 2 threshold × 1 horizon × 1 alloc = 8
        assert len(configs) == 8
        combos = {
            (pc.values["withdrawal_rate"],
             pc.values["borrow_pct"],
             pc.values["drawdown_threshold"])
            for pc in configs
        }
        assert len(combos) == 8

    def test_no_leverage_axes_when_not_declared(self) -> None:
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = self._yaml(
            withdrawal_policy={
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
        )
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        assert all("borrow_pct" not in pc.values for pc in configs)
        assert all("drawdown_threshold" not in pc.values for pc in configs)

    def test_non_part52_policy_ignores_borrow_pct_axis(self) -> None:
        """When borrow_pct axis exists but policy is not Part52, axis is harmless."""
        from fbf.core.study.builder import StudyConfiguration, _build_unified_parameter_configs

        data = self._yaml(
            withdrawal_policy={
                "type": "FixedRealWithdrawalPolicy",
                "withdrawal_rate": [0.04],
            },
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "borrow_pct": [0.1, 0.4]},
        )
        config = StudyConfiguration.from_yaml(data)
        configs = _build_unified_parameter_configs(config)
        assert len(configs) == 2
        assert all("borrow_pct" in pc.values for pc in configs)

    def test_policy_resolver_uses_axis_values(self) -> None:
        """Resolver reads borrow_pct from ParameterConfiguration, not closure."""
        from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
        from fbf.core.study.builder import StudyConfiguration, _make_policy_resolver
        from fbf.core.study.internal.parameter.configuration import (
            ParameterConfiguration,
        )

        data = self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "borrow_pct": [0.1, 0.4]},
        )
        config = StudyConfiguration.from_yaml(data)
        resolver = _make_policy_resolver(config)

        pc1 = ParameterConfiguration({
            "equity_allocation": 0.75, "withdrawal_rate": 0.0358,
            "horizon_years": 10, "borrow_pct": 0.1,
        })
        pc2 = ParameterConfiguration({
            "equity_allocation": 0.75, "withdrawal_rate": 0.0358,
            "horizon_years": 10, "borrow_pct": 0.4,
        })

        _, policy1 = resolver(pc1)
        _, policy2 = resolver(pc2)

        assert isinstance(policy1, Part52WithdrawalPolicy)
        assert isinstance(policy2, Part52WithdrawalPolicy)
        assert policy1.borrow_pct == Decimal("0.1")
        assert policy2.borrow_pct == Decimal("0.4")
        assert policy1 is not policy2

    def test_policy_cache_distinguishes_borrow_pct(self) -> None:
        """Two configs with same WR but different borrow_pct get different policies."""
        from fbf.core.study.builder import StudyConfiguration, _make_policy_resolver
        from fbf.core.study.internal.parameter.configuration import (
            ParameterConfiguration,
        )

        data = self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "borrow_pct": [0.1, 0.4]},
        )
        config = StudyConfiguration.from_yaml(data)
        resolver = _make_policy_resolver(config)

        pc1 = ParameterConfiguration({
            "equity_allocation": 0.75, "withdrawal_rate": 0.0358,
            "horizon_years": 10, "borrow_pct": 0.1,
        })
        pc2 = ParameterConfiguration({
            "equity_allocation": 0.75, "withdrawal_rate": 0.0358,
            "horizon_years": 10, "borrow_pct": 0.4,
        })

        _, policy1 = resolver(pc1)
        _, policy2 = resolver(pc2)

        assert policy1 is not policy2

    def test_scalar_fallback_when_no_axis(self) -> None:
        """Resolver falls back to scalar config when no axis exists."""
        from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
        from fbf.core.study.builder import StudyConfiguration, _make_policy_resolver
        from fbf.core.study.internal.parameter.configuration import (
            ParameterConfiguration,
        )

        data = self._yaml(
            debt={"interest_rate": 0.015, "ltv_limit": 0.50, "borrow_pct": 0.4108},
        )
        config = StudyConfiguration.from_yaml(data)
        resolver = _make_policy_resolver(config)

        pc = ParameterConfiguration({
            "equity_allocation": 0.75, "withdrawal_rate": 0.0358,
            "horizon_years": 10,
        })

        _, policy = resolver(pc)
        assert isinstance(policy, Part52WithdrawalPolicy)
        assert policy.borrow_pct == Decimal("0.4108")


class TestProductionBuilderHorizon:
    """Regression test for the production builder's horizon calculation.

    Ensures the builder does not double-count the pre-retirement snapshot.
    A 10-year horizon = 120 return periods, 121 snapshots (pre-retirement + 120 returns).
    """

    def _make_config(self) -> StudyConfiguration:
        """Create a minimal config for 10-year horizon testing."""
        from decimal import Decimal

        from fbf.core.study import StudyConfiguration

        config = StudyConfiguration(
            name="test-horizon",
            description="test",
            version="1.0",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.5"),),
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.04"),),
            horizon_years=(10,),
            cohort_horizon_years=None,
            expense_ratio=Decimal("0.0005"),
        )
        return config

    def test_ten_year_horizon_has_121_snapshots_and_120_returns(self) -> None:
        """Production builder yields correct snapshot count and return periods."""
        from decimal import Decimal

        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        config = self._make_config()
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)

        # Build the study plan using the production builder
        # Uses canonical ERN dataset from data/inputs/ern
        built_study = build_study_plan(config, "data/inputs/ern", initial_wealth)
        plan = built_study.plan

        # Verify the plan has units (at least 2 cohorts)
        assert len(plan.units) >= 2

        # Verify each unit has correct horizon
        for unit in plan.units[:2]:
            # 10 years = 120 return periods
            # unit.horizon_months should be 121 (120 returns + 1 pre-retirement snapshot)
            assert unit.horizon_months == 121, (
                f"Expected unit.horizon_months=121, got {unit.horizon_months}"
            )

            # Dataset should have 121 snapshots (pre-retirement + 120 returns)
            assert len(unit.dataset.snapshots) == 121, (
                f"Expected 121 snapshots, got {len(unit.dataset.snapshots)}"
            )

            # The first snapshot is pre-retirement, returns start from snapshot 1 to 120
            # Number of return periods = len(snapshots) - 1 = 120

        # Verify the experiment definition horizon matches
        assert plan.experiment_definition.horizon_months == 121

    def test_ten_year_horizon_wb_horizon_semantics(self) -> None:
        """Verify wb_horizon = unit.horizon_months - 1 = 120 return periods."""
        from decimal import Decimal

        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.execution.pipeline.simulation_context import SimulationContext
        from fbf.core.study import build_study_plan

        config = self._make_config()
        initial_wealth = Money(Decimal("1000000"), Currency.EUR)

        built_study = build_study_plan(config, "data/inputs/ern", initial_wealth)
        plan = built_study.plan

        unit = plan.units[0]

        # Create context to verify wb_horizon semantics
        assert unit.horizon_months is not None
        ctx = SimulationContext(
            experiment_name="test",
            cohort=str(unit.cohort.start_date),
            start_date=unit.cohort.start_date,
            horizon_months=unit.horizon_months,
            initial_wealth=plan.experiment_definition.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=unit.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
            expense_ratio=unit.expense_ratio,
        )

        # For unit.horizon_months = 121, the Numba kernel simulates 121
        # monthly periods (month 0 through month 120), driven by 120 returns.
        from fbf.core.execution.pipeline.simulation import (
            ExperimentDefinition as EngineExperimentDefinition,
        )
        from fbf.core.execution.strategies.numba_executor import (
            NumbaSimulationExecutor,
        )

        run = NumbaSimulationExecutor().execute(
            EngineExperimentDefinition(
                name="horizon-semantics",
                description="",
                simulation_contexts=(ctx,),
            )
        )
        assert run.simulation_results[0].statistics.months_simulated == 121


_BASE_YAML = {
    "metadata": {"name": "test-allocations", "description": "explicit allocations"},
    "dataset": {"identifier": "ern_swr_h720"},
    "cohorts": {"horizon_years": [10, 20]},
    "allocation_policy": {"type": "ConstantAllocationPolicy"},
    "withdrawal_policy": {
        "type": "FixedRealWithdrawalPolicy",
        "withdrawal_rate": [0.04],
    },
}


class TestExplicitAllocationsConfiguration:
    """Tests for ``allocation_policy.allocations`` (explicit N-asset form)."""

    def _data(self, allocation_policy: dict[str, object]) -> dict[str, object]:
        return {**_BASE_YAML, "allocation_policy": allocation_policy}

    def test_from_yaml_populates_allocation_weights(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        config = StudyConfiguration.from_yaml(
            self._data(
                {
                    "type": "ConstantAllocationPolicy",
                    "allocations": {
                        "equity": "0.5",
                        "bond": "0.3",
                        "gold": "0.2",
                    },
                }
            )
        )
        assert config.allocation_weights == (
            ("bond", Decimal("0.3")),
            ("equity", Decimal("0.5")),
            ("gold", Decimal("0.2")),
        )
        assert config.allocation_policy_values == ()

    def test_allocations_and_equity_allocation_mutually_exclusive(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        with pytest.raises(ValueError, match="mutually exclusive"):
            StudyConfiguration.from_yaml(
                self._data(
                    {
                        "type": "ConstantAllocationPolicy",
                        "allocations": {"equity": "0.5", "bond": "0.5"},
                        "equity_allocation": ["0.5"],
                    }
                )
            )

    def test_allocations_and_configurations_mutually_exclusive(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        with pytest.raises(ValueError, match="mutually exclusive"):
            StudyConfiguration.from_yaml(
                self._data(
                    {
                        "type": "ConstantAllocationPolicy",
                        "allocations": {"equity": "0.5", "bond": "0.5"},
                        "configurations": [{"equity_allocation": "0.5"}],
                    }
                )
            )

    def test_allocations_rejected_for_glidepath(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        with pytest.raises(ValueError, match="only supported for ConstantAllocationPolicy"):
            StudyConfiguration.from_yaml(
                self._data(
                    {
                        "type": "GlidepathAllocationPolicy",
                        "allocations": {"equity": "0.5", "bond": "0.5"},
                    }
                )
            )

    def test_allocations_must_sum_to_one(self) -> None:
        from fbf.core.study.builder import StudyConfiguration

        with pytest.raises(ValueError, match="sum to exactly 1"):
            StudyConfiguration.from_yaml(
                self._data(
                    {
                        "type": "ConstantAllocationPolicy",
                        "allocations": {"equity": "0.5", "bond": "0.4"},
                    }
                )
            )

    def test_build_configs_has_no_equity_axis(self) -> None:
        from fbf.core.study.builder import (
            StudyConfiguration,
            _build_unified_parameter_configs,
        )

        config = StudyConfiguration.from_yaml(
            self._data(
                {
                    "type": "ConstantAllocationPolicy",
                    "allocations": {"equity": "0.5", "bond": "0.5"},
                }
            )
        )
        configs = _build_unified_parameter_configs(config)
        assert len(configs) == 2  # 1 allocation x 1 rate x 2 horizons
        for pc in configs:
            assert "equity_allocation" not in pc.values

    def test_policy_resolver_builds_explicit_policy(self) -> None:
        from fbf.core.domain.policies import ConstantAllocationPolicy
        from fbf.core.study.builder import (
            StudyConfiguration,
            _build_unified_parameter_configs,
            _make_policy_resolver,
        )

        config = StudyConfiguration.from_yaml(
            self._data(
                {
                    "type": "ConstantAllocationPolicy",
                    "allocations": {"equity": "0.5", "bond": "0.5"},
                }
            )
        )
        configs = _build_unified_parameter_configs(config)
        resolver = _make_policy_resolver(config)
        allocation, _ = resolver(configs[0])
        assert isinstance(allocation, ConstantAllocationPolicy)
        assert allocation.allocations == (
            ("bond", Decimal("0.5")),
            ("equity", Decimal("0.5")),
        )

    def test_representative_policies_builds_explicit_policy(self) -> None:
        from fbf.core.domain.policies import ConstantAllocationPolicy
        from fbf.core.study.builder import (
            StudyConfiguration,
            _representative_policies,
        )

        config = StudyConfiguration.from_yaml(
            self._data(
                {
                    "type": "ConstantAllocationPolicy",
                    "allocations": {"equity": "0.5", "bond": "0.5"},
                }
            )
        )
        allocation, _ = _representative_policies(config)
        assert isinstance(allocation, ConstantAllocationPolicy)
        assert allocation.allocations == (
            ("bond", Decimal("0.5")),
            ("equity", Decimal("0.5")),
        )


def _make_monthly_dataset(num_months: int = 120) -> Dataset:
    snapshots = []
    year = 2000
    month = 1
    for _ in range(num_months):
        snapshots.append(
            MarketSnapshot(
                date=date(year, month, 1),
                index_levels={
                    _loader_asset("equity"): Decimal("100"),
                    _loader_asset("bond"): Decimal("100"),
                },
                inflation=Decimal("0"),
                inflation_cumulative=Decimal("0"),
                is_ath=True,
                is_underwater=False,
                running_ath=Decimal("100"),
            )
        )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return Dataset(snapshots=tuple(snapshots), frequency="monthly")


def _make_filter_config() -> StudyConfiguration:
    return StudyConfiguration(
        name="cohort-filter-test",
        description="",
        version="1.0",
        allocation_policy_type="ConstantAllocationPolicy",
        allocation_policy_values=(Decimal("0.5"),),
        withdrawal_policy_type="FixedRealWithdrawalPolicy",
        withdrawal_policy_values=(Decimal("0.04"),),
        horizon_years=(5,),
        cohort_horizon_years=5,
    )


class TestCohortFilter:
    def test_filter_selects_subset_before_plan_materialization(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        dataset = _make_monthly_dataset()
        built = build_study_plan(
            _make_filter_config(),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=dataset,
            cohort_filter=lambda cohort: cohort.start_date.year == 2000,
        )

        assert len(built.cohorts) == 11
        assert len(built.plan.units) == 11
        assert built.experiment_definition.cohorts == built.cohorts
        assert all(cohort.start_date.year == 2000 for cohort in built.cohorts)

    def test_default_filter_preserves_generator_universe(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan
        from fbf.core.study.internal.cohort.generator import CohortGenerator

        dataset = _make_monthly_dataset()
        expected = CohortGenerator.generate_rolling_monthly(dataset, 61)[1:]
        built = build_study_plan(
            _make_filter_config(),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=dataset,
        )

        assert built.cohorts == expected
        assert len(built.cohorts) == 59
        assert len(built.plan.units) == 59

    def test_filter_excluding_every_cohort_raises(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        with pytest.raises(ValueError, match="cohort_filter excluded all"):
            build_study_plan(
                _make_filter_config(),
                "data/inputs/ern",
                Money(Decimal("1000000"), Currency.EUR),
                dataset=_make_monthly_dataset(),
                cohort_filter=lambda _: False,
            )

    def test_run_study_propagates_cohort_filter(self) -> None:
        from fbf.core.application import run_study
        from fbf.core.domain.model.money import Currency, Money

        result = run_study(
            _make_filter_config(),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=_make_monthly_dataset(),
            cohort_filter=lambda cohort: cohort.start_date.year == 2000,
        )

        assert len(result.experiment_result.simulation_results) == 11


class TestCohortDateConfiguration:
    """Tests for optional ``cohorts.start_date`` / ``cohorts.end_date``."""

    @staticmethod
    def _yaml(**cohort_values: object) -> dict[str, object]:
        return {
            **_BASE_YAML,
            "cohorts": {
                "horizon_years": [5],
                **cohort_values,
            },
        }

    @staticmethod
    def _config(
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> StudyConfiguration:
        return StudyConfiguration(
            name="cohort-date-test",
            description="",
            version="1.0",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.5"),),
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.04"),),
            horizon_years=(5,),
            cohort_horizon_years=5,
            cohort_start_date=start_date,
            cohort_end_date=end_date,
        )

    def test_from_yaml_parses_month_dates(self) -> None:
        config = StudyConfiguration.from_yaml(
            self._yaml(start_date="2000-03", end_date="2000-08")
        )

        assert config.cohort_start_date == date(2000, 3, 1)
        assert config.cohort_end_date == date(2000, 8, 1)

    def test_from_yaml_parses_full_iso_dates_and_date_objects(self) -> None:
        config = StudyConfiguration.from_yaml(
            self._yaml(
                start_date="2000-03-01",
                end_date=date(2000, 8, 1),
            )
        )

        assert config.cohort_start_date == date(2000, 3, 1)
        assert config.cohort_end_date == date(2000, 8, 1)

    def test_from_yaml_rejects_datetime_values(self) -> None:
        with pytest.raises(ValueError, match="without a time component"):
            StudyConfiguration.from_yaml(
                self._yaml(start_date=datetime(2000, 3, 1, 12, 0))
            )

    def test_from_yaml_omitted_bounds_preserve_defaults(self) -> None:
        config = StudyConfiguration.from_yaml(self._yaml())

        assert config.cohort_start_date is None
        assert config.cohort_end_date is None

    @pytest.mark.parametrize("raw", ["2000-3", "2000-03-1", "200003", "not-a-date"])
    def test_from_yaml_rejects_invalid_date_shape(self, raw: str) -> None:
        with pytest.raises(ValueError, match="must be an ISO date"):
            StudyConfiguration.from_yaml(self._yaml(start_date=raw))

    def test_from_yaml_rejects_invalid_calendar_date(self) -> None:
        with pytest.raises(ValueError, match="not a valid calendar date"):
            StudyConfiguration.from_yaml(self._yaml(start_date="2000-13"))

    def test_from_yaml_rejects_reversed_bounds(self) -> None:
        with pytest.raises(ValueError, match="must not be after"):
            StudyConfiguration.from_yaml(
                self._yaml(start_date="2000-08", end_date="2000-03")
            )

    def test_build_plan_selects_exact_inclusive_range(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        built = build_study_plan(
            self._config(start_date=date(2000, 2, 1), end_date=date(2000, 6, 1)),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=_make_monthly_dataset(),
        )

        assert [cohort.start_date for cohort in built.cohorts] == [
            date(2000, 2, 1),
            date(2000, 3, 1),
            date(2000, 4, 1),
            date(2000, 5, 1),
            date(2000, 6, 1),
        ]
        assert len(built.plan.units) == 5

    def test_default_bounds_preserve_rolling_universe(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan
        from fbf.core.study.internal.cohort.generator import CohortGenerator

        dataset = _make_monthly_dataset()
        expected = CohortGenerator.generate_rolling_monthly(dataset, 61)[1:]
        built = build_study_plan(
            self._config(),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=dataset,
        )

        assert built.cohorts == expected
        assert len(built.cohorts) == 59

    def test_start_bound_without_end_uses_dataset_end(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        built = build_study_plan(
            self._config(start_date=date(2000, 6, 1)),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=_make_monthly_dataset(),
        )

        assert built.cohorts[0].start_date == date(2000, 6, 1)
        assert built.cohorts[-1].start_date == date(2004, 12, 1)

    def test_end_bound_without_start_uses_dataset_start(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        built = build_study_plan(
            self._config(end_date=date(2000, 6, 1)),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=_make_monthly_dataset(),
        )

        assert built.cohorts[0].start_date == date(2000, 2, 1)
        assert built.cohorts[-1].start_date == date(2000, 6, 1)
        assert len(built.cohorts) == 5

    def test_explicit_end_does_not_override_horizon_feasibility(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        built = build_study_plan(
            self._config(end_date=date(2009, 12, 1)),
            "data/inputs/ern",
            Money(Decimal("1000000"), Currency.EUR),
            dataset=_make_monthly_dataset(),
        )

        assert built.cohorts[-1].start_date == date(2004, 12, 1)
        assert len(built.cohorts) == 59

    def test_infeasible_range_raises(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        with pytest.raises(ValueError, match="no feasible cohorts"):
            build_study_plan(
                self._config(
                    start_date=date(2005, 1, 1),
                    end_date=date(2005, 6, 1),
                ),
                "data/inputs/ern",
                Money(Decimal("1000000"), Currency.EUR),
                dataset=_make_monthly_dataset(),
            )


class TestInjectedDatasetCutoff:
    def test_ffr_requires_historical_cutoff_for_injected_dataset(self) -> None:
        from fbf.core.domain.model.money import Currency, Money
        from fbf.core.study import build_study_plan

        config = StudyConfiguration(
            name="injected-ffr-cutoff",
            description="",
            version="1.0",
            allocation_policy_type="ConstantAllocationPolicy",
            allocation_policy_values=(Decimal("0.5"),),
            withdrawal_policy_type="FixedRealWithdrawalPolicy",
            withdrawal_policy_values=(Decimal("0.04"),),
            horizon_years=(5,),
            cohort_horizon_years=5,
            ffr_spread=Decimal("0.005"),
        )

        with pytest.raises(ValueError, match="FFR historical cutoff is required"):
            build_study_plan(
                config,
                "data/inputs/ern",
                Money(Decimal("1000000"), Currency.EUR),
                dataset=_make_monthly_dataset(),
            )
