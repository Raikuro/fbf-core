# S6.5 — Solver/Search Analysis

## 1. ERN Part 52 Replication Requirements

### What ERN Explicitly Does

ERN's Part 52 methodology has two distinct components:

**A. Case Studies (known parameters → outcomes)**

For specific cohorts (1965, 1929), ERN fixes all parameters and runs the simulation:

| Parameter | Values tested |
|-----------|--------------|
| Drawdown threshold | none, 20%, 25%, 30%, 35% |
| Borrow% | 0% to ~50% (varies by scenario) |
| FFR spread | 0.50%, 1.25%, 2.75% |
| Repayment | on/off |
| WR | varies |

For each fixed parameter set, the simulation runs and produces a terminal net worth and maximum LTV. This is pure execution — no solver needed.

**B. Optimization (find optimal parameters)**

ERN uses Excel Solver to **maximize WR** subject to:
- Terminal net worth ≥ $250,000 (30-year horizon)
- LTV ≤ 50% at all times

The Solver simultaneously adjusts **two decision variables**: WR and Borrow%. This is the part that "may require a solver."

**C. Published optimization results**

| Cohort | Threshold | WR | Borrow% | Constraints |
|--------|-----------|----|---------|-------------|
| 1965 | none | 3.78% | 10.76% | Both binding |
| 1965 | 20% | 3.91% | 41.08% | Both binding |
| 1965 | 25% | 3.92% | — | Solver-optimized |
| 1965 | 30% | — | — | Solver-optimized |
| 1965 | 35% | — | — | Solver-optimized |
| 1929 | none | 4.39% | 31.86% | Solver-optimized |
| 1929 | 35% | 4.93% | — | Solver-optimized |

**D. Grid tables (from the article)**

ERN presents two summary tables (Figures in the article) showing WR and Borrow% for each (cohort, threshold) combination. These are the "published results" that FBF must reproduce.

## 2. Current FBF Capabilities

| Capability | Status | Notes |
|-----------|--------|-------|
| Run simulation with fixed (WR, borrow%, threshold, FFR) | **YES** | S6.1–S6.3 complete |
| Sweep WR values | **YES** | `withdrawal_policy_values` in grid |
| Sweep borrow_pct values | **YES** | `debt_borrow_pct_values` (S6.4A) |
| Sweep drawdown_threshold values | **YES** | `debt_drawdown_threshold_values` (S6.4A) |
| Sweep FFR spread scenarios | **PARTIAL** | `ffr_dataset_identifier` + `ffr_spread` in config |
| Measure terminal net worth | **YES** | `SimulationResult.statistics` |
| Measure max LTV | **YES** | `LTVEvaluationStep` records LTV |
| Enforce LTV ≤ 50% | **YES** | `ltv_enforcement=True` |
| Optimize WR subject to constraints | **NO** | No solver exists |
| Optimize (WR, Borrow%) jointly | **NO** | No solver exists |

## 3. Gap Analysis

### What FBF Can Reproduce Today

FBF can already reproduce **ERN's case studies** (fixed parameters → outcomes). Given the published (WR, Borrow%, threshold, FFR spread) values, FBF runs the simulation and should produce matching results.

The 1733/1739 discrepancy in S6.3 is a separate numerical issue (6 cohorts fail by portfolio depletion), not a solver gap.

### What FBF Cannot Do Today

FBF cannot **independently discover** the optimal WR and Borrow% for a given (threshold, FFR spread) combination. This requires:

1. A feasibility predicate: given (WR, Borrow%), does the simulation satisfy both constraints?
2. A search procedure: find max WR such that there exists a Borrow% making both constraints satisfied.

### Is the Solver Gap a Blocking Issue?

**For S6.6 (canonical replication):** Possibly not. If FBF reproduces the published parameter values exactly, the solver is not strictly needed. The published results ARE the known (WR, Borrow%) pairs.

**For "full Part 52 replication" (as defined in §7):** Yes. Reproducing ERN's optimization process requires a solver.

## 4. Solver Objective and Feasibility Definition

### Objective

For each (drawdown_threshold, FFR_spread) combination:

```
maximize  WR
subject to:
  ∃ Borrow% ∈ (0, 1) such that:
    1. Terminal net worth ≥ $250,000
    2. max_t LTV(t) ≤ 0.50
```

This is a **bilevel optimization**: for each candidate WR, we must find a Borrow% that satisfies both constraints. The outer problem maximizes WR; the inner problem finds a feasible Borrow%.

