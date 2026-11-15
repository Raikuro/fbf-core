# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
are removed. See `AGENTS.md` for the documentation policy. Current methodology,
acceptance anchors, and project conclusions are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

---

## Part 3 Published-Anchor Classification

**Classification:** open; canonical 2026 C divergence and exact 2016 methodology
reproduction unresolved

### Canonical 2026 C Divergence

The canonical 2026 Part 3 study executes all 292,152 units. Two of the six
published anchors differ by more than the one-percentage-point tolerance:

| Anchor | Canonical 2026 | Published | Delta | Result |
|---|---:|---:|---:|---|
| A/30Y/CAPE20-30 | 89.66% | 89% | +0.66pp | pass |
| A/60Y/CAPE20-30 | 72.07% | 72% | +0.07pp | pass |
| B/60Y/CAPE20-30 | 71.51% | 71% | +0.51pp | pass |
| C/60Y/CAPE20-30 | 91.62% | 88% | +3.62pp | fail |
| C/60Y/overall | 97.76% | 96% | +1.76pp | fail |
| D/60Y/CAPE20-30 | 97.21% | 97% | +0.21pp | pass |

The published D value is the CAPE 20-30 anchor. The D/60Y overall diagnostic is
99.31% and is not compared with 97%. The canonical E2E asserts deterministic
canonical counts as regression snapshots; it does not assert the historical
2016 anchors. The comparison table above is diagnostic.

The canonical 2026 configuration is not expected to reproduce the 2016 article
anchors without the article-era cutoff and projection assumptions. Determine
whether the canonical 2026 C divergence requires any change beyond that expected
era/configuration difference.

### Exact 2016 Methodology Reproduction

The historical 2016 Part 3 implementation and validation are complete. The
dedicated `part3_2016.yaml` configuration reproduces all six published article
anchors within 1pp. This is not an exact reproduction claim.

Exact reproduction remains unconfirmed. The original GNU Octave research engine
is unavailable. The current v2.0 workbook is a methodological reference, not a
four-regime Part 3 oracle: it exposes binary CAPE groups rather than the Part 3
CAPE 20-30 output, so the six published anchors have no workbook-backed
numerical comparison.

Remaining open questions:

- Confirm the article's exact cohort eligibility rules.
- Verify historical calculation conventions, including fee ordering,
  withdrawal timing, and aggregation.
- Verify the historical CAPE vintage and confirm the origin and applicability
  of each published anchor.
- Establish whether the engine's one-month-later timing convention is the
  article's convention; it currently matches A/60Y and B better but is not
  conclusively established.

Do not update, re-baseline, weaken, or remove the anchors or assertions without
explicit approval.

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
