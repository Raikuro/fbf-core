# Dataset Distribution & Ownership Model

**Status:** Adopted.
**Scope:** All datasets consumed by the framework (e.g. the ERN dataset bundle in
`data/ern/`). The model is generic; nothing here is ERN-specific.

## Decision summary

1. Datasets are **not** part of the Core distribution. The `fbf-core` wheel ships code and
   type information only; it contains no dataset files.
2. Dataset resolution, loading, and caching are **owned by fbf-core**. The CLI is a
   pass-through: it carries a `--data-dir` path and never implements loading or discovery.
3. The discovery contract is a **Dataset Directory**: any directory containing one JSON
   file per dataset. A dataset is identified by its filename stem (stable identifier) and
   carries a `version` marker inside the file.
4. An installed-only deployment supplies a Dataset Directory explicitly (CLI `--data-dir`,
   or the `data_dir` parameter of the Core APIs) and must have obtained that directory
   itself (repo checkout, released bundle, or own data).
5. Loading is cached process-locally; datasets are immutable once loaded. There is no
   network/materialization step in the framework — local materialization *is* the Dataset
   Directory.
6. Future datasets are distributed as new JSON files in a Dataset Directory (or a new
   release of a bundle). Identifier stability and the `version` field provide
   reproducibility.

## 1. Is the dataset part of the Core distribution?

**No.** `fbf-core` ships as a pure-code wheel (`fbf_core-*.whl`), containing `fbf/core/**`
modules plus `py.typed`. The packaging configuration
(`[tool.setuptools.package-data]` in `pyproject.toml`) declares exactly one entry —
`"fbf.core" = ["py.typed"]` — and the `data/` directory lives outside `src/`, so it is
structurally excluded from the wheel. This is enforced by a contract test
(`tests/contract/test_dataset_distribution.py`).

## 2. Is it intentionally external to the Core wheel?

**Yes, deliberately.** Rationale:

- **Data is not code.** Dataset files are large, immutable artifacts with their own
  release cadence and provenance; coupling their distribution to code releases couples two
  unrelated lifecycles.
- **Wheel hygiene.** Keeping the wheel small and data-free makes builds fast and
  reproducible and avoids licensing/ownership questions about data inside a Python package.
- **Precedent.** This pattern was validated in prior projects and proven to work for
  deployments that require reproducibility and data provenance control.

## 3. How does an installed-only deployment obtain or locate datasets?

An installed-only deployment must obtain a **Dataset Directory** from one of:

- a checkout of the `fbf-core` repository (the committed `data/` directory);
- a released "dataset bundle" (any directory produced by packaging the dataset files);
- its own data files that conform to the JSON contract below.

There is no built-in fetch/materialization step. The deployment then passes the directory
to the framework explicitly:

```bash
fbf --data-dir /path/to/datasets run study.yaml
```

or programmatically:

```python
from fbf.core.study import StudyConfiguration, build_study_plan, load_yaml

config = StudyConfiguration.from_yaml(load_yaml("study.yaml"))
built = build_study_plan(config, data_dir="/path/to/datasets", initial_wealth=...)
```

## 4. Who owns dataset resolution?

**fbf-core owns the entire resolution stack.** The CLI and any external application layer
only supply a path.

| Component | Responsibility |
|---|---|
| `fbf.core.persistence.studies.sqlite.dataset_cache.DatasetCache` | Process-local cache keyed by canonical directory path; loads each directory once |
| `fbf.core.persistence.studies.sqlite.context._load_datasets_from_dir` | Directory → `{identifier: Dataset}` scan (`*.json` files) |
| `fbf.core.persistence.studies.sqlite.codecs.DefaultDatasetResolver` | Identifier/version → `Dataset` resolution (canonical identifier, legacy unique-version fallback, ambiguity/not-found errors) |
| `fbf.core.study.builder.resolve_dataset` | The public study-facing resolver used by `build_study_plan` |
| External CLI consumers | Pass-through only: expose `--data-dir` and forward it into `build_study_plan` / `create_persistence_context`. No loading or discovery logic lives in the consumer |

