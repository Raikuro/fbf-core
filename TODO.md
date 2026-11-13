# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
are removed. See `AGENTS.md` for the documentation policy. Current methodology,
acceptance anchors, and project conclusions are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

---

## Part 3 Published-Anchor Mismatch

**Classification:** deferred investigation; published anchors frozen

The Part 3 canonical E2E is NOT PASSING. The complete 292,152-unit execution
completes successfully, but four of six published anchors differ by more than
the one-percentage-point tolerance. The mismatch predates the runtime-manifest
migration and persists with the current canonical dataset and cohort semantics,
so it has not been demonstrated to result from that migration.

| Anchor | Canonical | Published | Delta |
|---|---:|---:|---:|
| A/30Y/HIGH | 89.69% | 89% | +0.69pp |
| A/60Y/HIGH | 72.14% | 72% | +0.14pp |
| B/60Y/HIGH | 72.14% | 71% | +1.14pp |
| C/60Y/HIGH | 93.87% | 88% | +5.87pp |
| C/60Y/overall | 98.33% | 96% | +2.33pp |
| D/60Y/overall | 99.37% | 97% | +2.37pp |

Do not update, re-baseline, weaken, or remove the anchors or assertions. A
future investigation must reproduce the discrepancy and identify its cause
before proposing any implementation or anchor change. Scope:

- Data vintage and source-series semantics.
- CAPE projection inputs and projection boundaries.
- Cohort-window definitions and population membership.
- Part 3 calculation and aggregation methodology.
- The origin and applicability of each published anchor.

---

## Numba Annual Withdrawal Frequency Coverage

**Classification:** unsupported Numba scope; explicitly rejected

The generic fixed-real, constant-nominal, buy-and-hold, fixed-real glidepath,
Part 49, and Part 52 Numba kernels implement monthly withdrawals only. The
policy layer, escalating Numba paths, and the deterministic kernel support
annual frequency, but the monthly-only kernels reject annual contexts.

If a consumer requires annual withdrawals in a monthly-only family, implement
the annual boundary (`period_index % 12 == 0`) in the kernel and add an
independent Decimal recurrence test. Otherwise retain the explicit rejection.
Do not silently map annual to monthly.

---

## Part 52 Solver Reproduction

**Classification:** completed (test-only)

The workbook's recorded Solver optimum is reproduced by
`tests/integration/ern/test_part52_workbook_solver_reproduction.py` using the
exact cached `Return Data` fixture and the production Part 52 evaluator. The
deterministic nested bisection recovers WR and Borrow% within `1e-6` of the
recorded values on the workbook-effective `1965-10` cohort.

Limitations: this reproduces the recorded optimum, not GRG's iteration history
or a global-optimality proof. Canonical acceptance remains the A2/A3/A10
fixed-parameter feasibility surface on the `1965-11` anchor; the one-month
cohort difference is intentional and must not be conflated.

---

## Euro-Area Reference-Rate Analogue

**Classification:** research-only; separate design required

No exact long-history euro-area equivalent of the US FFR exists. A euro study
must choose and document an explicit reference-rate role, use euro-denominated
returns, handle negative policy rates and loan-rate floors, recalibrate lending
spreads, and document splice boundaries. Do not substitute a US series, policy
rate, or government yield for a market overnight rate.

---

## Deferred Scalability Architecture

**Classification:** deferred; not required for current workloads

The largest required Part 49 workload completes within operational limits.
Revisit only when a concrete workload approaches the memory or storage
envelope. Candidate work:

- Batched execution with bounded-memory emit-and-release semantics.
- Normalized research persistence (metadata in SQLite, trajectories in binary
  files).
- Hybrid SQLite plus binary storage.
- Result-model normalization.
- Removal of the six architecturally dead `MonthlyResult` fields:
  `allocation_drift`, `rebalance_result`, `drawdown`, `cumulative_return`,
  `cumulative_inflation`, `events`.