### Feasibility Predicate

A (WR, Borrow%) pair is **feasible** if:
- Running the simulation with these parameters produces terminal net worth ≥ $250,000
- The maximum LTV across all months ≤ 0.50

### Monotonicity Analysis

**Claim:** For a fixed Borrow%, the feasibility predicate is monotonic in WR — if WR₁ is feasible, then any WR₂ < WR₁ is also feasible (assuming no LTV constraint interaction).

**Argument:** Lower WR means lower withdrawals, which means higher terminal net worth. So the terminal-networth constraint is satisfied. However, lower WR also means less budget, which means less borrowing, which means lower LTV. So the LTV constraint is also more easily satisfied.

**Complication:** The LTV constraint depends on Borrow%, not directly on WR. For a fixed Borrow%, lower WR → lower absolute borrowing → lower LTV. So both constraints are monotonic in WR for fixed Borrow%.

**For the joint optimization (WR, Borrow%):** The feasible region in (WR, Borrow%) space is not necessarily convex or simply connected. Higher Borrow% increases both leverage (risking LTV) and terminal net worth (if leverage is beneficial). The interaction is non-trivial.

## 5. Manual Sweep vs Binary Search

### Option A — Manual Parameter Sweep

For each (threshold, FFR_spread):
1. Fix a grid of WR values: [3.0%, 3.25%, 3.5%, 3.75%, 4.0%, 4.25%, 4.5%, 4.75%, 5.0%]
2. Fix a grid of Borrow% values: [0%, 10%, 20%, 30%, 40%, 50%]
3. Run all 9 × 6 = 54 simulations per (threshold, FFR_spread)
4. Find the max WR where at least one Borrow% satisfies both constraints

**Pros:**
- Simple, deterministic, no convergence issues
- Parallelizable (each simulation is independent)
- Faithful to ERN's grid-based presentation
- No solver dependencies

**Cons:**
- Limited precision (WR resolution = 0.25%)
- May miss optimal between grid points
- Higher computational cost than binary search

### Option B — Binary Search on WR

For each (threshold, FFR_spread):
1. Binary search on WR ∈ [3.0%, 5.0%]
2. For each candidate WR, find the best Borrow% (could use a nested binary search or sweep)
3. Check feasibility
4. Narrow interval

**Assumptions required:**
- For each WR, there exists a range of feasible Borrow% values (not just a single point)
- The feasibility boundary is monotonic in WR

**Pros:**
- Higher precision (can find WR to arbitrary precision)
- Fewer simulations needed
- Well-understood convergence

**Cons:**
- Requires monotonicity assumption
- Nested search adds complexity
- Less parallelizable
- May not be faithful to ERN's methodology (ERN uses Solver, not binary search)

### Option C — ERN's Actual Methodology (Excel Solver)

ERN uses a general-purpose nonlinear optimizer. The Solver:
- Simultaneously adjusts WR and Borrow%
- Handles nonlinear constraints
- Finds a local optimum

**FBF equivalent:** Use `scipy.optimize.minimize` or similar. But this violates the zero-dependency rule.

**Alternative:** Implement a simple grid-search + refinement:
1. Coarse grid: WR ∈ {3.5%, 3.75%, 4.0%, 4.25%, 4.5%}, Borrow% ∈ {10%, 20%, 30%, 40%}
2. For each (WR, Borrow%), run simulation
3. Find the max feasible WR
4. Refine around the boundary

## 6. Precision and Termination Design

### WR Precision

ERN reports WR to 2 decimal places (e.g., 3.91%, 3.78%). This suggests 0.01% precision is sufficient.

For a sweep approach: grid spacing of 0.01% over [3.0%, 5.0%] = 201 WR values per threshold. Combined with 6 Borrow% values = 1,206 simulations per (threshold, FFR_spread). With 4 thresholds × 3 FFR scenarios = 12 combinations × 1,206 = 14,472 simulations. Each simulation takes ~1.6ms → ~23 seconds total.

For binary search: ~8 iterations to converge to 0.01% precision over [3.0%, 5.0%]. Each iteration needs a feasibility check (which may involve a Borrow% sub-search). Total: ~50–100 simulations per (threshold, FFR_spread). Much faster.

### Termination Criteria

- Binary search: stop when interval width < 0.01%
- Grid search: evaluate all grid points, select max feasible WR
- Refinement: after coarse grid, refine around boundary

