# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

---

## S1 Follow-Up: ERN Validation Discrepancies

**Classification:** known discrepancy / unresolved investigation

The S1 glidepath implementation produces results that differ from published
ERN Part 19 anchors. The causes have not been attributed.

### 80% static allocation failsafe

* Engine result: **3.00%** (100% success rate across all 1,739 cohorts)
* Published ERN anchor: **3.14%**
* Difference: 0.14%
* The pinned oracle table (`p49_oracle_table.csv`) does not include 80%
  equity; this anchor comes from the published paper only.
* The engine matches the pinned oracle exactly for 75% equity (all 9 rates,
  ±0pp tolerance), confirming correct dataset loading, cohort generation,
  pipeline execution, and aggregation for constant-allocation policies.

### 60→100% glidepath failsafe

* Engine result: **below 3.00%** (no rate achieves 100% success for CAPE > 20
  cohorts at the tested rates)
* Published ERN anchor: **3.47%** (for CAPE > 20 cohorts)
* Difference: ~0.5%
* All four tested configurations (passive/active × slope 0.3/0.4) produce
  similar results, suggesting the discrepancy is not slope-dependent.

### Required future investigation

Diagnose the methodological or data difference without tuning the
implementation merely to reproduce published anchors. Potential areas:

1. Forward extrapolation methodology beyond Sep 2016
2. Fee application timing or compounding
3. CAPE filtering methodology (cohort-level vs period-level)
4. Dataset version or construction differences
5. Rebalancing or withdrawal timing conventions

---

## S1 Follow-Up: Part 19 Configuration Representation

**Classification:** architectural/documentation follow-up

The generic builder (`_build_unified_parameter_configs`) creates Cartesian
products of independent parameter axes. Part 19 requires constrained
`(start, end, slope)` combinations where slopes are associated with specific
start/end pairs.

* Current S1 approach: express valid combinations explicitly in the study
  specification/YAML.
* The `GlidepathAllocationPolicy` itself correctly accepts any
  `(start, end, slope, mode)` tuple.
* The builder's Cartesian product design is a general-purpose approach that
  works when the YAML is structured appropriately.
* Verify this constraint when the Part 19 study configuration YAML is
  finalized.

---

## S1 Follow-Up: Performance Profiling

**Classification:** future optimization candidate

The active glidepath policy performs an O(M) historical scan at each of the
721 monthly periods per cohort. S1 measurement results:

* Total policy calls per config: 11,284,371
* Total historical comparisons (active): 4,073,657,931
* Active execution time: ~126s per config (8 workers)
* Passive execution time: ~100s per config (8 workers)
* Absolute overhead: ~26s (26% of passive)
* Extrapolated full 24-config grid: ~45 min total, ~5 min overhead

### Current decision

**No optimization is warranted now.** The overhead is measurable but does not
fundamentally change the project's performance characteristics.

### Future profiling requirements

Before any optimization, establish a reproducible baseline and profile:

* total simulation time;
* policy evaluation time (including historical scans);
* withdrawal-decision time;
* allocation/rebalancing time;
* market-evolution time;
* statistics/aggregation time;
* serialization/IPC overhead;
* worker/process overhead.

### Potential optimization hypothesis (do not implement without profiling)

If profiling later demonstrates that repeated historical scans are a material
bottleneck, a prefix-count representation (precomputed running count of
underwater periods) could be evaluated. This would trade O(M) per-call work
for O(1) lookup at the cost of O(M) preprocessing and memory. Do not
implement without profiling evidence.
