# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
are removed. See `AGENTS.md` for the documentation policy. Current methodology,
acceptance anchors, and project conclusions are in
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

---

## Part 3 Published-Anchor Classification

**Classification:** partially resolved; exact 2016 methodology remains open

### Exact 2016 Methodology Reproduction

The historical 2016 Part 3 implementation and validation are complete. The
dedicated `part3_2016.yaml` configuration reproduces all six published article
anchors within 1pp. The canonical 2026 C divergence is closed: controlled runs
and independent workbook recalculation establish it as an expected
cutoff/projection difference, not an implementation defect. See
[`docs/ERN_METHODOLOGY.md`](docs/ERN_METHODOLOGY.md).

Exact historical reproduction remains unconfirmed. The original GNU Octave
research engine is unavailable. The current v2.0 workbook has now been
recalculated independently with its own formulas and aggregated externally by
prior-month Shiller CAPE; this reproduces all six anchor counts exactly. The
five A30/B60 overall-only differences in the initial June-cutoff comparison were
caused by the June-versus-September 2016 cutoff and projection-start mismatch:
the workbook copy began projection in July 2016, while production begins in
October 2016. Aligning the workbook projection start to October 2016 removes all
five differences. No unresolved A30/B60 engine discrepancy remains.

Remaining open questions:

- Confirm the article's exact cohort eligibility rules.
- Verify the historical CAPE vintage and confirm the origin and applicability
  of each published anchor.
- Establish whether the engine/workbook withdrawal and timing convention is the
  article's convention; production matches the independently recalculated
  workbook when historical cutoffs and projection starts are aligned, and it
  reproduces all six published anchors, but this does not conclusively establish
  that the original GNU Octave engine used identical conventions.

Do not update, re-baseline, weaken, or remove the anchors or assertions without
explicit approval.
