"""FIRE Backtesting Framework (FBF) Core Engine."""

from __future__ import annotations

from fbf.core.errors import CoreError
from fbf.core.execution import (
    ExecutionBackend,
    ExecutionOptions,
    ExecutionProfiler,
    ExecutionStrategy,
    NoOpProfiler,
    Profiler,
    ProfileReport,
    ResearchExecutionResult,
    execute_study_plan,
)
from fbf.core.optimization import optimize_study_swr
from fbf.core.persistence import StudyRepository, create_study_repository
from fbf.core.study import (
    BuiltStudy,
    CohortGenerator,
    CohortSpecification,
    ExperimentDefinition,
    ParameterAxis,
    ParameterConfiguration,
    ParameterSweepEngine,
    PlannedSimulationUnit,
    ResearchPlan,
    StudyConfiguration,
    StudyPlanResult,
    build_study_plan,
)

__version__ = "0.1.0"

__all__ = [
    "StudyConfiguration",
    "StudyPlanResult",
    "build_study_plan",
    "BuiltStudy",
    "ResearchPlan",
    "PlannedSimulationUnit",
    "CohortGenerator",
    "CohortSpecification",
    "ParameterSweepEngine",
    "ParameterConfiguration",
    "ParameterAxis",
    "ExperimentDefinition",
    "ExecutionBackend",
    "ExecutionStrategy",
    "ExecutionOptions",
    "execute_study_plan",
    "ResearchExecutionResult",
    "optimize_study_swr",
    "StudyRepository",
    "create_study_repository",
    "CoreError",
    "__version__",
    "Profiler",
    "NoOpProfiler",
    "ExecutionProfiler",
    "ProfileReport",
]
