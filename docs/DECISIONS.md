# Architectural Decisions

Durable decisions whose rationale should survive implementation churn. Each
record states the choice, why it was made, and the consequence a future
maintainer must respect. Superseded variants and historical implementation
narratives are omitted.

---

## Semantic Equivalence for Soft-Delete Restoration

**Decision:** Persistence IDs are storage-generated UUIDs, incidental to
identity. Restoring a soft-deleted entity requires semantic equivalence of its
content fields, not ID matching.

**Why:** Matching an ID alone could resurrect an unrelated row. Identity is
determined by configuration fields such as name, revision, description,
dataset configuration, and policy definitions. Timestamps, UUIDs, durations,
and simulation results are provenance or outputs, not identity.

**Consequence:** Every future persisted entity must define its explicit
equivalent-field set.

---

## Arrays-Only Configuration Model

**Decision:** Study configurations use arrays of values for parameterized
studies. There is no base/fallback/override duality and no `parameters`
section. The sole materialization path is the Cartesian product of
`nominal_rates`, `real_rates`, and `inflation_rates`. `StudyConfiguration` has
a singular `dataset:` field and a mandatory `policy.type`.

**Why:** Base scalars with array overrides make precedence ambiguous. Arrays
are simpler: `equity_allocation: [0.60, 0.75, 0.90]` crosses every value.

**Consequence:** Single-value studies use one-element arrays. `optimize`
requires exactly one value per array. There is no compatibility with earlier
configuration formats.

---

## Multi-Horizon Execution

**Decision:** Execute the longest horizon per family and derive shorter
horizons by truncation. Derived results reuse identical objects. Work is split
into cohort-aligned slices and merged in plan order.

**Why:** Derivation cuts month-work by about 3× without changing semantics
(for example 169M → 56M months). Whole-plan materialization would hold about
0.37 MiB per unit, extrapolating to roughly 110 GiB for a full ERN grid;
sliced dispatch bounds peak memory.

**Consequence:** Numba execution uses slice-based dispatch. Cohorts are never
split. Process-parallel execution is not a production strategy.

---

## Policy Instance Sharing

**Decision:** Reuse one policy instance per distinct parameter value rather
than creating a fresh object per simulation unit.

**Why:** Parameterized studies repeat policy values across units. Sharing
reduced about 626k objects to roughly 14 instances and plan-build RSS by 46%.

**Consequence:** Policies must remain stateless for sharing to be safe.

---

## Frozen Layers

**Decision:** Core simulation semantics are frozen. New behaviour is added
through policy interfaces, strategy protocols, persistence codecs, and
consumer layers, not by ad hoc changes to the simulation pipeline.

**Why:** This prevents accidental coupling between simulation semantics and
presentation or I/O concerns.

**Consequence:** A new capability must fit a defined seam or require an
explicit architectural decision.

---

## ERN Oracle as Canonical Ground Truth

**Decision:** The independent ERN and workbook oracles are canonical ground
truth for their respective methodologies. Production conformance is validated
against independent `Decimal` or hand-calculated oracles, not by routing
production through a second engine. The documented T vs T+1 and fee-convention
differences remain separate comparison targets.

**Why:** SWR research requires exact expected values. Oracle comparison uses
exact `Decimal` equality; a discrepancy is a defect, not a tolerance issue.
Independent oracles make correctness verifiable without a parallel production
engine.

**Consequence:** ERN E2E gates are opt-in. The float64 Numba engine is the sole
production path. Float boundary divergences are documented and pinned.

---

## Evaluation Dimensions vs Simulation Dimensions

**Decision:** `final_value_target` is an evaluation dimension, not a simulation
dimension. It must not participate in trajectory identity and must not cause
additional trajectory execution.

**Why:** A trajectory is defined by start cohort/date, allocation and
withdrawal parameters, initial wealth, initial portfolio, and other
state-affecting inputs. `final_value_target` is a post-simulation
classification check; it does not affect monthly state.

The executor deduplicates contexts that share trajectory parameters but differ
only in target. The final-value check runs per target after path evaluation.
Measured worker time was nearly constant across 0, 1, 2, and 5 targets; the
small total increase came from iterating expanded context lists, not from
re-simulating trajectories.

**Alternatives rejected:** Separating `TrajectoryPlan` from `EvaluationPlan`
was rejected because the measured overhead did not justify the API complexity
and correctness risk.

