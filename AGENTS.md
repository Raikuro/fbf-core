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
| Test suite | 673 tests (unit / integration / infrastructure / benchmarks / oracle / contract) |

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

---

## Public API Tiers

| Tier | Modules | Who may import |
|------|---------|----------------|
| Tier 1 | `fbf.core` (root `__init__`) | All consumers |
| Tier 2 | `fbf.core.domain`, `fbf.core.domain.model`, `fbf.core.domain.policies`, `fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence` | CLI and Core |
| Tier 3 | All other submodules | Core tests only — never CLI |

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
