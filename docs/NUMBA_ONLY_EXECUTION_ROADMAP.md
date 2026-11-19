# Numba-Only Execution Roadmap

Status: COMPLETE (with documented UI full-suite caveat)

## Objective

Make Numba the only production simulation execution implementation across
`fbf-core`, `fbf-cli`, and `fbf-ui`.

Required end state:

- No public execution backend selector.
- No public execution strategy selector.
- No obsolete worker or batch-size compatibility parameters.
- No production or test-only multiprocessing simulation execution helper.
- One capability-driven Numba executor dispatcher.
- Numba internal parallelism remains (`parallel=True`, `numba.prange`).
- Streaming, materialization, progress reporting, and profiling remain.
- Core, CLI, and UI APIs and dependency constraints are coordinated.

## Non-Goals

- Removing or retuning Numba kernels.
- Removing `numba.prange` or `parallel=True`.
- Removing meaningful execution options such as materialization limits,
  streaming slices, progress callbacks, or profilers.
- Removing UI job-orchestration concurrency.
- Removing CLI `compare --strategy`, which filters study strategies.
- Renaming UI `execution_mode="FAST"` provenance during this migration.
- Running heavyweight ERN E2E tests without separate authorization.
- Committing, staging, pushing, tagging, rebasing, or creating branches.

## Preflight

Observed before edits:

| Repository | Path | Branch | HEAD | Working tree |
|---|---|---|---|---|
| Core | `/mnt/datos/workspace/fbf/fbf-core` | `main` | `4cbd39c8bf49cb5765524c203e0176c92cc2f870` | clean |
| CLI | `/mnt/datos/workspace/fbf/fbf-cli` | `main` | `b0ce829fde419164c2b7405eedc2cd81d9eb5782` | dirty |
| UI | `/mnt/datos/workspace/fbf/fbf-ui` | `main` | `6e7afcf467fac3bfda0f40a4601bdf55fcd1d33f` | dirty |

Pre-existing CLI and UI changes must be preserved. They are unrelated user
work and are not part of this initiative. No change may be staged or committed.

Package versions before this initiative:

- Core `0.4.0`
- CLI `0.1.0`, dependency `fbf-core[numba]>=0.3.0,<0.4.0`
- UI `0.1.0`, dependency `fbf-core[numba]>=0.3.0,<0.4.0`

## Architectural Decisions

1. One fail-closed capability dispatcher replaces backend/strategy routing.
   The dispatcher selects exactly one Numba executor for the whole plan and
   raises `UnsupportedConfigurationError` when no executor supports it.
2. The existing AUTO capability behavior is the starting point. Mixed plans
   receive explicit tests; unsupported mixed plans must fail rather than fall
   back.
3. The canonical single-process orchestration moves out of
   `parallel_executor.py` into `plan_executor.py`.
4. `sequential_execute` is replaced by a single `execute_plan` low-level
   operation. It is not an execution-mode selector.
5. Removed public APIs are not replaced with compatibility aliases.
6. UI `execution_mode="FAST"` remains informational provenance.
7. `docs/REPOSITORY_FILE_AUDIT.md` remains a historical snapshot.
8. Core becomes `0.5.0`. CLI and UI become `0.2.0` and require
   `fbf-core[numba]>=0.5.0,<0.6.0`.
9. Numba's optional dependency policy is unchanged: `numpy>=2.1`,
   `numba>=0.68`, with no upper pin and no lockfile.

## Batches

### Batch 1 — Core Execution API and Routing

Repository: Core

Affected areas:

- `src/fbf/core/__init__.py`
- `src/fbf/core/execution/__init__.py`
- `src/fbf/core/application/__init__.py`
- `src/fbf/core/execution/errors.py`
- Core tests and contracts

Work:

- [x] DONE Remove `ExecutionBackend` and `ExecutionStrategy`.
- [x] DONE Remove `ExecutionOptions.backend`, `.strategy`, `.workers`,
      `.batch_size`.
