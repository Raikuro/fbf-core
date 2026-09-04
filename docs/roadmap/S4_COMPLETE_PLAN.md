# S4-COMPLETE — Validation Closure Plan

**Purpose:** Close the remaining S4 acceptance criteria after K.1–K.7 infrastructure completion.

**Status:** PLANNING — not yet authorized for implementation.

---

## 1. S4 Acceptance Criteria (from S4 Design Review)

| # | Criterion | K.7 Status | S4-COMPLETE Action |
|---|-----------|------------|-------------------|
| 1 | Full regression: all existing tests pass | ✓ 1428 pass | Already satisfied |
| 2 | Performance: leverage execution within 2× non-leverage baseline | NOT MEASURED | Benchmark required |
| 3 | Research validation: compare against ERN published values | NOT DONE | Anchor validation required |
| 4 | Multi-cohort execution: 10+ cohorts complete successfully | NOT TESTED | Multi-cohort test required |
| 5 | Research validation documented (methodology differences identified) | NOT DONE | Documentation required |

---

## 2. Validation Targets

### 2A. ERN Part 49 Published Anchors (4 scenarios)

Source: `MULTI_STUDY_REPLICATION_ROADMAP.md` lines 197-202, `S4_ARCHITECTURAL_DESIGN_REVIEW.md` lines 695-698.

| # | Cohort | Allocation | Leverage | Expected Outcome | Anchor Type |
|---|--------|-----------|----------|------------------|-------------|
| A1 | 1929 | 100/0 | Full (100% borrowed) | Depleted after 12 years | Qualitative (depletion timing) |
| A2 | 1929 | 75/25 | Full (100% borrowed) | Near wipeout at month 238: $1.085M loan vs $1.185M portfolio | Numerical (portfolio + loan values) |
| A3 | 1965 | 75/25 | Partial ($30k portfolio + $10k loan, 4% WR) | LTV stayed below 70% at worst point | Qualitative (LTV bound) |
| A4 | 1965 | 75/25 | 50% ($20k portfolio + $20k loan, 4% WR) | LTV reached 84–93% depending on rate — likely margin call | Qualitative (LTV range) |

**Note:** These are case study results from the article, not the full study grid. They are diagnostic anchors, not tuning targets.

### 2B. Validation Classification

| Anchor | Classification | Tolerance |
|--------|---------------|-----------|
| A1: 1929 depletion timing | Qualitative directional | Must deplete within 30y; ~12y is approximate |
| A2: 1929 near-wipeout values | Numerical (chart-derived reference) | Portfolio value match; loan value approximate (chart-read source) |
| A3: 1965 LTV bound | Qualitative directional | LTV must stay below 75% (the limit) |
| A4: 1965 LTV range | Qualitative directional | LTV must reach 84%+; compatible with ERN multi-rate range |

### 2C. What We Cannot Validate

- Full 54-cell grid results (S5 scope)
- Per-cohort success rates across the full grid (S5 scope)
- Exact numerical SWR thresholds (S5 scope)
- Chart reproduction (S10 scope)

---

## 3. Sub-Phases

### S4-C1: Methodology and Dataset Audit

**Purpose:** Verify that FBF's Part 49 configuration matches ERN's methodology before running validation.

**Deliverable:** `docs/roadmap/S4_C1_METHODOLOGY_AUDIT.md`

**Scope:**
- ERN Part 49 methodology parameters vs FBF configuration
- Dataset temporal coverage vs ERN article period
- Interest rate semantics (fixed real vs nominal)
- LTV constraint interpretation
- Leverage split model (3% portfolio + 1% loan = 4% total)
- Fee application methodology
- Forward extrapolation methodology
- Cohort generation methodology

**Key question:** Can FBF reproduce ERN's Part 49 results given the available dataset, or are there known methodology/data differences that prevent exact reproduction?

### S4-C2: Part 49 E2E Oracle Validation

**Purpose:** Create the missing Part 49 E2E validation test.

**Deliverable:** `tests/oracle/ern/test_part49_e2e.py`

**Scope:**
- Execute the 4 anchor scenarios (A1-A4) through the full production path
- Compare against independently derived expectations
- Use the independent debt oracle (`debt_oracle.py`) as the mathematical authority
- Document any methodology differences

**Test structure:**
```python
class TestPart49E2E:
    def test_1929_full_leverage_100_equity_depletes(self) -> None: ...
    def test_1929_full_leverage_75_25_near_wipeout(self) -> None: ...
    def test_1965_partial_leverage_ltv_below_70(self) -> None: ...
    def test_1965_50_percent_leverage_margin_call(self) -> None: ...
```

