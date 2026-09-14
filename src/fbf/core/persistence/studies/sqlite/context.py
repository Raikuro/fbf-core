"""Persistence context factory.

Provides the ``create_persistence_context`` function for creating fully
wired PersistenceReconstructionContext instances.
"""

from __future__ import annotations

from fbf.core.persistence.studies.sqlite.codecs import (
    AllocationPolicyCodec,
    CanonicalDatasetLoader,
    SimulationResultCodec,
    WithdrawalPolicyCodec,
)
from fbf.core.persistence.studies.sqlite.sqlite_repository import (
    PersistenceReconstructionContext,
)


def create_persistence_context(
    data_dir: str,
) -> PersistenceReconstructionContext:
    """Create a persistence context wired to the canonical CSV loader."""
    loader = CanonicalDatasetLoader(data_dir)
    return PersistenceReconstructionContext(
        dataset_loader=loader,
        policy_codecs={
            ("allocation", "AllocationPolicy"): AllocationPolicyCodec(),
            ("withdrawal", "WithdrawalPolicy"): WithdrawalPolicyCodec(),
        },
        simulation_result_codec=SimulationResultCodec(),
    )