## 7. Expected Computational Cost

| Approach | Simulations per (threshold, FFR) | Total (12 combos) | Time (@ 1.6ms/unit × 1,739 cohorts) |
|----------|----------------------------------:|-------------------:|-------------------------------------:|
| Coarse grid (0.25% WR, 6 Borrow%) | 54 | 648 | ~1.8s |
| Fine grid (0.01% WR, 6 Borrow%) | 1,206 | 14,472 | ~40s |
| Binary search (~8 iterations) | ~50 | ~600 | ~1.7s |
| ERN Solver equivalent | ~200 | ~2,400 | ~6.7s |

**Note:** These costs are for the optimization only. The full 1,739-cohort × 180-parameter-grid execution (313K units) is a separate cost (~501s sequential, ~155s parallel 8w).

## 8. Recommended Solver Architecture

### Recommendation: Two-Phase Approach

**Phase 1 — Known Parameter Replication (S6.6 scope)**

No solver needed. FBF runs simulations at the published (WR, Borrow%, threshold, FFR spread) values and validates against ERN's results. This is pure execution.

**Phase 2 — Optimization Reproduction (S6.5 scope, if authorized)**

Use a **manual parameter sweep** with refinement:

1. Coarse sweep: WR ∈ {3.5%, 3.75%, 4.0%, 4.25%, 4.5%}, Borrow% ∈ {10%, 20%, 30%, 40%}
2. Find boundary: max WR where at least one Borrow% satisfies both constraints
3. Refine: sweep around boundary at 0.01% WR resolution
4. Record: optimal (WR, Borrow%) for each (threshold, FFR_spread)

**Why not binary search:**
- The feasibility predicate involves two constraints (net worth AND LTV)
- For each WR, the feasible Borrow% range may be non-trivial
- A sweep is simpler, more robust, and produces a complete picture
- The computational cost difference is small (~40s vs ~1.7s)

**Why not scipy.optimize:**
- Violates zero-dependency rule
- Overkill for a 2D search with cheap evaluations
- Grid sweep is more transparent and reproducible

### Implementation Requirements

1. A function `is_feasible(wr, borrow_pct, threshold, ffr_spread, cohort)` → bool
2. A function `find_optimal_wr(threshold, ffr_spread)` → (wr, borrow_pct)
3. Integration with `StudyConfiguration` to accept optimization targets
4. Output: table of (threshold, ffr_spread) → (optimal_wr, optimal_borrow_pct, terminal_networth, max_ltv)

## 9. Implementation Scope for a Subsequent Phase

If authorized, the implementation would:

1. Add `OptimizationTarget` dataclass to `fbf.core.study`:
   - `objective: str` (e.g., "maximize_wr")
   - `constraints: list[Constraint]` (terminal net worth, max LTV)
   - `search_space: SearchSpace` (WR bounds, Borrow% bounds)

2. Add `sweep_optimization()` function to `fbf.core.optimization`:
   - Takes `OptimizationTarget` + `StudyConfiguration`
   - Runs coarse sweep, then refinement
   - Returns `OptimizationResult` with optimal parameters

3. Add CLI integration (if needed) or study YAML fields for optimization targets

4. Add tests verifying:
   - Sweep finds WR values matching ERN's published results
   - Binary search converges to same results as sweep
   - Edge cases (infeasible regions, degenerate constraints)

## 10. Tests and Acceptance Criteria

### Unit Tests

| Test | Purpose |
|------|---------|
| `test_feasibility_predicate_known_good` | (WR=3.58%, Borrow%=0%, 1965) is feasible |
| `test_feasibility_predicate_known_bad` | (WR=4.0%, Borrow%=25%, 1965) is infeasible (LTV breach) |
| `test_sweep_finds_1965_baseline` | Sweep finds WR ≥ 3.58% for (no threshold, no leverage) |
| `test_sweep_finds_1965_timing` | Sweep finds WR ≥ 3.91% for (20% threshold, FFR+0.50%) |

### Integration Tests

| Test | Purpose |
|------|---------|
| `test_optimization_reproduces_ern_table` | Sweep produces WR and Borrow% matching ERN's published tables |
| `test_optimization_1929_case` | Sweep finds WR ≥ 4.39% for 1929 cohort without timing |

### Acceptance Criteria

