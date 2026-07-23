"""Research execution orchestrator.

Contains ``ResearchExecutor`` — the stateless research execution orchestration service.

``ResearchExecutor`` accepts an immutable, pre-validated ``ResearchPlan``, translates
every planned simulation unit into the frozen engine's ``SimulationContext`` contract,
delegates execution exactly once to the injected ``SimulationExecutor``, and returns
a ``ResearchExecutionResult`` preserving lossless index-based provenance between each
planned unit and its corresponding engine result.

Ownership Boundaries (Frozen)
------------------------------
- ``ResearchPlan`` is consumed, never built or modified.
- No planning logic, cohort generation, parameter generation, policy materialisation,
  aggregation, optimisation, or financial calculations are present in this module.
- Parallelisation must be achieved externally by partitioning ``ResearchPlan`` instances
  above this layer; ``ResearchExecutor`` is deterministic and single-threaded.
"""

from __future__ import annotations

from engine.application.executor import SimulationExecutor
from engine.application.simulation import ExperimentDefinition as EngineExperimentDefinition
from engine.application.simulation_context import SimulationContext
from research.domain.experiment.definition import ExperimentDefinition
from research.domain.plan import PlannedSimulationUnit, ResearchPlan
from research.orchestration.errors import InvalidResearchPlanError, ResearchExecutionError
from research.orchestration.result import ResearchExecutionResult


