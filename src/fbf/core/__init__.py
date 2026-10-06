"""FIRE Backtesting Framework (FBF) Core Engine."""

from __future__ import annotations

from fbf.core.application import (
    ExecutionOptions,
    ResearchExecutionResult,
    run_study,
)
from fbf.core.datasets import build_prescribed_dataset, load_canonical_dataset
from fbf.core.domain.policies import AllocationPolicyType, WithdrawalPolicyType
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy, GlidepathCadence
from fbf.core.errors import CoreError
from fbf.core.execution import (
    CompositeProfiler,
    CpuProfiler,
    DeterministicResult,
    DeterministicTrajectory,
    EnhancedProfileReport,
    ExecutionBackend,
    ExecutionProfiler,
    ExecutionStrategy,
    MemoryProfiler,
    NestedPhaseTiming,
    NoOpProfiler,
    Profiler,
    ProfileReport,
    execute_deterministic_trajectory,
    execute_study_plan,
)
from fbf.core.optimization import optimize_part52, optimize_study_swr
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
    "AllocationPolicyType",
    "WithdrawalPolicyType",
    "GlidepathAllocationPolicy",
    "GlidepathCadence",
    "StudyConfiguration",
    "run_study",
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
    "execute_deterministic_trajectory",
    "ResearchExecutionResult",
    "run_study",
    "optimize_study_swr",
    "optimize_part52",
    "load_canonical_dataset",
    "build_prescribed_dataset",
    "StudyRepository",
    "create_study_repository",
    "CoreError",
    "__version__",
    "DeterministicTrajectory",
    "DeterministicResult",
    "Profiler",
    "NoOpProfiler",
    "ExecutionProfiler",
    "ProfileReport",
    "NestedPhaseTiming",
    "EnhancedProfileReport",
    "CpuProfiler",
    "MemoryProfiler",
    "CompositeProfiler",
]
