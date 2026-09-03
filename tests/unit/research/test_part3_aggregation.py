"""Tests for Part 3 CAPE regime aggregation.

Validates the ``aggregate_part3_results`` function and the
``get_regime_table`` filtering helper.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from fbf.core.domain.policies.cape_regime import CapeRegime
from fbf.core.execution.pipeline.simulation import (
    SimulationResult,
    SimulationStatistics,
)
from fbf.core.research.part3_aggregation import (
    Part3AggregationResult,
    RegimeAggregation,
    aggregate_part3_results,
    get_regime_table,
)
from fbf.core.study.internal.cohort.specification import CohortSpecification
from fbf.core.study.internal.parameter.configuration import ParameterConfiguration

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


_D = date.fromisoformat


def _cohort(cohort_date: str) -> CohortSpecification:
    """Build a CohortSpecification for testing."""
    return CohortSpecification(start_date=_D(cohort_date))


def _params(
    horizon: int,
    equity: str,
    withdrawal: str,
    target: str | None = None,
) -> ParameterConfiguration:
    """Build a ParameterConfiguration for testing."""
    bindings: dict[str, Any] = {
        "horizon_years": horizon,
        "equity_allocation": equity,
        "withdrawal_rate": withdrawal,
    }
    if target is not None:
        bindings["final_value_target"] = target
    return ParameterConfiguration(values=bindings)


def _result(success: bool) -> SimulationResult:
    """Build a minimal SimulationResult for testing."""
    return SimulationResult(
        timeline=None,  # type: ignore[arg-type]
        statistics=SimulationStatistics(
            final_wealth=None,  # type: ignore[arg-type]
            max_drawdown=0.0,
            success=success,
            failure_month=None,
            months_simulated=120,
            execution_time_seconds=0.0,
        ),
    )


def _cape_registry(
    metadata: Mapping[date, tuple[Decimal | None, str | None]],
) -> dict[str, tuple[Decimal | None, str | None]]:
    """Convert date-keyed metadata to isoformat string keys for lookup."""
    return {d.isoformat(): v for d, v in metadata.items()}


def _make_get_cape(
    metadata: Mapping[date, tuple[Decimal | None, str | None]],
) -> Any:
    """Build a get_cape_metadata callable from a date-keyed dict."""
    registry = _cape_registry(metadata)

    def get_cape(spec: CohortSpecification) -> tuple[Decimal | None, str | None]:
        return registry.get(spec.start_date.isoformat(), (None, None))

    return get_cape


# ---------------------------------------------------------------------------
# RegimeAggregation tests
# ---------------------------------------------------------------------------


class TestRegimeAggregation:
    """Unit tests for RegimeAggregation."""

    def test_success_rate(self) -> None:
        agg = RegimeAggregation(
            horizon_years=30,
            equity_allocation=Decimal("1.0"),
            withdrawal_rate=Decimal("0.04"),
            terminal_target=None,
            cape_regime=CapeRegime.MODERATE,
            successful_cohorts=80,
            total_cohorts=100,
        )
        assert agg.success_rate == Decimal("0.80")

    def test_success_rate_zero_total(self) -> None:
        agg = RegimeAggregation(
            horizon_years=30,
            equity_allocation=Decimal("1.0"),
            withdrawal_rate=Decimal("0.04"),
            terminal_target=None,
            cape_regime=CapeRegime.HIGH,
            successful_cohorts=0,
            total_cohorts=0,
        )
        assert agg.success_rate == Decimal("0")

    def test_success_rate_all_success(self) -> None:
        agg = RegimeAggregation(
            horizon_years=30,
            equity_allocation=Decimal("0.6"),
            withdrawal_rate=Decimal("0.04"),
            terminal_target=None,
            cape_regime=CapeRegime.BELOW_15,
            successful_cohorts=50,
            total_cohorts=50,
        )
        assert agg.success_rate == Decimal("1")


# ---------------------------------------------------------------------------
# aggregate_part3_results tests
# ---------------------------------------------------------------------------


class TestAggregatePart3Results:
    """Unit tests for aggregate_part3_results."""

    def test_single_regime_single_param(self) -> None:
        """Single parameter config, single regime — all same group."""
        cohorts = [_cohort(f"1980-{m:02d}-01") for m in range(1, 13)]
        params = [_params(30, "1.0", "0.04") for _ in range(12)]
        cape = {
            date(1980, m, 1): (Decimal("25"), "HIGH") for m in range(1, 13)
        }
        results = [_result(m % 3 != 0) for m in range(1, 13)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert agg.total_units == 12
        assert len(agg.regime_aggregations) == 1
        assert agg.regime_aggregations[0].cape_regime == CapeRegime.HIGH
        assert agg.regime_aggregations[0].total_cohorts == 12
        assert agg.regime_aggregations[0].successful_cohorts == 8

    def test_multiple_regimes(self) -> None:
        """Multiple CAPE regimes produce separate aggregation cells."""
        cohorts = [_cohort("1980-01-01"), _cohort("1990-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(30, "1.0", "0.04")]
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        results = [_result(True), _result(False)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        regimes = {a.cape_regime for a in agg.regime_aggregations}
        assert regimes == {CapeRegime.HIGH, CapeRegime.BELOW_15}
        assert agg.total_units == 2

    def test_multiple_params_multiple_regimes(self) -> None:
        """Multiple parameters × multiple regimes create the full cross-product."""
        cohorts = [
            _cohort("1980-01-01"),
            _cohort("1980-06-01"),
            _cohort("1990-01-01"),
            _cohort("1990-06-01"),
        ]
        params = [_params(30, "1.0", "0.04")] * 4
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1980-06-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
            _D("1990-06-01"): (Decimal("12"), "BELOW_15"),
        }
        results = [_result(True), _result(True), _result(False), _result(False)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert len(agg.regime_aggregations) == 2
        by_regime = {a.cape_regime: a for a in agg.regime_aggregations}
        assert by_regime[CapeRegime.HIGH].successful_cohorts == 2
        assert by_regime[CapeRegime.HIGH].total_cohorts == 2
        assert by_regime[CapeRegime.BELOW_15].successful_cohorts == 0
        assert by_regime[CapeRegime.BELOW_15].total_cohorts == 2

    def test_different_horizons_produce_separate_groups(self) -> None:
        """Different horizons create different aggregation groups."""
        cohorts = [_cohort("1980-01-01"), _cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(40, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        results = [_result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert len(agg.regime_aggregations) == 2
        horizons = {a.horizon_years for a in agg.regime_aggregations}
        assert horizons == {30, 40}

    def test_different_equity_produces_separate_groups(self) -> None:
        """Different equity allocations create different groups."""
        cohorts = [_cohort("1980-01-01"), _cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(30, "0.5", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        results = [_result(True), _result(False)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert len(agg.regime_aggregations) == 2
        equities = {a.equity_allocation for a in agg.regime_aggregations}
        assert equities == {Decimal("1.0"), Decimal("0.5")}

    def test_terminal_target_in_key(self) -> None:
        """Terminal target is part of the aggregation key."""
        cohorts = [_cohort("1980-01-01"), _cohort("1980-01-01")]
        params = [
            _params(30, "1.0", "0.04"),
            _params(30, "1.0", "0.04", target="0.5"),
        ]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        results = [_result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert len(agg.regime_aggregations) == 2
        targets = {a.terminal_target for a in agg.regime_aggregations}
        assert targets == {None, Decimal("0.5")}

    def test_length_mismatch_raises(self) -> None:
        """Mismatched input lengths raises ValueError."""
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}

        with pytest.raises(ValueError, match="matching lengths"):
            aggregate_part3_results(
                tuple(cohorts),
                tuple(params),
                (_result(True), _result(True)),
                _make_get_cape(cape),
            )

    def test_empty_inputs(self) -> None:
        """Empty inputs returns empty aggregation."""
        agg = aggregate_part3_results((), (), (), _make_get_cape({}))
        assert agg.total_units == 0
        assert len(agg.regime_aggregations) == 0

    def test_no_cape_metadata_excluded_counted(self) -> None:
        """Cohorts without CAPE metadata are excluded and counted."""
        cohorts = [_cohort("1870-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape: dict[date, tuple[Decimal | None, str | None]] = {
            _D("1870-01-01"): (None, None),
        }
        results = [_result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert agg.excluded_no_cape == 1
        assert agg.total_units == 1

    def test_sorted_output(self) -> None:
        """Output is sorted by (horizon, equity, regime)."""
        cohorts = [
            _cohort("1990-01-01"),
            _cohort("1980-01-01"),
            _cohort("1970-01-01"),
        ]
        params = [
            _params(30, "1.0", "0.04"),
            _params(30, "1.0", "0.04"),
            _params(40, "0.6", "0.04"),
        ]
        cape = {
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1970-01-01"): (Decimal("18"), "MODERATE"),
        }
        results = [_result(True), _result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        keys = [
            (a.horizon_years, a.equity_allocation, a.cape_regime.value)
            for a in agg.regime_aggregations
        ]
        assert keys == sorted(keys)

    def test_all_success(self) -> None:
        """All simulations succeed — success rate = 1.0 for all cells."""
        cohorts = [_cohort("1980-01-01"), _cohort("1985-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(30, "1.0", "0.04")]
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1985-01-01"): (Decimal("18"), "MODERATE"),
        }
        results = [_result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        for ra in agg.regime_aggregations:
            assert ra.success_rate == Decimal("1")

    def test_all_failure(self) -> None:
        """All simulations fail — success rate = 0 for all cells."""
        cohorts = [_cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        results = [_result(False)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert agg.regime_aggregations[0].success_rate == Decimal("0")


# ---------------------------------------------------------------------------
# get_regime_table tests
# ---------------------------------------------------------------------------


class TestGetRegimeTable:
    """Unit tests for get_regime_table filtering."""

    @pytest.fixture()
    def sample_aggregation(self) -> Part3AggregationResult:
        """Pre-built aggregation with known values."""
        aggregations = (
            RegimeAggregation(
                horizon_years=30,
                equity_allocation=Decimal("1.0"),
                withdrawal_rate=Decimal("0.04"),
                terminal_target=None,
                cape_regime=CapeRegime.BELOW_15,
                successful_cohorts=100,
                total_cohorts=100,
            ),
            RegimeAggregation(
                horizon_years=30,
                equity_allocation=Decimal("1.0"),
                withdrawal_rate=Decimal("0.04"),
                terminal_target=None,
                cape_regime=CapeRegime.MODERATE,
                successful_cohorts=90,
                total_cohorts=100,
            ),
            RegimeAggregation(
                horizon_years=30,
                equity_allocation=Decimal("1.0"),
                withdrawal_rate=Decimal("0.04"),
                terminal_target=None,
                cape_regime=CapeRegime.HIGH,
                successful_cohorts=80,
                total_cohorts=100,
            ),
            RegimeAggregation(
                horizon_years=30,
                equity_allocation=Decimal("1.0"),
                withdrawal_rate=Decimal("0.04"),
                terminal_target=None,
                cape_regime=CapeRegime.EXTREME,
                successful_cohorts=50,
                total_cohorts=100,
            ),
            RegimeAggregation(
                horizon_years=40,
                equity_allocation=Decimal("1.0"),
                withdrawal_rate=Decimal("0.04"),
                terminal_target=None,
                cape_regime=CapeRegime.MODERATE,
                successful_cohorts=85,
                total_cohorts=100,
            ),
        )
        return Part3AggregationResult(
            regime_aggregations=aggregations,
            total_units=500,
            excluded_no_cape=0,
        )

    def test_no_filter(self, sample_aggregation: Part3AggregationResult) -> None:
        """No filter returns all rows."""
        rows = get_regime_table(sample_aggregation)
        assert len(rows) == 5

    def test_filter_horizon(self, sample_aggregation: Part3AggregationResult) -> None:
        """Filter by horizon returns only matching rows."""
        rows = get_regime_table(sample_aggregation, horizon_years=30)
        assert len(rows) == 4
        assert all(r["horizon"] == 30 for r in rows)

    def test_filter_regime(self, sample_aggregation: Part3AggregationResult) -> None:
        """Filter by horizon+equity returns only matching rows."""
        rows = get_regime_table(
            sample_aggregation, equity_allocation=Decimal("1.0"), horizon_years=40
        )
        assert len(rows) == 1
        assert rows[0]["CAPE_regime"] == CapeRegime.MODERATE

    def test_filter_target_depletion(
        self, sample_aggregation: Part3AggregationResult
    ) -> None:
        """Filter target=None returns depletion rows."""
        rows = get_regime_table(sample_aggregation, terminal_target=None)
        assert len(rows) == 5

    def test_sorted_output(self, sample_aggregation: Part3AggregationResult) -> None:
        """Output is sorted by (horizon, equity, regime)."""
        rows = get_regime_table(sample_aggregation)
        keys = [
            (r["horizon"], r["equity_allocation"], r["CAPE_regime"].value)
            for r in rows
        ]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Part3AggregationResult tests
# ---------------------------------------------------------------------------


class TestPart3AggregationResult:
    """Tests for Part3AggregationResult properties."""

    def test_regimes_property(self) -> None:
        agg = Part3AggregationResult(
            regime_aggregations=(
                RegimeAggregation(
                    horizon_years=30,
                    equity_allocation=Decimal("1.0"),
                    withdrawal_rate=Decimal("0.04"),
                    terminal_target=None,
                    cape_regime=CapeRegime.HIGH,
                    successful_cohorts=80,
                    total_cohorts=100,
                ),
                RegimeAggregation(
                    horizon_years=30,
                    equity_allocation=Decimal("1.0"),
                    withdrawal_rate=Decimal("0.04"),
                    terminal_target=None,
                    cape_regime=CapeRegime.BELOW_15,
                    successful_cohorts=90,
                    total_cohorts=100,
                ),
            ),
            total_units=200,
            excluded_no_cape=0,
        )
        assert agg.regimes == (CapeRegime.HIGH, CapeRegime.BELOW_15)

    def test_regimes_empty(self) -> None:
        agg = Part3AggregationResult(
            regime_aggregations=(),
            total_units=0,
            excluded_no_cape=0,
        )
        assert agg.regimes == ()


# ---------------------------------------------------------------------------
# Regression tests: CAPE-unavailable cohort exclusion
# ---------------------------------------------------------------------------


class TestCapeUnavailableExclusion:
    """Regression tests ensuring CAPE-unavailable cohorts are never
    assigned an artificial regime and do not bias regime statistics."""

    def test_no_cape_cohort_excluded_from_regimes(self) -> None:
        """A cohort without CAPE metadata must not appear in any regime."""
        cohorts = [_cohort("1870-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape: dict[date, tuple[Decimal | None, str | None]] = {
            _D("1870-01-01"): (None, None),
        }
        results = [_result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert agg.excluded_no_cape == 1
        assert agg.total_units == 1
        total_in_regimes = sum(a.total_cohorts for a in agg.regime_aggregations)
        assert total_in_regimes == 0

    def test_mixed_cape_and_no_cape(self) -> None:
        """Only CAPE-available cohorts contribute to regime statistics."""
        cohorts = [
            _cohort("1980-01-01"),  # CAPE available
            _cohort("1870-01-01"),  # CAPE unavailable
            _cohort("1990-01-01"),  # CAPE available
        ]
        params = [_params(30, "1.0", "0.04")] * 3
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1870-01-01"): (None, None),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        results = [_result(True), _result(True), _result(False)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert agg.total_units == 3
        assert agg.excluded_no_cape == 1
        total_in_regimes = sum(a.total_cohorts for a in agg.regime_aggregations)
        assert total_in_regimes == 2

        regimes = {a.cape_regime: a for a in agg.regime_aggregations}
        assert regimes[CapeRegime.HIGH].total_cohorts == 1
        assert regimes[CapeRegime.BELOW_15].total_cohorts == 1

    def test_regime_populations_sum_to_cape_eligible(self) -> None:
        """Regime totals must equal CAPE-eligible count, not total count."""
        cohorts = [
            _cohort("1980-01-01"),  # HIGH
            _cohort("1985-01-01"),  # MODERATE
            _cohort("1870-01-01"),  # no CAPE
            _cohort("1975-01-01"),  # BELOW_15
        ]
        params = [_params(30, "1.0", "0.04")] * 4
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1985-01-01"): (Decimal("18"), "MODERATE"),
            _D("1870-01-01"): (None, None),
            _D("1975-01-01"): (Decimal("12"), "BELOW_15"),
        }
        results = [_result(True)] * 4

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        regime_total = sum(a.total_cohorts for a in agg.regime_aggregations)
        cape_eligible = len(cohorts) - agg.excluded_no_cape
        assert regime_total == cape_eligible
        assert regime_total == 3  # not 4

    def test_no_cape_cannot_become_below_15(self) -> None:
        """Verify that a no-CAPE cohort never creates a BELOW_15 entry."""
        cohorts = [_cohort("1870-01-01")]
        params = [_params(30, "1.0", "0.04")]
        cape: dict[date, tuple[Decimal | None, str | None]] = {
            _D("1870-01-01"): (None, None),
        }
        results = [_result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        for a in agg.regime_aggregations:
            assert a.cape_regime != CapeRegime.BELOW_15 or a.total_cohorts == 0

    def test_all_no_cape_empty_regimes(self) -> None:
        """When all cohorts lack CAPE, no regime entries are produced."""
        cohorts = [_cohort("1870-01-01"), _cohort("1871-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(30, "1.0", "0.04")]
        cape: dict[date, tuple[Decimal | None, str | None]] = {
            _D("1870-01-01"): (None, None),
            _D("1871-01-01"): (None, None),
        }
        results = [_result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        assert agg.excluded_no_cape == 2
        assert len(agg.regime_aggregations) == 0


# ---------------------------------------------------------------------------
# Regression tests: multi-parameter cross-product
# ---------------------------------------------------------------------------


class TestMultiParameterCrossProduct:
    """Regression tests for multi-parameter aggregation correctness."""

    def test_cross_product_preserves_all_cells(self) -> None:
        """Two cohorts × two params produce the correct cross-product."""
        cohorts = [_cohort("1980-01-01"), _cohort("1990-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(40, "0.6", "0.03")]
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        # Replicate for cross-product: 2 cohorts × 2 params = 4 units
        replicated_cohorts = tuple(c for c in cohorts for _ in range(2))
        replicated_params = tuple(p for _ in range(2) for p in params)
        results = [_result(True), _result(True), _result(False), _result(False)]

        agg = aggregate_part3_results(
            replicated_cohorts, replicated_params, tuple(results), _make_get_cape(cape)
        )

        # Should produce 4 cells: 2 regimes × 2 horizons
        assert len(agg.regime_aggregations) == 4
        # Each cell has exactly 1 cohort
        for a in agg.regime_aggregations:
            assert a.total_cohorts == 1

    def test_cross_product_correct_regime_assignment(self) -> None:
        """Each cell gets the correct regime from its cohort's CAPE metadata."""
        cohorts = [_cohort("1980-01-01"), _cohort("1990-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(30, "1.0", "0.04")]
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        # Replicate: 2 cohorts × 2 params = 4 units
        replicated_cohorts = tuple(c for c in cohorts for _ in range(2))
        replicated_params = tuple(p for _ in range(2) for p in params)
        results = [_result(True)] * 4

        agg = aggregate_part3_results(
            replicated_cohorts, replicated_params, tuple(results), _make_get_cape(cape)
        )

        by_regime = {a.cape_regime: a for a in agg.regime_aggregations}
        assert by_regime[CapeRegime.HIGH].total_cohorts == 2
        assert by_regime[CapeRegime.BELOW_15].total_cohorts == 2

    def test_broadcast_single_param(self) -> None:
        """Single param config broadcasts to all cohorts."""
        cohorts = [_cohort("1980-01-01"), _cohort("1990-01-01")]
        params = [_params(30, "1.0", "0.04")]  # single config
        cape = {
            _D("1980-01-01"): (Decimal("25"), "HIGH"),
            _D("1990-01-01"): (Decimal("12"), "BELOW_15"),
        }
        results = [_result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        # Single param means same (horizon, equity, withdrawal) for both
        # but different regimes
        assert len(agg.regime_aggregations) == 2
        assert agg.total_units == 2


# ---------------------------------------------------------------------------
# Regression tests: horizon-specific eligibility
# ---------------------------------------------------------------------------


class TestHorizonEligibility:
    """Regression tests for horizon-specific cohort eligibility."""

    def test_different_horizons_create_separate_groups(self) -> None:
        """Different horizons produce distinct aggregation cells."""
        cohorts = [_cohort("1980-01-01"), _cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(40, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        results = [_result(True), _result(True)]

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        horizons = {a.horizon_years for a in agg.regime_aggregations}
        assert horizons == {30, 40}

    def test_horizon_cells_independent(self) -> None:
        """Success in one horizon doesn't affect another."""
        cohorts = [_cohort("1980-01-01"), _cohort("1980-01-01")]
        params = [_params(30, "1.0", "0.04"), _params(40, "1.0", "0.04")]
        cape = {_D("1980-01-01"): (Decimal("25"), "HIGH")}
        results = [_result(True), _result(False)]  # 30y succeeds, 40y fails

        agg = aggregate_part3_results(
            tuple(cohorts), tuple(params), tuple(results), _make_get_cape(cape)
        )

        by_horizon = {a.horizon_years: a for a in agg.regime_aggregations}
        assert by_horizon[30].successful_cohorts == 1
        assert by_horizon[40].successful_cohorts == 0
