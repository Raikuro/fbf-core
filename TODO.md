# Technical TODOs

Unresolved technical work with continuing value. Completed or superseded items
must be removed. See `AGENTS.md` for the documentation policy governing this
file.

## Determinism

- Add a contract test proving `parallel_execute(plan, workers=k)` produces
  identical results to `sequential_execute(plan)` for the same plan.

- Add a test proving repeated execution of the same runner and context produces
  identical `SimulationResult` values.

## Boundary contracts

- Add a contract test preventing `SimulationRunner` and `SimulationExecutor`
  from importing financial-domain implementation details (enforce the
  orchestration-only invariant at the AST level).