There is no environment-variable, well-known-path, or ERN-specific discovery mechanism.
If `data_dir` is `None`, resolution uses an empty resolver and any lookup fails with a
clear `StudyNotFoundError`.

## 5. Dataset path and discovery contract

**Dataset Directory contract**

- A Dataset Directory is any directory containing zero or more dataset files.
- One dataset per file, named `<identifier>.json` — the filename stem **is** the dataset
  identifier.
- Dataset files are UTF-8 JSON with exactly this schema:

```json
{
  "version": "<string, data lineage/version marker>",
  "frequency": "<string, e.g. 'monthly'>",
  "snapshots": [
    {
      "date": "<YYYY-MM-DD>",
      "index_levels": {"<asset id>": "<decimal as string>"},
      "inflation": "<decimal as string>",
      "inflation_cumulative": "<decimal as string>",
      "is_ath": true,
      "is_underwater": false,
      "running_ath": "<decimal as string>"
    }
  ]
}
```

- Discovery is: given `data_dir`, scan for `*.json` (sorted, deterministic order); the
  resulting mapping is keyed by file stem.
- A study declares exactly one dataset by identifier:
  `dataset.identifier: "<identifier>"` in the study YAML.
- Errors are explicit: a missing directory raises `StudyNotFoundError`
  ("Dataset directory not found: ..."); an unknown identifier raises `StudyNotFoundError`
  ("Dataset not found: ..."); a `version` shared by multiple datasets raises an ambiguity
  error rather than guessing.

The contract is deliberately generic — the framework never hardcodes `data/ern/`,
specific identifiers, or horizon families. The ERN bundle is simply a particular Dataset
Directory using the same contract.

## 6. Dataset model invariants

The `Dataset` domain object (`fbf.core.domain.model.dataset`) enforces three
structural invariants at construction time:

1. **Non-empty:** a Dataset must contain at least one `MarketSnapshot`.
2. **Ordered by date:** snapshots must be in chronological order.
3. **Unique dates:** no two snapshots may share the same date.

These invariants are enforced by `Dataset.__post_init__` and validated by the
test suite. A Dataset that violates any of these constraints raises `ValueError`
at construction time.

## 7. Canonical CSV filename contract (ERN dataset)

The ERN dataset directory contains CSV source files whose **filenames define the
semantic identity** of each series. The `--data-dir` flag specifies the directory
location; the canonical filenames carry the asset semantics. Study YAML does not
repeat this mapping.

```
--data-dir/
  ├── spx_tr_real.csv            → equity asset
  ├── bond_10y_tr_real.csv       → bond / fixed-income asset
  ├── spx_tr.csv                 → nominal equity index (auxiliary)
  ├── bm10.csv                   → nominal 10-year bond index (auxiliary)
  ├── cpi.csv                    → CPI levels (interest-rate inflation adjustment)
  ├── cape_shiller.csv           → Shiller CAPE for cohort manifests (research)
  └── ffr.csv                    → Federal Funds Rate (rate-only time series)
```

| Canonical filename | Semantic role | Loader |
|---|---|---|
| `spx_tr_real.csv` | S&P 500 total-return real returns | `fbf.core.datasets.ern` → `AssetClass(id="equity")` |
| `bond_10y_tr_real.csv` | 10-Year Bond Market real returns | `fbf.core.datasets.ern` → `AssetClass(id="bond")` |
| `spx_tr.csv` | S&P 500 total-return nominal index | auxiliary data; not loaded by `load_ern_dataset` |
| `bm10.csv` | 10-Year Bond Market cumulative nominal index | auxiliary data; not loaded by `load_ern_dataset` |
| `cpi.csv` | CPI index level | `fbf.core.datasets.ern` (interest-rate inflation adjustment) |
| `cape_shiller.csv` | Shiller CAPE for Part 3/19/20 cohort manifests | research manifest; not loaded by `load_ern_dataset` |
| `ffr.csv` | Federal Funds Rate (annual, nominal) | `fbf.core.study.builder.load_ffr_rates` → `tuple[date, Decimal]` |

