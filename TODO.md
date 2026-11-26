# TODO

Open work only. Remove entries when resolved. Architectural and product
decisions are separated from routine cleanup.

## Domain Invariants

- [x] **Deep immutability of `MarketSnapshot` and `Dataset`.**
  - `MarketSnapshot` is frozen, but `index_levels` remains an externally mutable
    mapping.
  - `Dataset` is frozen, but `snapshots` is typed as `Sequence` and the
    constructor retains caller-owned lists without defensive copying.
  - Decide whether to use defensive copying and immutable mapping/sequence
    representations.
  - Verify serialization and persistence compatibility.
  - Assess performance implications for large simulation workloads.
  - Add tests proving that external mutations cannot alter constructed domain
    objects.

- [x] **Dataset asset-set consistency.**
  - `Dataset.__post_init__` enforces exact `AssetClass` key-set equality across
    all snapshots and reports the offending snapshot dates plus missing and
    extra assets.
  - Consistently empty asset sets remain structurally valid.

- [x] **Dataset frequency contract.**
  - `Dataset.__post_init__` enforces exactly `"monthly"` and rejects every
    other value with `ValueError`.
  - `ReturnSequence` continues to enforce the same monthly-only contract.
  - Calendar spacing is not validated; monthly is a semantic contract, not a
    guarantee of exact month-to-month snapshot dates.

- [x] **Canonical loader consistency.**
  - `prepare_ern_dataset` validates historical and projection timeline
    continuity, historical CPI coverage, ATH/underwater consistency after the
    synthetic base snapshot, and the exact canonical equity/bond asset universe.
  - The synthetic `1871-01-31` base snapshot is exempt from CPI and ATH checks.
  - Explicit projection `end_date` and `required_through` values must be
    first-of-month dates; non-month-start values are rejected.
  - These checks remain at the canonical loader boundary and are not applied by
    generic `Dataset`/`MarketSnapshot` constructors or prescribed/custom
    dataset builders.

- [x] **`ReturnSequence` return-domain validation.**
  - `ReturnSequence` requires finite Decimal returns greater than or equal to
    -100%; `-100%` remains a valid total loss.
  - `annual_to_monthly` and `expand_annual_to_monthly` apply the same input
    validation.
  - `build_prescribed_dataset` rejects non-positive initial levels and
    non-positive compounded levels because the engine requires strictly
    positive prices.