**Not in scope:** Full grid execution, success rate computation, SWR threshold finding.

### S4-C3: Multi-Cohort Validation

**Purpose:** Validate that the debt pipeline works correctly across 10+ cohorts.

**Deliverable:** `tests/integration/test_part49_multi_cohort.py`

**Scope:**
- Execute 10+ cohorts with debt parameters
- Verify deterministic results
- Verify correct cohort count
- Verify debt state isolation between simulations
- Verify no state leakage
- Verify stable failure classification
- Verify correct result aggregation

**Not in scope:** Full cohort universe (1,739 cohorts), production-scale execution.

### S4-C4: Performance Benchmark

**Purpose:** Measure the cost of the debt-capable pipeline.

**Deliverable:** `tests/benchmarks/test_part49_performance.py`

**Scope:**
Three measurement conditions:
1. **Non-debt baseline:** Pipeline with `interest_rate=0` (debt steps are no-ops)
2. **Debt-capable, inactive:** Pipeline with `interest_rate=0.06` but no loan draws (interest accrues on zero balance)
3. **Active leverage:** Pipeline with `interest_rate=0.06`, `loan_draw_rate=0.01` (full debt mechanics)

**Metrics:**
- Per-cohort execution time
- Per-month execution time
- Memory overhead (if measurable)
- Pipeline step breakdown (which steps are most costly)

**Gate:** Leverage execution within 2× non-leverage baseline (S4 design review requirement).

### S4-C5: ERN Anchor Validation Report

**Purpose:** Document the validation results and methodology differences.

**Deliverable:** `docs/roadmap/S4_C5_VALIDATION_REPORT.md`

**Scope:**
- Results from S4-C2 (E2E oracle)
- Results from S4-C3 (multi-cohort)
- Results from S4-C4 (performance)
- Methodology differences identified
- Acceptance recommendation

---

## 4. Files to Create

| File | Phase | Purpose |
|------|-------|---------|
| `docs/roadmap/S4_C1_METHODOLOGY_AUDIT.md` | S4-C1 | Methodology audit document |
| `tests/oracle/ern/test_part49_e2e.py` | S4-C2 | E2E oracle validation tests |
| `tests/integration/test_part49_multi_cohort.py` | S4-C3 | Multi-cohort validation tests |
| `tests/benchmarks/test_part49_performance.py` | S4-C4 | Performance benchmark tests |
| `docs/roadmap/S4_C5_VALIDATION_REPORT.md` | S4-C5 | Validation report |

## 5. Files to Modify

None expected. S4-COMPLETE is validation-only, not feature implementation.

If validation reveals an architectural defect, that defect should be addressed as a separate corrective action, not within S4-COMPLETE.

## 6. Execution Order

```
S4-C1 (Methodology Audit)
    ↓
S4-C2 (E2E Oracle) — can start after C1
S4-C3 (Multi-Cohort) — can start after C1
S4-C4 (Performance) — can start after C1
    ↓
S4-C5 (Validation Report) — requires C2, C3, C4
```

C2, C3, C4 are independent and can run in parallel.

## 7. Acceptance Criteria for S4-COMPLETE

| # | Criterion | How Verified |
|---|-----------|-------------|
| 1 | Methodology audit complete | S4-C1 document exists and identifies all differences |
| 2 | E2E oracle tests pass | `pytest tests/oracle/ern/test_part49_e2e.py` |
| 3 | Multi-cohort test passes | `pytest tests/integration/test_part49_multi_cohort.py` |
| 4 | Performance within 2× baseline | Benchmark results documented in S4-C4 |
| 5 | Validation report exists | S4-C5 document exists with results and recommendations |
| 6 | All quality gates pass | ruff, mypy, pytest |

## 8. What S4-COMPLETE Should Not Do

- Implement the full 54-cell study grid (S5 scope)
- Add new leverage strategies (S5 scope)
- Introduce timing-based borrowing (S6 scope)
- Modify repayment semantics (S6 scope)
- Redesign the debt engine
- Begin Part 52
- Optimize the engine beyond measured requirements
- Modify production code (unless a defect is found)

## 9. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| ERN dataset differences prevent exact reproduction | Low — qualitative anchors still valid | Document differences; accept methodological replication |
| Performance exceeds 2× gate | Medium — may require optimization | Investigate before S5; optimize if needed |
| Anchor scenarios produce unexpected results | High — may indicate architectural defect | Stop and investigate; do not tune to match |
| Multi-cohort reveals state leakage | High — architectural defect | Address as corrective action outside S4-COMPLETE |