The equity and bond CSVs are loaded by the canonical ERN dataset loader and
materialised as `MarketSnapshot.index_levels` entries. The FFR CSV is a
rate-only time series loaded separately by `load_ffr_rates` for Part 52
floating-rate interest schedules; it does not produce `MarketSnapshot` entries.

### Workbook provenance (current production)

The canonical asset-return and index files in `data/ern/` are generated from
`SWR_Toolbox_v2.0.xlsx` by `tools/ern/extract_workbook_returns.py`.
The extractor reads the **cached values** of the workbook's `Asset Returns`
sheet, validates contiguous monthly dates and the `Q`/`R` formulas, and writes:

| Output | Workbook source |
|---|---|
| `spx_tr_real.csv` | `Q` (S&P 500 total-return real return) |
| `bond_10y_tr_real.csv` | `R` (10-year bond market total-return real return) |
| `spx_tr.csv` | `F` (S&P 500 total-return nominal index) |
| `bm10.csv` | `G` (10-year bond market cumulative nominal index) |
| `cpi.csv` | `E` (CPI level) |
| `cape_shiller.csv` | `O` (Shiller CAPE; canonical CAPE source) |
| `workbook_returns.csv` | `Q` and `R`, combined oracle fixture |

The cached values are preserved exactly: no formula is re-evaluated and no
rounding, normalization, or reconstruction is applied. Each output has a
sibling `<name>.provenance.json` recording the workbook sheet, source column,
observation count, and date range. CAPE provenance additionally records the
extraction tool/version and explicit no-merge transformations.

CAPE is **workbook-only**. `SWR_Toolbox_v2.0.xlsx`, `Asset Returns!O`
(`O6:O1871`, 1,866 observations, `1871-01..2026-06`) is authoritative. Raw
`data/ern/raw/ie_data.csv`, any Shiller JSON source,
`canonical/ern_asset_returns.csv`, and the pre-migration hybrid
`cape_shiller.csv` composition are not canonical CAPE sources and must not be
used to fill, extend, or correct it. The committed CAPE artifact is awaiting
the workbook-only migration. The extraction and replacement procedure is in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md); acceptance categories are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

`ffr.csv` is a separate canonical series. Its historical segment
(`1871-01..2021-12`, 1,812 observations) is extracted from
`Timing-Leverage-Calc.xlsx`, sheet `Return Data`, column `K`
(`K4:K1815`), by `tools/ern/extract_ffr_from_workbook.py`. Column `K` is the
workbook's spliced series: Federal Funds Rate where available, otherwise the
short-term yield. The extractor validates the `K` formulas, including
shared-formula masters, and fails if the expected
`IF(ISNUMBER(M),M,N)` pattern is absent. The `2022-01..2026-08` extension is
derived from
`data/ern/raw/FEDFUNDS.csv` and is documented separately in
`data/ern/ffr.provenance.json`. The canonical `ffr.csv` artifact is frozen by
SHA-256
`98591457d5d03867bd81992d43b57a6cabc4ce967f3ec9324676216abbf2f5f1`.
The 2026-11 source audit confirms FRED `FEDFUNDS` as the correct post-2021
extension and rejects target-rate, Treasury-bill, SOFR, and reconstructed-FFR
substitutes. See `docs/ERN_METHODOLOGY.md` §3 for the current Part 52 FFR
treatment.
`ffr_monthly.json` is a reconstructed research series, not the canonical
workbook `K` series, and must not replace the historical segment.