- [x] DONE Remove strategy validation.
- [x] DONE Consolidate routing into `_select_numba_executor`.
- [x] DONE Preserve Part 52, Part 49, Part 49 buy-and-hold, and generic
      Numba capability routing.
- [x] DONE Preserve fail-closed and missing-Numba behavior.
- [x] DONE Update public exports, callers, tests, and contracts.
- [x] DONE Add assertions that removed symbols are absent.

Acceptance criteria:

- `ExecutionOptions` contains no selector or obsolete concurrency fields.
- One dispatcher selects the Numba executor.
- Unsupported configurations raise `UnsupportedConfigurationError`.
- Missing Numba raises a clear `ModuleNotFoundError`.
- No alternative engine fallback exists.
- Targeted Core tests and contracts pass.

Validation:

```bash
ruff check .
mypy --strict .
pytest tests/unit/execution tests/contract -p no:cacheprovider
```

Status: DONE

### Batch 2 — Remove Test-Only Multiprocessing Execution

Repository: Core

Affected areas:

- `src/fbf/core/execution/strategies/parallel_executor.py`
- New `src/fbf/core/execution/plan_executor.py`
- `src/fbf/core/execution/__init__.py`
- `src/fbf/core/execution/strategies/__init__.py`
- Execution, streaming, determinism, integration, and benchmark tests
- Architecture and design documentation

Work:

- [x] DONE Move canonical orchestration to `plan_executor.py`.
- [x] DONE Preserve progress, summary stripping, profiling, and
      deterministic behavior.
- [x] DONE Delete `parallel_execute`, `ParallelExecutor`,
      `ExecutionConfig`, batching, worker initialization, and pool helpers.
- [x] DONE Remove parallel-equivalence tests and benchmarks.
- [x] DONE Preserve meaningful determinism, streaming, progress, and
      materialization tests.
- [x] DONE Update architecture and design documents.
- [x] DONE Keep Numba kernel-level parallelism unchanged.

Acceptance criteria:

- No multiprocessing or thread-pool simulation execution helper remains.
- Single-process orchestration is preserved in a clearly named module.
- Streaming, progress, summary stripping, and profiling still work.
- Numba kernels retain internal parallelism.

Validation:

```bash
ruff check .
mypy --strict .
pytest tests/unit/execution tests/integration -p no:cacheprovider
```

Status: DONE

### Batch 3 — Remove Obsolete Worker and Compatibility Parameters

Repository: Core

Affected areas:

- `src/fbf/core/optimization/part52_evaluator.py`
- `src/fbf/core/optimization/__init__.py`
- `src/fbf/core/research/part20_planner.py`
- `src/fbf/core/execution/deterministic.py`
- Core tests, benchmarks, and ERN harness support

Work:

- [x] DONE Remove `Part52EvaluatorConfig.workers`.
- [x] DONE Remove `workers` from `optimize_part52`.
- [x] DONE Simplify Part 20 planner execution.
- [x] DONE Remove ignored deterministic `options` parameter.
- [x] DONE Remove worker plumbing from tests, benchmarks, and ERN
      harnesses.
- [x] DONE Preserve canonical ERN acceptance data and semantics.

Acceptance criteria:

- No obsolete worker parameters remain in Core public APIs.
- No execution-strategy override remains in research planners.
- Canonical ERN acceptance data is unchanged.
- Targeted optimization, research, and harness tests pass.

Validation:

```bash
ruff check .
mypy --strict .
pytest tests/unit/optimization tests/unit/research -p no:cacheprovider
```

Status: DONE

### Batch 4 — CLI Integration

Repository: CLI

Affected areas:

- `src/fbf/cli/commands/run_command.py`
- `src/fbf/cli/commands/compare_command.py`
- `src/fbf/cli/commands/optimize_command.py`
- CLI tests, examples, configuration schema, and architecture documentation
- CLI package version and Core dependency constraint

Work:

- [x] DONE Remove execution-related `--workers` options.
- [x] DONE Remove worker resolution, ETA adjustment, and warnings.
- [x] DONE Remove `ExecutionBackend` and `ExecutionStrategy` imports and
      arguments.
