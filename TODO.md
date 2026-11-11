# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
are removed. See `AGENTS.md` for the documentation policy. Current methodology,
acceptance anchors, and project conclusions are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

---

## Canonical Data Regeneration and Revalidation

**Classification:** final validation task; deferred until explicitly authorized

Several canonical comparisons still use provisional anchors or research
datasets whose vintage relative to the authorized workbooks has not been
re-established. Existing numerical evidence is valid only for the data actually
used, not as a final canonical-data conclusion.

Required sequence:

1. Re-extract required source data from the authorized workbooks.
2. Regenerate affected datasets and derived research artifacts.
3. Re-run affected Part 3, 19/20, and 49 comparisons.
4. Reassess the Part 20 A/B/C conclusions using regenerated data.
5. Update structural populations and published-anchor comparisons, classifying
   every difference. Do not silently re-baseline anchors.

Part 52 Solver reproduction and the euro-area analogue are outside this task.

---

## Part 3 Published-Anchor Mismatch

**Classification:** deferred investigation; published anchors frozen

The Part 3 canonical E2E is NOT PASSING. The complete 438,228-unit execution
completes successfully in bounded batches, but the published anchors do not
match. The mismatch is present with both the committed v1.0 manifest and the
independently rebuilt v2.0 manifest, so it has not been demonstrated to result
from the manifest migration.

| Anchor | Committed v1.0 | Rebuilt v2.0 | Published | v2.0 delta |
|---|---:|---:|---:|---:|
| A/30Y/HIGH | 90.53% | 90.81% | 89% | +1.81pp |
| A/60Y/HIGH | 72.70% | 72.70% | 72% | +0.70pp |
| B/60Y/HIGH | 72.14% | 72.14% | 71% | +1.14pp |
| C/60Y/HIGH | 92.76% | 93.04% | 88% | +5.04pp |
| C/60Y/overall | 98.16% | 98.16% | 96% | +2.16pp |
| D/60Y/overall | 99.31% | 99.31% | 97% | +2.31pp |

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

**Classification:** deferred

Published Part 52 WR/Borrow% values are Solver outputs. Canonical acceptance is
the A2/A3/A10 fixed-parameter feasibility surface; it does not reproduce the
Solver. Do not treat fixed-parameter feasibility as Solver replication.

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