The FRED extension source is a local snapshot at
`data/ern/raw/FEDFUNDS.csv` (866 monthly observations, `1954-07..2026-08`).
Workbook `M` matches the raw series after `/100` for all 810 months
`1954-07..2021-12`. The
repository records the source hash but does not contain a reproducible
download recipe, so the acquisition path is a documented provenance
limitation rather than a claim of full reproducibility. The workbook also
does not document the upstream source or vintage of column `N`, the
pre-1954-07 short-term-yield fallback; accepting `N` is therefore a recorded
data-fidelity limitation. Do not replace the canonical series with
`ffr_monthly.json` or with a cash-return proxy.

### SWR cash series is not an FFR source

`SWR_Toolbox_v2.0.xlsx`, sheet `Asset Returns`, column `I`
(`I6:I1871`), is a cumulative nominal 3-month US Treasury-bill
total-return index used by ERN for cash returns. It is not a federal funds
rate and must not be used as one. The series contains actual observations for
`1871-01..2026-06` (1,866 months), starts at `100.0` in `1871-01`, reaches
`47574.20198548` in `2026-06`, and is blank after the workbook's projection
boundary.

Post-1954 annualized cash returns differ from FRED `FEDFUNDS` with a mean bias
of `-0.383` pp, mean absolute error of `0.464` pp, and correlation of `0.986`
over 864 months. Before 1954-07 the cash series closely matches the workbook's
short-term-yield leg (MAE `0.0095` pp over 1,001 months), which confirms it is
the T-bill leg rather than FFR. It must not be used as an FFR source, fallback,
or extension.

### Euro-area reference rates (research only)

No exact long-history euro-area equivalent of the US FFR exists. Any euro-area
study must choose and document an explicit reference-rate role rather than
renaming a proxy as FFR. Candidate sources are:

| Role | Candidate series | Coverage | Boundary |
|---|---|---|---|
| Modern overnight market rate | ECB €STR `EST.B.EU000A2X2A25.WT` | `2019-10-01` onward | Primary modern market-rate analogue |
| Pre-€STR bridge | ECB pre-€STR `MMSR.B.U2._X._Z.S12._Z.U.BO.WT.D76.MA._Z._Z.EUR._Z` | `2017-03-15..2019-09-30` | Short bridge only; not a long history |
| Legacy overnight rate | EONIA | `1999-01-04..2021-12-29` | Stop at `2019-09-30`; later EONIA is €STR + 8.5 bp |
| Policy rate | ECB deposit facility rate `FM.B.U2.EUR.4F.KR.DFR.LEV` | `1999-01-01` onward | Policy sensitivity, not a market borrowing rate |
| Term market rate | 3M EURIBOR `FM.M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA` | `1999-01` onward | Term borrowing sensitivity, not overnight |
| Government yield | ECB 3M AAA spot rate `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_3M` | `2004-09-06` onward | Continuously compounded yield; not a total-return index |
| Inflation | Euro-area HICP `HICP.M.U2.N.000000.4D0.INX` | `1996-12` onward | Euro-area composition; not US CPI |

These are research candidates only. No euro dataset, loader, or euro Part 52
path is implemented. A future euro study must also use euro-denominated asset
returns, preserve an explicit monthly aggregation/publication convention,
handle negative policy rates and loan-rate floors, recalibrate any lending
spread for the euro product, and document coverage and splice boundaries.
Do not silently substitute a US series, a policy rate, or a government yield
for a market overnight rate.

Do not replace `spx_tr_real.csv` or `bond_10y_tr_real.csv` with a derivation
from the nominal index and CPI files. The workbook stores the real-return
columns directly, and deriving them from rounded runtime series changes
compounded index levels enough to break exact oracle comparisons.

The frozen `data/ern/published_2016/` directory is a separate historical
replication fixture. It contains rounded returns through September 2016 under
the published ERN forward assumptions and is used only by the published-ERN E2E
and reference oracle. It is not current production data.

The canonical loader is the **single source of truth** for CSV → `AssetClass`
mapping. No second mapping (e.g. in study YAML) is needed or desirable.

`equity_allocation: 0.75` therefore means 75% equity and 25% bond under the
current two-asset allocation policy. The complement is implicit.

### Future extension: explicit role mapping

