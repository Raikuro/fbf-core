# Dataset Distribution and Provenance

This document is authoritative for dataset distribution, canonical status, and
provenance. Methodology and acceptance anchors are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md); extraction and
regeneration commands are in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

**Status:** adopted. The canonical ERN production data lives in
`data/inputs/ern/`; auxiliary extraction inputs live in
`data/inputs/ern/extraction/`. Pinned test fixtures and oracles remain in
`data/ern/` pending fixture migration, and generated outputs belong in the
gitignored `data/outputs/` directory.

---

## 1. Distribution Model

1. Datasets are **not** part of the Core wheel. The wheel ships code and type
   information only.
2. A data directory is an external local directory supplied explicitly through
   the CLI `--data-dir` option or the `data_dir` Core API parameter. Core owns
   dataset loading; consumers only supply the path.
3. The canonical ERN loader expects the fixed CSV filenames listed in
   [§2](#2-ern-dataset-files). Persisted market/CPI series are historical-only;
   the loader reconstructs an immutable `Dataset` and generates any required
   forward projection in memory under explicit cutoff and projection rules.
4. There is no generic JSON dataset discovery, identifier/version resolver, or
   process-local dataset cache. `build_study_plan` calls
   `load_canonical_dataset(Path(data_dir))` unless the caller supplies an
   already-loaded `Dataset`. The `data_dir` parameter is still required for
   auxiliary series such as FFR when the configuration requests them.
5. Installed-only deployments must obtain and supply the required files
   explicitly. There is no built-in fetch or materialization step.
6. There is no environment-variable or well-known-path fallback.

`Dataset` requires at least one snapshot, chronological order, and unique dates.
The loaded dataset is immutable and shared across simulations.

### Repository data layout

| Location | Contents | Status |
|---|---|---|
| `data/inputs/ern/` | Five canonical simulation CSVs and provenance sidecars | Production inputs |
| `data/inputs/ern/extraction/` | `spx_tr.csv`, `bm10.csv`, `FEDFUNDS.csv` and sidecars | Auxiliary extraction inputs; not loader inputs |
| `data/ern/` | Oracle tables, `workbook_returns.csv`, Part 2 regression fixture, deferred `raw/ie_data.*` | Test fixtures and pinned oracles |
| `data/outputs/` | Generated run artifacts | Gitignored scratch output; never canonical input |

Canonical files are the five series consumed by the production loader in
`data/inputs/ern/`. Auxiliary extraction files support provenance and
regeneration but are not production loader inputs. Fixtures and oracles under
`data/ern/` are test-only and may move to `tests/fixtures/ern/` in a later
phase; they are not canonical production data.

---

## 2. ERN Dataset Files

Canonical filenames define each series' semantic role. Study YAML does not
repeat this mapping.

| File | Role | Location | Loader |
|---|---|---|---|
| `spx_tr_real.csv` | S&P 500 total-return real returns | `data/inputs/ern/` | `fbf.core.datasets.ern` → equity asset |
| `bond_10y_tr_real.csv` | 10-year bond total-return real returns | `data/inputs/ern/` | `fbf.core.datasets.ern` → bond asset |
| `spx_tr.csv` | S&P 500 total-return nominal index | `data/inputs/ern/extraction/` | auxiliary |
| `bm10.csv` | 10-year bond cumulative nominal index | `data/inputs/ern/extraction/` | auxiliary |
| `cpi.csv` | CPI index level | `data/inputs/ern/` | `fbf.core.datasets.ern` |
| `cape_shiller.csv` | Canonical Shiller CAPE used for runtime cohort conditioning | `data/inputs/ern/` | research manifest only |
| `ffr.csv` | Federal Funds Rate time series | `data/inputs/ern/` | `fbf.core.study.builder.load_ffr_rates` |
| `workbook_returns.csv` | Exact combined oracle fixture | `data/ern/` | test fixtures only |

Equity and bond CSV roles are fixed by the canonical loader: weight `w` means
`w` equity and `1 - w` bond. Equity-derived state (ATH, underwater, drawdown)
follows the semantic equity role. Do not derive `spx_tr_real.csv` or
`bond_10y_tr_real.csv` from nominal indices and CPI; the workbook stores the
real-return columns directly and derivation changes exact oracle values.

---

## 3. Canonical Source Policy

The authorized Excel workbooks are the sole source of truth for production ERN
data. Extraction reads cached values only; no formula is re-evaluated, rounded,
normalized, or reconstructed.

| Workbook | SHA-256 | Role |
|---|---|---|
| `SWR_Toolbox_v2.0.xlsx` | `d393e898a918e179d381768b187c8d5b54f58050500190b9e69403321acdf2c6` | Market returns, CPI, CAPE |
| `Timing-Leverage-Calc.xlsx` | `e0a0dbea11543809b2f2e8544cc84e21a19e0ca864d8ef3664135b945bbcda38` | Historical FFR segment |

If a workbook is missing or its hash differs, extraction stops. Legacy
datasets, Shiller raw archives, Google-Sheet exports, and external series must
not fill, extend, correct, or replace workbook data. The frozen FFR extension
below is the only documented exception.

### SWR workbook outputs

`SWR_Toolbox_v2.0.xlsx`, sheet `Asset Returns`:

| Output | Source | Meaning |
|---|---|---|
| `spx_tr_real.csv` | `Q` (`Q7:Q1871`) | S&P 500 total-return real return |
| `bond_10y_tr_real.csv` | `R` (`R7:R1871`) | 10-year bond total-return real return |
| `spx_tr.csv` | `F` (`F6:F1871`) | S&P 500 total-return nominal index |
| `bm10.csv` | `G` (`G6:G1871`) | 10-year bond cumulative nominal index |
| `cpi.csv` | `E` (`E6:E1871`) | CPI level |
| `cape_shiller.csv` | `O` (`O6:O1871`) | Shiller CAPE; canonical CAPE source |
| `workbook_returns.csv` | `Q` and `R` | Exact combined oracle fixture |

CAPE is **workbook-only**: `SWR_Toolbox_v2.0.xlsx`, sheet `Asset Returns`,
column `O` (`O6:O1871`; 1,866 observations; `1871-01..2026-06`). Raw
`data/ern/raw/ie_data.csv`, Shiller JSON sources,
`canonical/ern_asset_returns.csv`, and any prior hybrid CAPE composition are
not canonical CAPE sources. The committed `cape_shiller.csv` is the exact
workbook-only extraction.

Each workbook-generated canonical output has a sibling
`<name>.provenance.json` recording source workbook, sheet, column/cells,
observation count, date range, artifact hash, and validation result. CAPE
provenance additionally records the extraction tool/version and explicit
no-merge transformations.

### FFR frozen exception

`ffr.csv` is a separate canonical rate series. Its historical segment
(`1871-01..2021-12`, 1,812 observations) is extracted from
`Timing-Leverage-Calc.xlsx`, sheet `Return Data`, column `K` (`K4:K1815`).
Column `K` is the workbook splice `IF(ISNUMBER(M),M,N)`: Federal Funds Rate
where available, otherwise the short-term yield.

The `2022-01..2026-08` extension comes from the frozen FRED `FEDFUNDS`
snapshot at `data/inputs/ern/extraction/FEDFUNDS.csv`, recorded separately in
`data/inputs/ern/ffr.provenance.json`. This extension is admissible only as the
documented Part 52 historical-diagnostic exception. It does not permit using
external sources for new canonical datasets, and it must not be refreshed
during a run.

`ffr.csv` is frozen by SHA-256
`98591457d5d03867bd81992d43b57a6cabc4ce967f3ec9324676216abbf2f5f1`.
Workbook `M` matches the raw FRED series after `/100` for all 810 overlapping
months (`1954-07..2021-12`). The workbook's pre-1954 short-term-yield fallback
column `N` has no documented upstream vintage; accepting it is a recorded
fidelity limitation. The former `ffr_monthly.json` reconstructed research
series and its raw FFH* inputs have been removed; reconstructed FFR must not
replace the historical segment.

The SWR workbook's cash-return index (`Asset Returns!I`) is a T-bill
total-return series, not a federal funds rate. It must not be used as an FFR
source, fallback, or extension.

### Non-canonical and research-only artifacts

- The former `canonical/ern_asset_returns.csv` legacy artifact and its
  provenance sidecar have been removed and must not be reintroduced.
- Persisted projected manifests such as
  `data/inputs/ern/cohort_manifest_part3.json` and
  `data/inputs/ern/ern_swr_h720.json` are obsolete; manifests are built at runtime.
- `data/ern/raw/ie_data.csv` and Shiller JSON archives are not canonical CAPE
  sources; `ie_data` remains deferred fixture-adjacent research input pending a
  later migration phase.
- The research-only reconstructed FFR artifact and its raw FFH* inputs are not
  retained; the raw daily series remain available from FRED category 33951
  (Anbil et al., 1928–1954).
- The former 2016-vintage published-replication fixture has been retired; only
  the pinned `data/ern/p49_oracle_table.csv` remains. That table can no longer
  be regenerated or independently re-derived because its regeneration tool was
  retired with the fixture.

Euro-area reference rates are research-only; no euro dataset, loader, or Part
52 path exists. See [`TODO.md`](TODO.md).

---

## 4. Certification Targets

Keep these targets distinct:

| Target | Dataset | Pinned result |
|---|---|---|
| Published-ERN historical replication | pinned table only (source fixture retired) | `data/ern/p49_oracle_table.csv` (T+1 terms, multiplicative fee) |
| Current workbook conformance | canonical workbook output | `data/ern/workbook_oracle_table.csv` (T terms, additive fee) |
| Part 2 regression | current production data | `data/ern/part2_regression_fixture.csv` |

The production E2E compares the engine to the workbook matrix, not the
published oracle. `part2_regression_fixture.csv` is regression coverage only.
Changing production data requires re-certifying the workbook oracle and
regenerating the Part 2 fixture; it does not re-baseline the pinned
published-ERN oracle table. Published anchors must never be updated to match a
new run.

---

## 5. Frozen Artifacts

Do not modify without separate explicit authorization:

- `data/inputs/ern/ffr.csv`
- `data/inputs/ern/ffr.provenance.json`
- `data/inputs/ern/extraction/FEDFUNDS.csv`
- the Timing workbook historical FFR segment
- `data/ern/p49_oracle_table.csv`
- `data/ern/workbook_oracle_table.csv`
- `data/ern/part2_regression_fixture.csv`
- `tests/functional/ern/constants.py`
- published anchors in tests and YAML
- any pinned Part 49/Part 52 oracle constant
