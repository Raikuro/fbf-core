# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

---

## S2 Part 20: 0.111 pp/month Glidepath Endpoint Timing

**Classification:** intentional semantic consequence (not a defect)

The Part 20 glidepaths with 0.111 pp/month slope (30→70% and 20→60%)
reach their target equity at month 361, not month 360.

### Explanation

The slope is interpreted as 0.111 percentage points per month, applied as a
fraction: `slope_fraction = 0.111 / 100 = 0.00111`. The equity weight at
month `t` is:

```
equity(t) = min(start + slope_fraction * t, end_equity)
```

For 30→70% (40pp spread):
- Month 360: `30 + 0.111 * 360 = 69.960%` (not yet 70%)
- Month 361: `30 + 0.111 * 361 = 70.071%` → capped to 70%

For 20→60% (40pp spread):
- Month 360: `20 + 0.111 * 360 = 59.960%` (not yet 60%)
- Month 361: `20 + 0.111 * 361 = 60.071%` → capped to 60%

### Why this is correct

The 0.111 pp/month value is a rounded representation of the Kitces/Pfau
glidepath slope. The ceiling of 40/0.111 = 360.36 is 361 months. This is an
intentional consequence of the slope granularity, not an implementation defect.

The 361-month endpoint should be preserved as-is. Do not round the slope or
adjust the implementation to force the endpoint at month 360.

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

**Classification:** architectural/documentation follow-up — RESOLVED in L.1

The generic builder (`_build_unified_parameter_configs`) creates Cartesian
products of independent parameter axes. Part 19 requires constrained
`(start, end, slope)` combinations where slopes are associated with specific
start/end pairs.

**Resolution:** L.1 introduced the `allocation_policy.configurations` list in
the YAML schema, enabling explicit parameter tuples that are crossed only
with the remaining study axes (withdrawal_rate, horizon_years). This
eliminates the need for Cartesian products of glidepath parameters.

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
