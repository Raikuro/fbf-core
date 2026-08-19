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
from .dataset_cache import (
    DatasetCache,
    clear_default_dataset_cache,
    get_default_dataset_cache,
)
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
    "clear_default_dataset_cache",
    "CorruptedDatabaseError",
    "create_persistence_context",
    "DatasetCache",
    "DefaultDatasetResolver",
    "DuplicateStudyError",
    "ExperimentIdentity",
    "get_default_dataset_cache",
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
