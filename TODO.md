# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

## Reference Execution Path Reassessment

- Evaluate whether the Reference execution path can be removed or restricted
  to oracle/validation use after the complete execution use-case and E2E
  inventory is available.

  The Decimal Fast Path is now proven bit-exact for its eligible policy
  family (constant-allocation + fixed-real-withdrawal) and provides an 8×
  speedup. However, the Reference implementation remains the canonical
  correctness/oracle implementation because it supports the general policy
  space and is the implementation against which optimized paths are validated.

  Compare all supported execution scenarios against the optimized paths. If
  every required production/research use case has an exact or otherwise
  explicitly justified optimized implementation, determine whether the
  Reference implementation should remain only as a canonical
  validation/oracle implementation or whether it still needs to be available
  as a runtime execution path.

  **Do not frame this as "remove Reference". The outcome is deliberately
  undecided.** The decision should be made only after we have the complete
  use-case inventory.

## Determinism

- Add a test proving repeated execution of the same runner and context produces
  identical `SimulationResult` values.

## load_yaml() Runtime Error Clarity

- `fbf.core.study.builder.load_yaml()` is a supported Tier 2 API that performs
  a lazy `import yaml`. When PyYAML is not installed, it raises a `RuntimeError`
  with a clear message suggesting `StudyConfiguration.from_dict()` as an
  alternative. Consider whether this error message should explicitly name the
  required pip extra (`pip install fbf-core[dev]`) or whether the current
  message is sufficient for the intended dependency model.
