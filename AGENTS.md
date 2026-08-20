# AGENTS.md — fbf-core Agent Guide

This is the standalone `fbf-core` repository.
It contains the simulation engine, research library, and ERN oracle.

---

## Repository Identity

| Property | Value |
|----------|-------|
| Package name | `fbf-core` |
| Root namespace | `fbf.core` |
| Third-party runtime deps | **Zero** |
| Python requirement | ≥ 3.13 |
| Test suite | 692 tests (unit / integration / infrastructure / benchmarks / oracle / contract) |

---

## Absolute Rules

1. **Never import from `fbf.cli` or any CLI package.**
2. **Never add a third-party runtime dependency** to `[project] dependencies` in `pyproject.toml`.
   Dev dependencies (`[project.optional-dependencies] dev`) are exempt.
3. **All monetary arithmetic uses `decimal.Decimal`.** Never use `float` for financial values.
4. **The domain layer must remain pure.** `fbf.core.domain` must never import from
   `fbf.core.execution`, `fbf.core.study`, `fbf.core.optimization`, `fbf.core.persistence`,
   or `fbf.cli`.
5. **`fbf.core.execution` must never import `fbf.core.optimization`.**
6. **No legacy imports** (`engine.*`, `research.*`, `infrastructure.*`, old `cli.*`) may appear
   in any production source file.
7. **Do not add `argparse`, `sys.argv`, or any presentation logic to Core.**
8. **Do not modify `tests/oracle/ern/`** constants without a corresponding update to
   the canonical ERN acceptance matrix and explicit user approval.
9. **Datasets are external to the wheel.** Never embed datasets in the package or
   hardcode dataset paths; discovery is explicit via `data_dir` (see `DATASETS.md`).
10. **No machine-specific absolute paths** (`/tmp/`, `/home/`, `/Users/`, `C:\`) in
    `src/` or `tests/` — tests use `tmp_path` (enforced by `tests/contract/`).
11. **External CLI-binary use is confined to `tests/oracle/`** — the black-box ERN
    harness is the only test surface allowed to drive the installed `sim-retire` binary
    (enforced by `tests/contract/test_core_boundaries.py`).

---

## Public API Tiers

| Tier | Modules | Who may import |
|------|---------|----------------|
| Tier 1 | `fbf.core` (root `__init__`) | All consumers |
| Tier 2 | `fbf.core.domain`, `fbf.core.domain.model`, `fbf.core.domain.policies`, `fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence` | CLI and Core |
| Tier 3 | All other submodules | Core tests only — never CLI production. CLI **tests** may use a small, explicitly documented allow-list (see `fbf-cli/tests/contract/test_cli_boundaries.py`). |

---

## Quality Gate

Run every command below from a clean checkout **before** committing to `fbf-core`.
This is the reproducible Phase 2 closure gate (2.10). A change that does not
pass every step is not committed.

```bash
# 1. Lint — must report "All checks passed!"
ruff check src tests

# 2. Type check — must report "Success: no issues found in N source files"
mypy --strict src

# 3. Full test suite — must be 0 failed
pytest -p no:cacheprovider

# 4. Boundary contract — repository independence + tier discipline
pytest tests/contract/

# 5. ERN oracle gate (CI / release only) — uses SIM_RETIRE_BIN + RUN_ERN_E2E
#    Run separately: pytest tests/oracle/ with the ERN environment (see report §E).
```

`ruff` runs with `--fix` for auto-applicable findings, but the final state must
be clean under the plain `ruff check src tests` form above.

---

## Common Tasks

### Run the full test suite
```bash
pytest
```

### Run type checking
```bash
mypy --strict src
```

### Run linting (auto-fix)
```bash
ruff check src tests --fix
```

### Run only boundary contract tests
```bash
pytest tests/contract/
```

### Run the ERN oracle
```bash
pytest tests/oracle/
```

### Build the distribution wheel
```bash
python -m build --wheel
```

---

## Adding a New Public Symbol

1. Implement in the appropriate subpackage (`domain/`, `execution/`, etc.).
2. Export from the subpackage's `__init__.py`.
3. If the symbol is Tier 1, add it to `src/fbf/core/__init__.py` and `__all__`.
4. Update `test_public_facade_symbols` in `tests/contract/test_core_boundaries.py`.
5. Run `mypy --strict src` and `ruff check src tests` before committing.

---

## Adding a New Core Test

* Unit tests: `tests/unit/<layer>/test_<module>.py`
* Integration tests: `tests/integration/`
* Benchmark tests: `tests/benchmarks/`
* Oracle tests: `tests/oracle/ern/` (canonical only — do not add ad-hoc oracle tests)
* Boundary contract tests: `tests/contract/`

---

## Breaking API Changes (During 0.x)

Breaking changes to the Tier 1 or Tier 2 public API require a **Core minor version increment**
(e.g. `0.1.x` → `0.2.0`) and must update the `fbf-cli` dependency pin accordingly.