The current canonical filenames are sufficient for today's ERN studies, which
have a fixed two-series input set. This must not become a permanent assumption
that the framework can only use those specific files.

If a future study needs alternative market series (e.g. a different equity
index or a different bond benchmark), `--data-dir` alone becomes insufficient.
It answers only *where* the files are, not *which file plays which role*. At
that point, an explicit semantic role mapping would be needed:

```yaml
market_data:
  equity: my_equity_series.csv
  fixed_income: my_bond_series.csv
```

This is fundamentally different from dataset identity (which was removed
earlier). The conceptual hierarchy is:

```
--data-dir         → physical location of input files
market_data        → semantic mapping from input series to framework roles
AssetClass         → runtime representation of those semantic roles
```

Until an actual requirement demands alternative series:

- Keep the current canonical filename contract for the present ERN studies.
- Keep `--data-dir` as the location mechanism.
- Do not add `market_data:` to the current YAMLs.
- Ensure future implementation maps files to semantic roles before
  constructing the runtime Dataset.
- Never reintroduce `Dataset.identifier` as a substitute for series-role
  mapping.
- Do not introduce generic N-asset infrastructure until an actual requirement
  requires it.

Equity-derived state (ATH, underwater, drawdown) follows the semantic `equity`
role, not a hardcoded filename. If a future study maps another CSV to the
`equity` role, the derived state pipeline must operate on whichever series
occupies that role.

## 8. Caching and local materialization

- `DatasetCache` loads each canonical directory path at most once per process; repeated
  resolution returns the identical `Dataset` object (identity preserved across resolvers,
  persistence contexts, and study builders).
- Datasets are immutable once loaded; a file modified on disk after its directory was
  cached is intentionally not re-read within that process.
- Load failures are not cached (a later attempt after the directory appears succeeds).
- Local materialization **is** the Dataset Directory; there is no cache-rebuild or
  remote-sync stage.

## 9. How should future datasets be distributed?

- Add a new `<identifier>.json` file to a Dataset Directory (and release it in a new
  dataset bundle, if bundles are used).
- Changing the contents of an existing identifier is a **breaking change**: reuse of an
  identifier implies content stability. If contents change incompatibly, ship a new
  identifier (or a new bundle version) and update the studies that reference it.
- The framework code itself does not change when a dataset is added; the loader is
  schema-driven, not identifier-driven.

## 10. Reproducibility and dataset versioning

- Every dataset carries a `version` marker; datasets in one bundle should share the
  bundle's version for easy provenance checks.
- Reproducibility at the run level is anchored by `dataset.identifier` in the study YAML,
  plus the recorded `dataset_identifier` column in persisted studies.
- The ERN certification has three separate targets. The published-ERN historical
  replication uses the frozen `data/ern/published_2016/` fixture and the pinned
  `p49_oracle_table.csv` (T+1 cohort terms, multiplicative fee). Current production
  is workbook-conformant and is checked independently by `tools/ern/workbook_oracle.py`
  against `workbook_returns.csv`; its pinned production matrix is
  `data/ern/workbook_oracle_table.csv` (T cohort terms, additive fee). The production
  E2E compares the engine to the workbook matrix, not to the published oracle.
  Part 2.1 adds `data/ern/part2_regression_fixture.csv`, generated from the current
  production dataset by `tools/ern/build_part2_regression_fixture.py`; it is
  regression coverage only, not an independent replication oracle. The four Part 2
  published anchors are evaluated against the frozen `published_2016` fixture.
  Part 2.2 cross-checks the 90 Part 2 FV=0 cells against
  `workbook_oracle_table.csv`; it introduces no additional dataset.
  Changing the production data requires re-certifying the workbook oracle and
  regenerating the Part 2 regression fixture; it does not re-baseline the
  published-ERN fixture.
- Consumers should record `dataset.identifier` **and** `dataset.version` (both available on
  the resolved `fbf.core.domain.model.dataset.Dataset`) alongside results for full
  reproducibility.