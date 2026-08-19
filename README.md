# fbf-core

High-performance, deterministic FIRE (Financial Independence, Retire Early) simulation and safe withdrawal rate research engine.

## Features
- **Deterministic Decimal Arithmetic:** Bit-exact financial modeling with zero floating-point drift.
- **Canonical 9-Step Monthly Pipeline:** Modular monthly execution steps for cash withdrawals, allocations, and market evolution.
- **Closed-Form Fast Path:** Analytical recurrence optimization for constant policies.
- **Zero Third-Party Runtime Dependencies:** Runs 100% on the Python 3.13 standard library.
