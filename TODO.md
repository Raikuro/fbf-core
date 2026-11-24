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

- [ ] **Dataset frequency contract.**
  - `Dataset.frequency` is an unvalidated `str`, while `ReturnSequence`
    independently enforces a monthly-only contract.
  - Decide and document whether `Dataset` is strictly monthly.
  - Review the current engine assumptions and the existing `ReturnSequence`
    monthly-only contract.
  - If monthly-only is confirmed, enforce it consistently and add tests.
  - Do not impose this restriction until the specification decision is explicit.

- [ ] **Canonical loader consistency.**
  - Canonical loaders compute ATH/underwater flags and running-ATH values but do
    not validate them at loader boundaries.
  - Review whether these should be validated at canonical loader/factory
    boundaries.
  - Keep these checks out of the generic `MarketSnapshot` constructor unless the
    domain specification is explicitly broadened.
  - Identify the appropriate tests and enforcement points.

- [ ] **`ReturnSequence` return-domain validation.**
  - `ReturnSequence` validates lengths and frequency but not return values; it
    accepts returns below -100%, which can produce negative index levels.
  - Decide whether monthly returns must be bounded below by -100%.
  - If confirmed, enforce the constraint at the appropriate input boundary and
    add tests.
  - Do not duplicate the `MarketSnapshot` non-negative index-level validation or
    change it without evidence.
