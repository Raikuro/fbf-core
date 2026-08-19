# fbf-core

High-performance, deterministic FIRE (Financial Independence, Retire Early)
simulation and safe withdrawal rate research engine.

---

## Overview

`fbf-core` is a pure Python library with **zero third-party runtime
dependencies**. It provides the computational substrate for FIRE research:
a canonical monthly simulation pipeline, a closed-form analytical fast path,
parameter-sweep study planning, SWR optimisation, and an SQLite-backed
persistence layer.

---

## Features

| Feature | Description |
|---------|-------------|
| **Deterministic Decimal arithmetic** | All monetary calculations use `decimal.Decimal`. No floating-point drift. |
| **9-Step monthly pipeline** | Canonical per-month simulation: withdrawal, rebalance, market evolution, and seven other steps. |
| **Closed-form fast path** | Analytical recurrence for constant-policy studies, validated bit-exact against the reference pipeline. |
| **Reference chaining** | Deterministic historical-dataset chaining for multi-worker cohort execution. |
| **SWR optimisation** | Binary-search solver for maximum safe withdrawal rate across a parameter space. |
| **ERN oracle** | Canonical acceptance matrix for regression testing against published ERN data. |
| **Study planning** | Cohort generators, parameter axes, experiment definitions. |
| **SQLite persistence** | Study repository with codecs, schema management, and dataset caching. |

---

## Installation

```bash
pip install fbf-core
```

### Requirements

* Python ≥ 3.13
* No third-party runtime dependencies

---

## Quick Start

```python
import fbf.core

# Build a study plan from a configuration dict
config = fbf.core.StudyConfiguration.from_dict({...})
plan = fbf.core.build_study_plan(config)

# Execute the plan
result = fbf.core.execute_study_plan(plan)

# Optimise SWR
optimal = fbf.core.optimize_study_swr(evaluator)
```

See `ARCHITECTURE.md` for the full public API reference.

---

## Development

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest                       # run all 690 tests
mypy --strict src            # type check
ruff check src tests         # lint
```

---

## Repository Layout

```
fbf-core/
├── src/
│   └── fbf/
│       └── core/
│           ├── __init__.py          # public Tier 1 facade
│           ├── errors.py            # CoreError hierarchy
│           ├── py.typed             # PEP 561 marker
│           ├── domain/              # value objects, policies, services
│           ├── execution/           # pipeline, strategies, executor
│           ├── optimization/        # SWR solver, strategy comparator
│           ├── persistence/         # SQLite repository
│           └── study/               # study planning, cohort generation
├── tests/
│   ├── unit/                        # fast, isolated unit tests
│   ├── integration/                 # cross-module integration tests
│   ├── infrastructure/              # persistence and I/O tests
│   ├── benchmarks/                  # performance benchmarks
│   ├── oracle/ern/                  # ERN canonical truth table tests
│   └── contract/                    # architectural boundary assertions
├── ARCHITECTURE.md
├── AGENTS.md
└── pyproject.toml
```

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full system architecture
including API tiers, import rules, dependency direction, and layer isolation
invariants.

---

## License

MIT — see `pyproject.toml`.
