# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

## Determinism / Repeatability

- Define determinism and cross-strategy equivalence contracts.
- Add repeatability regression coverage for Reference, Decimal Fast Path,
  and Float Fast Path.
- Use exact assertions only where the contract guarantees exact equivalence.
- Use tolerance-based comparisons for Float Fast Path versus Reference.

## load_yaml() Runtime Error Clarity

- Improve the missing-PyYAML error so that the optional dependency and
  supported installation path are clear.
- Add regression coverage for the error behaviour.
