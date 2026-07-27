"""Exception hierarchy for the persistence layer."""

class RepositoryError(Exception):
    """Base class for all persistence-related errors."""

class StudyNotFoundError(RepositoryError):
    """Raised when an experiment or plan is not found."""

class ResultsNotFoundError(RepositoryError):
    """Raised when execution results are not found."""

class DuplicateStudyError(RepositoryError):
    """Raised when an experiment name/revision already exists."""

class PersistenceError(RepositoryError):
    """Raised for general database constraint or operational failures."""

class CorruptedDatabaseError(RepositoryError):
    """Raised when the database schema or data is structurally invalid."""

class ReconstructionContextError(RepositoryError):
    """Raised when context-based reconstruction fails."""

class UnsupportedSerializationError(RepositoryError):
    """Raised when a codec fails to serialize or deserialize."""
