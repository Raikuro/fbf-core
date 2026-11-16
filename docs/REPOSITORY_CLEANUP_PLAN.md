# Repository Cleanup Plan

**Status:** Batch 1, Batch 2a, Batch 2b, Batch 3a, and Batch 3b are complete.
The Batch 4a documentation audit and Batch 4b documentation corrections are
complete; the remaining cleanup and decision batches are awaiting authorization.

**Input:** `docs/REPOSITORY_FILE_AUDIT.md` (untracked audit report, 136,192 bytes).

**Baseline:** `main` at `20b7879c8c71404a10cbc002757d38cff4635bbf`.

**Date:** 2026-11-16. Last updated after Batch 1, Batch 2a, the Batch 2b
retention decision, the Batch 3a test move, the Batch 3b persistence test move
and validation, the Batch 4a documentation audit, and the Batch 4b corrections.

---

## 1. Executive Summary

The repository inventory is internally consistent: 370 project files are tracked and the audit found no untracked or ignored files inside the agreed inventory scope. The cleanup work is therefore mostly targeted hygiene, one removed orphan module, one retained compatibility surface, two completed test-organization corrections, and several stale documentation references. The Batch 4a documentation audit found no broken Markdown links or anchors; the substantive issue is outdated reference content, not link rot.

Recommended disposition:

| Priority | Action | Classification |
|---|---|---|
| 1 | Remove the stale `.gitignore` roadmap entry | Completed (Batch 1) |
| 2 | Remove the empty untracked `canonical/` directory | Completed (Batch 1) |
| 3 | Remove orphan `research/cape_aggregation.py` | Completed (Batch 2a) |
| 4 | Retain `domain/optimizer/optimizer.py` and its package exports | Investigated — retain (compatibility surface) |
| 5 | Move `tests/fixtures/test_debt_fixtures.py` to `tests/unit/execution/` | Completed (Batch 3a) |
| 6 | Move `tests/infrastructure/` to `tests/integration/persistence/` | Completed (Batch 3b) |
| 7 | Audit documentation contents, links, duplication, and placement | Completed (Batch 4a) |
| 8 | Correct stale documentation claims and references | Completed (Batch 4b) |
| 9 | Decide the validation status of `examples/studies/ern_part52.yaml` | Needs decision |
| 10 | Decide whether the debt-fixture self-test should be retired | Needs decision |
| 11 | Keep `TODO.md` empty and keep the two independent debt oracles | Do not change |

Batch 1, Batch 2a, Batch 3a, Batch 3b, Batch 4a, and Batch 4b have been
executed. `cape_aggregation.py` was removed after verification; it was never
imported and never appeared in a tagged release.
`domain/optimizer/optimizer.py` has shipped since `v0.1.0` as a directly
importable Tier 3 module and is retained as a compatibility surface. It is not
automatically removable as “low-risk dead code.”

No supported source behavior changed. Batch 2a removed only an orphan module;
Batch 2b made no code change; Batch 3a moved one test module without changing
its contents; Batch 3b moved a test package and updated one internal import;
Batch 4a changed only this plan; Batch 4b corrected documentation only and did
not modify source, tests, fixtures, examples, or configuration. Deletions and
moves should be made only after explicit authorization, as separate
implementation batches, with the quality gate run after each batch.

---

## 2. Verified Repository State

