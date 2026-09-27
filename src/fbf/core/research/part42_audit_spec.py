"""Part 42 audit specification — machine-readable loaders and types.

Loads the T5.1 audit specification from
``tests/fixtures/ern_part42_e2e_audit.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class Part42Anchor:
    """One published anchor from Tables 01–05."""

    table: int  # 1, 2, 3, 4, or 5
    scenario: str  # e.g., "Baseline", "Delay RE 1Y", "$5k/m contributions"
    published: str  # The published value as string for exact Decimal parsing
    unit: str  # "usd", "percent", "percent_2dp"
    experiment_id: str  # Maps to Part42ExperimentConfig.id
    decade: str | None = None  # e.g., "1920s", "1930s", ..., "Min", "Rel to Base"
    condition: str | None = None  # e.g., "All", "CAPE > 20", "Drdwn 0-10%"
    metric: str = "failsafe"  # "failsafe", "failure_rate", "relative"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Part42AuditSpec:
    """Complete Part 42 audit specification."""

    meta: dict[str, Any]
    structural_counts: dict[str, int]
    experiments: list[dict[str, Any]]
    table01_anchors: dict[str, dict[str, str]]
    table02_anchors: dict[str, dict[str, str]]
    table03_anchors: dict[str, dict[str, str]]
    table04_anchors: dict[str, dict[str, str]]
    table05_anchors: dict[str, dict[str, str]]
    aggregation: dict[str, Any]
    data_vintage: dict[str, Any]

    @property
    def anchors(self) -> list[Part42Anchor]:
        """Generate all anchor entries from the table data."""
        anchors = []

        # Table 01 anchors
        for scenario, conditions in self.table01_anchors.items():
            for cond, value in conditions.items():
                anchors.append(Part42Anchor(
                    table=1,
                    scenario=scenario,
                    condition=cond,
                    metric="failure_rate",
                    published=value,
                    unit="percent",
                    experiment_id=self._scenario_to_experiment(scenario, 1),
                ))

        # Table 02 anchors
        for decade, values in self.table02_anchors.items():
            for scenario, value in values.items():
                anchors.append(Part42Anchor(
                    table=2,
                    scenario=scenario,
                    decade=decade,
                    metric="failsafe",
                    published=value,
                    unit="usd",
                    experiment_id=self._scenario_to_experiment(scenario, 2),
                ))

        # Table 03 anchors
        for decade, values in self.table03_anchors.items():
            for scenario, value in values.items():
                metric = "relative" if decade == "Rel to Base" else "failsafe"
                unit = "percent_2dp" if decade == "Rel to Base" else "usd"
                anchors.append(Part42Anchor(
                    table=3,
                    scenario=scenario,
                    decade=decade,
                    metric=metric,
                    published=value,
                    unit=unit,
                    experiment_id=self._scenario_to_experiment(scenario, 3),
                ))

        # Table 04 anchors
        for decade, values in self.table04_anchors.items():
            for scenario, value in values.items():
                metric = "relative" if decade == "Rel to Base" else "failsafe"
                unit = "percent_2dp" if decade == "Rel to Base" else "usd"
                anchors.append(Part42Anchor(
                    table=4,
                    scenario=scenario,
                    decade=decade,
                    metric=metric,
                    published=value,
                    unit=unit,
                    experiment_id=self._scenario_to_experiment(scenario, 4),
                ))

        # Table 05 anchors
        for decade, values in self.table05_anchors.items():
            for scenario, value in values.items():
                metric = "relative" if decade == "Rel to Base" else "failsafe"
                unit = "percent_2dp" if decade == "Rel to Base" else "usd"
                anchors.append(Part42Anchor(
                    table=5,
                    scenario=scenario,
                    decade=decade,
                    metric=metric,
                    published=value,
                    unit=unit,
                    experiment_id=self._scenario_to_experiment(scenario, 5),
                ))

        return anchors

    def _scenario_to_experiment(self, scenario: str, table: int) -> str:
        """Map scenario name to experiment ID based on table."""
        # Table 01 scenarios
        if table == 1:
            mapping = {
                "Baseline": "A",
                "Delay RE 1Y": "B",
                "$5k/m contributions": "C",
                "50Y Baseline": "D",
                "Delay RE 1Y (50Y)": "E_delay",
                "$5k/m contributions (50Y)": "E_contrib",
                "50Y Baseline + SocSec": "F_baseline",
                "Delay RE 1Y (50Y+SocSec)": "F_delay",
                "$5k/m contributions (50Y+SocSec)": "F_contrib",
                "2-year delay": "G_2yr",
            }
            return mapping.get(scenario, "A")

        # Tables 02-05: all use 75/25 constant allocation
        # The experiment mapping is based on the scenario
        mapping = {
            "Baseline": "A",
            "Delay RE 1Y": "B",
            "$5k/m contributions": "C",
            "30Y Baseline": "A",
            "30Y Delay RE 1Y": "B",
            "30Y $5k/m contr.": "C",
            "50Y Baseline": "D",
            "50Y Delay RE 1Y": "E_delay",
            "50Y $5k/m contr.": "E_contrib",
            "50Y+SS Baseline": "F_baseline",
            "50Y+SS Delay RE 1Y": "F_delay",
            "50Y+SS $5k/m contr.": "F_contrib",
            "2-year delay": "G_2yr",
        }
        return mapping.get(scenario, "A")


def load_part42_audit_spec(path: Path) -> Part42AuditSpec:
    """Load the Part 42 audit specification from YAML."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    def list_to_dict(table_list: list[dict[str, str]], key_field: str) -> dict[str, dict[str, str]]:
        """Convert list of dicts to dict keyed by key_field."""
        result: dict[str, dict[str, str]] = {}
        for row in table_list:
            key = row.pop(key_field)
            result[key] = row
        return result

    return Part42AuditSpec(
        meta=raw.get("meta", {}),
        structural_counts=raw.get("structural_counts", {}),
        experiments=raw.get("experiments", []),
        table01_anchors=raw.get("table01_anchors", {}),
        table02_anchors=list_to_dict(raw.get("table02_anchors", []), "decade"),
        table03_anchors=list_to_dict(raw.get("table03_anchors", []), "decade"),
        table04_anchors=list_to_dict(raw.get("table04_anchors", []), "decade"),
        table05_anchors=list_to_dict(raw.get("table05_anchors", []), "decade"),
        aggregation=raw.get("aggregation", {}),
        data_vintage=raw.get("data_vintage", {}),
    )
