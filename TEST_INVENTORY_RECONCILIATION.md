# Phase 1 Test Inventory Reconciliation

The P1.7 baseline was 978 tests: 686 allocated to Core and 292 allocated to
CLI. P1.8 planned four Core and three CLI architectural contract tests, for a
historical post-extraction target of 985.

P1.12R established that 17 tests had been assigned to the wrong repository in
the historical allocation: seven grid command-output tests in
`tests/cli/test_grid_chaining.py` and ten CLI framework-smoke tests in
`tests/integration/test_framework_infrastructure.py`. They test terminal
behavior, command registration, and CLI execution-mode selection, not Core
implementation behavior.

| Inventory | Core | CLI | Combined |
|---|---:|---:|---:|
| P1.7 legacy baseline | 686 | 292 | 978 |
| Corrected ownership transfer (Core → CLI) | -17 | +17 | 0 |
| Corrected baseline | 669 | 309 | 978 |
| P1.8 contracts | +4 | +3 | +7 |
| Certified target inventory | **673** | **312** | **985** |

The transfer does not remove an assertion. The restored seven grid command
tests are in `fbf-cli/tests/unit/test_grid_cli_contract.py`; the ten framework
CLI tests are in `fbf-cli/tests/unit/test_framework_cli_smoke.py`. Core retains
the engine-level chaining, exact-equivalence, and oracle tests.

The 16 initially missing ERN tests were restored to Core: four engine-to-oracle
acceptance tests (environment-gated), twelve worker-selection tests, and their
black-box harness/fixtures. The prior 657 Core collection therefore became 673
after restoration and corrected ownership allocation.
