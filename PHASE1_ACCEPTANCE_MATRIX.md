# Phase 1 Acceptance Matrix

This is the authoritative, versioned list of Phase 1 separation acceptance
conditions. Each condition must be re-evaluated by P1.12; completion of an
implementation milestone is not evidence of certification.

| # | Acceptance condition | Mechanical evidence |
|---:|---|---|
| 1 | `fbf-core` is an independent Git repository. | `git rev-parse --show-toplevel` |
| 2 | `fbf-cli` is an independent Git repository. | `git rev-parse --show-toplevel` |
| 3 | The workspace parent has no `.git`. | path assertion |
| 4 | Neither permanent repository has a configured remote. | `git remote -v` |
| 5 | Core namespace migration is identifiable in history. | `git log` |
| 6 | CLI namespace migration is identifiable in history. | `git log` |
| 7 | The fixture restoration commit is retained. | `git log -- fixtures.py` |
| 8 | The legacy monorepo is clean and owner-controlled. | fixed-HEAD/status audit |
| 9 | Core test inventory is reconciled to its documented allocation. | collection manifest |
| 10 | CLI test inventory is reconciled to its documented allocation. | collection manifest |
| 11 | No behavioral assertion loss is unexplained. | AST/path manifest audit |
| 12 | Core contains no CLI implementation artifacts. | positive allowlist scan |
| 13 | CLI contains no Core implementation artifacts. | positive allowlist scan |
| 14 | Core never imports CLI. | AST import contract |
| 15 | Core domain remains downward-pure. | AST import contract |
| 16 | Execution never imports optimization. | AST import contract |
| 17 | CLI imports only documented Core Tier 1/Tier 2 modules. | AST import contract |
| 18 | Core root facade `__all__` matches the documented public surface. | contract test |
| 19 | Core builds with no third-party runtime dependency and packages `py.typed`. | wheel metadata audit |
| 20 | CLI wheel metadata declares the Core pin, PyYAML, and both entry points. | wheel metadata audit |
| 21 | CLI consumes an installed Core wheel, not a source tree. | clean-vEnv provenance check |
| 22 | Core and CLI complete applicable test suites successfully. | pytest results |
| 23 | The engine matches the complete ERN matrix using canonical Decimal comparison semantics. | ERN engine/oracle gate |
| 24 | Required parallel execution validates in a multiprocessing-capable environment. | process-pool test run |

P1.12 may certify Phase 1 only when all 24 conditions are PASS.
