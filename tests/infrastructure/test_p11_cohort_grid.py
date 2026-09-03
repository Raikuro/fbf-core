"""Tests for P11 cohort-horizon grid repository methods.

Tests get_available_parameters() and get_cohort_horizon_grid() on SQLiteRepository.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from fbf.core.persistence.studies.sqlite import SQLiteRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return "2026-01-01T00:00:00Z"


def _to_canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _make_stats_json(
    success: bool,
    final_wealth: str = "500000.00",
    failure_month: int | None = None,
) -> str:
    return json.dumps({
        "final_wealth_amount": final_wealth,
        "final_wealth_currency": "EUR",
        "max_drawdown": 0.05,
        "success": success,
        "failure_month": failure_month,
        "months_simulated": 360,
        "execution_time_seconds": 0.01,
    }, sort_keys=True, separators=(",", ":"))


def _make_cohort_date(index: int) -> date:
    base_year = 2000
    total_months = base_year * 12 + index
    year = (total_months - 1) // 12
    month = ((total_months - 1) % 12) + 1
    return date(year, month, 1)


def _seed_p11_database(
    conn: sqlite3.Connection,
    cohorts: list[date],
    equity_allocations: list[float],
    withdrawal_rates: list[float],
    horizon_years: list[int],
    result_id: str | None = None,
    experiment_name: str = "p11-test",
) -> str:
    """Seed a database with P11-style data. Returns the result_id."""
    if result_id is None:
        result_id = _uuid()

    experiment_id = _uuid()
    plan_id = _uuid()

    conn.execute(
        "INSERT INTO experiments (experiment_id, name, revision, description, "
        "dataset_identifier, horizon_months, initial_wealth, "
        "initial_wealth_currency, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (experiment_id, experiment_name, "v1", "P11 test",
         "test", 721, "1000000", "EUR", _now_iso(), _now_iso()),
    )

    cohort_ids: list[str] = []
    for d in cohorts:
        cid = _uuid()
        cohort_ids.append(cid)
        conn.execute(
            "INSERT INTO cohorts (cohort_id, experiment_id, start_date, "
            "cohort_ref, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, experiment_id, d.isoformat(), d.isoformat(), _now_iso()),
        )

    param_config_map: dict[tuple[float, float, int], str] = {}
    for eq in equity_allocations:
        for wr in withdrawal_rates:
            for hy in horizon_years:
                params = {
                    "equity_allocation": eq,
                    "withdrawal_rate": wr,
                    "horizon_years": hy,
                }
                pj = _to_canonical_json(params)
                ph = _hash(pj)
                existing = conn.execute(
                    "SELECT param_config_id FROM parameter_configurations "
                    "WHERE params_hash = ?",
                    (ph,),
                ).fetchone()
                if existing:
                    pcid = existing[0]
                else:
                    pcid = _uuid()
                    conn.execute(
                        "INSERT INTO parameter_configurations "
                        "(param_config_id, params_json, params_hash, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (pcid, pj, ph, _now_iso()),
                    )
                param_config_map[(eq, wr, hy)] = pcid

    alloc_pid = _uuid()
    withdraw_pid = _uuid()
    existing_alloc = conn.execute(
        "SELECT policy_id FROM policies "
        "WHERE policy_type = 'allocation' AND params_hash = ?",
        (_hash("{}"),),
    ).fetchone()
    if existing_alloc:
        alloc_pid = existing_alloc[0]
    else:
        conn.execute(
            "INSERT INTO policies "
            "(policy_id, policy_type, params_json, params_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (alloc_pid, "allocation", "{}", _hash("{}"), _now_iso()),
        )
    existing_withdraw = conn.execute(
        "SELECT policy_id FROM policies "
        "WHERE policy_type = 'withdrawal' AND params_hash = ?",
        (_hash("{}"),),
    ).fetchone()
    if existing_withdraw:
        withdraw_pid = existing_withdraw[0]
    else:
        conn.execute(
            "INSERT INTO policies "
            "(policy_id, policy_type, params_json, params_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (withdraw_pid, "withdrawal", "{}", _hash("{}"), _now_iso()),
        )

    unit_count = (
        len(cohorts) * len(equity_allocations)
        * len(withdrawal_rates) * len(horizon_years)
    )
    conn.execute(
        "INSERT INTO research_plans "
        "(plan_id, experiment_id, created_at, unit_count, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (plan_id, experiment_id, _now_iso(), unit_count, "completed"),
    )

    unit_index = 0
    for ci, cid in enumerate(cohort_ids):
        for eq in equity_allocations:
            for wr in withdrawal_rates:
                for hy in horizon_years:
                    pcid = param_config_map[(eq, wr, hy)]
                    uid = _uuid()
                    conn.execute(
                        "INSERT INTO planned_units "
                        "(unit_id, plan_id, unit_index, cohort_id, "
                        "param_config_id, allocation_policy_id, "
                        "withdrawal_policy_id, initial_portfolio_json, "
                        "final_value_target) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (uid, plan_id, unit_index, cid, pcid,
                         alloc_pid, withdraw_pid, "{}", None),
                    )

                    success = (hash(f"{ci}-{eq}-{wr}-{hy}") % 100) < 70
                    fm = (
                        None if success
                        else (hash(f"fm-{ci}-{eq}-{wr}-{hy}") % 360) + 1
                    )
                    fw = str(500000 + hash(f"w-{ci}-{eq}-{wr}-{hy}") % 1000000)
                    stats_json = _make_stats_json(success, fw, fm)

                    conn.execute(
                        "INSERT INTO simulation_results "
                        "(execution_result_id, unit_index, month_index, "
                        "monthly_payload_json, statistics_payload_json, "
                        "final_month) VALUES (?, ?, ?, ?, ?, ?)",
                        (result_id, unit_index, 0,
                         '{"dummy":true}', stats_json, 1),
                    )
                    unit_index += 1

    conn.execute(
        "INSERT INTO execution_results "
        "(result_id, plan_id, executed_at, duration_seconds, "
        "success_count, failure_count, total_units) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (result_id, plan_id, _now_iso(), 1.0, 0, 0, unit_index),
    )

    conn.commit()
    return result_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    db_file = tmp_path / "test_p11.db"
    return SQLiteRepository(str(db_file))


@pytest.fixture
def seeded_result(
    repo: SQLiteRepository,
) -> tuple[str, dict[str, Any]]:
    """Seed a database with 2 cohorts, 2 equities, 2 rates, 2 horizons."""
    cohorts = [_make_cohort_date(0), _make_cohort_date(1)]
    equities = [0.0, 0.5]
    rates = [0.03, 0.04]
    horizons = [30, 40]

    with sqlite3.connect(repo.db_path) as conn:
        result_id = _seed_p11_database(
            conn, cohorts, equities, rates, horizons,
        )

    return result_id, {
        "cohorts": [d.isoformat() for d in cohorts],
        "equities": equities,
        "rates": rates,
        "horizons": horizons,
    }


# ---------------------------------------------------------------------------
# TestAvailableParameters
# ---------------------------------------------------------------------------


class TestAvailableParameters:
    def test_returns_unique_selectors(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        params = repo.get_available_parameters(result_id)
        assert params is not None
        assert len(params) == 4
        for p in params:
            assert "equity_allocation" in p
            assert "withdrawal_rate" in p
            assert "horizon_years" not in p

    def test_returns_none_for_missing_result(
        self, repo: SQLiteRepository,
    ) -> None:
        assert repo.get_available_parameters("nonexistent-id") is None

    def test_correct_parameter_values(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        params = repo.get_available_parameters(result_id)
        assert params is not None
        values = {
            (p["equity_allocation"], p["withdrawal_rate"])
            for p in params
        }
        assert values == {
            (0.0, 0.03), (0.0, 0.04), (0.5, 0.03), (0.5, 0.04),
        }

    def test_ordering(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        params = repo.get_available_parameters(result_id)
        assert params is not None
        equities = [p["equity_allocation"] for p in params]
        assert equities == sorted(equities)
        for eq in set(equities):
            rates = [
                p["withdrawal_rate"]
                for p in params
                if p["equity_allocation"] == eq
            ]
            assert rates == sorted(rates)

    def test_multiple_horizons_produce_one_entry(
        self, repo: SQLiteRepository,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30, 40, 50, 60]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        params = repo.get_available_parameters(result_id)
        assert params is not None
        assert len(params) == 1
        assert params[0] == {
            "equity_allocation": 0.5,
            "withdrawal_rate": 0.04,
        }

    def test_deterministic_output(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        params1 = repo.get_available_parameters(result_id)
        params2 = repo.get_available_parameters(result_id)
        assert params1 == params2

    def test_empty_database(self, repo: SQLiteRepository) -> None:
        assert repo.get_available_parameters("any-id") is None


# ---------------------------------------------------------------------------
# TestCohortHorizonGrid
# ---------------------------------------------------------------------------


class TestCohortHorizonGrid:
    def test_single_cohort_single_horizon_success(
        self, repo: SQLiteRepository,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert grid["result_id"] == result_id
        assert len(grid["cohorts"]) == 1
        assert grid["horizons"] == [30]
        assert grid["total_units"] == 1
        assert len(grid["grid"]["success"]) == 1
        assert len(grid["grid"]["success"][0]) == 1

    def test_single_cohort_single_horizon_failure(
        self, repo: SQLiteRepository,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )
            fail_stats = _make_stats_json(False, "100000.00", 12)
            conn.execute(
                "UPDATE simulation_results SET statistics_payload_json = ? "
                "WHERE execution_result_id = ?",
                (fail_stats, result_id),
            )
            conn.commit()

        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert grid["success_count"] == 0
        assert grid["failure_count"] == 1
        assert grid["grid"]["success"][0][0] is False

    def test_multiple_cohorts_multiple_horizons(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert len(grid["cohorts"]) == 2
        assert grid["horizons"] == [30, 40]
        assert grid["total_units"] == 4
        assert len(grid["grid"]["success"]) == 2
        for row in grid["grid"]["success"]:
            assert len(row) == 2

    def test_filter_by_equity_and_withdrawal(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, meta = seeded_result
        grid = repo.get_cohort_horizon_grid(result_id, 0.0, 0.03)
        assert grid is not None
        assert grid["parameters"] == {
            "equity_allocation": 0.0,
            "withdrawal_rate": 0.03,
        }
        assert grid["total_units"] == 4

    def test_returns_none_for_missing_result(
        self, repo: SQLiteRepository,
    ) -> None:
        assert repo.get_cohort_horizon_grid(
            "nonexistent-id", 0.5, 0.04,
        ) is None

    def test_returns_none_for_non_matching_params(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        assert repo.get_cohort_horizon_grid(
            result_id, 0.99, 0.99,
        ) is None

    def test_ordering_chronological_horizons_ascending(
        self, repo: SQLiteRepository,
    ) -> None:
        cohorts = [
            _make_cohort_date(2),
            _make_cohort_date(0),
            _make_cohort_date(1),
        ]
        equities = [0.5]
        rates = [0.04]
        horizons = [40, 30]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert grid["cohorts"] == sorted(grid["cohorts"])
        assert grid["horizons"] == [30, 40]

    def test_no_duplicate_cells(self, repo: SQLiteRepository) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30, 40]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert grid["total_units"] == 2

    def test_no_missing_cells(self, repo: SQLiteRepository) -> None:
        cohorts = [_make_cohort_date(0), _make_cohort_date(1)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30, 40, 50]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert grid["total_units"] == 6
        assert len(grid["grid"]["success"]) == 2
        for row in grid["grid"]["success"]:
            assert len(row) == 3

    def test_deterministic_output(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        grid1 = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        grid2 = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid1 == grid2

    def test_grid_structure(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert "result_id" in grid
        assert "cohorts" in grid
        assert "horizons" in grid
        assert "parameters" in grid
        assert "grid" in grid
        assert "total_units" in grid
        assert "success_count" in grid
        assert "failure_count" in grid
        assert "success" in grid["grid"]
        assert "failure_month" in grid["grid"]
        assert "terminal_wealth" in grid["grid"]

    def test_success_count_plus_failure_count_equals_total(
        self,
        repo: SQLiteRepository,
        seeded_result: tuple[str, dict[str, Any]],
    ) -> None:
        result_id, _ = seeded_result
        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert (
            grid["success_count"] + grid["failure_count"]
            == grid["total_units"]
        )

    def test_all_horizons_included(
        self, repo: SQLiteRepository,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30, 40, 50, 60]

        with sqlite3.connect(repo.db_path) as conn:
            result_id = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
            )

        grid = repo.get_cohort_horizon_grid(result_id, 0.5, 0.04)
        assert grid is not None
        assert grid["horizons"] == [30, 40, 50, 60]
        assert grid["total_units"] == 4

    def test_result_from_different_plan_does_not_leak(
        self, repo: SQLiteRepository,
    ) -> None:
        cohorts = [_make_cohort_date(0)]
        equities = [0.5]
        rates = [0.04]
        horizons = [30]

        with sqlite3.connect(repo.db_path) as conn:
            result_id1 = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
                experiment_name="p11-test-1",
            )
            result_id2 = _seed_p11_database(
                conn, cohorts, equities, rates, horizons,
                experiment_name="p11-test-2",
            )

        grid1 = repo.get_cohort_horizon_grid(result_id1, 0.5, 0.04)
        grid2 = repo.get_cohort_horizon_grid(result_id2, 0.5, 0.04)
        assert grid1 is not None
        assert grid2 is not None
        assert grid1["result_id"] == result_id1
        assert grid2["result_id"] == result_id2
        assert grid1["total_units"] == 1
        assert grid2["total_units"] == 1