- [x] DONE Preserve `compare --strategy`.
- [x] DONE Update CLI tests and docs.
- [x] DONE Require `fbf-core[numba]>=0.5.0,<0.6.0`.

Acceptance criteria:

- CLI no longer offers or passes execution worker/backend/strategy settings.
- Study-strategy comparison remains unchanged.
- CLI tests pass against the new Core.
- No unrelated CLI changes are lost.

Validation:

```bash
ruff check .
mypy --strict .
pytest -p no:cacheprovider
```

Status: DONE

### Batch 5 — UI Integration

Repository: UI

Affected areas:

- `src/fbf/ui/orchestration/execution_service.py`
- UI tests and dependency constraint

Work:

- [x] DONE Remove `ExecutionBackend` import and `backend=FAST`.
- [x] DONE Keep `_DEFAULT_WORKERS` and `ThreadPoolExecutor`.
- [x] DONE Keep `execution_mode="FAST"` informational provenance.
- [x] DONE Update tests and require `fbf-core[numba]>=0.5.0,<0.6.0`.

Acceptance criteria:

- UI uses the simplified Core execution API.
- UI job concurrency remains intact.
- UI integration tests pass against the new Core.
- No unrelated UI changes are lost.

Validation:

```bash
ruff check .
mypy --strict .
pytest -p no:cacheprovider
```

Status: DONE — integration complete; the full-suite caveat is recorded under
Batch 7 validation evidence.

### Batch 6 — Documentation, Contracts, and Version Coordination

Repositories: Core, CLI, UI

Affected areas:

- Core `pyproject.toml` and `src/fbf/core/__init__.py`
- CLI/UI package versions, runtime versions, and dependency constraints
- CLI/UI dependency and version documentation
- `README.md`
- `ARCHITECTURE.md`
- `docs/DESIGN.md`
- `docs/DECISIONS.md`
- `docs/PROFILING.md`
- `docs/DOMAIN.md`
- `docs/EXECUTION_MODES.md`
- CLI/UI architecture documentation

Work:

- [x] DONE Delete or replace `docs/EXECUTION_MODES.md`.
- [x] DONE Update incoming links.
- [x] DONE Add a new durable decision superseding FAST-only.
- [x] DONE Remove backend/strategy/parallel-helper descriptions.
- [x] DONE Keep repository audit historical.
- [x] DONE Bump Core to `0.5.0`.
- [x] DONE Bump CLI/UI to `0.2.0` and update Core constraints.
- [x] DONE Align CLI runtime `__version__` and fallback to `0.2.0`.
- [x] DONE Align UI runtime `__version__` to `0.2.0`.
- [x] DONE Correct stale CLI/UI Core dependency documentation.
- [x] DONE Update the UI reproducibility envelope to Core `0.5.0` and UI
      `0.2.0`.
- [x] DONE Preserve Numba dependency policy.

Acceptance criteria:

- Documentation describes one Numba execution path.
- No obsolete selector documentation remains.
- Version constraints accept Core `0.5.0`.
- CLI and UI runtime versions match their package metadata.
- Historical records are preserved as historical.

Validation:

```bash
rg -n 'ExecutionBackend|ExecutionStrategy|parallel_execute|ParallelExecutor|ExecutionConfig|default_workers|ERN_E2E_WORKERS' .
rg -n 'fbf-core(\[numba\])?[><=]' README.md AGENTS.md ARCHITECTURE.md docs/DECISIONS.md
git diff --check
```

Status: DONE — corrected after the final read-only review identified stale
runtime versions and dependency documentation.

### Batch 7 — Final Cross-Repository Validation

Repositories: Core, CLI, UI

Work:

- [x] DONE Recheck three-repository branch, HEAD, and working-tree state.
- [x] DONE Run Core quality gates.
- [x] DONE Run CLI quality gates.
- [x] DONE Run UI lint, strict mypy, and targeted tests; isolate and classify
      full-suite failures.