class ResearchExecutor:
    """Stateless Research Execution Orchestrator.

    Translates one pre-validated, immutable ``ResearchPlan`` into engine execution
    requests, delegates exactly once to the injected ``SimulationExecutor``, and
    returns an immutable ``ResearchExecutionResult`` with lossless, ordered plan-unit
    provenance.

    Parameters
    ----------
    simulation_executor:
        A fully initialised ``SimulationExecutor`` instance injected by the caller.
        ``ResearchExecutor`` never instantiates runners, generators, policies, or
        any other collaborator internally.
    """

    def __init__(self, simulation_executor: SimulationExecutor) -> None:
        if simulation_executor is None:
            raise ValueError("simulation_executor cannot be None")
        if not callable(getattr(simulation_executor, "execute", None)):
            raise ValueError("simulation_executor must expose a callable execute() method")
        self._simulation_executor = simulation_executor

    def execute(self, plan: ResearchPlan) -> ResearchExecutionResult:
        """Execute an immutable ResearchPlan exactly once via SimulationExecutor.

        Steps
        -----
        1. Defensively validate the plan's structural invariants.
        2. Translate every ``PlannedSimulationUnit`` into a ``SimulationContext``
           in the plan's exact index order.
        3. Delegate to ``SimulationExecutor.execute(...)`` exactly once.
        4. Wrap the result in a ``ResearchExecutionResult`` preserving provenance.

        Parameters
        ----------
        plan:
            An immutable, fully materialised ``ResearchPlan`` built externally by
            a dedicated planning component. Must satisfy the approved ``ResearchPlan``
            structural contract.

        Returns
        -------
        ResearchExecutionResult
            Immutable result containing the original plan and the ordered engine output.

        Raises
        ------
        InvalidResearchPlanError
            If the plan is missing, of wrong type, empty, structurally malformed, or
            a planned unit cannot be translated to a ``SimulationContext``. Raised
            before any call to ``SimulationExecutor``.
        ResearchExecutionError
            If ``SimulationExecutor`` raises an unexpected exception during execution.
            The original exception is preserved as the cause.
        """
        # --- Step 1: Defensive structural validation ---
        if not isinstance(plan, ResearchPlan):
            raise InvalidResearchPlanError(f"execute() expected a ResearchPlan, got {type(plan)!r}")
        # ResearchPlan.__post_init__ already enforces non-empty, but we validate again
        # here as per the approved defensive boundary at the executor's public entry point.
        if len(plan) == 0:
            raise InvalidResearchPlanError(
                "Cannot execute an empty ResearchPlan: units tuple must be non-empty"
            )

        # --- Step 2: Translate all units before calling SimulationExecutor ---
        # Full upfront translation ensures the complete plan can be expressed as engine
        # contexts before we make any engine call (fail-fast guarantee).
        contexts: list[SimulationContext] = []
        for idx, unit in enumerate(plan.units):
            try:
                context = self._create_context_for_unit(plan.experiment_definition, unit)
                contexts.append(context)
            except (InvalidResearchPlanError, ResearchExecutionError):
                raise
            except Exception as err:
                raise InvalidResearchPlanError(
                    f"Failed to translate plan unit at index {idx} "
                    f"(cohort={unit.cohort.start_date.isoformat()!r}) "
                    f"to SimulationContext: {err}"
                ) from err

        # --- Step 3: Build the engine experiment definition and delegate exactly once ---
        engine_definition = EngineExperimentDefinition(
            name=plan.experiment_definition.name,
            description=plan.experiment_definition.description,
            simulation_contexts=tuple(contexts),
        )
        try:
            experiment_run = self._simulation_executor.execute(engine_definition)
        except Exception as err:
            raise ResearchExecutionError(
                f"SimulationExecutor delegation failed for experiment "
                f"{plan.experiment_definition.name!r}: {err}"
            ) from err

        # --- Step 4: Return result preserving lossless index provenance ---
        return ResearchExecutionResult(plan=plan, experiment_result=experiment_run)

    def _create_context_for_unit(
        self,
        experiment_def: ExperimentDefinition,
        unit: PlannedSimulationUnit,
    ) -> SimulationContext:
        """Translate a single PlannedSimulationUnit to a frozen engine SimulationContext.

        Maps fields from the shared ``ExperimentDefinition`` and the unit-specific
        ``PlannedSimulationUnit`` onto the engine's ``SimulationContext`` contract.
        Policy objects and the materialised ``initial_portfolio`` are passed through
        unchanged — no interpretation or materialisation occurs here.

        Parameters
        ----------
        experiment_def:
            The shared experiment definition providing dataset, horizon, and wealth.
        unit:
            The planned unit providing cohort start date, allocation policy,
            withdrawal policy, and already-materialised initial portfolio.

        Returns
        -------
        SimulationContext
            A fully populated, frozen engine context ready for ``SimulationRunner``.

        Raises
        ------
        InvalidResearchPlanError
            If any field required to construct a valid ``SimulationContext`` is absent
            or incomplete in the unit.
        """
        # Validate completeness of the unit's engine-ready fields before constructing a
        # context. Fail-fast: all translation failures are caught before the first call
        # to SimulationExecutor.
        if unit.allocation_policy is None:
            raise InvalidResearchPlanError(
                f"PlannedSimulationUnit with cohort={unit.cohort.start_date.isoformat()!r} "
                "has a None allocation_policy; unit is incomplete"
            )
        if unit.withdrawal_policy is None:
            raise InvalidResearchPlanError(
                f"PlannedSimulationUnit with cohort={unit.cohort.start_date.isoformat()!r} "
                "has a None withdrawal_policy; unit is incomplete"
            )
        if unit.initial_portfolio is None:
            raise InvalidResearchPlanError(
                f"PlannedSimulationUnit with cohort={unit.cohort.start_date.isoformat()!r} "
                "has a None initial_portfolio; unit is incomplete"
            )

        # CohortSpecification.__post_init__ always sets a non-None id; assert for mypy.
        cohort_id: str = unit.cohort.id  # type: ignore[assignment]
        assert (
            cohort_id is not None
        ), f"CohortSpecification.id must not be None (cohort={unit.cohort.start_date!r})"

        return SimulationContext(
            experiment_name=experiment_def.name,
            cohort=cohort_id,
            start_date=unit.cohort.start_date,
            horizon_months=experiment_def.horizon_months,
            initial_wealth=experiment_def.initial_wealth,
            initial_portfolio=unit.initial_portfolio,
            dataset=experiment_def.dataset,
            allocation_policy=unit.allocation_policy,
            withdrawal_policy=unit.withdrawal_policy,
        )
