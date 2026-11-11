"""High-level Part 3 study construction from validated configuration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fbf.core.datasets.ern import load_cape_rows, prepare_ern_dataset
from fbf.core.domain.model.money import Money
from fbf.core.research.cohort_manifest import build_effective_manifest
from fbf.core.research.part3_planner import (
    PART3_EXPENSE_RATIO,
    Part3PlannerConfig,
    Part3PlanResult,
    materialize_part3_plan,
)
from fbf.core.study.builder import StudyConfiguration

__all__ = [
    "build_part3_plan_from_configuration",
    "load_packaged_part3_configuration",
]


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def load_packaged_part3_configuration() -> StudyConfiguration:
    """Load the packaged canonical Part 3 YAML configuration."""
    from importlib import resources

    try:
        import yaml
    except ImportError as err:
        raise RuntimeError(
            "PyYAML is required to load the packaged Part 3 configuration"
        ) from err
    text = (
        resources.files("fbf.core.research.config")
        .joinpath("part3_canonical.yaml")
        .read_text(encoding="utf-8")
    )
    raw: Any = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("Packaged Part 3 configuration must be a YAML mapping")
    return StudyConfiguration.from_yaml(raw)


def build_part3_plan_from_configuration(
    data_dir: Path,
    initial_wealth: Money,
    *,
    configuration: StudyConfiguration | None = None,
    require_cape: bool = True,
) -> Part3PlanResult:
    """Prepare data, build the effective manifest, and materialize Part 3."""
    config = configuration or load_packaged_part3_configuration()
    if config.experiments is None:
        raise ValueError(
            "Part 3 requires explicit experiments; provide A-D pairs in YAML"
        )
    if config.cohort_start_date is None or config.cohort_end_date is None:
        raise ValueError(
            "Part 3 configuration requires cohorts.start_date and cohorts.end_date"
        )

    coverage_years = max(
        max(config.horizon_years), config.cohort_horizon_years or 0
    )
    required_through = _add_months(
        config.cohort_end_date, coverage_years * 12
    )
    prepared = prepare_ern_dataset(
        data_dir,
        config=config.projection_config,
        required_through=required_through,
        legacy_mode=config.legacy_mode,
    )
    manifest = build_effective_manifest(
        dataset=prepared.dataset,
        metadata=prepared.metadata,
        cape_rows=load_cape_rows(data_dir),
        cohort_start=config.cohort_start_date,
        cohort_end=config.cohort_end_date,
        fee=config.expense_ratio or PART3_EXPENSE_RATIO,
        require_cape=require_cape,
    )
    planner_config = Part3PlannerConfig(
        equity_allocations=config.allocation_policy_values,
        withdrawal_rates=config.withdrawal_policy_values,
        horizon_years=config.horizon_years,
        final_value_targets=None,
        allocation_policy_type=config.allocation_policy_type,
        withdrawal_policy_type=config.withdrawal_policy_type,
        expense_ratio=config.expense_ratio or PART3_EXPENSE_RATIO,
        experiments=config.experiments,
        legacy_cartesian=config.legacy_mode,
    )
    return materialize_part3_plan(
        manifest=manifest,
        canonical_trajectory=prepared.dataset,
        config=planner_config,
        initial_wealth=initial_wealth,
    )
