"""Part 20 T2.1 audit specification — YAML loader and typed model.

The audit matrix (Experiments A–E structural parameters and published
anchors) is defined once in ``tests/fixtures/ern_part20_e2e_audit.yaml``.
This module parses that file into frozen dataclasses for the gated E2E
test and its helpers.  Production code must not depend on this module.

Part 19/20 shared abstraction: DEFERRED (T2.1 architecture decision).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

from fbf.core.study import load_yaml

__all__ = [
    "AuditAnchor",
    "AuditMeta",
    "ECase",
    "FixedSWRSpec",
    "Part20AuditSpec",
    "PercentileSearchSpec",
    "StructuralCounts",
    "UnsupportedSpec",
    "load_part20_audit_spec",
    "PART20_AUDIT_UNITS",
]

# Display-precision quantum per anchor unit (constraint: unit-driven).
PART20_AUDIT_UNITS: frozenset[str] = frozenset({"percent", "percent_1dp", "usd"})

_PERCENTILE_METRICS: frozenset[str] = frozenset(
    {"failsafe", "p01", "p03", "p05", "p10", "p25"}
)
_E_METRICS: frozenset[str] = frozenset(
    {"portfolio_y2", "portfolio_y10", "stock_allocation"}
)


@dataclass(frozen=True, slots=True)
class AuditMeta:
    """File-level identification for the audit specification."""

    name: str
    spec_version: str
    notes: str


@dataclass(frozen=True, slots=True)
class StructuralCounts:
    """Frozen structural expectations (audit §3–§7)."""

    total_cohorts: int
    cape_available: int
    cape_high: int
    strategy_count: int
    cells_a: int
    cells_b: int
    cells_c: int
    cells_d: int
    cells_e_cases: int


@dataclass(frozen=True, slots=True)
class PercentileSearchSpec:
    """Experiments A/B/D: batched per-cohort SWR search."""

    id: str
    horizon_years: int
    populations: tuple[str, ...]
    fv_targets: tuple[Decimal, ...]
    cells: int
    reuse_from: str | None = None


@dataclass(frozen=True, slots=True)
class FixedSWRSpec:
    """Experiment C: fixed-SWR failure-rate grid."""

    id: str
    horizons_years: tuple[int, ...]
    fixed_swrs: tuple[Decimal, ...]
    population: str
    final_value_target: Decimal
    cells: int


@dataclass(frozen=True, slots=True)
class ECase:
    """One declarative Experiment E case (never executed)."""

    id: str
    strategy: str
    sequence: str


@dataclass(frozen=True, slots=True)
class UnsupportedSpec:
    """Experiment E: declarative capability gaps."""

    id: str
    capability_gaps: tuple[str, ...]
    cases: tuple[ECase, ...]
    cells: int


PercentileSearchSpecT = PercentileSearchSpec
AuditExperiment = PercentileSearchSpec | FixedSWRSpec | UnsupportedSpec


@dataclass(frozen=True, slots=True)
class AuditAnchor:
    """One published reference value (external reference data)."""

    experiment: str
    strategy: str
    metric: str
    horizon_years: int | None
    final_value_target: Decimal | None
    cape_regime: str
    published: Decimal
    unit: str
    withdrawal_rate: Decimal | None = None
    scenario: str | None = None

    def __post_init__(self) -> None:
        if self.unit not in PART20_AUDIT_UNITS:
            raise ValueError(
                f"anchor {self.experiment}/{self.strategy}: invalid unit {self.unit!r}"
            )
        if self.experiment not in {"A", "B", "C", "D", "E"}:
            raise ValueError(f"invalid experiment id {self.experiment!r}")


@dataclass(frozen=True, slots=True)
class Part20AuditSpec:
    """Fully loaded Part 20 T2.1 audit specification."""

    meta: AuditMeta
    structural_counts: StructuralCounts
    experiments: tuple[AuditExperiment, ...]
    anchors: tuple[AuditAnchor, ...]

    def experiment(self, exp_id: str) -> AuditExperiment:
        """Return the experiment with *exp_id* (A–E)."""
        for exp in self.experiments:
            if exp.id == exp_id:
                return exp
        raise KeyError(f"experiment {exp_id!r} not present in audit spec")

    def anchors_for(self, exp_id: str) -> tuple[AuditAnchor, ...]:
        """Return published anchors belonging to *exp_id*."""
        return tuple(a for a in self.anchors if a.experiment == exp_id)


def _req(raw: Mapping[str, object], key: str, where: str) -> object:
    if key not in raw:
        raise ValueError(f"{where}: missing required key {key!r}")
    return raw[key]


def _dec(raw: object, where: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise ValueError(f"{where}: expected numeric value, got {raw!r}")
    return Decimal(str(raw))


def _int(raw: object, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{where}: expected int, got {raw!r}")
    return raw


def _str(raw: object, where: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{where}: expected str, got {raw!r}")
    return raw


def _str_tuple(raw: object, where: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{where}: expected list, got {type(raw).__name__}")
    return tuple(_str(item, f"{where}[{i}]") for i, item in enumerate(raw))


def _dec_tuple(raw: object, where: str) -> tuple[Decimal, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{where}: expected list, got {type(raw).__name__}")
    return tuple(_dec(item, f"{where}[{i}]") for i, item in enumerate(raw))


def _int_tuple(raw: object, where: str) -> tuple[int, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{where}: expected list, got {type(raw).__name__}")
    return tuple(_int(item, f"{where}[{i}]") for i, item in enumerate(raw))


def _parse_meta(raw: object) -> AuditMeta:
    if not isinstance(raw, dict):
        raise ValueError(f"meta: expected mapping, got {type(raw).__name__}")
    return AuditMeta(
        name=_str(_req(raw, "name", "meta"), "meta.name"),
        spec_version=_str(_req(raw, "spec_version", "meta"), "meta.spec_version"),
        notes=_str(raw.get("notes", ""), "meta.notes"),
    )


def _parse_counts(raw: object) -> StructuralCounts:
    if not isinstance(raw, dict):
        raise ValueError(
            f"structural_counts: expected mapping, got {type(raw).__name__}"
        )
    keys = (
        "total_cohorts",
        "cape_available",
        "cape_high",
        "strategy_count",
        "cells_a",
        "cells_b",
        "cells_c",
        "cells_d",
        "cells_e_cases",
    )
    values = {key: _int(_req(raw, key, "structural_counts"), key) for key in keys}
    return StructuralCounts(**values)


def _parse_experiment(raw: object, index: int) -> AuditExperiment:
    where = f"experiments[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected mapping, got {type(raw).__name__}")
    exp_id = _str(_req(raw, "id", where), f"{where}.id")
    kind = _str(_req(raw, "kind", where), f"{where}.kind")
    cells = _int(_req(raw, "cells", where), f"{where}.cells")
    if kind == "percentile_search":
        reuse = raw.get("reuse_from")
        return PercentileSearchSpec(
            id=exp_id,
            horizon_years=_int(
                _req(raw, "horizon_years", where), f"{where}.horizon_years"
            ),
            populations=_str_tuple(
                _req(raw, "populations", where), f"{where}.populations"
            ),
            fv_targets=_dec_tuple(_req(raw, "fv_targets", where), f"{where}.fv_targets"),
            cells=cells,
            reuse_from=_str(reuse, f"{where}.reuse_from") if reuse is not None else None,
        )
    if kind == "fixed_swr":
        return FixedSWRSpec(
            id=exp_id,
            horizons_years=_int_tuple(
                _req(raw, "horizons_years", where), f"{where}.horizons_years"
            ),
            fixed_swrs=_dec_tuple(_req(raw, "fixed_swrs", where), f"{where}.fixed_swrs"),
            population=_str(_req(raw, "population", where), f"{where}.population"),
            final_value_target=_dec(
                _req(raw, "final_value_target", where), f"{where}.final_value_target"
            ),
            cells=cells,
        )
    if kind == "unsupported":
        cases_raw = _req(raw, "cases", where)
        if not isinstance(cases_raw, list):
            raise ValueError(f"{where}.cases: expected list")
        cases: list[ECase] = []
        for j, case_raw in enumerate(cases_raw):
            cwhere = f"{where}.cases[{j}]"
            if not isinstance(case_raw, dict):
                raise ValueError(f"{cwhere}: expected mapping")
            cases.append(
                ECase(
                    id=_str(_req(case_raw, "id", cwhere), f"{cwhere}.id"),
                    strategy=_str(
                        _req(case_raw, "strategy", cwhere), f"{cwhere}.strategy"
                    ),
                    sequence=_str(
                        _req(case_raw, "sequence", cwhere), f"{cwhere}.sequence"
                    ),
                )
            )
        gaps = _str_tuple(
            _req(raw, "capability_gaps", where), f"{where}.capability_gaps"
        )
        return UnsupportedSpec(id=exp_id, capability_gaps=gaps, cases=tuple(cases), cells=cells)
    raise ValueError(f"{where}: unknown experiment kind {kind!r}")


def _parse_anchor(raw: object, index: int) -> AuditAnchor:
    where = f"anchors[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected mapping, got {type(raw).__name__}")
    horizon = raw.get("horizon_years")
    fv = raw.get("final_value_target")
    wr = raw.get("withdrawal_rate")
    scenario = raw.get("scenario")
    return AuditAnchor(
        experiment=_str(_req(raw, "experiment", where), f"{where}.experiment"),
        strategy=_str(_req(raw, "strategy", where), f"{where}.strategy"),
        metric=_str(_req(raw, "metric", where), f"{where}.metric"),
        horizon_years=_int(horizon, f"{where}.horizon_years") if horizon is not None else None,
        final_value_target=_dec(fv, f"{where}.final_value_target") if fv is not None else None,
        cape_regime=_str(_req(raw, "cape_regime", where), f"{where}.cape_regime"),
        published=_dec(_req(raw, "published", where), f"{where}.published"),
        unit=_str(_req(raw, "unit", where), f"{where}.unit"),
        withdrawal_rate=_dec(wr, f"{where}.withdrawal_rate") if wr is not None else None,
        scenario=_str(scenario, f"{where}.scenario") if scenario is not None else None,
    )


def _validate(spec: Part20AuditSpec) -> None:
    ids = [exp.id for exp in spec.experiments]
    if sorted(ids) != ["A", "B", "C", "D", "E"]:
        raise ValueError(f"experiments must be exactly A–E, got {ids}")
    for exp in spec.experiments:
        if isinstance(exp, PercentileSearchSpec):
            for pop in exp.populations:
                if pop not in {"HIGH", "LOW"}:
                    raise ValueError(f"experiment {exp.id}: bad population {pop!r}")
            if not exp.fv_targets:
                raise ValueError(f"experiment {exp.id}: fv_targets must be non-empty")
        if isinstance(exp, FixedSWRSpec):
            if exp.population not in {"HIGH", "LOW"}:
                raise ValueError(f"experiment {exp.id}: bad population {exp.population!r}")
            if not exp.fixed_swrs or not exp.horizons_years:
                raise ValueError(f"experiment {exp.id}: empty grid axes")
        if isinstance(exp, UnsupportedSpec):
            if len(exp.cases) != exp.cells:
                raise ValueError(
                    f"experiment {exp.id}: cells={exp.cells} != len(cases)={len(exp.cases)}"
                )
            if not exp.capability_gaps:
                raise ValueError(f"experiment {exp.id}: capability_gaps must be non-empty")
    if not spec.anchors:
        raise ValueError("audit spec must declare at least one anchor")
    for anchor in spec.anchors:
        if anchor.experiment == "C" and anchor.withdrawal_rate is None:
            raise ValueError(
                f"C anchor {anchor.strategy}: withdrawal_rate is required"
            )
        if anchor.experiment != "C" and anchor.metric == "failure_rate":
            raise ValueError("failure_rate metric is only valid for experiment C")
        if anchor.experiment in {"A", "B", "D"} and anchor.metric not in _PERCENTILE_METRICS:
            raise ValueError(
                f"{anchor.experiment} anchor metric {anchor.metric!r} not in "
                f"{sorted(_PERCENTILE_METRICS)}"
            )
        if anchor.experiment == "E" and anchor.metric not in _E_METRICS:
            raise ValueError(f"E anchor metric {anchor.metric!r} not in {sorted(_E_METRICS)}")
    counts = spec.structural_counts
    by_id = {exp.id: exp for exp in spec.experiments}
    if by_id["A"].cells != counts.cells_a:
        raise ValueError("experiment A cells disagree with structural_counts.cells_a")
    if by_id["B"].cells != counts.cells_b:
        raise ValueError("experiment B cells disagree with structural_counts.cells_b")
    if by_id["C"].cells != counts.cells_c:
        expected = counts.strategy_count * len(
            by_id["C"].fixed_swrs  # type: ignore[union-attr]
        ) * len(by_id["C"].horizons_years)  # type: ignore[union-attr]
        if by_id["C"].cells != expected:
            raise ValueError("experiment C cells disagree with strategy×swr×horizon product")
    if by_id["D"].cells != counts.cells_d:
        raise ValueError("experiment D cells disagree with structural_counts.cells_d")
    if by_id["E"].cells != counts.cells_e_cases:
        raise ValueError("experiment E cells disagree with structural_counts.cells_e_cases")
    for exp_id, cells in (
        ("A", counts.cells_a),
        ("B", counts.cells_b),
        ("D", counts.cells_d),
    ):
        exp = by_id[exp_id]
        assert isinstance(exp, PercentileSearchSpec)
        expected = counts.strategy_count * len(exp.populations) * len(exp.fv_targets)
        if cells != expected:
            raise ValueError(
                f"experiment {exp_id}: cells={cells} != strategy×pop×fv={expected}"
            )


def load_part20_audit_spec(path: Path) -> Part20AuditSpec:
    """Load and validate the Part 20 T2.1 audit specification from *path*."""
    raw = load_yaml(path)
    experiments_raw = _req(raw, "experiments", "root")
    anchors_raw = _req(raw, "anchors", "root")
    if not isinstance(experiments_raw, list):
        raise ValueError("experiments: expected list")
    if not isinstance(anchors_raw, list):
        raise ValueError("anchors: expected list")
    spec = Part20AuditSpec(
        meta=_parse_meta(_req(raw, "meta", "root")),
        structural_counts=_parse_counts(_req(raw, "structural_counts", "root")),
        experiments=tuple(
            _parse_experiment(item, i) for i, item in enumerate(experiments_raw)
        ),
        anchors=tuple(_parse_anchor(item, i) for i, item in enumerate(anchors_raw)),
    )
    _validate(spec)
    return spec
