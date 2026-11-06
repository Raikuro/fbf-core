# fbf-core

Deterministic FIRE simulation and safe-withdrawal-rate research engine.

`fbf-core` is a pure Python library with **zero required third-party runtime
dependencies**. It provides a Decimal domain model, a Numba-backed simulation
engine (optional `numba` extra), study planning, SWR optimization, ERN oracle
tooling, and SQLite persistence.

---

## Installation

```bash
pip install "fbf-core[numba]"
```

Requires Python ≥ 3.13. Numba is optional for installation but required to
execute studies.

---

## Quick Start

```python
from decimal import Decimal

import fbf.core
from fbf.core.domain.model import Currency, Money

config = fbf.core.StudyConfiguration.from_yaml({...})
result = fbf.core.run_study(
    config,
    data_dir="/path/to/datasets",
    initial_wealth=Money(Decimal("1000000"), Currency.EUR),
)
```

Monetary domain values use `decimal.Decimal`. The Numba kernel converts inputs
to `float64` for execution and reconstructs reported monetary values as
`Decimal`; derived statistical metrics remain `float`. Correctness is pinned
by independent Decimal and hand-calculated oracles. See
[`ARCHITECTURE.md`](./ARCHITECTURE.md#10-key-invariants).

---

## Development

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check .
mypy --strict .
pytest -p no:cacheprovider
```

Full setup, extraction, regeneration, and validation workflows are in
[`docs/DEVELOPMENT.md`](./docs/DEVELOPMENT.md).

---

## Documentation

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System boundaries, API tiers, invariants, execution flow |
| [`docs/DESIGN.md`](./docs/DESIGN.md) | Design rationale and rejected approaches |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | Durable architectural decisions |
| [`docs/DOMAIN.md`](./docs/DOMAIN.md) | Domain model and simulation state |
| [`docs/EXECUTION_MODES.md`](./docs/EXECUTION_MODES.md) | Backend and strategy selection |
| [`docs/PROFILING.md`](./docs/PROFILING.md) | Profiling and timing instrumentation |
| [`DATASETS.md`](./DATASETS.md) | Dataset inventory, source policy, and provenance |
| [`docs/ERN_METHODOLOGY.md`](./docs/ERN_METHODOLOGY.md) | ERN methodology and published anchors |
| [`docs/DEVELOPMENT.md`](./docs/DEVELOPMENT.md) | Development and canonical-data workflow |
| [`TODO.md`](./TODO.md) | Unresolved technical work |
| [`AGENTS.md`](./AGENTS.md) | Contributor and coding-agent constraints |

Datasets are external to the wheel. Point `--data-dir` (CLI) or the `data_dir`
Core API parameter at a Dataset Directory of `<identifier>.json` files. ERN
CSV sources and provenance are documented in [`DATASETS.md`](./DATASETS.md).

---

## License

MIT — see `pyproject.toml`.
