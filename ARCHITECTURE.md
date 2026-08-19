# FBF Architecture — FIRE Backtesting Framework

This document describes the high-level architecture of the FIRE Backtesting
Framework (FBF): the responsibilities of each repository, the public API
boundary, the dependency direction, and the local development workflow.

---

## 1. Repository Overview

The FBF system is split into two standalone Git repositories that are
**peers with no parent Git repository**:

```
/workspace/
├── fbf-core/          — simulation engine and research library (this repo)
└── fbf-cli/           — command-line interface and presentation frontend
```

A third repository is preserved as a read-only historical reference:

```
└── simulador_jubilacion/   — legacy monorepo (archived; do not modify)
```

There is **no umbrella `fbf/.git`** and no monorepo layer.

---

## 2. fbf-core — Simulation Engine

### 2.1 Responsibility

`fbf-core` is the computation and research library. It owns:

* **Domain model** — value objects (`Money`, `Portfolio`, `Asset`, `Dataset`,
  market snapshots, decision contexts) with deterministic `Decimal` arithmetic.
* **Policy interfaces** — abstract protocols for withdrawal and allocation
  decisions; concrete built-in implementations (`FixedRealWithdrawalPolicy`,
  etc.).
* **Canonical 9-step monthly simulation pipeline** — the ordered sequence of
  steps executed per calendar month:
  1. Build Decision Context
  2. Withdrawal Decision
  3. Withdrawal Execution
  4. Allocation Decision
  5. Portfolio Rebalance
  6. Market Evolution
  7. Monthly Result Builder
  8. Simulation State Update
  9. (Internal close-out / statistics accumulation)
* **Closed-form fast path** — analytical recurrence for constant-policy studies,
  validated to be bit-exact against the reference pipeline.
* **Parallel / reference-chaining execution strategies** — deterministic
  multi-worker execution, historical chaining for reference datasets.
* **Study planning** — cohort generation, parameter sweeps, experiment
  definitions.
* **SWR optimisation** — binary-search solver for maximum safe withdrawal rates.
* **Persistence** — SQLite-backed study repository (codecs, schema, context).
* **ERN oracle** — canonical Decimal truth table for regression testing.

### 2.2 What fbf-core must NOT contain

* Any import from `fbf.cli` or any CLI package.
* Argument parsing, `argparse`, `sys.argv` access, or presentation logic.
* `pyyaml` at runtime (YAML is an optional, lazily imported convenience; the
  caller is expected to own the YAML dependency).
* UI progress display, formatting utilities, or console escape sequences.

---

## 3. fbf-cli — Command-Line Interface

### 3.1 Responsibility

`fbf-cli` is the user-facing frontend. It owns:

* **Entry points** — `fbf` and `sim-retire` console scripts.
* **Command dispatch** — `run`, `validate`, `compare`, `optimize`, `list`,
  `export`, `config` sub-commands.
* **YAML loading** — the one place that owns the `pyyaml` runtime dependency
  and converts YAML study files into structured data.
* **Presentation** — human-readable tables, progress bars, formatted error
  messages, stdout/stderr routing.
* **Integration glue** — translates CLI arguments into `fbf.core` API calls and
  formats results for the user.
* **CLI-level tests** — black-box tests that drive the entry point and assert on
  console output and exit codes.

### 3.2 What fbf-cli must NOT contain

* Any simulation arithmetic or domain logic.
* Imports of Core internal modules (Tier 3: `fbf.core.study.internal`,
  `fbf.core.execution.pipeline.steps`, etc.).
* Copies or re-implementations of any Core business logic.

---

## 4. Public Core API Boundary

The Core API is organised in three access tiers:

| Tier | Modules | Access |
|------|---------|--------|
| **Tier 1** | `fbf.core` (root facade) | All consumers |
| **Tier 2** | `fbf.core.domain`, `fbf.core.domain.model`, `fbf.core.domain.policies`, `fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence` | CLI production code and tests |
| **Tier 3** | `fbf.core.study.internal`, `fbf.core.execution.pipeline.steps`, and all other non-facade submodules | Core tests only — **never CLI** |