**Consequence:** Future evaluation-only dimensions must follow the same
pattern. The generic Numba fixed-real path uses the workbook recurrence for
every context regardless of target; earlier target-dependent recurrence
selection was a defect.

---

## Explicit Configuration Mode for Constrained Parameter Tuples

**Decision:** The study builder supports `allocation_policy.configurations` for
declaring constrained parameter tuples as an alternative to the Cartesian
product of independent axes.

**Why:** Part 19/20 glidepath studies require specific `(start, end, slope,
mode)` combinations. A Cartesian product would generate invalid combinations,
such as slope 0.5 for a 20pp spread that should use slope 0.2.

**Consequence:** `configurations` and axis-based policy parameters are mutually
exclusive. Each explicit configuration is crossed with the remaining study
axes. The implementation is confined to the builder layer.

---

## Binary CAPE Classification for Part 20

**Decision:** Part 20 uses a binary CAPE classification (HIGH/LOW) that differs
from the four-level model at the `CAPE=20` boundary.

**Why:** Part 20 splits cohorts into `HIGH: CAPE > 20` and `LOW: CAPE <= 20`.
The four-level model classifies `CAPE=20` as HIGH, while the binary model
classifies it as LOW. The difference is intentional.

**Consequence:** `CapeBinary`/`classify_cape_binary()` and
`CapeRegime`/`classify_cape_regime()` coexist independently. Missing CAPE
values fail fast rather than defaulting to a regime.

---

## Part 42 Accumulation Temporal Semantics

**Decision:** The Part 42 OMY study uses research-layer pre-processing. A
12-month accumulation phase produces the retirement starting portfolio before
the retirement simulation; no engine modification is required.

### Timing

A 30-year horizon is 360 calendar months:

| Phase | Period indices | Months | Snapshots | Transitions |
|---|---:|---:|---:|---:|
| Accumulation | 0-11 | 12 | 13 | 12 |
| Retirement | 12-359 | 348 | 349 | 348 |

`Dataset.slice(start, N)` returns N snapshots. `horizon_months` specifies the
number of return transitions. Accumulation uses `slice(start, 13)` with
`horizon_months=12`; retirement uses `slice(retirement_start, 349)` with
`horizon_months=348`.

Retirement contexts use local period indices starting at 0. The engine is not
modified to preserve global study-level indices.

### Units and contributions

The simulation is currency-neutral. The ERN study is specified in US dollars,
but FBF canonicalizes monetary values as `Money(amount, Currency.EUR)`; all
values are proportional, so the currency label does not change results.

The `$5,000/month` contribution is constant in real terms and is not deflated.
Each accumulation month: value the portfolio at current prices, add the
contribution split by target weights, rebalance, then apply the market return.

### Handoff and targets

The accumulation phase ends at `dataset[12]` prices. That portfolio becomes
`initial_portfolio` for retirement.

- `original_initial_wealth`: study-level wealth (`$2M` for Part 42).
- `retirement_initial_wealth`: post-OMY accumulation output.
- `SimulationContext.initial_wealth` means `retirement_initial_wealth` during
  retirement.

The Part 42 final-value target is 25% of `original_initial_wealth`, not 25% of
`retirement_initial_wealth`.

### Accumulation uniqueness

Accumulation depends only on `(cohort_start_date, contribution_amount,
allocation_policy, initial_portfolio, dataset)`, not on retirement SWR, final
target, or horizon. It is computed once per unique cohort and reused across
retirement configurations. Total Part 42 time must not exceed 2× the measured
retirement-only baseline on the same machine and output configuration.

---

## Part 42 Published-Table Audit Retirement

**Decision:** The historical Part 42 published-table audit is retired and will
not be ported to the Numba path.

**Why:** The historical audit is not a clean oracle for the current path: it is
data-vintage dependent and would require supplemental cash-flow support for the
Social Security scenarios. Recreating it would add execution capability for a
retired validation target without current validation value.

**Consequence:** Part 42 keeps structural and accumulation-oracle coverage but
has no current published-table replication surface. The retired audit spec and
fixture were removed; do not recreate them.

---

## Part 49 Debt Temporal Semantics

**Decision:** The Part 49 leverage study uses an engine-level debt state model.
The margin loan balance, interest accrual, LTV evaluation, and forced
liquidation are managed by dedicated pipeline steps operating on
`SimulationState`. Policies observe an immutable `DebtInfo` snapshot in
`DecisionContext` but never mutate debt.

