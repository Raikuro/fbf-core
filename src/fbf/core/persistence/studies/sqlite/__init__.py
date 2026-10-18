"""Infrastructure persistence package (schema v4).

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
    ExecutionInProgressError,
    PersistenceError,
    PlanNotFoundError,
    ReconstructionContextError,
    RepositoryError,
    ResultsNotFoundError,
    StaleExecutionAttemptError,
    StudyNotFoundError,
    UnsupportedSerializationError,
)
from .sqlite_repository import (
    ExecutionAttempt,
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
    "ExecutionAttempt",
    "ExecutionInProgressError",
    "ExperimentIdentity",
    "PersistenceError",
    "PersistenceReconstructionContext",
    "PlanNotFoundError",
    "ReconstructionContextError",
    "RepositoryError",
    "ResultsNotFoundError",
    "SimulationResultCodec",
    "SQLiteRepository",
    "StaleExecutionAttemptError",
    "StudyNotFoundError",
    "UnsupportedSerializationError",
    "WithdrawalPolicyCodec",
]
