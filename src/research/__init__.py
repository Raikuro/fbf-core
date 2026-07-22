"""Research package for the Retirement Simulator.

Contains scientific study definitions, cohort generators, parameter sweep engines,
research execution orchestration, result aggregation, and reproducibility management.
"""

from research.domain.cohort.generator import CohortGenerator
from research.domain.cohort.specification import CohortSpecification
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.parameter.axis import ParameterAxis
from research.domain.parameter.configuration import ParameterConfiguration
from research.domain.parameter.engine import ParameterSweepEngine

__all__ = [
    "CohortSpecification",
    "CohortGenerator",
    "ExperimentDefinition",
    "ParameterConfiguration",
    "ParameterAxis",
    "ParameterSweepEngine",
]