**Why:** Debt evolves during retirement, so it is execution state rather than
pre-processing or policy configuration. Engine management keeps mechanical
operations deterministic and preserves policy statelessness.

**Alternatives rejected:** Research-layer debt models, policy-owned debt state,
debt as configuration, and negative holdings. Each either misplaces runtime
state or violates the non-negative portfolio invariant.

### Monthly ordering

1. **Beginning-of-period state:** compute portfolio value from holdings and
   prices, carry the prior loan balance, compute LTV and net worth.
2. **Withdrawal decision:** observe beginning-of-period state. Portfolio
   withdrawal is `initial_wealth × withdrawal_rate / 12`; loan draw is
   `initial_wealth × loan_draw_rate / 12`. Part 49 uses 3% portfolio
   withdrawal plus a 1% loan draw for 4% total spending.
3. **Withdrawal execution:** sell at dataset[M] prices. A shortfall is recorded
   but not yet a failure; borrowing may cover it.
4. **Loan draw:** increase the loan balance and add borrowed cash to the
   portfolio. Debt is active immediately and participates in this period's
   returns, but borrowed funds are not used for the current withdrawal.
5. **Allocation decision:** observe beginning-of-period state, including debt.
6. **Rebalance:** rebalance at dataset[M] prices; debt is unaffected.
7. **Market evolution:** apply dataset[M] → dataset[M+1] returns.
8. **Interest accrual:** `interest = loan_balance × annual_rate / 12`;
   capitalize it at period end.
9. **LTV evaluation:** value the portfolio at dataset[M+1] prices. If LTV
   exceeds the limit, liquidate.
10. **Net worth:** `net_worth = portfolio_value - loan_balance` (derived).
11. **Failure detection:** stop on insolvency, depletion, or an unsatisfiable
    margin call.

### Liquidation

```text
liquidation_amount = (loan_balance - ltv_limit × portfolio_value) / (1 - ltv_limit)
```

After selling `x` and repaying the loan, `(L - x) / (P - x) <= λ`, so
`x >= (L - λP) / (1 - λ)`. Using only the numerator would leave LTV above the
limit because the denominator also shrinks.

Liquidation reduces portfolio value and debt by the same amount. A margin call
is unsatisfiable exactly when `loan_balance > portfolio_value`; the entire
portfolio is sold, debt is partially repaid, and the result is
`margin_call_impossible`.

When `loan_balance = portfolio_value`, liquidation sells the entire portfolio,
repays the loan, and leaves zero net worth. `loan_balance = 0` with
`portfolio_value = 0` is clean depletion. `loan_balance > 0` with zero
portfolio is an unsatisfiable margin call.

### Policy snapshot

`DecisionContext` exposes immutable `DebtInfo(loan_balance, interest_rate,
ltv_limit, net_worth)`. Policies may observe it but never mutate debt.

### Failure and invariants

Failure stops the simulation at the first condition:

- `"depleted"`: portfolio value is non-positive, with or without debt.
- `"margin_call_impossible"`: debt exceeds a portfolio that cannot satisfy the
  required liquidation.

Invariants:

1. `loan_balance >= 0` always.
2. All holding units remain non-negative.
3. A loan draw increases portfolio cash and debt by the same amount.
4. Interest capitalization follows `loan_balance += loan_balance × monthly_rate`.
5. Liquidation reduces portfolio value and debt equally and never creates
   wealth.
6. `net_worth = portfolio_value - loan_balance`.
7. Margin-call mechanics and pipeline ordering are deterministic.
8. Liquidation restores LTV to exactly the limit when the portfolio can pay.

---

## Part 49 LTV Enforcement

**Decision:** The ERN Part 49 canonical replication enforces the 75% LTV
margin-call constraint. A breach triggers terminal forced liquidation; the
trajectory does not continue or recover. LTV observation and enforcement are
both enabled.

**Why:** The article's published 84–93% LTV values for the 1965 cohort are
terminal measurements at margin-call failure, not steady-state observations.
Observation-only LTV is a different, legitimate study model, not the canonical
replication.

**Consequence:** `LTVEvaluationStep` enforces only when `ltv_enforcement=True`.
If liquidation is unsatisfiable, the portfolio is sold and the trajectory ends
with an appropriate margin-call failure state.

---

## Part 52: Index-Level Drawdown and Repayment Triggers