- For each (threshold, FFR_spread) in ERN's tables, FBF's sweep finds WR within 0.05% of ERN's published value
- Borrow% is within 5% absolute of ERN's published value
- All found parameters satisfy both constraints when re-simulated

## 11. Decision

**APPROVE DESIGN**

The analysis establishes:

1. **ERN's optimization is a 2D search** over (WR, Borrow%) subject to terminal net worth and LTV constraints.
2. **FBF can already execute** any fixed (WR, Borrow%, threshold, FFR) configuration.
3. **The gap is the search procedure**, not the simulation engine.
4. **A manual parameter sweep** is the most faithful and robust approach — it matches ERN's grid-based presentation, requires no new dependencies, and produces complete results.
5. **Binary search is faster** but less faithful to ERN's methodology and adds complexity for marginal speed gain.
6. **The computational cost is low** — a fine grid sweep of 14,472 simulations takes ~40s sequential.
7. **The solver is not blocking for S6.6** (known parameter replication), but is needed for "full Part 52 replication" as defined in §7.

---

## Addendum: Existing Optimization Infrastructure Review

### 1. Existing Optimization Infrastructure

FBF already contains a binary search optimizer:

**`SWROptimizer`** — `src/fbf/core/optimization/swr_optimizer.py`

```python
class SWROptimizer:
    def optimize(
        self,
        evaluator: Evaluator,
        domain_min: Decimal,
        domain_max: Decimal,
        precision: Decimal = Decimal("0.0001"),
    ) -> OptimizerOutcome:
```

- Binary search over a 1D domain `[domain_min, domain_max]`
- Converges to `precision` (default 0.0001 = 0.01%)
- Pluggable `Evaluator` protocol: `evaluate(candidate: Any) → EvaluationOutcome(success, provenance)`
- Returns `OptimizerOutcome(candidate_value, provenance, diagnostic)`
- Exported as Tier 1 public API via `fbf.core.optimization.optimize_study_swr`

**`Evaluator` protocol** — `src/fbf/core/optimization/swr_optimizer.py:18`

```python
class Evaluator(Protocol):
    def evaluate(self, candidate: Any) -> EvaluationOutcome:
        ...
```

- `candidate` is the value being optimized (typically WR as `Decimal`)
- Returns `EvaluationOutcome(success=True/False, provenance={...})`
- The evaluator encapsulates ALL feasibility logic — the optimizer is agnostic to what "success" means

**`StrategyComparator`** — `src/fbf/core/domain/optimizer/strategy_comparator.py`

- Comparative analytics tool for ranking strategies by metrics
- Not directly relevant to the Part 52 optimization problem

**Tests** — `tests/unit/optimization/test_swr_optimizer.py`

- 3 tests covering: correct rate finding, no-success case, validation error
- Uses `MockEvaluator` with simple threshold logic
- Confirms the optimizer is tested and working

### 2. ERN Methodology — Verified from Source

From the ERN Part 52 article (exact quotes):

> "I use the built-in Excel Solver function to **maximize the retirement budget** subject to the **$250,000 final net worth target** and the **50% upper limit on the loan/portfolio ratio** (=2x leverage), **by changing the withdrawal rate and the 'Borrow%' value**, i.e., the share of retirement budget funded by the margin loan."

> "Also, to explain again how the numbers were created: with the exception of the first column, where I just calibrate the WR and the Borrow% at 4% and 25% (and we clearly get way too much leverage), **I use the Excel Solver function to maximize the retirement budget subject to the $250,000 final net worth and the 50% upper limit on the loan/portfolio ratio (=2x leverage), by changing the withdrawal rate and the 'Borrow%' value**."

**Confirmed interpretation:**
1. **Objective:** Maximize WR (the "retirement budget")
2. **Decision variables:** WR and Borrow% (simultaneously adjusted by Solver)
3. **Constraints:**
   - Terminal net worth ≥ $250,000 (after 30 years)
   - LTV = loan_balance / portfolio_value ≤ 0.50 at ALL times (not just terminal)
4. **Borrow% is an optimization variable**, not a fixed parameter — Solver finds the optimal Borrow% for each WR
5. **The published values are Solver outputs**, not grid points — they may fall between grid points

**Implications for FBF:**
- A grid sweep over WR at fixed Borrow% values is an **approximation** of ERN's procedure, not an exact reproduction
- The exact reproduction requires finding the **joint optimum** of (WR, Borrow%)
- However, the grid sweep approximation is sufficient if it produces WR values within 0.05% of ERN's published values