- Repository root: `/mnt/datos/workspace/fbf/fbf-core`.
- Branch: `main`; HEAD: `20b7879c8c71404a10cbc002757d38cff4635bbf`.
- Working tree at plan creation: no tracked modifications; only `?? docs/REPOSITORY_FILE_AUDIT.md`.
- `docs/REPOSITORY_CLEANUP_PLAN.md` was absent before this plan.
- The audit report is the authoritative input for this plan and was not modified.
- Excluded from the inventory as before: `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, and generated/install metadata.
- Tracked project inventory: 370 files. Categories: production 114, tests 204, resources 34, documentation 12, other 6.
- No material divergence was found between the audited state and the current checkout.
- No cleanup, move, rename, deletion, merge, or content edit to existing project files was performed while preparing the original plan.
- Current state after Batch 1, Batch 2a, the Batch 2b decision, Batch 3a, and
  Batch 3b: `M .gitignore`, ` D src/fbf/core/research/cape_aggregation.py`,
  ` D tests/fixtures/test_debt_fixtures.py`, ten
  ` D tests/infrastructure/...` entries,
  `?? docs/REPOSITORY_CLEANUP_PLAN.md`, `?? docs/REPOSITORY_FILE_AUDIT.md`,
  `?? tests/unit/execution/test_debt_fixtures.py`, and
  `?? tests/integration/persistence/`; `canonical/` and
  `tests/infrastructure/` are absent.
- Batch 1 removed only the stale `.gitignore` rule and the empty `canonical/`
  directory. Batch 1 validation passed: contract tests `21 passed in 1.44s`,
  `git check-ignore` reported no matching rule, `test ! -e canonical` passed,
  and `git diff --check` was clean.
- Batch 2a removed only `src/fbf/core/research/cape_aggregation.py` after
  confirming no current references, no package export, no configuration or
  documentation dependency, and no tagged release containing the file.
- Batch 2a validation after deletion: `356 passed, 5 skipped` for
  `tests/unit/research tests/contract`; full suite `2323 passed, 128 skipped`
  (170.93s); `ruff check .` passed; `mypy --strict .` passed; no `RUN_ERN_E2E`
  command was run.
- Batch 2b retained `src/fbf/core/domain/optimizer/optimizer.py` and its exports
  without modification as an existing compatibility surface.
- Batch 3a moved `tests/fixtures/test_debt_fixtures.py` to
  `tests/unit/execution/test_debt_fixtures.py`. The new file is byte-identical
  to the HEAD version (Git blob `4b7127d6fa2108af8e07593002596056754a9603`);
  no test content, imports, assertions, or fixtures changed.
- Batch 3a validation: `25 tests collected` and `25 passed` at the new path;
  `tests/unit/execution` `336 passed`; full suite `2323 passed, 128 skipped`
  (183.16s); `ruff check .` passed; `mypy --strict .` passed.
- Batch 3b moved all 10 files from `tests/infrastructure/` to
  `tests/integration/persistence/`. Nine files are byte-identical to HEAD; the
  streaming persistence file differs only in the updated helper import.
- Batch 3b validation: `180 tests collected`; direct run `180 passed in 1.19s`;
  full suite `2323 passed, 128 skipped` (172.98s); contract suite `21 passed`;
  `ruff check .` passed; `mypy --strict .` passed (`317 source files`);
  `git diff --check` clean; no `RUN_ERN_E2E` command was run.
- Batch 4a was a read-only audit of every Markdown document, `TODO.md`, and
  doc-like YAML in the repository. It modified no documentation, source, test,
  fixture, example, or configuration file; only this plan was updated. The audit
  report remains unchanged at `136,192` bytes with SHA-256
  `3051764112593f9f9e9d838a6f5df5c73d54fa19a105a9874ce834da4dea4206`.
- Batch 4b corrected `ARCHITECTURE.md`, `DATASETS.md`, `docs/DECISIONS.md`,
  `docs/DEVELOPMENT.md`, `docs/DOMAIN.md`, and `docs/EXECUTION_MODES.md`, and
  recorded the results in section 3.11. It did not change source, tests,
  fixtures, examples, configuration, either `SimulationState` implementation,
  or any package export. The audit report remains unchanged.
- The Phase 2 investigation modified no source, test, fixture, export, or
  configuration file. Phase 2 read-only validation covered optimization, Part 3
  aggregation/pipeline, and contract tests: `103 passed in 16.69s`.
- No staging, commit, push, or history rewrite has been performed.

---

## 3. Findings for Named Candidates

### 3.1 `src/fbf/core/research/cape_aggregation.py`

**Evidence**

- 222 lines at HEAD (228 when introduced), added in `5324d72` and last modified
  in `189964a`.
- No importer in `src/`, `tests/`, or `tools/`; not exported by
  `fbf.core.research.__init__`; no documentation reference.
- `part3_aggregation.py` (272 lines) was added later in `5bd729f`, is exported by
  the public research facade, and is used by `part3_pipeline.py` and the Part 3
  tests.
- The orphan uses runtime `classify_cape_regime()` and defaults missing CAPE to
  `BELOW_15`. The supported Part 3 aggregation consumes manifest regime metadata
  and deliberately excludes units without CAPE metadata via `excluded_no_cape`.
  The two modules therefore encode divergent semantics, not merely duplicate
  formatting.
- Its module docstring describes itself as a Research-layer aggregator, so this
  is not a hidden domain utility.

**Phase 2 verification (2026-11-15)**

- The introduction commit `5324d72` is not contained in any tag. `v0.1.0`, the
  only tag with packaged-release metadata, predates the file; all other tags
  also lack it.
- Historical import searches found no importer at any revision:
  `from fbf.core.research.cape_aggregation`, `cape_aggregation import`, and
  `import cape_aggregation` all returned no import sites.
- The only historical non-test mention is the removed
  `docs/roadmap/S5_ARCHITECTURE_PLAN.md`, which proposed adding an `interest_rate`
  grouping key to `aggregate_success_rates`; the module was never wired to that
  plan.
- The module’s unique helper `_determine_experiment_name` produces experiment
  labels for an aggregation path that no supported pipeline uses.

**Recommendation:** Removed in Batch 2a on 2026-11-15 after all preconditions
passed.

**Classification:** **Completed (Batch 2a) — superseded orphan removed.** The
module was Tier 3, unexported, absent from all tags, and had no in-repository
consumer. It was superseded by the exported and tested Part 3 aggregation. A
hypothetical external import would have been an unsupported direct import of a
file that was never part of a release.

**Batch 2a outcome (2026-11-15)**

- Pre-deletion checks found no importer, indirect consumer, package export, test
  dependency, script reference, documentation reference, or configuration
  dependency.
- `git tag --contains 5324d72` returned no tags; the file was absent from every
  tag tree.
- History review found only the introduction (`5324d72`) and a later cleanup
  (`189964a`). The `aggregate_success_rates` mentions in `fc54202` and
  `53badc7` were roadmap prose, not imports or executable consumers.
- The file was deleted. No other source, test, fixture, example, configuration,
  or documentation file was modified.
- Post-deletion reference search found no remaining `cape_aggregation` or
  `aggregate_success_rates` references outside this plan and the audit report.
- Targeted tests: `356 passed, 5 skipped` in 3.24s. Full suite:
  `2323 passed, 128 skipped` in 170.93s. `ruff` and `mypy --strict` passed.

**Tests to update:** None. The module had no test coverage or import
dependencies; the existing research and full suites pass after removal.

### 3.2 `.gitignore` stale roadmap entry

**Evidence**

- The last lines are:

  ```gitignore
  # Generated benchmark output (reproducible, not versioned)
  docs/roadmap/s57_benchmark_results.json
  ```

- The entry was added in `6366c39`.
- `docs/roadmap/` was removed in `6c50f39`; the related benchmark script was
  removed in `2c43e68`.
- No current source, test, tool, workflow, or documentation reference keeps the
  path alive. The remaining `roadmap` matches are unrelated prose in `AGENTS.md`
  and do not refer to this path.

**Recommendation:** Remove both the comment and the path entry.

**Classification:** **Safe.** It changes only ignore rules for a path that no
longer exists.

**Tests to update:** None. Verify with:

```bash
git check-ignore -v docs/roadmap/s57_benchmark_results.json
```

The command must no longer report a matching ignore rule after the change.

### 3.3 Empty `canonical/` directory

**Evidence**

- `canonical/` is untracked and contains zero files.
- `canonical/README.md` was removed in `6c50f39`.
- `DATASETS.md` records the former `canonical/ern_asset_returns.csv` artifact as
  removed and not to be reintroduced.
- No current code or workflow reads from `canonical/`.
- `tools/ern/extract_workbook_returns.py` mentions the retired path only in
  historical provenance text, not as an input or output.

**Recommendation:** Remove the empty directory with `rmdir canonical` after
confirming it is still empty. Do not recreate it.

**Classification:** **Safe.** It is untracked, contains no files, and is not part
of the wheel or test inputs.

**Tests to update:** None. Verify with:

```bash
test ! -e canonical
```

### 3.4 `TODO.md`

**Evidence**

- The file is zero bytes.
- It was intentionally emptied in the current HEAD commit `20b7879` after its
  remaining 45 lines were resolved.
- `AGENTS.md` and `README.md` still describe it as the canonical register of
  unresolved technical work.
- The instructions already say to remove items once resolved, which makes an
  empty register a valid state.

**Recommendation:** Keep the empty file. Do not populate it with inferred or
hypothetical work. If clarity is desired later, add one sentence to the
documentation stating that an empty `TODO.md` means no recorded open items; that
is a documentation decision, not a cleanup requirement.

**Classification:** **Do not change.** The empty state is deliberate and
consistent with the documented removal rule.

**Tests to update:** None.

### 3.5 `examples/studies/ern_part52.yaml`

**Evidence**

- The file is a complete, documented Part 52 example with a run command.
- No automated test, tool, or documentation reference loads it.
- The other seven example studies have automated references, except
  `ern_part19.yaml`, which is documentation/support-only.
- `docs/DEVELOPMENT.md` describes committed YAML studies in `examples/studies/`
  as functional scenarios executed through the public boundary, which creates an
  expectation of validation that this file does not currently meet.

**Recommendation:** Keep the file. Choose one of:

1. Add a lightweight parse/build smoke test for this example, or for all example
   YAMLs, without executing the full ERN workload; or
2. Explicitly document it as an illustrative, non-validated example.

Deleting it is not recommended because it is a user-facing example and already
contains the run instructions.

**Classification:** **Needs decision.** The correct choice depends on whether
examples are a supported, tested surface or illustrative documentation.

**Tests to update:** If option 1 is chosen, add a fast test that parses the YAML
and builds a plan; do not add it to the heavyweight ERN suite.

### 3.6 `src/fbf/core/domain/optimizer/optimizer.py`

**Evidence**

- Defines `OptimizationResult` and an abstract `Optimizer.search()` that only
  raises `NotImplementedError`.
- The only reference is the re-export in
  `src/fbf/core/domain/optimizer/__init__.py`.
- No source, test, tool, or documentation module imports `Optimizer` or
  `OptimizationResult` directly.
- The actual optimizer is `fbf.core.optimization.swr_optimizer.SWROptimizer`.
- `StrategyComparator` and the comparison types in the same package are used by
  the supported optimization API and must remain.
- The abstraction is Tier 3. It is not exported from `fbf.core` and is not
  listed in the Tier 2 documentation.

**Phase 2 verification (2026-11-15)**

- The module is present in every tag because its introduction commit `c07c5b8`
  predates all tags. It was present in the `v0.1.0` release tree.
- `v0.1.0` did not re-export `Optimizer` from `fbf.core.domain`; current
  `fbf.core.domain` also does not. The supported facade therefore never exposed
  these names.
- The pre-`v0.1.0` tags retained the `engine.domain` re-export (confirmed in
  `v0.1-execution-engine`, `v0.2.1-cohort-schema`, and `v0.2.3`). That re-export
  was dropped during the `fbf.core` namespace migration in `2eac2f5`.
- Current direct references are limited to `optimizer.py` and
  `src/fbf/core/domain/optimizer/__init__.py`; no source, test, tool, or
  documentation module imports either name directly.
- The `StrategyComparator` tests import other names from
  `fbf.core.domain.optimizer`, so they indirectly execute the package import of
  `Optimizer`. Any removal must update that package `__init__.py` in the same
  change, even though no test asserts `Optimizer` behavior.
- Runtime inspection confirms `fbf.core.domain.optimizer.Optimizer` is directly
  importable, `fbf.core.domain` has no `Optimizer`, `fbf.core.optimization` has
  no `Optimizer`, and `Optimizer.search()` raises `NotImplementedError`.
- `SWROptimizer` is the implemented solver and uses `Decimal` candidates and
  `OptimizerOutcome`; `Optimizer`/`OptimizationResult` are not used by it.

**Batch 2b decision (2026-11-15): RETAIN.**

`src/fbf/core/domain/optimizer/optimizer.py` and its package exports are
retained without modification. The module has been directly importable since
`v0.1.0`. Although it is not exposed through `fbf.core.domain` or the Tier 1/Tier
2 API, its direct import path `fbf.core.domain.optimizer` is an existing
compatibility surface. Removing it would break consumers relying on that path;
the benefit of removing an apparently unused module does not justify that
compatibility break.

**Recommendation:** Retain the module and exports. Any future removal would
require a deliberate API deprecation/breaking-change decision, not routine
repository cleanup.

**Classification:** **Investigated — retain (compatibility surface).**

**Tests to update:** None. No code or export changed. The optimization,
contract, and full suites pass with the module retained.

### 3.7 `tests/fixtures/test_debt_fixtures.py` and `tests/fixtures/debt.py`

**Evidence**

- `test_debt_fixtures.py` is a collected test module inside a fixtures
  directory.
- It validates `tests/fixtures/debt.py` against the independent oracle in
  `tests/support/ern/debt_oracle.py`.
- `tests/fixtures/debt.py` has exactly one consumer: this self-test.
- No production test uses the debt fixture module.
- The self-test was maintained recently: its oracle import was updated when the
  shared support package was introduced.
- The independent oracle is also tested directly by
  `tests/integration/ern/test_debt_oracle.py`.

**Recommendation:** Moved in Batch 3a to
`tests/unit/execution/test_debt_fixtures.py`. The destination matches the test's
execution-layer debt subject and the existing `tests/unit/execution` suite,
which already contains Part 49/52 and debt-flow tests. `tests/fixtures/` now
contains support code and resources only. Keep `tests/fixtures/debt.py` for now.

If the owner confirms that the fixture suite is obsolete, a later separate
change may retire both `tests/fixtures/debt.py` and its self-test. That is not
recommended without explicit confirmation because the fixture module is a
deliberately maintained known-answer suite.

**Classification:** **Completed (Batch 3a) — test moved; coverage preserved.**
The move is low risk for behavior; retirement of the fixture suite remains a
separate decision.

**Batch 3a outcome (2026-11-15)**

- Original path: `tests/fixtures/test_debt_fixtures.py`.
- New path: `tests/unit/execution/test_debt_fixtures.py`.
- The test uses absolute imports from `tests.fixtures.debt` and
  `tests.support.ern.debt_oracle`; no relative paths or resource lookups
  required adjustment.
- No test, support module, tool, script, pytest configuration, or CI workflow
  referenced the old path.
- The moved file is byte-identical to the HEAD version (Git blob
  `4b7127d6fa2108af8e07593002596056754a9603`). No test content, imports,
  assertions, markers, or fixtures changed.
- Test count is unchanged: 25 tests collected and passed before and after.
  Node IDs now use the `tests/unit/execution/...` prefix.
- Validation: `tests/unit/execution` `336 passed`; full suite
  `2323 passed, 128 skipped` (183.16s); `ruff check .` passed;
  `mypy --strict .` passed; `git diff --check` clean.

**Tests to update:** None. The move preserved all tests and coverage; no path
adjustment was necessary.

### 3.8 `tests/infrastructure/`

**Evidence**

- Contains 10 files: `__init__.py` plus nine persistence-focused test modules.
- These are integration-style tests for SQLite persistence and query behavior.
- `test_streaming_persistence.py` imports helper functions from
  `test_sqlite_persistence.py` using the absolute path
  `tests.infrastructure.test_sqlite_persistence`.
- No source, workflow, or documentation reference depends on the directory
  name. Only the audit report names it.
- The repository's documented test taxonomy is unit, integration, functional,
  contract, and benchmarks; there is no documented `infrastructure` level.
- Baseline collection is 180 tests; baseline execution is `180 passed in 1.26s`
  for `tests/infrastructure/`.
- No module has a pytest marker. `test_p10_visualization_queries.py` contains
  three unmarked ERN-scale timing checks inside `TestERNBenchmark`, but its
  primary subject is still the repository query API; splitting the file is a
  separate refactor and is not part of this move.

**Inventory and classification**

| File | Tests | Boundary evidence | Disposition |
|---|---:|---|---|
| `__init__.py` | 0 | Package marker for the existing test package. | Move with the package. |
| `test_codecs.py` | 31 | Codec round-trips plus `SQLiteRepository` integration with concrete codecs. | Integration/persistence. |
| `test_context.py` | 4 | `CanonicalDatasetLoader`, persistence context factory, and canonical dataset loading. | Integration/persistence. |
| `test_dataset_identity_persistence.py` | 3 | Dataset persistence identity, save/load round-trip, and direct SQLite inspection. | Integration/persistence. |
| `test_p10_visualization_queries.py` | 24 | Repository statistics/trajectory queries; contains an embedded ERN-scale benchmark class. | Integration/persistence; benchmark split deferred. |
| `test_p11_cohort_grid.py` | 24 | Repository parameter-discovery and cohort-horizon grid query methods. | Integration/persistence. |
| `test_schema_migration.py` | 4 | SQLite schema initialization, rejection, and reopen behavior. | Integration/persistence. |
| `test_sqlite_persistence.py` | 73 | Broad SQLite repository round-trip, schema, ordering, and error-path coverage. | Integration/persistence. |
| `test_sqlite_policy_fallback.py` | 8 | No-codec policy fallback serializer and repository regression behavior. | Integration/persistence. |
| `test_streaming_persistence.py` | 9 | Incremental/streamed persistence, concurrency, recovery, and retry behavior. | Integration/persistence. |

**Proposed mapping**

- `tests/infrastructure/__init__.py` → `tests/integration/persistence/__init__.py`
- `tests/infrastructure/test_codecs.py` → `tests/integration/persistence/test_codecs.py`
- `tests/infrastructure/test_context.py` → `tests/integration/persistence/test_context.py`
- `tests/infrastructure/test_dataset_identity_persistence.py` → `tests/integration/persistence/test_dataset_identity_persistence.py`
- `tests/infrastructure/test_p10_visualization_queries.py` → `tests/integration/persistence/test_p10_visualization_queries.py`
- `tests/infrastructure/test_p11_cohort_grid.py` → `tests/integration/persistence/test_p11_cohort_grid.py`
- `tests/infrastructure/test_schema_migration.py` → `tests/integration/persistence/test_schema_migration.py`
- `tests/infrastructure/test_sqlite_persistence.py` → `tests/integration/persistence/test_sqlite_persistence.py`
- `tests/infrastructure/test_sqlite_policy_fallback.py` → `tests/integration/persistence/test_sqlite_policy_fallback.py`
- `tests/infrastructure/test_streaming_persistence.py` → `tests/integration/persistence/test_streaming_persistence.py`

No file is retained in `tests/infrastructure/`. No test content, assertion,
fixture, marker, or test name changes. Only the absolute helper import in
`test_streaming_persistence.py` changes to
`tests.integration.persistence.test_sqlite_persistence`.

**Classification:** **Completed (Batch 3b).** The move changed test paths and
one import, not production behavior.

**Tests to update:** The streaming persistence import, updated to
`tests.integration.persistence.test_sqlite_persistence`.

**Batch 3b outcome (2026-11-15)**

- Moved all 10 files to `tests/integration/persistence/`; the old
  `tests/infrastructure/` directory is absent.
- Nine moved files are byte-identical to their HEAD versions. The streaming
  persistence file differs only in the updated helper import line.
- Collection is unchanged: `180 tests collected`.
- Direct run is unchanged: `180 passed in 1.19s`.
- Full suite: `2323 passed, 128 skipped` (172.98s).
- Contract suite: `21 passed`; `ruff check .` passed; `mypy --strict .` passed
  (`317 source files`); `git diff --check` clean.
- No stale `tests.infrastructure` or `tests/infrastructure` references remain
  outside this plan and the audit report. `RUN_ERN_E2E` was unset.

### 3.9 Stale file references in comments and docstrings

**Evidence**

The following references point to files or artifacts that no longer exist:

- `src/fbf/core/persistence/studies/sqlite/sqlite_repository.py:4` references
  `INFRASTRUCTURE_SQLITE_PERSISTENCE_SPECIFICATION.md`.
- `src/fbf/core/persistence/studies/sqlite/codecs.py:193` references
  `NEXT_SESSION.md P3.1 TD-1`.
- `src/fbf/core/execution/strategies/part49_buy_and_hold_numba_executor.py:95`
  points to `TODO.md` for a fee limitation that is no longer recorded there.
- `src/fbf/core/research/part20_anchors.py:5` references
  `ern_part20_replication.md`, removed in `6c50f39`.
- `src/fbf/core/research/part20_aggregation.py:150,158,165,222` references
  removed `ern_part20_e2e_audit.md` and `ern_part20_replication.md` files in
  evidence strings.
- `tests/integration/persistence/test_sqlite_persistence.py:3` references the
  removed persistence specification.
- `tests/unit/execution/test_parallel_execution.py:3` references
  `PARALLEL_EXECUTION_SPECIFICATION.md`.
- `tests/unit/execution/test_research_executor.py:3` references
  `RESEARCH_EXECUTOR_SPECIFICATION.md`.
- `tests/integration/test_part49_grid_audit.py:21` references the removed
  `S4_ARCHITECTURAL_DESIGN_REVIEW.md`.
- `tests/unit/optimization/test_strategy_comparator_additional.py:1` references
  `RESEARCH_STRATEGYCOMPARATOR_IMPLEMENTATION_HANDOFF.md`.
- `tests/functional/ern/test_part20_e2e_audit.py:3,554` references the removed
  `ern_part20_e2e_audit.md`; line 12 also says it preserves a removed
  `test_part20_replication.py`.
- `tests/fixtures/ern_part20_e2e_audit.yaml:25` references the removed
  `ern_part20_e2e_audit.md`.
- `tests/unit/execution/test_debt_fixtures.py:5` refers to a removed `K.4` work
  item.
- `tests/unit/execution/test_research_layer_debt_flow.py:8` refers to
  `K.4-K.6` tests, some of which have been removed or renamed. The phase label
  itself is historical and is not an actionable broken path.

**Recommendation:** Replace file references with the current authority, or
remove them. For Part 20, point to `docs/ERN_METHODOLOGY.md` and the audit YAML
under `tests/fixtures/` instead of removed Markdown research reports. Do not
mass-edit historical phase labels such as `S5.4`, `K.6`, or `P3.1`; those are
provenance labels, not necessarily broken paths.

**Classification:** **Low risk.** These are comments, docstrings, and internal
evidence strings. No runtime semantics are intended to change.

**Tests to update:** None expected. Re-run the affected unit/integration suites
and `ruff`/`mypy`.

### 3.10 Documentation audit (Batch 4a)

**Scope and method**

- Audited every tracked Markdown document, `TODO.md`, and the doc-like YAML
  under `examples/`, `src/fbf/core/research/config/`, and `tests/`.
- Compared documentation claims with the current public exports, source
  modules, tests, package metadata, and the sibling `fbf-cli` and `fbf-ui`
  repositories.
- Checked all Markdown links, same-file anchors, and cross-file anchors.
- Checked for duplication, misplaced content, stale paths, and removable
  documents.
- The audit report and this plan were treated as working inputs, not
  documentation cleanup targets. No documentation file was edited in Batch 4a.

**Document classification**

| Document | Audit result | Status |
|---|---|---|
| `README.md` | Project overview, installation, quick start, and documentation index match package metadata and current public exports. | Investigated — current, retain. |
| `AGENTS.md` | Repository rules, API tiers, quality gate, test taxonomy, and commit governance are current. | Investigated — current, retain. |
| `ARCHITECTURE.md` | Intended architecture is mostly current, but repository topology and several implementation terms are outdated. | Completed — corrected and verified (Batch 4b). |
| `DATASETS.md` | Dataset layout, canonical sources, provenance, and required files are current. Obsolete manifest paths are explicitly described as obsolete. Line 170 contained a dangling `TODO.md` reference. | Completed — corrected and verified (Batch 4b). |
| `TODO.md` | Deliberately empty; consistent with the documented no-open-items state. | Investigated — current, retain. |
| `docs/DECISIONS.md` | Decision records are current except the solver-status wording at line 457. | Completed — corrected and verified (Batch 4b). |
| `docs/DESIGN.md` | Rationale and rejected alternatives are current. Overlap with architecture and decisions is role-driven, not accidental duplication. Batch 4b found an obsolete policy lifecycle at lines 184-185. | Investigated — stale policy lifecycle retained; not in Batch 4b scope. |
| `docs/DEVELOPMENT.md` | Workflows and commands are current. The universal claim about examples and functional fixtures at line 111 was inaccurate because several functional tests construct `StudyConfiguration` inline. | Completed — corrected and verified (Batch 4b). |
| `docs/DOMAIN.md` | Several core names, policy inventories, lifecycle roles, and result semantics were outdated or contradicted current code and `DESIGN.md`. | Partially completed — model corrected; state ownership remains deferred (Batch 4b). |
| `docs/ERN_METHODOLOGY.md` | ERN anchors, dataset conventions, validation rules, and conclusion dates are current. Lines 605-608 contain cross-repo project status that may be misplaced. | Investigated — current, retain; optional placement investigation only. |
| `docs/EXECUTION_MODES.md` | Backend and strategy semantics match the current executors. The routing example omitted an `ExecutionStrategy` import. | Completed — corrected and verified (Batch 4b). |
| `docs/PROFILING.md` | Profiler classes, exports, phase semantics, and examples match the current API. | Investigated — current, retain. |

**Verification results**

- No broken Markdown links or anchors were found in any non-plan/non-audit
  document.
- The apparent missing dataset paths in `DATASETS.md` are intentional
  obsolete-path documentation, not broken current references.
- The absent `data/outputs/ern-extraction/` path in `docs/DEVELOPMENT.md` is the
  documented gitignored generated output location.
- No normal documentation file is an orphan or an unreferenced duplicate that
  warrants removal. The README and AGENTS documentation indexes serve different
  audiences; `DESIGN.md`, `DECISIONS.md`, and `ARCHITECTURE.md` encode rationale,
  decisions, and intended structure respectively.
- The audit report is an input artifact, not documentation to consolidate into
  the normal documentation set.
- The `examples/studies/` and fixture YAML files are data/config material, not
  prose documentation. `ern_part52.yaml` still needs the Batch 5 decision;
  `ern_part19.yaml` is documentation/support-only rather than an automated
  functional scenario.

**Substantive corrections proposed**

1. **`ARCHITECTURE.md`: repository topology and implementation terms.**
   - Lines 23-34 describe a two-repository ecosystem plus a generic consumer.
     The actual workspace contains three sibling repositories: `fbf-core`
     (engine and research library), `fbf-cli` (terminal delivery and
     orchestration), and `fbf-ui` (web interface and visualization). The
     overview should show them as peers, not as core plus one generic consumer.
   - Line 60 describes `SimulationExecutor.execute(experiment)`; the public
     operation is `execute(definition: ExperimentDefinition) -> ExperimentRun`.
   - Line 97 says `Python stdlib only`. The base library is dependency-free,
     but execution requires the optional Numba extra. Clarify the distinction
     rather than presenting both claims as unconditional.
   - Line 217 says history is not rewritten in either repository; update the
     wording to the three-repository ecosystem.
   - Line 272 says the infrastructure layer owns the SQLite schema; current
     terminology is the persistence layer.
   - The section 12 `Workers` description and the line 275 parallel-read wording
     should be checked against current production execution. Production
     simulation is sequential; `parallel_execution.py` is a low-level
     test-equivalence helper, not a production worker pool. Reword if the text
     implies otherwise.

2. **`DOMAIN.md`: current domain model.**
   - Line 38 documents `SimulationUnit`; the current public planned type is
     `PlannedSimulationUnit`, and no `SimulationUnit` class exists.
   - Lines 126-127 list Constant Allocation, Passive Glidepath, and Active
     Glidepath. The current enum is `CONSTANT`, `GLIDEPATH`, and
     `BUY_AND_HOLD`; the passive/active split is outdated and Buy and Hold is
     missing.
   - Line 134 lists only Constant Inflation-Adjusted Withdrawal. The current
     withdrawal enum includes `FIXED_REAL`, `CONSTANT`, `PART49`, `PART52`, and
     `ESCALATING`; update or summarize this inventory accurately.
   - Lines 140-146 describe mutable `SimulationState` as the domain heart.
     Two mutable `SimulationState` classes are exported: one from
     `domain.model.simulation` and one from `execution.pipeline.simulation`.
     No current production Numba executor references either class directly;
     `DESIGN.md` says mutable state belongs to execution. The relationship
     between the two exports is a specification divergence, not just a wording
     error: the owner must decide their ownership or compatibility status
     before either is declared canonical.
   - Line 174 says `SimulationStatistics` is updated automatically; the current
     type is frozen and its statistics are assembled at the end.
   - The `ExperimentDefinition` description assigns study configuration and
     optimization targets to the wrong type. Current public configuration and
     axes are represented by `StudyConfiguration`; `ExperimentDefinition` is a
     narrower execution input.

3. **`DECISIONS.md`: solver status.**
   - Line 457 says solver replication remains a separate deferred milestone.
     `ERN_METHODOLOGY.md:602-604` says Part 52 solver reproduction is completed
     as a test-only deterministic reproduction. The status should distinguish
     full solver replication, which remains deferred, from reproduction of the
     recorded workbook optimum, which is complete and does not prove global
     optimality.

4. **`DATASETS.md`: dangling TODO reference.**
   - Line 170 says to see `TODO.md` for Euro reference rates, but `TODO.md` is
     empty. Remove the dangling reference unless the owner decides this is a
     genuine open item that belongs in `TODO.md`.

5. **`DEVELOPMENT.md`: examples and fixtures claim.**
   - Line 111 states that functional scenarios are committed YAML studies in
     `examples/studies/` and `tests/fixtures/`. This is inaccurate: several
     functional tests construct `StudyConfiguration` inline
     (`tests/functional/ern/test_part52_replication.py:261,278`,
     `test_ern_part2.py:207`, and `test_part42_replication.py:115`). Qualify
     the statement to say that YAML is the preferred/canonical representation or
     that scenarios may also be constructed programmatically. The separate
     `examples/studies/ern_part52.yaml` validation question remains a Batch 5
     decision.

6. **`EXECUTION_MODES.md`: example import.**
   - The example around lines 162-175 uses `ExecutionStrategy.SEQUENTIAL`
     without importing `ExecutionStrategy`. Add the import; backend and executor
     routing semantics otherwise match the implementation.

7. **Stale non-documentation references.**
   - Fix the actionable comments and docstrings listed in section 3.9 after the
     documentation corrections are approved. Do not mass-edit historical phase
     labels such as `S5.4`, `K.6`, or `P3.1`.

**Duplication and placement conclusions**

- No merge or removal is recommended for `README.md`, `AGENTS.md`,
  `DESIGN.md`, `DECISIONS.md`, or `ARCHITECTURE.md`; their overlapping material
  has distinct authority and audience.
- `ERN_METHODOLOGY.md:605-608` mixes cross-repo project status into core
  methodology. This is a low-priority placement issue; do not move it without a
  stable destination document and owner approval.
- `DATASETS.md` and `ERN_METHODOLOGY.md` overlap on dataset conventions, but
  `DATASETS.md` is the source/provenance authority and `ERN_METHODOLOGY.md` is
  the methodology authority. Do not consolidate them.
- No subdirectory README is missing in a way that warrants adding one. The
  existing root and `docs/` indexes are sufficient.

**Risk assessment**

- Rewriting `DOMAIN.md` without deciding the status of the domain
  `SimulationState` mirror could legitimize a duplicate model or erase a
  compatibility surface.
- Rewriting architecture text without checking sibling repositories could
  produce a third inconsistent topology description.
- Editing historical status or evidence wording can erase provenance. Limit
  changes to current guidance and distinguish deferred work from completed
  test-only reproduction.
- Qualifying the examples claim must not accidentally state that every YAML
  example is validated. Functional scenarios and illustrative examples are
  separate; the Part 52 example decision remains with Batch 5.
- Moving documentation to fix placement would change anchors and links for no
  current functional benefit; no move is recommended in this cleanup.

**Recommended documentation batch order**

1. Correct semantics first: `DOMAIN.md`, `ARCHITECTURE.md`, and the solver-status
   wording in `DECISIONS.md`.
2. Correct integrity/accuracy second: the `DATASETS.md` dangling reference,
   the `EXECUTION_MODES.md` import, the `DEVELOPMENT.md` examples wording, and
   the actionable stale references in section 3.9.
3. Leave `ERN_METHODOLOGY.md` content and placement unchanged unless the owner
   wants a separate cross-repo status document.

### 3.11 Batch 4b implementation record

**Scope clarification:** the authorization named `docs/ARCHITECTURE.md` and
`docs/DATASETS.md`, but those files do not exist. The audited documents are
`ARCHITECTURE.md` and `DATASETS.md` at the repository root. The owner confirmed
that the root files were the intended targets. No other documentation was
changed.

| Item | Original finding | Correction made | Evidence used | Validation | Final status |
|---|---|---|---|---|---|
| `ARCHITECTURE.md` | Two-repository overview, stale executor signature, stdlib-only dependency claims, infrastructure terminology, worker/parallel wording, CLI-only data-dir wording, and an obsolete policy lifecycle. | Updated the overview to three peer repositories; corrected the executor contract to `execute(definition: ExperimentDefinition) -> ExperimentRun`; separated the stdlib base from the optional `numba` execution extra; updated persistence terminology; reworded execution data flow and WAL concurrency; named both frontends for dataset-directory handling; replaced the policy lifecycle with `decide(context: DecisionContext) -> PolicyDecision`. | `fbf-cli/README.md`, `fbf-cli/pyproject.toml`, `fbf-ui/README.md`, `fbf-ui/pyproject.toml`, `src/fbf/core/execution/pipeline/executor.py`, `src/fbf/core/domain/policies/policy.py`, `pyproject.toml`, and SQLite PRAGMA settings. | Markdown links/anchors; symbol and path checks; diff review. | Completed — corrected and verified. |
| `docs/DOMAIN.md` | Outdated `SimulationUnit`, policy inventory, policy lifecycle, result/statistics semantics, and state description. | Replaced the study/unit descriptions with `StudyConfiguration`, `ResearchPlan`, and `PlannedSimulationUnit`; updated allocation and withdrawal inventories; documented the current single-operation policy contract; corrected state, result, statistics, and reproducibility descriptions. | `src/fbf/core/study/builder.py`, `src/fbf/core/study/plan.py`, `src/fbf/core/execution/pipeline/simulation.py`, `src/fbf/core/domain/policies/types.py`, policy classes, and `src/fbf/core/domain/model/decision_context.py`. | Symbol and field checks; Markdown links/anchors; diff review. | Partially completed — model corrected; state ownership remains deferred. |
| `docs/DECISIONS.md` | Solver status implied all Solver reproduction was deferred. | Distinguished full Solver replication from the completed test-only reproduction of the recorded workbook optimum; linked to `ERN_METHODOLOGY.md`. | `docs/ERN_METHODOLOGY.md:539-554,602-604` and `tests/integration/ern/test_part52_workbook_solver_reproduction.py`. | Claim check against the reproduction test and methodology text. | Completed — corrected and verified. |
| `DATASETS.md` | Dangling `TODO.md` reference for Euro reference rates. | Removed the dangling reference and retained the verified statement that no euro dataset, loader, or Part 52 path exists. | `docs/ERN_METHODOLOGY.md:607-608`, empty `TODO.md`, and the absence of euro dataset code. | Search and source check. | Completed — corrected and verified. |
| `docs/DEVELOPMENT.md` | Claim implied all functional scenarios are committed YAML studies. | Documented that scenarios may be stored as YAML or built directly as `StudyConfiguration` objects in test code. | `tests/functional/ern/test_part52_replication.py:261,278`, `test_ern_part2.py:207`, `test_part42_replication.py:115`, and `fbf.core.application.run_study`. | Source/test inspection; Markdown checks. | Completed — corrected and verified. |
| `docs/EXECUTION_MODES.md` | Example used `ExecutionStrategy` without importing it. | Added `ExecutionStrategy` to the `fbf.core.execution` import block. | `src/fbf/core/execution/__init__.py:87,651`. | Symbol import check; snippet review. | Completed — corrected and verified. |
| Section 3.9 source/test references | Several comments and docstrings name removed specifications, reports, or old paths. | No source or test file was changed because Batch 4b authorizes documentation only. The plan’s current-path reference to persistence tests was already updated in Batch 4a. Historical references remain for provenance. | Section 3.9; repository diff scope. | Confirmed no source/test change in Batch 4b. | Not changed — outside authorized scope; current documentation references corrected, historical references retained. |
| `docs/DESIGN.md` | The same obsolete policy lifecycle appears at lines 184-185. | Left unchanged because `DESIGN.md` was outside the six authorized Batch 4b files. `ARCHITECTURE.md` and `DOMAIN.md` now state the actual single-operation contract. | `docs/DESIGN.md:184-185`; `src/fbf/core/domain/policies/policy.py`. | Cross-document scan found the remaining stale passage. | Not changed — outside scope; follow-up required. |
| `SimulationState` | Two mutable implementations/exports with an unresolved relationship. | Both implementations and exports were left unchanged. `DOMAIN.md` now records both and states that their relationship is unresolved; no canonical or obsolete claim is made. | `src/fbf/core/domain/model/simulation.py:18`, `src/fbf/core/execution/pipeline/simulation.py:24`, and repository-wide `SimulationState` references. | Confirmed neither implementation nor exports changed. | Deferred — requires a separate architectural/API decision. |

**Validation for Batch 4b:** links and anchors pass across all 14 Markdown
files; corrected paths, symbols, and snippets were checked against source;
`git diff --check` is clean; the audit report is unchanged; no source, test,
fixture, example, or configuration file changed; both `SimulationState`
implementations and their exports remain unchanged. A post-edit scan found the
remaining `DESIGN.md` policy-lifecycle claim, recorded in section 4.6.

---

## 4. Additional Cleanup Opportunities

### 4.1 Stale Phase-4 design references

The removed S4/S6 roadmap documents are still referenced by several test and
source docstrings. The actionable cases are the broken file names listed in
section 3.9. The remaining phase labels are historical context and should be
left alone unless a specific inconsistency is proven.

### 4.2 Debt-fixture self-test

`tests/fixtures/debt.py` currently has no production consumer. The only test
that exercises it validates the fixture definitions against the independent
oracle. This is useful known-answer data, but it is not production coverage.
Treat retirement as a decision item, not an automatic deletion.

### 4.3 Test directory naming

`tests/unit/scripts/` tests `tools/ern/` rather than production `src/` code.
The placement is understandable and does not create an orphan or a broken
import. Do not move it in this cleanup.

### 4.4 No duplicate or generated leftovers

No duplicate non-empty tracked files were found. The only identical content is
the expected empty-file hash shared by package markers, `TODO.md`, and
`py.typed`. There are no generated artifacts left inside the inventory scope
beyond the documented frozen datasets and test fixtures.

### 4.5 Audit report disposition

The untracked audit report is an input to this plan, not a cleanup target. Its
eventual disposition (keep as a transient report, archive, or discard) is a
separate decision. Do not delete it while the plan is being reviewed.

### 4.6 Remaining policy-lifecycle documentation

`docs/DESIGN.md:184-185` still describes the removed
`before_simulation → before_month → decide → after_month → after_simulation`
lifecycle. Batch 4b corrected the same stale claim in `ARCHITECTURE.md` and
`DOMAIN.md` but was not authorized to edit `DESIGN.md`. Correct this in a
separate documentation batch; the code contract is
`decide(context: DecisionContext) -> PolicyDecision`.

---

## 5. Explicit Non-Candidates and Do-Not-Change Items

The following were reviewed and should not be removed or consolidated.

| Item | Reason |
|---|---|
| `tests/support/ern/debt_oracle.py` | Independent Part 49 month-transition oracle; used by the oracle test and debt-fixture test. |
| `tests/unit/execution/debt_recurrence_reference.py` | Independent full Part 49/52 trajectory recurrence; used by multiple Numba integration tests. Its scope differs from the month-transition oracle. |
| `src/fbf/core/execution/strategies/parallel_executor.py` and `parallel_execute` | Intentionally retained low-level test-equivalence helper; documented in `docs/PROFILING.md`. Production execution remains sequential. |
| `tests/fixtures/accumulation.py` | Used by seven Part 42/study tests. |
| `tests/benchmarks/_memory_bounded_probe.py` | Executed as a subprocess by path from `test_memory_bounded_execution.py`; not imported. |
| Empty package `__init__.py` files | Required for import/package discovery or `importlib.resources` behavior; not cleanup candidates. |
| `src/fbf/core/py.typed` | Packaging marker for downstream type checkers. |
| `src/fbf/core/domain/optimizer/optimizer.py` and its package exports | Retained compatibility surface: directly importable since `v0.1.0`; future removal requires a deliberate API deprecation/breaking-change decision, not routine cleanup. |
| `src/fbf/core/research/config/__init__.py` | Package marker needed by the packaged-resource path; retain. |
| ERN datasets, fixtures, and oracle constants | Frozen acceptance inputs. Changing them requires the canonical acceptance-matrix process and explicit approval. |
| `TODO.md` | Deliberately empty; keep until real unresolved work exists. |

---

## 6. Proposed Target Structure

The top-level repository layout remains unchanged. The removal of the empty root
directory, the orphan research module, the debt-fixture test move, and the
persistence test move are complete. The optimizer package is retained.

```text
fbf-core/
├── .github/workflows/
├── data/
│   ├── inputs/ern/
│   └── outputs/
├── docs/
├── examples/studies/
├── src/fbf/core/
│   ├── domain/optimizer/          # retained compatibility surface (Batch 2b)
│   ├── research/                  # cape_aggregation.py removed (Batch 2a)
│   └── ...
├── tests/
│   ├── unit/
│   │   ├── execution/
│   │   │   └── test_debt_fixtures.py   # moved from tests/fixtures/ (Batch 3a)
│   │   └── ...
│   ├── integration/
│   │   ├── ern/
│   │   └── persistence/           # moved from tests/infrastructure/ (Batch 3b)
│   ├── functional/
│   ├── contract/
│   ├── benchmarks/
│   ├── fixtures/                  # support code and resources only
│   └── support/
├── tools/ern/
└── ...
```

The `tests/infrastructure/` move was accepted and completed; no exception is
needed in `AGENTS.md`.

---

## 7. Dependency and Test Impact

| Change | Production impact | Test impact | Rollback |
|---|---|---|---|
| Remove `cape_aggregation.py` | Completed in Batch 2a; no importers or exports; never in a tagged release. | Targeted and full suites pass. | Restore file from Git. |
| Retain `domain/optimizer/optimizer.py` and exports | No change; direct import compatibility preserved. | No change; existing suites pass. | Not applicable. |
| Remove stale `.gitignore` entry | None. | None. | Restore two lines. |
| Remove empty `canonical/` | None; directory is untracked. | None. | Recreate directory if ever needed. |
| Correct documentation content | None; documentation only. | Re-run link/claim checks and affected suites. | Revert text edits. |
| Repair stale source/test references | None intended; some evidence strings change wording. | Re-run affected suites. | Revert text edits. |
| Move `test_debt_fixtures.py` | Completed in Batch 3a; no production impact. | Node IDs change; 25-test collection count unchanged. | Move file back. |
| Move `tests/infrastructure/` | Completed in Batch 3b; no production impact. | Updated one absolute import; 180-test collection unchanged; node IDs changed. | Move directory back and restore import. |
| Add Part 52 example smoke test | None. | Adds a fast parse/build test if approved. | Remove the test. |
| Retire debt fixture suite | None. | Removes fixture-only tests, not production coverage. | Restore both files. |

No production dependency, public Tier 1 symbol, or Tier 2 export was changed.
Batch 2a removed only an untagged, unexported Tier 3 file; the full suite and
quality checks pass afterward. The `Optimizer` module is Tier 3 but is retained
because its direct import path has shipped since `v0.1.0`. Its package exports
were not changed, so the existing compatibility surface remains intact.

---

## 8. Prioritized Implementation Sequence

Each batch below is a separately reviewable change set. Do not commit any batch
without explicit authorization.

### Batch 1: Safe filesystem and ignore hygiene — Completed

1. Removed the stale `.gitignore` comment and path.
2. Removed the empty `canonical/` directory.

Validation passed: `git check-ignore` reports no matching rule,
`test ! -e canonical` passes, `git diff --check` is clean, and contract tests
passed (`21 passed in 1.44s`).

### Batch 2a: Orphan research module — Completed

1. Verified no current importer, indirect consumer, package export, test
   dependency, script reference, documentation reference, or configuration
   dependency.
2. Confirmed `5324d72` is not contained in any tag and the file is absent from
   every tag tree.
3. Reviewed the file history; the only non-code mentions were roadmap prose.
4. Deleted `src/fbf/core/research/cape_aggregation.py`.
5. Re-ran the repository-wide reference search after deletion; no references
   remain outside this plan and the audit report.

Validation passed: targeted `356 passed, 5 skipped`; full suite
`2323 passed, 128 skipped` (170.93s); `ruff check .` passed;
`mypy --strict .` passed.

### Batch 2b: Optimizer compatibility decision — Completed (retain)

Decision: retain `src/fbf/core/domain/optimizer/optimizer.py` and its exports.
No deletion, move, rename, modification, or export change was made.

Rationale: the module has been directly importable since `v0.1.0`. Although it
is not exposed through `fbf.core.domain` or Tier 1/2, its direct import path is
an existing compatibility surface. Removing it would break consumers relying on
that path; the benefit does not justify the break. Any future removal requires a
deliberate API deprecation/breaking-change decision, not routine cleanup.

Validation: existing optimization, contract, and full suites pass unchanged.

### Batch 3a: Debt fixture test move — Completed

1. Moved `tests/fixtures/test_debt_fixtures.py` to
   `tests/unit/execution/test_debt_fixtures.py`.
2. Selected `tests/unit/execution/` because the test validates execution-layer
   debt fixtures and that directory already contains the related Part 49/52 and
   debt-flow tests.
3. Confirmed the test uses absolute imports, so no path adjustment was needed.
4. Confirmed no test, tool, script, pytest configuration, or CI workflow
   referenced the old path.
5. Verified the new file is byte-identical to the HEAD version and that the
   25-test collection count and results are unchanged.

Validation passed: new-path collection `25 tests`; direct run `25 passed`;
`tests/unit/execution` `336 passed`; full suite `2323 passed, 128 skipped`
(183.16s); `ruff check .` passed; `mypy --strict .` passed.

### Batch 3b: Infrastructure test directory move — Completed

1. Inventoried and classified all nine test modules plus the package marker in
   `tests/infrastructure/`; all exercise SQLite persistence/query integration.
2. Recorded the full disposition table and old→new mapping in section 3.8.
3. Established the pre-move baseline: `180 tests collected`, `180 passed in
   1.26s`.
4. Moved `tests/infrastructure/` to `tests/integration/persistence/`.
5. Updated the one internal import in the moved streaming persistence test.
6. Confirmed test collection still discovers the same 180 test cases.

Validation passed: `180 tests collected`; direct run `180 passed in 1.19s`;
full suite `2323 passed, 128 skipped` (172.98s); contract suite `21 passed`;
`ruff check .` passed; `mypy --strict .` passed; `git diff --check` clean. No
`RUN_ERN_E2E` command was run.

### Batch 4a: Documentation audit — Completed

1. Inventoried every Markdown document, `TODO.md`, and doc-like YAML.
2. Checked all Markdown links and anchors; no broken links or anchors were
   found.
3. Compared documentation claims with current exports, source modules, tests,
   sibling repositories, and package metadata.
4. Classified each document as current, correction candidate, or needing
   further investigation; recorded the results in section 3.10.
5. Modified only this plan. No documentation file was edited, moved, merged, or
   removed.

### Batch 4b: Documentation corrections — Completed

1. Corrected `ARCHITECTURE.md` topology, executor signature, dependency wording,
   persistence terminology, execution data-flow wording, and dataset-directory
   description.
2. Corrected the current model in `DOMAIN.md` without changing domain code or
   declaring either `SimulationState` implementation obsolete.
3. Distinguished full solver replication from completed test-only
   recorded-optimum reproduction in `DECISIONS.md`.
4. Removed the dangling `TODO.md` reference in `DATASETS.md`.
5. Added the missing `ExecutionStrategy` import in `EXECUTION_MODES.md`.
6. Qualified the examples/fixtures claim in `DEVELOPMENT.md`; left
   `ern_part52.yaml` validation as a separate Batch 5 decision.
7. Did not change source or test references because Batch 4b is documentation
   only. Section 3.9 remains the register for those follow-ups; historical
   references were preserved.
8. Left `README.md`, `AGENTS.md`, `DESIGN.md`, `PROFILING.md`, `TODO.md`, and
   `ERN_METHODOLOGY.md` content in place. A stale policy lifecycle remains in
   `DESIGN.md:184-185` and is recorded as a follow-up.

The item-by-item evidence and final statuses are in section 3.11. Validation:
Markdown links/anchors pass; corrected paths/symbols were checked; the audit
report is unchanged; no source, test, fixture, example, or configuration file
changed; both `SimulationState` implementations and their exports are unchanged;
`git diff --check` is clean. No `RUN_ERN_E2E` command was run because no
execution/test code changed.

### Batch 5: Decision items

1. Decide whether to add a Part 52 example smoke test or document the example as
   illustrative.
2. Decide whether the debt-fixture self-test and `tests/fixtures/debt.py` should
   be retained or retired.
3. If desired, add one sentence to the documentation stating that an empty
   `TODO.md` is the valid no-open-items state.

Do not execute these until the owner chooses the intended behavior.

### Batch 6: Final quality gate

Run from a clean checkout after the approved batches:

```bash
ruff check .
mypy --strict .
pytest -p no:cacheprovider
pytest tests/contract/ -p no:cacheprovider
git diff --check
```

Do not set `RUN_ERN_E2E=1` for routine cleanup validation. Heavyweight ERN
suites remain manual and are not part of this cleanup.

---

## 9. Validation Commands

### General quality gate

```bash
ruff check .
mypy --strict .
pytest -p no:cacheprovider
pytest tests/contract/ -p no:cacheprovider
```

### Dead-code reference search

```bash
rg -n 'cape_aggregation|Optimizer|OptimizationResult' src tests tools docs \
  --glob '!docs/REPOSITORY_FILE_AUDIT.md' \
  --glob '!docs/REPOSITORY_CLEANUP_PLAN.md'
