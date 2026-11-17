# TODO

Open work only. Remove entries when resolved. Architectural and product
decisions are separated from routine cleanup.

## Decisions

- [ ] Decide the ownership and compatibility status of the two exported mutable
  `SimulationState` implementations before removing or consolidating either:
  `fbf.core.domain.model.simulation.SimulationState` and
  `fbf.core.execution.pipeline.simulation.SimulationState`. Both are exported
  since `v0.1.0` and may have external consumers even though no current
  production or sibling-repository code imports either directly. The domain
  state is a generic model with optional fields; the execution state is a
  richer pipeline state with context, debt, status, and timeline fields. Keep
  both unchanged unless an API deprecation plan is approved.

- [ ] Decide whether to retain or retire the legacy debt fixtures and their
  self-test: `tests/fixtures/debt.py` and
  `tests/unit/execution/test_debt_fixtures.py`. The self-test validates the
  fixture only against `tests/support/ern/debt_oracle.py`, which is separately
  covered by `tests/integration/ern/test_debt_oracle.py`; no production, example,
  documentation, or sibling-repository consumer was found. Recommendation:
  retain as a known-answer reference suite unless retirement is approved, in
  which case port its unique multi-month and terminal-liquidation cases to the
  oracle or production-facing tests first.
