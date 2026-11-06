# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
are removed. See `AGENTS.md` for the documentation policy. Current methodology,
acceptance anchors, and project conclusions are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

---

## Next Actionable Task: Canonical Data Regeneration and Revalidation

**Classification:** final validation task — deferred until the work below is
otherwise complete.

Several canonical comparisons still use provisional anchors or research
datasets whose vintage relative to the authorized workbooks has not been
re-established. Existing numerical evidence is valid only for the data actually
used, not as a final canonical-data conclusion.

Required sequence, after explicit authorization:

1. Re-extract required source data from the authorized workbooks.
2. Regenerate affected datasets and derived research artifacts.
3. Re-run the relevant Part 3, 19/20, and 49 comparisons.
4. Reassess the Part 20 A/B/C conclusions using regenerated data.
5. Update structural populations and published-anchor comparisons, classifying
   every difference. Do not silently re-baseline anchors.

Part 52 Solver reproduction, the euro-area analogue, and unrelated scalability
work are outside this task. Do not perform any of this until authorized.

---

## Dataset Loader Type Discrimination

**Classification:** architectural debt

The JSON dataset loader identifies auxiliary datasets by checking
`"frequency" in raw`. Any JSON file with that key could be misidentified.

Recommended correction: positive identification through an explicit dataset
type field, schema discriminator, registry, or validation of both `frequency`
and `snapshots`. The current workaround is the FFR file's `data_frequency` key.
Do not let the broader issue disappear.

---

## Numba Annual Withdrawal Frequency Coverage

**Classification:** unsupported Numba scope — explicitly rejected

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

**Classification:** deferred — not required for current canonical workloads

The largest required Part 49 workload completes within operational limits.
None of the following is required until a workload approaches the memory or
storage envelope:

- Batched execution with bounded-memory emit-and-release semantics.
- Normalized research persistence (metadata in SQLite, trajectories in binary
  files).
- Hybrid SQLite plus binary storage.
- Result-model normalization.
- Removal of the six architecturally dead `MonthlyResult` fields:
  `allocation_drift`, `rebalance_result`, `drawdown`, `cumulative_return`,
  `cumulative_inflation`, `events`.

Revisit only with a concrete workload that exceeds the current envelope.

---

## Glidepath Policy Profiling

**Classification:** future optimization candidate

The active glidepath policy performs an O(M) historical scan at each monthly
period. Current measurements do not warrant optimization. Before implementing
anything, establish a reproducible baseline and profile total simulation time,
policy evaluation, withdrawal decisions, rebalancing, market evolution,
aggregation, serialization, and worker overhead.

A prefix-count representation (precomputed running underwater count) is a
hypothesis only. Do not implement it without profiling evidence.
