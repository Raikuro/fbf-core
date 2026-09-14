"""Infrastructure persistence package (v0.4).

Public API for the SQLite persistence layer.
"""

from .codecs import (
    AllocationPolicyCodec,
    CanonicalDatasetLoader,
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
    "CanonicalDatasetLoader",
    "CorruptedDatabaseError",
    "create_persistence_context",
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