### 3. Reuse Assessment

| Component | Reusable? | How |
|-----------|-----------|-----|
| `SWROptimizer` (binary search on WR) | **YES** | Outer loop: binary search on WR |
| `Evaluator` protocol | **YES** | Implement `Part52Evaluator` that sweeps Borrow% internally |
| `EvaluationOutcome` | **YES** | `success=True` if any Borrow% satisfies both constraints |
| `StrategyComparator` | No | Not relevant to optimization |
| `Optimizer` base class | No | `SWROptimizer` doesn't use it |
| `optimize_study_swr` convenience function | **YES** | Can be called directly or wrapped |

**The existing `SWROptimizer` is directly reusable for Part 52.**

### 4. Architecture Comparison

#### Option A — Reuse `SWROptimizer` with `Part52Evaluator`

Create a `Part52Evaluator` that:
1. Receives `(threshold, ffr_spread, cohort_spec)` at construction
2. For each candidate WR (from binary search):
   - Sweeps Borrow% ∈ {0%, 10%, 20%, 30%, 40%, 50%}
   - For each (WR, Borrow%): runs simulation, checks terminal net worth ≥ $250K AND max LTV ≤ 50%
   - Returns `success=True` if any Borrow% satisfies both constraints
   - Returns the best (WR, Borrow%) in provenance

Then:
```python
for threshold in [0.20, 0.25, 0.30, 0.35]:
    for ffr_spread in [0.005, 0.0125, 0.0275]:
        evaluator = Part52Evaluator(threshold, ffr_spread, cohort_spec)
        result = SWROptimizer().optimize(evaluator, domain_min=0.03, domain_max=0.06)
```

| Aspect | Assessment |
|--------|------------|
| Implementation complexity | Low — one new class (~50 lines) |
| Reuse of existing abstractions | High — reuses `SWROptimizer`, `Evaluator`, `EvaluationOutcome` |
| Determinism | Deterministic — binary search is deterministic; Borrow% sweep is exhaustive |
| Testability | High — `Part52Evaluator` can be tested independently; `SWROptimizer` is already tested |
| Performance | ~8 WR iterations × 6 Borrow% values × 1,739 cohorts = ~83K simulations per (threshold, FFR) |
| Suitability for future studies | High — any new study can provide a custom `Evaluator` |
| Coupling to Part 52 | Low — the evaluator is Part 52-specific, but the optimizer is generic |
| Zero-runtime-dependency | Preserved — no new dependencies |

#### Option B — Extend `SWROptimizer` generically

Modify `SWROptimizer` to support multi-dimensional search. This would require:
- Changing the `Evaluator` protocol to accept multiple variables
- Implementing multi-dimensional binary search or grid search
- More complex convergence criteria

| Aspect | Assessment |
|--------|------------|
| Implementation complexity | Medium — changes to tested code |
| Reuse | Low — modifies existing abstractions |
| Risk | Higher — changes to tested optimizer |

**Not recommended.** The existing 1D optimizer is sufficient.

#### Option C — Dedicated Part 52 sweep implementation

Ignore the existing optimizer. Implement a standalone `part52_sweep()` function.

| Aspect | Assessment |
|--------|------------|
| Implementation complexity | Medium — reimplements binary search |
| Reuse | None — ignores existing infrastructure |
| Determinism | Deterministic |
| Testability | Medium — standalone function, no existing test patterns |

**Not recommended.** Reimplements what `SWROptimizer` already does.

#### Option D — Generic deterministic grid-search

Implement a new `GridSearchOptimizer` that sweeps over N-dimensional parameter space.

| Aspect | Assessment |
|--------|------------|
| Implementation complexity | Medium — new generic abstraction |
| Reuse | Potentially useful for future studies |
| YAGNI risk | High — no current use case beyond Part 52 |
| Zero-runtime-dependency | Preserved |

**Not recommended now.** YAGNI. The `SWROptimizer` + `Part52Evaluator` approach is simpler and sufficient. A generic grid-search can be added later if a second study needs it.

### 5. Updated Cost Estimate

The previous report estimated:

> 14,472 simulations × 1.6ms ≈ 40s

This assumed a fine grid sweep. The actual cost using `SWROptimizer` + `Part52Evaluator`:

