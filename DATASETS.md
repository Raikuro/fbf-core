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

## 7. Caching and local materialization

- `DatasetCache` loads each canonical directory path at most once per process; repeated
  resolution returns the identical `Dataset` object (identity preserved across resolvers,
  persistence contexts, and study builders).
- Datasets are immutable once loaded; a file modified on disk after its directory was
  cached is intentionally not re-read within that process.
- Load failures are not cached (a later attempt after the directory appears succeeds).
- Local materialization **is** the Dataset Directory; there is no cache-rebuild or
  remote-sync stage.

## 8. How should future datasets be distributed?

- Add a new `<identifier>.json` file to a Dataset Directory (and release it in a new
  dataset bundle, if bundles are used).
- Changing the contents of an existing identifier is a **breaking change**: reuse of an
  identifier implies content stability. If contents change incompatibly, ship a new
  identifier (or a new bundle version) and update the studies that reference it.
- The framework code itself does not change when a dataset is added; the loader is
  schema-driven, not identifier-driven.

## 9. Reproducibility and dataset versioning

- Every dataset carries a `version` marker; datasets in one bundle should share the
  bundle's version for easy provenance checks.
- Reproducibility at the run level is anchored by `dataset.identifier` in the study YAML,
  plus the recorded `dataset_identifier` column in persisted studies.
- The ERN certification is the reference case: the oracle matrix is pinned, and
  acceptance is exact-`Decimal` equality against it. Changing the dataset bundle requires
  re-certifying against the pinned matrix.
- Consumers should record `dataset.identifier` **and** `dataset.version` (both available on
  the resolved `fbf.core.domain.model.dataset.Dataset`) alongside results for full
  reproducibility.