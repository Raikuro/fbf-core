# AGENTS.md — fbf-core Architecture Guide

This is the standalone `fbf-core` simulation repository.

## Layer Invariants
1. `fbf.core.domain` is pure math and entities with 0 upward dependencies.
2. `fbf.core.execution` manages simulation pipelines and execution strategies.
3. `fbf.core.study` handles Cartesian parameter sweeps and study configuration.
4. `fbf.core.optimization` provides SWR solvers.
5. Zero dependencies on CLI or presentation concerns.
