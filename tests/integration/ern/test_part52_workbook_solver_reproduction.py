"""Deterministic reproduction of the Part 52 workbook Solver optimum.

The workbook ``Timing-Leverage-Calc.xlsx`` stores its Solver configuration as
hidden defined names on the ``Calc`` sheet.  The recovered problem is:

* maximize ``Calc!B12`` (monthly consumption), which is equivalent to
  maximizing the withdrawal rate because ``B12 = B5 * B11 / 12``;
* decision variables ``Calc!B11`` (WR) and ``Calc!B21`` (Borrow%);
* meaningful constraints ``S32 >= 1000``, ``S33 >= 250000``,
  ``B29 <= 0.5``, and ``B21 <= 1``.

Cohort boundary
----------------
The workbook's ``OFFSET('Return Data'!A$3, O3 + t, 0)`` uses the header row as
its base.  With ``O3 = 1138`` this maps ``Calc`` row 40 to ``Return Data`` row
1141, which is **1965-10**, not 1965-11.  The workbook therefore solved a
cohort with 360 withdrawal months from 1965-10 through 1995-09 plus a terminal
valuation at 1995-10.

The canonical published/tested Part 52 anchor starts at **1965-11** and its
tests live in ``test_part52_replication.py``.  That anchor is intentionally
kept unchanged.  The one-month difference is a real property of the workbook's
OFFSET references, not an indexing correction: do not shift either convention
to make the two cases agree.

Search domain
-------------
The workbook configured no explicit WR bound.  This reproduction uses
``WR in [0, 0.06]`` and ``Borrow% in [0, 1]``:

* ``Borrow% = 1`` is the workbook's explicit ``B21 <= 1`` Solver constraint and
  ``Borrow% = 0`` is the economic no-borrow boundary.
* ``WR = 0`` is the economic lower bound.  ``WR = 0.06`` is an implementation
  choice, not a Solver-configured bound: a coarse feasibility scan over the
  full Borrow% domain finds no feasible point above ``0.0463``, so ``0.06``
  comfortably contains the feasible region.

The search is a nested bisection.  For a fixed Borrow%, it finds the largest WR
satisfying terminal net worth and minimum net worth.  It then bisects Borrow%
for the point where the maximum LTV constraint becomes binding.  The result is
a feasible point just inside the LTV boundary.  This reproduces the recorded
optimum; it does not replay GRG's iteration path or prove global optimality of
the original Solver run.  A coarse dominance scan provides evidence, not proof.

The fixture is an exact cached-value extraction of the workbook's ``Return
Data`` series (CPI, SPX total return, 10-year bond, FFR) for the effective
cohort.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from fbf.core.domain.model.asset import AssetClass
from fbf.core.domain.model.dataset import Dataset
from fbf.core.domain.model.market_snapshot import MarketSnapshot
from fbf.core.domain.model.money import Currency, Money
from fbf.core.domain.model.portfolio import AssetHolding, Portfolio
from fbf.core.domain.policies.concrete import ConstantAllocationPolicy
from fbf.core.domain.policies.part52_withdrawal import Part52WithdrawalPolicy
from fbf.core.execution.pipeline.simulation import ExperimentDefinition
from fbf.core.execution.pipeline.simulation_context import SimulationContext
from fbf.core.execution.strategies.part52_numba_executor import (
    Part52FeasibilityMetrics,
    Part52NumbaExecutor,
    evaluate_part52_feasibility,
)

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "ern"
    / "part52_solver_workbook_1965_10.csv"
)
_PROVENANCE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "ern"
    / "part52_solver_workbook_1965_10.provenance.json"
)
_SOURCE_WORKBOOK_SHA256 = (
    "e0a0dbea11543809b2f2e8544cc84e21a19e0ca864d8ef3664135b945bbcda38"
)
_EXPECTED_SOURCE_COLUMNS = {
    "date": "A (year) and B (month)",
    "cpi": "C",
    "spx_tr": "E",
    "bond_10y": "F",
    "ffr": "K",
}

_EQUITY = AssetClass(id="equity", name="", description="")
_BOND = AssetClass(id="bond", name="", description="")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_HUNDRED = Decimal("100")

INITIAL_WEALTH = Decimal("1000000")
EQUITY_WEIGHT = Decimal("0.75")
BOND_WEIGHT = Decimal("0.25")
EXPENSE_RATIO = Decimal("0.0005")
FFR_SPREAD = Decimal("0.005")
DRAWDOWN_THRESHOLD = Decimal("0.20")
MIN_NW_TARGET = Decimal("1000")
TERMINAL_NW_TARGET = Decimal("250000")
LTV_LIMIT = Decimal("0.50")
HORIZON_MONTHS = 361
START_DATE = date(1965, 10, 1)
END_DATE = date(1995, 10, 1)

RECORDED_WR = Decimal("0.039083138465484564")
RECORDED_BORROW_PCT = Decimal("0.41077504950778576")
RECORDED_MONTHLY_CONSUMPTION = Decimal("3256.9282054570467")

REFERENCE_FINAL_PORTFOLIO_VALUE = Decimal("380446.8471104856")
REFERENCE_FINAL_LOAN_BALANCE = Decimal("130447.0714066872")
REFERENCE_FINAL_NET_WORTH = Decimal("249999.7757037983")
REFERENCE_MIN_NET_WORTH = Decimal("170343.9887653289")
REFERENCE_MAX_LTV = Decimal("0.5000002015300957")
REFERENCE_DRAW_MONTHS = 125
REFERENCE_REPAYMENT_MONTHS = 47

WR_SEARCH_UPPER = Decimal("0.06")
BORROW_SEARCH_LOWER = Decimal("0")
BORROW_SEARCH_UPPER = Decimal("1")
BISECTION_ITERATIONS = 60

WR_TOLERANCE = Decimal("1e-6")
BORROW_TOLERANCE = Decimal("1e-6")
CASH_TOLERANCE = Decimal("1e-6")
LTV_TOLERANCE = Decimal("1e-9")
DOMINANCE_TOLERANCE = Decimal("1e-9")
SOLVER_PRECISION = Decimal("1e-6")


@dataclass(frozen=True)
class _WorkbookCohort:
    dataset: Dataset
    initial_portfolio: Portfolio
    interest_rate_schedule: tuple[Decimal, ...]


def _read_fixture() -> tuple[dict[str, str], ...]:
    with _FIXTURE.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        expected = ["date", "cpi", "spx_tr", "bond_10y", "ffr"]
        assert header == expected, f"Unexpected fixture header: {header}"
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            rows.append(dict(zip(header, raw_row, strict=True)))
    return tuple(rows)


@lru_cache(maxsize=1)
def _load_workbook_cohort() -> _WorkbookCohort:
    rows = _read_fixture()
    assert len(rows) == HORIZON_MONTHS, (
        f"Workbook Solver fixture must contain {HORIZON_MONTHS} rows, "
        f"got {len(rows)}"
    )

    cpi = tuple(Decimal(row["cpi"]) for row in rows)
    spx_tr = tuple(Decimal(row["spx_tr"]) for row in rows)
    bond_10y = tuple(Decimal(row["bond_10y"]) for row in rows)
    ffr = tuple(Decimal(row["ffr"]) for row in rows)

    # Normalize the real total-return levels to 100 at the cohort start.  The
    # kernel consumes only price ratios, so this leaves returns and drawdowns
    # unchanged while making the initial portfolio value exactly $1,000,000.
    base_equity = spx_tr[0] / cpi[0]
    base_bond = bond_10y[0] / cpi[0]

    snapshots: list[MarketSnapshot] = []
    running_ath = _ZERO
    for index, row in enumerate(rows):
        equity_level = spx_tr[index] / cpi[index] / base_equity * _HUNDRED
        bond_level = bond_10y[index] / cpi[index] / base_bond * _HUNDRED

        if index == 0:
            inflation = _ZERO
            running_ath = equity_level
            is_ath = False
            is_underwater = True
        else:
            inflation = cpi[index] / cpi[index - 1] - _ONE
            running_ath = max(running_ath, equity_level)
            is_ath = equity_level >= running_ath
            is_underwater = equity_level < running_ath

        snapshots.append(
            MarketSnapshot(
                date=date.fromisoformat(row["date"]),
                index_levels={_EQUITY: equity_level, _BOND: bond_level},
                inflation=inflation,
                inflation_cumulative=cpi[index],
                is_ath=is_ath,
                is_underwater=is_underwater,
                running_ath=running_ath,
            )
        )

    dataset = Dataset(snapshots=tuple(snapshots), frequency="monthly")
    initial_portfolio = Portfolio(
        holdings=(
            AssetHolding(
                asset_class=_EQUITY,
                units=INITIAL_WEALTH * EQUITY_WEIGHT / _HUNDRED,
            ),
            AssetHolding(
                asset_class=_BOND,
                units=INITIAL_WEALTH * BOND_WEIGHT / _HUNDRED,
            ),
        )
    )
    # The workbook uses FFR from month T-1: M_t = (1 + I_{t-1}/12 + spread/12)
    # * CPI_{t-1}/CPI_t - 1.  Index 0 is a filler and is never consumed because
    # the loan balance is zero at initialization.
    interest_rate_schedule = tuple(
        (ffr[index - 1] if index > 0 else ffr[0]) + FFR_SPREAD
        for index in range(len(rows))
    )
    return _WorkbookCohort(
        dataset=dataset,
        initial_portfolio=initial_portfolio,
        interest_rate_schedule=interest_rate_schedule,
    )


def _context(withdrawal_rate: Decimal, borrow_pct: Decimal) -> SimulationContext:
    cohort = _load_workbook_cohort()
    return SimulationContext(
        experiment_name="part52-workbook-solver-reproduction",
        cohort="1965-10",
        start_date=START_DATE,
        horizon_months=HORIZON_MONTHS,
        initial_wealth=Money(INITIAL_WEALTH, Currency.EUR),
        initial_portfolio=cohort.initial_portfolio,
        dataset=cohort.dataset,
        allocation_policy=ConstantAllocationPolicy(equity_allocation=EQUITY_WEIGHT),
        withdrawal_policy=Part52WithdrawalPolicy(
            withdrawal_rate,
            borrow_pct,
            DRAWDOWN_THRESHOLD,
        ),
        interest_rate_schedule=cohort.interest_rate_schedule,
        ltv_limit=LTV_LIMIT,
        ltv_enforcement=False,
        expense_ratio=EXPENSE_RATIO,
    )


def _metrics(
    withdrawal_rate: Decimal,
    borrow_pct: Decimal,
) -> Part52FeasibilityMetrics:
    return evaluate_part52_feasibility(_context(withdrawal_rate, borrow_pct))


def _growth_feasible(metrics: Part52FeasibilityMetrics) -> bool:
    return (
        metrics.min_net_worth >= MIN_NW_TARGET
        and metrics.final_net_worth >= TERMINAL_NW_TARGET
    )


def _max_feasible_wr(borrow_pct: Decimal) -> Decimal:
    lower = _ZERO
    upper = WR_SEARCH_UPPER
    for _ in range(BISECTION_ITERATIONS):
        midpoint = (lower + upper) / _TWO
        if _growth_feasible(_metrics(midpoint, borrow_pct)):
            lower = midpoint
        else:
            upper = midpoint
    return lower


@lru_cache(maxsize=1)
def _solve_workbook_optimum() -> tuple[Decimal, Decimal, Part52FeasibilityMetrics]:
    lower = BORROW_SEARCH_LOWER
    upper = BORROW_SEARCH_UPPER
    for _ in range(BISECTION_ITERATIONS):
        midpoint = (lower + upper) / _TWO
        wr = _max_feasible_wr(midpoint)
        if _metrics(wr, midpoint).max_loan_to_portfolio < LTV_LIMIT:
            lower = midpoint
        else:
            upper = midpoint

    borrow_pct = lower
    withdrawal_rate = _max_feasible_wr(borrow_pct)
    return (
        withdrawal_rate,
        borrow_pct,
        _metrics(withdrawal_rate, borrow_pct),
    )


def _trajectory_metrics(
    withdrawal_rate: Decimal,
    borrow_pct: Decimal,
) -> tuple[int, int, Decimal, Decimal]:
    definition = ExperimentDefinition(
        name="part52-workbook-solver-trajectory",
        description="Part 52 workbook Solver trajectory",
        simulation_contexts=(_context(withdrawal_rate, borrow_pct),),
    )
    result = Part52NumbaExecutor(materialize_timeline=True).execute(definition)
    months = result.simulation_results[0].timeline.monthly_results

    draw_months = 0
    repayment_months = 0
    max_ltv = _ZERO
    for month in months:
        decision = month.withdrawal_decision
        if decision is not None:
            if decision.loan_draw_amount > _ZERO:
                draw_months += 1
            if decision.is_repayment:
                repayment_months += 1
        debt = month.debt_snapshot
        if debt is not None and debt.ltv > max_ltv:
            max_ltv = debt.ltv

    last_debt = months[-1].debt_snapshot
    assert last_debt is not None
    return draw_months, repayment_months, last_debt.net_worth, max_ltv


def _assert_decimal_close(
    actual: Decimal,
    expected: Decimal,
    tolerance: Decimal,
) -> None:
    assert abs(actual - expected) <= tolerance, (
        f"{actual} != {expected} (tolerance {tolerance})"
    )


def test_fixture_matches_workbook_effective_cohort() -> None:
    cohort = _load_workbook_cohort()
    assert cohort.dataset.start_date == START_DATE
    assert cohort.dataset.end_date == END_DATE
    assert len(cohort.dataset) == HORIZON_MONTHS


def test_fixture_matches_provenance_metadata() -> None:
    fixture_bytes = _FIXTURE.read_bytes()
    provenance = json.loads(_PROVENANCE.read_text(encoding="utf-8"))
    rows = _read_fixture()

    assert hashlib.sha256(fixture_bytes).hexdigest() == provenance["artifact_sha256"]
    assert provenance["schema_version"] == "1.0"
    assert provenance["source_file"] == "Timing-Leverage-Calc.xlsx"
    assert provenance["source_sha256"] == _SOURCE_WORKBOOK_SHA256
    assert provenance["source_sheet"] == "Return Data"
    assert provenance["source_rows"] == "1141:1501"
    assert provenance["source_columns"] == _EXPECTED_SOURCE_COLUMNS
    assert provenance["date_range"] == f"{rows[0]['date']} to {rows[-1]['date']}"
    assert provenance["observation_count"] == len(rows) == HORIZON_MONTHS
    assert list(rows[0]) == list(provenance["source_columns"])

    start_row, end_row = (
        int(value) for value in provenance["source_rows"].split(":")
    )
    assert end_row - start_row + 1 == provenance["observation_count"]

    cohort_note = provenance["cohort_note"]
    assert "Calc row 40 maps to Return Data row 1141 (1965-10)" in cohort_note
    assert "360 withdrawal months plus a terminal valuation month" in cohort_note
    assert "1965-11" in cohort_note


def test_recorded_point_constraint_violations_are_within_solver_precision() -> None:
    metrics = _metrics(RECORDED_WR, RECORDED_BORROW_PCT)

    assert metrics.gross_survival is True
    assert metrics.min_net_worth >= MIN_NW_TARGET
    assert metrics.final_net_worth < TERMINAL_NW_TARGET
    assert (
        TERMINAL_NW_TARGET - metrics.final_net_worth
        <= TERMINAL_NW_TARGET * SOLVER_PRECISION
    )
    assert metrics.max_loan_to_portfolio > LTV_LIMIT
    assert metrics.max_loan_to_portfolio - LTV_LIMIT <= SOLVER_PRECISION


def test_recorded_point_matches_independent_workbook_trajectory() -> None:
    metrics = _metrics(RECORDED_WR, RECORDED_BORROW_PCT)

    _assert_decimal_close(
        metrics.final_portfolio_value,
        REFERENCE_FINAL_PORTFOLIO_VALUE,
        CASH_TOLERANCE,
    )
    _assert_decimal_close(
        metrics.final_loan_balance,
        REFERENCE_FINAL_LOAN_BALANCE,
        CASH_TOLERANCE,
    )
    _assert_decimal_close(
        metrics.final_net_worth,
        REFERENCE_FINAL_NET_WORTH,
        CASH_TOLERANCE,
    )
    _assert_decimal_close(
        metrics.min_net_worth,
        REFERENCE_MIN_NET_WORTH,
        CASH_TOLERANCE,
    )
    _assert_decimal_close(
        metrics.max_loan_to_portfolio,
        REFERENCE_MAX_LTV,
        LTV_TOLERANCE,
    )
    _assert_decimal_close(
        INITIAL_WEALTH * RECORDED_WR / Decimal("12"),
        RECORDED_MONTHLY_CONSUMPTION,
        CASH_TOLERANCE,
    )


def test_reproduced_optimum_matches_recorded_values() -> None:
    withdrawal_rate, borrow_pct, _ = _solve_workbook_optimum()

    assert abs(withdrawal_rate - RECORDED_WR) <= WR_TOLERANCE
    assert abs(borrow_pct - RECORDED_BORROW_PCT) <= BORROW_TOLERANCE


def test_reproduced_optimum_satisfies_constraints() -> None:
    _, _, metrics = _solve_workbook_optimum()

    assert metrics.gross_survival is True
    assert metrics.min_net_worth >= MIN_NW_TARGET
    assert metrics.final_net_worth >= TERMINAL_NW_TARGET - CASH_TOLERANCE
    assert metrics.max_loan_to_portfolio <= LTV_LIMIT + LTV_TOLERANCE
    assert metrics.feasible is True
    assert metrics.withdrawal_months == HORIZON_MONTHS - 1


def test_reproduced_trajectory_loan_activity_matches_workbook() -> None:
    withdrawal_rate, borrow_pct, _ = _solve_workbook_optimum()
    draw_months, repayment_months, final_net_worth, max_ltv = _trajectory_metrics(
        withdrawal_rate,
        borrow_pct,
    )

    assert draw_months == REFERENCE_DRAW_MONTHS
    assert repayment_months == REFERENCE_REPAYMENT_MONTHS
    _assert_decimal_close(final_net_worth, TERMINAL_NW_TARGET, CASH_TOLERANCE)
    assert max_ltv <= LTV_LIMIT + LTV_TOLERANCE


def test_recorded_trajectory_matches_cached_reference() -> None:
    draw_months, repayment_months, final_net_worth, max_ltv = _trajectory_metrics(
        RECORDED_WR,
        RECORDED_BORROW_PCT,
    )

    assert draw_months == REFERENCE_DRAW_MONTHS
    assert repayment_months == REFERENCE_REPAYMENT_MONTHS
    _assert_decimal_close(final_net_worth, REFERENCE_FINAL_NET_WORTH, CASH_TOLERANCE)
    _assert_decimal_close(max_ltv, REFERENCE_MAX_LTV, LTV_TOLERANCE)


def test_feasibility_transition_around_reproduced_optimum() -> None:
    withdrawal_rate, borrow_pct, _ = _solve_workbook_optimum()

    assert _metrics(withdrawal_rate - Decimal("1e-5"), borrow_pct).feasible is True
    assert _metrics(withdrawal_rate + Decimal("1e-5"), borrow_pct).feasible is False


def test_ltv_boundary_transition_around_reproduced_optimum() -> None:
    _, borrow_pct, _ = _solve_workbook_optimum()
    step = Decimal("0.001")

    below = _metrics(_max_feasible_wr(borrow_pct - step), borrow_pct - step)
    above = _metrics(_max_feasible_wr(borrow_pct + step), borrow_pct + step)

    assert below.max_loan_to_portfolio < LTV_LIMIT
    assert above.max_loan_to_portfolio > LTV_LIMIT


def test_boundary_cases() -> None:
    assert _metrics(_ZERO, _ZERO).feasible is True
    assert _metrics(WR_SEARCH_UPPER, _ZERO).feasible is False
    assert _metrics(WR_SEARCH_UPPER, BORROW_SEARCH_UPPER).feasible is False


def test_search_upper_bound_excludes_feasible_points() -> None:
    for borrow_pct in (
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.50"),
        Decimal("0.75"),
        Decimal("1"),
    ):
        for withdrawal_rate in (
            Decimal("0.05"),
            Decimal("0.055"),
            WR_SEARCH_UPPER,
        ):
            assert _metrics(withdrawal_rate, borrow_pct).feasible is False


def test_max_feasible_wr_is_monotone_in_borrow_pct() -> None:
    samples = (
        Decimal("0"),
        Decimal("0.2"),
        Decimal("0.4"),
        Decimal("0.6"),
        Decimal("0.8"),
        Decimal("1"),
    )
    values = [_max_feasible_wr(borrow_pct) for borrow_pct in samples]
    for index in range(1, len(values)):
        assert values[index] >= values[index - 1] - DOMINANCE_TOLERANCE


def test_solution_is_not_dominated_on_coarse_grid() -> None:
    withdrawal_rate, _, _ = _solve_workbook_optimum()
    best_wr = withdrawal_rate

    for borrow_index in range(21):
        borrow_pct = BORROW_SEARCH_UPPER * Decimal(borrow_index) / Decimal("20")
        for wr_index in range(25):
            candidate_wr = WR_SEARCH_UPPER * Decimal(wr_index) / Decimal("24")
            metrics = _metrics(candidate_wr, borrow_pct)
            if metrics.feasible and candidate_wr > best_wr:
                best_wr = candidate_wr

    assert best_wr <= withdrawal_rate + DOMINANCE_TOLERANCE
