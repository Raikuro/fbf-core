"""Infrastructure persistence package (v0.4).

Public API for the SQLite persistence layer.
"""

from .codecs import (
    AllocationPolicyCodec,
    DefaultDatasetResolver,
    SimulationResultCodec,
    WithdrawalPolicyCodec,
)
from .context import create_persistence_context
from .errors import (
    CorruptedDatabaseError,
    DuplicateStudyError,
    PersistenceError,
    PlanNotFoundError,
    ReconstructionContextError,
    RepositoryError,
    ResultsNotFoundError,
    StudyNotFoundError,
    UnsupportedSerializationError,
)
from .sqlite_repository import (
    ExperimentIdentity,
    PersistenceReconstructionContext,
    SQLiteRepository,
)

__all__ = [
    "AllocationPolicyCodec",
    "CorruptedDatabaseError",
    "create_persistence_context",
    "DefaultDatasetResolver",
    "DuplicateStudyError",
    "ExperimentIdentity",
    "PersistenceError",
    "PersistenceReconstructionContext",
    "PlanNotFoundError",
    "ReconstructionContextError",
    "RepositoryError",
    "ResultsNotFoundError",
    "SimulationResultCodec",
    "SQLiteRepository",
    "StudyNotFoundError",
    "UnsupportedSerializationError",
    "WithdrawalPolicyCodec",
]