```

### Test collection

```bash
pytest --collect-only -q
```

### Ignore rule and directory checks

```bash
git check-ignore -v docs/roadmap/s57_benchmark_results.json || true
test ! -e canonical
```

The `git check-ignore` command should report no rule after the `.gitignore`
change.

### Stale-reference scan

```bash
rg -n \
  'INFRASTRUCTURE_SQLITE_PERSISTENCE_SPECIFICATION|PARALLEL_EXECUTION_SPECIFICATION|RESEARCH_EXECUTOR_SPECIFICATION|NEXT_SESSION|ern_part20_replication|ern_part20_e2e_audit|test_part20_replication|S4_ARCHITECTURAL_DESIGN_REVIEW|RESEARCH_STRATEGYCOMPARATOR_IMPLEMENTATION_HANDOFF' \
  src tests tools docs \
  --glob '!docs/REPOSITORY_FILE_AUDIT.md' \
  --glob '!docs/REPOSITORY_CLEANUP_PLAN.md'
```

### Targeted suites by batch

```bash
pytest tests/unit/research tests/unit/optimization tests/contract -p no:cacheprovider
pytest tests/unit/execution/test_debt_fixtures.py tests/integration/persistence -p no:cacheprovider
```

The persistence tests now live under `tests/integration/persistence`; no old
infrastructure path should be restored or reintroduced.

---

## 10. Uncertainties and Human-Approval Decisions

1. **Tier 3 compatibility decisions are resolved.** No in-repository importer
   of `cape_aggregation.py` existed, and the file never appeared in a tag; it
   was therefore removed after explicit authorization. `domain/optimizer/optimizer.py`
   has shipped since `v0.1.0` and remains directly importable as
   `fbf.core.domain.optimizer`; the owner chose to retain it as a compatibility
   surface. Any future removal requires a deliberate API deprecation/breaking
   change, not routine cleanup.
2. **Part 52 example status.** The file is useful and well documented but has no
   automated reference. The owner must choose between smoke coverage and
   illustrative-status documentation.
3. **Debt-fixture retirement.** The fixture self-test is deliberately maintained
   but does not exercise production code. It was moved in Batch 3a; retire it
   only with explicit confirmation.
4. **Infrastructure test move is resolved.** `tests/infrastructure/` was moved
   to `tests/integration/persistence/` in Batch 3b; no documented exception was
   retained. The node-ID change was accepted and validation passed.
5. **Empty TODO register.** Keeping it empty is consistent with the documented
   resolution rule. The dangling `DATASETS.md` reference was removed in Batch
   4b; no open Euro dataset work is recorded.
6. **Domain state model.** Two mutable `SimulationState` classes are exported:
   one from `domain.model.simulation` and one from
   `execution.pipeline.simulation`. No current production Numba executor
   references either directly. `docs/DOMAIN.md` now records both and states that
   their ownership relationship is unresolved. This requires a separate
   architectural/API decision; neither implementation, export, nor import was
   changed.
7. **Documentation topology.** Batch 4b states the three-repository ecosystem
   against confirmed evidence from `fbf-cli` and `fbf-ui`. No documentation move
   or merge is proposed.
8. **ERN cross-repo status.** `ERN_METHODOLOGY.md:605-608` contains current
   cross-repo project status. Keeping it is acceptable; moving it requires a
   stable destination and owner approval.
9. **Audit report disposition.** The untracked audit report is not part of the
   cleanup scope. Its eventual retention or removal is a separate decision.
10. **Commit authorization.** No batch may be committed until the owner
    authorizes it. The normal rule is one commit per approved phase.

---

## 11. Final Statement

This plan is based on the current repository state and the completed file audit.
Batch 1, Batch 2a, the Batch 2b decision, Batch 3a, Batch 3b, Batch 4a, and
Batch 4b are complete. Batch 2a removed only
`src/fbf/core/research/cape_aggregation.py`; Batch 2b retained the optimizer
module and exports unchanged; Batch 3a moved only
`tests/fixtures/test_debt_fixtures.py` to
`tests/unit/execution/test_debt_fixtures.py`, byte-for-byte; Batch 3b moved the
persistence tests to `tests/integration/persistence/` and updated one import;
Batch 4a modified only this plan and found no broken Markdown links or anchors;
Batch 4b corrected `ARCHITECTURE.md`, `DATASETS.md`, `docs/DECISIONS.md`,
`docs/DEVELOPMENT.md`, `docs/DOMAIN.md`, and `docs/EXECUTION_MODES.md`.

No production source, test logic, assertions, fixtures, examples, configuration,
`SimulationState` implementation/export, or other unauthorized documentation
file was modified in Batch 4b. Nothing was staged, committed, or pushed.

Recommended next step: authorize the remaining decision-item batches separately.
The `SimulationState` ownership question and `ern_part52.yaml` validation remain
unresolved and require explicit decisions. Defer Batch 2b follow-up unless the
owner explicitly chooses a future deprecation/breaking change.