**Decision:** Both the drawdown trigger and the fresh-ATH repayment trigger use
the S&P 500 TR index, not the simulated portfolio.

**Why:** ERN defines the triggers against the real S&P 500 TR ATH.
`MarketSnapshot.running_ath` and `is_ath` are index-level fields.

**Consequence:** No portfolio-peak state is needed. Drawdown comes from index
levels plus `running_ath`; repayment uses `is_ath`.

---

## Part 52: Loan Repayment as Explicit Pipeline Step

**Decision:** Repayment is a dedicated `LoanRepaymentStep` at sequence order 32,
not a negative loan draw or part of withdrawal execution.

**Why:** Repayment is a distinct debt-reducing transition. `LoanDrawStep`
rejects negative draws, and embedding repayment in withdrawal execution would
couple unrelated concerns.

**Consequence:** The step reads `WithdrawalDecision.is_repayment` and reduces
`loan_balance` by the excess withdrawal.

---

## Part 52: Periodic LTV Evaluation

**Decision:** LTV is evaluated once per month at end-of-month (step 66), after
interest accrual (step 65).

**Why:** The dataset is monthly. "Continuous" in the ERN decision context means
at every evaluation point within the simulation's temporal resolution. Interest
must be capitalized before the LTV check.

**Consequence:** The step enforces the 50% LTV constraint. A breach caused by
interest accrual triggers liquidation immediately.

---

## Part 52: Borrow% Budget Base

**Decision:** Borrow% is the share of the monthly budget funded by the loan,
where `budget = initial_wealth × withdrawal_rate / 12`.

**Why:** ERN calibrates the withdrawal rate against the initial portfolio, and
the solver maximizes WR subject to constraints, which requires a fixed budget
base.

**Consequence:** Budget is computed from initial wealth, not current portfolio
value, so it stays constant across periods.

---

## Part 52: Full-Universe Eligibility Is Diagnostic-Only

**Decision:** Part 52 canonical acceptance is the published-anchor
fixed-parameter feasibility surface for A2 (`1965-11`), A3 (`1965-11`), and A10
(`1929-09`). Full-universe runs are diagnostics.

| Layer | Cohorts | Role |
|---|---:|---|
| Historical market/CPI with observed FFR | 1,506 | Primary historical diagnostic |
| Workbook-native FFR sensitivity | 1,453 | Mandatory sensitivity |
| Distribution/projection | 1,739 | Projection-only diagnostic |
| Legacy terminal filter | 1,452 | Retired from eligibility policy |

**Why:** The article publishes only the case studies; neither the article nor
the Timing workbook defines a complete Part 52 universe. The 1,739 distribution
sheet is an SWR Toolbox artifact, not a Part 52 target. Without a source-defined
universe or independent published target, a full-universe count cannot be
canonical acceptance.

The 1,506 layer is preferred because every input is observed, not because it is
larger. Its 53 post-2021 cohorts use the frozen FRED extension permitted only in
the historical diagnostic, where market/CPI are observed, the FFR is within the
artifact endpoint, same-measure provenance and workbook overlap are retained,
and the artifact is not refreshed during the run. The 1,453 sensitivity bounds
the extension's effect.

**Consequence:** Full-universe reports must state the layer and dataset vintage,
report 1,506 alongside the 1,453 sensitivity, and never present either as
canonical acceptance. Solver replication remains a separate deferred milestone.

---

## Execution Backend: FAST-only

**Decision:** `ExecutionBackend` exposes exactly one value, `FAST`. The
`DECIMAL_FAST_PATH` and `REFERENCE` values, the legacy Decimal engine, the
Decimal fast path, the nine-step pipeline, and their public helpers are
removed. Numba is the sole production engine.

**Why:** Two engines produced divergent recurrence, fee/timing semantics, and
permanent fallback ambiguity. Numba plus independent oracles removes that
divergence and forces unsupported configurations to fail explicitly.

**Alternatives rejected:** Deprecated aliases with no backend, a legacy AUTO
fallback that hides capability gaps, and silent Numba approximation of
unsupported workloads.

**Consequence:** `FAST` and AUTO dispatch both route through Numba capability
selection. Unsupported configurations raise `UnsupportedConfigurationError`;
missing Numba raises an installation-guidance `ModuleNotFoundError`. The
`PARALLEL` strategy is rejected for Numba workloads. This breaking API change
required the Core `0.3.0` minor version.
