"""Research package experiments module.

Re-exports CohortSpecification and ExperimentDefinition from research.domain.
"""

from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition

__all__ = [
    "CohortSpecification",
    "ExperimentDefinition",
]