- [x] DONE Search all repositories for obsolete references.
- [x] DONE Search CLI/UI active documentation for stale Core constraints.
- [x] DONE Classify remaining matches.
- [x] DONE Verify no pre-existing changes were lost.
- [x] DONE Run `git diff --check` in each repository.
- [x] DONE Confirm no staging, commits, pushes, tags, or branches.
- [x] DONE Confirm heavyweight ERN E2E tests were not run.

Acceptance criteria:

- All routine tests pass or failures are isolated and reported.
- Remaining matches are legitimate study strategies, Numba kernel settings,
  UI job concurrency, or historical records.
- Working trees contain only intended changes plus preserved pre-existing work.

Status: DONE — with the UI full-suite caveat recorded below.

## Validation Evidence

### Core

- Ruff and strict mypy pass.
- Full suite: 2262 passed, 128 skipped.
- Contract suite: 21 passed.
- These results were established during migration validation and were not
  rerun for the documentation-only release-consistency corrections.
- Heavyweight ERN E2E tests were intentionally not run because they require
  explicit `RUN_ERN_E2E=1` opt-in.

### CLI

- Ruff and strict mypy pass.
- Full suite: 318 passed.
- Runtime `__version__` and the `--version` fallback are `0.2.0`; package
  metadata declares `0.2.0`.

### UI

- Ruff and strict mypy pass.
- Full suite: 243 passed, 2 failed, 44 errors.
- The common failure is a test-fixture/schema mismatch:
  `sqlite3.IntegrityError: NOT NULL constraint failed:
  planned_units.dataset_start_date`.
- Affected groups:
  - `tests/browser/test_p11_playwright.py`
  - `tests/unit/test_p11_persistence_api.py`
  - `tests/unit/test_p11_persistence_service.py`
  - `tests/unit/test_p11_stage5_frontend.py`
- This issue predates the Numba migration and is unrelated to it. The
  `planned_units.dataset_start_date` NOT NULL constraint was added by Core
  commit `3da3caf` dated 2026-11-09, while UI HEAD `6e7afcf` is dated
  2026-11-05. The failing P11 seeders and tests are unchanged, and this
  migration did not modify persistence schema, seeders, or P11 tests.
- Targeted UI suite result: 116 passed. This result was reported during the
  migration validation pass, but the previous read-only review could not
  independently locate its saved log.
- The full UI suite was not rerun during the release-consistency correction
  pass; only version-related tests, Ruff, and strict mypy were rerun.

### Release Consistency

- CLI and UI runtime versions match their `pyproject.toml` declarations at
  `0.2.0`.
- CLI and UI dependency declarations and active documentation use
  `fbf-core[numba]>=0.5.0,<0.6.0`.
- No active CLI/UI documentation retains the obsolete `<0.4.0` ceiling.
- The UI reproducibility envelope shows Core `0.5.0` and UI `0.2.0`.

## Cross-Repository Release Coordination

Order:

1. Core API and execution changes.
2. Core tests and contracts.
3. CLI integration against local Core.
4. UI integration against local Core.
5. Version and dependency constraint updates.
6. Final cross-repository validation.

Core `0.5.0` is a breaking minor release. CLI and UI `0.2.0` releases must
declare `fbf-core[numba]>=0.5.0,<0.6.0`. No lockfile is introduced.

## Deviation Log

- No architectural deviations from the Numba-only design.
- The final read-only review found release-consistency defects: CLI/UI runtime
  versions and dependency documentation lagged package metadata. These were
  corrected in Batch 6 without changing the architecture.
- The UI full-suite failures are pre-existing P11 fixture/schema
  incompatibilities, not deviations from this migration.

## Final Status

- Implementation: COMPLETE with documented UI full-suite caveat
- Release consistency: COMPLETE
- Core working tree: implementation and documentation changes present
- CLI working tree: implementation changes plus preserved pre-existing work
- UI working tree: implementation changes plus preserved pre-existing work
- Heavyweight ERN E2E: intentionally not run
- Commits: none
