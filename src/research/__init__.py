"""Research package for the Retirement Simulator.

Contains scientific study definitions, cohort generators, parameter sweep engines,
research execution orchestration, result aggregation, and reproducibility management.
"""

from research.domain.cohort.specification import CohortSpecification
from research.domain.cohort.generator import CohortGenerator
from research.domain.experiment.definition import ExperimentDefinition

__all__ = [
    "CohortSpecification",
    "CohortGenerator",
    "ExperimentDefinition",
]
