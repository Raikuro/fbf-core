# Development, Extraction, and Validation

This document lists the supported contributor workflow. Methodology, published
anchors, and acceptance categories are in
[`ERN_METHODOLOGY.md`](ERN_METHODOLOGY.md). Dataset identity and frozen
artifacts are in [`DATASETS.md`](../DATASETS.md).

---

## 1. Environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The repository uses Python `>= 3.13`, `ruff`, `mypy --strict`, and `pytest`.

---

## 2. Quality Gate

Run from a clean checkout before committing:

```bash
.venv/bin/ruff check .
.venv/bin/mypy --strict .
.venv/bin/pytest -p no:cacheprovider
.venv/bin/pytest tests/contract/ -p no:cacheprovider
```

Heavyweight ERN replication and research-validation workloads are skipped by
default. Do not enable them as part of routine changes.

---

## 3. Canonical Extraction

### Market, CPI, and CAPE

`tools/ern/extract_workbook_returns.py` verifies the authorized workbook hash,
reads cached values only, and writes the canonical CSVs plus provenance:

```bash
.venv/bin/python tools/ern/extract_workbook_returns.py \
  --workbook /path/to/SWR_Toolbox_v2.0.xlsx \
  --output-dir /tmp/ern-canonical-review
```

The default output is a gitignored review bundle under
`data/outputs/ern-extraction/`. After review and explicit authorization, place
the five canonical CSVs and their sidecars in `data/inputs/ern/`, auxiliary
nominal inputs in `data/inputs/ern/extraction/`, and fixture/oracle files in
`data/ern/`. Do not overwrite datasets as part of routine development.

### Historical FFR

`tools/ern/extract_ffr_from_workbook.py` extracts the workbook-native
historical segment and appends the frozen FRED extension:

```bash
.venv/bin/python tools/ern/extract_ffr_from_workbook.py \
  --workbook /path/to/Timing-Leverage-Calc.xlsx
```

`data/inputs/ern/ffr.csv` is frozen. Do not regenerate it without explicit
authorization.

---

## 4. Derived Artifacts

### Cohort manifest

`tools/ern/build_cohort_manifest.py` builds the runtime effective Part 3/19/20
manifest from canonical historical CAPE, market, and CPI artifacts. It requires
workbook provenance and uses the same preparation pipeline as production. The
manifest is projection-dependent and must not be committed; `--output` is for
temporary inspection only:

```bash
.venv/bin/python tools/ern/build_cohort_manifest.py \
  --data-dir /tmp/ern-canonical-review \
  --output /tmp/ern-canonical-review/effective_manifest.json
```

### Workbook conformance oracle

`tools/ern/workbook_oracle.py` regenerates the workbook-derived conformance
matrix from `workbook_returns.csv`:

```bash
.venv/bin/python tools/ern/workbook_oracle.py
.venv/bin/python tools/ern/workbook_oracle.py --validate
```

### Part 2 regression fixture

`tools/ern/build_part2_regression_fixture.py` regenerates the production-path
Part 2 regression fixture through the public `run_study` application boundary:

```bash
.venv/bin/python tools/ern/build_part2_regression_fixture.py
```

This fixture is regression evidence, not an independent published oracle.
Review all differences before replacing it.

### Published-ERN reference oracle

`data/ern/p49_oracle_table.csv` is the pinned published-ERN matrix. It is
retained for historical comparison and must not be used to produce production
expected values. Its 2016-vintage source fixture and regeneration tool have
been retired, so the table can no longer be regenerated or independently
re-derived. Treat it as frozen evidence; independent verification of changes to
that table is no longer available.

---

## 5. Functional Validation

Functional scenarios are committed YAML studies in `examples/studies/` and
`tests/fixtures/`. They are executed through the public application boundary
(`fbf.core.application.run_study`) or the `sim-retire` CLI, never through
private simulation functions.

```bash
# Fast functional/supporting tests
.venv/bin/pytest tests/functional/ -p no:cacheprovider

# Full canonical and research validation (manual only)
RUN_ERN_E2E=1 .venv/bin/pytest tests/functional/ -v

# Full grid with fast-path equivalence
RUN_ERN_E2E=1 ERN_E2E_FAST_PATH=1 .venv/bin/pytest tests/functional/ -v
```

`ERN_E2E_WORKERS` controls worker count (default
`min(8, cpu_count)`; `max` uses all logical CPUs). `RUN_ERN_E2E=1` is the only
gate for heavyweight ERN workloads.

Expected results are either published anchors, structural invariants, or
canonical regression results. See
[`ERN_METHODOLOGY.md`](ERN_METHODOLOGY.md#3-acceptance-categories) before
changing any expected value.

---

## 6. Canonical Data Replacement Order

Only after explicit authorization:

1. Extract to a temporary directory and review CSV/provenance output.
2. Build the runtime effective manifest to a temporary path and review it.
3. Replace only approved artifacts. Do not delete legacy/research artifacts.
4. Re-derive structural populations and review published-anchor differences.
5. Run focused unit, integration, contract, and functional tests.
6. Request authorization for final canonical E2E/research validation.
7. Record any acceptance exception rather than silently re-baselining anchors.