CLI production code and CLI tests are **forbidden** from importing Tier 3 modules.
Core tests may freely test implementation details.

### 4.1 Tier 1 Facade (`fbf.core.__all__`)

```python
from fbf.core import (
    StudyConfiguration,
    StudyPlanResult,
    build_study_plan,
    ExecutionMode,
    ExecutionOptions,
    execute_study_plan,
    ResearchExecutionResult,
    optimize_study_swr,
    StudyRepository,
    create_study_repository,
    CoreError,
)
```

---

## 5. Dependency Direction

```
fbf-cli  ──depends on──►  fbf-core  ──► Python stdlib only
             (pyyaml)
```

* `fbf-core` has **zero third-party runtime dependencies**. It runs exclusively
  on the Python 3.13 standard library.
* `fbf-cli` depends on `fbf-core>=0.1.0,<0.2.0` and `pyyaml>=6.0`.
* The dependency arrow is **strictly one-directional**. Core never imports CLI.

### 5.1 Import Law

| Importer | May import |
|----------|-----------|
| `fbf.core.*` | Python stdlib; other `fbf.core.*` submodules (no upward domain violations) |
| `fbf.cli.*` | Python stdlib; `fbf.core` Tier 1 & Tier 2; `pyyaml` |
| CLI tests | Same as `fbf.cli.*` |
| Core tests | Python stdlib; all of `fbf.core.*` including Tier 3 |

---

## 6. Layer Isolation Rules (enforced by contract tests)

1. **Domain purity:** `fbf.core.domain` must never import `fbf.core.execution`,
   `fbf.core.study`, `fbf.core.optimization`, `fbf.core.persistence`, or
   `fbf.cli`.
2. **Execution / optimization isolation:** `fbf.core.execution` must never
   import `fbf.core.optimization`.
3. **CLI→Core direction:** `fbf.cli` may only import Core via Tier 1 or Tier 2.
4. **No legacy imports:** No `engine.*`, `research.*`, `infrastructure.*`, or
   old `cli.*` imports may appear in any production source file.

These rules are enforced by automated AST contract tests in each repository's
`tests/contract/` directory.

---

## 7. Repository Interaction

Both repositories are independently installable Python packages:

```bash
pip install fbf-core    # installs simulation engine only
pip install fbf-cli     # installs CLI + pulls in fbf-core and pyyaml
```

For local development, install Core first, then CLI against the local Core:

```bash
# In fbf-core/
pip install -e .

# In fbf-cli/
pip install -e ".[dev]"
```

The constraint `fbf-core>=0.1.0,<0.2.0` ensures CLI tracks the current minor
series. Breaking Core API changes (during 0.x development) require a Core minor
version increment.

---

## 8. Local Development Workflow

### 8.1 One-time setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate

# Install fbf-core in editable mode
pip install -e /path/to/fbf-core

# Install fbf-cli with dev extras
pip install -e "/path/to/fbf-cli[dev]"
```

### 8.2 Running tests

```bash
# Core tests (must pass without any CLI installed)
cd fbf-core && pytest

# CLI tests (must resolve Core from installed package, not local source tree)
cd fbf-cli && pytest

# Type checking
mypy --strict src   # in each repo
```

### 8.3 Linting

```bash
ruff check src tests   # in each repo
```

### 8.4 Building distribution artifacts

```bash
# Core wheel
cd fbf-core && python -m build --wheel

# CLI wheel (install Core wheel first)
cd fbf-cli && python -m build --wheel
```

---

## 9. Key Invariants

1. `fbf-core` is usable without `fbf-cli` installed.
2. `fbf-core` has zero third-party runtime dependencies.
3. All financial arithmetic uses `decimal.Decimal` — no `float` for monetary values.
4. The fast path is bit-exact against the reference monthly pipeline.
5. ERN oracle acceptance matrix passes with exact `Decimal` equality (no float tolerance).
6. CLI imports exclusively through the public Core API (Tier 1 and Tier 2).
7. No history is rewritten in either repository after the P1.9/P1.10 migration commit.
8. The legacy monorepo (`simulador_jubilacion`) is preserved as a read-only historical archive.