**Per (threshold, FFR_spread) combination:**
- Binary search on WR: ~8 iterations (converging from [3.0%, 6.0%] to 0.01% precision)
- Each iteration: sweep 6 Borrow% values, run simulation for each
- Simulations per iteration: 6
- Total simulations: ~8 × 6 = 48
- Per simulation: 1,739 cohorts × 1.6ms = 2.8s (sequential)
- Per (threshold, FFR): 48 × 2.8s = ~134s (sequential)

**Wait — this is more expensive than estimated.** Let me recalculate.

Actually, each "simulation" is not per-cohort. The `Evaluator.evaluate()` receives a single WR and must check ALL cohorts. For each (WR, Borrow%) pair, we run 1,739 cohort simulations.

Let me reconsider. The correct cost model:

**Per (threshold, FFR_spread):**
- Binary search: ~8 WR candidates
- Per WR candidate: 6 Borrow% values × 1,739 cohorts = 10,434 simulations
- Total: 8 × 10,434 = 83,472 simulations
- Time: 83,472 × 1.6ms = ~134s (sequential)

**Total (12 combinations):** 12 × 134s = ~1,608s (~27 min) sequential.

**With 8 workers:** ~1,608 / 3.22 = ~500s (~8.3 min).

**However**, this can be optimized:
- The binary search only needs to check feasibility, not compute full statistics
- If we use `summary_only=True` in parallel mode, results are smaller
- The Borrow% sweep can short-circuit on first feasible value
- Many (WR, Borrow%) pairs will fail quickly (LTV breach early in retirement)

**Revised estimate with short-circuiting:** ~50% of simulations will terminate early (LTV breach detected before 30 years). Effective cost: ~67s per (threshold, FFR), ~800s total sequential, ~250s parallel 8w.

**Compared to the grid sweep estimate:**
- Grid sweep (0.01% WR, 6 Borrow%): 201 × 6 = 1,206 simulations per (threshold, FFR) × 12 = 14,472 total × 2.8s = ~40s
- Binary search: 83,472 simulations per (threshold, FFR) × 12 = ~1M total × 2.8s = much more

**The grid sweep is actually cheaper** because it evaluates fewer WR points (201 fixed vs 8 binary search iterations). But the binary search finds the exact optimum, while the grid sweep finds the best grid point.

**Recommended approach:** Grid sweep with refinement. Start with coarse grid (0.25% WR spacing), find boundary, refine to 0.01% around boundary. Total: ~54 simulations per (threshold, FFR) for coarse + ~24 for refinement = ~78 simulations per combination. Total: 12 × 78 × 2.8s = ~262s sequential, ~81s parallel 8w.

**Using existing infrastructure:** The `SWROptimizer` binary search can be used for the refinement phase. The coarse sweep is a simple loop.

### 6. Final Recommendation

**APPROVE IMPLEMENTATION DESIGN**

The existing `SWROptimizer` is directly reusable for Part 52. The implementation requires:

1. **`Part52Evaluator`** — new class implementing the `Evaluator` protocol:
   - Constructor: `(threshold, ffr_spread, cohort_spec, dataset, initial_wealth)`
   - `evaluate(candidate_wr)`: sweeps Borrow%, runs simulations, returns `EvaluationOutcome`
   - Short-circuits on first feasible Borrow%
   - Returns best (WR, Borrow%) in provenance

2. **`optimize_part52()`** — new function in `fbf.core.optimization`:
   - For each (threshold, FFR_spread):
     - Coarse grid sweep: WR ∈ {3.0%, 3.25%, ..., 5.5%} with 6 Borrow% values
     - Find boundary WR where feasibility changes
     - Refine using `SWROptimizer` binary search around boundary
   - Returns `Part52OptimizationResult` with optimal (WR, Borrow%) per combination

3. **Tests:**
   - `test_part52_evaluator_feasible` — known good (WR, Borrow%)
   - `test_part52_evaluator_infeasible` — known bad (WR, Borrow%)
   - `test_part52_optimizer_finds_1965_baseline` — WR ≥ 3.58%
   - `test_part52_optimizer_finds_1965_timing` — WR ≥ 3.91%

**Key design decisions:**
- Reuse `SWROptimizer` binary search for refinement — no reimplementation
- Grid sweep for coarse search — simpler, more transparent, matches ERN's grid presentation
- Short-circuit Borrow% sweep — performance optimization
- No new dependencies — zero-runtime-dependency preserved
- Part 52 specific evaluator — but optimizer infrastructure is generic for future studies
