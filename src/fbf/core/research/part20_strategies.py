"""Part 20 strategy universe — 21 static + 32 glidepath allocations.

Representation is fixed once here: a frozen ``Part20Strategy`` value that
builds the existing domain allocation policy (``ConstantAllocationPolicy``
or ``GlidepathAllocationPolicy``).  No new allocation-policy types are
introduced; T2.1 reuses the policy architecture as-is.

Part 19/20 shared abstraction: DEFERRED (T2.1 architecture decision).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fbf.core.domain.policies.allocation_policy import AllocationPolicy
from fbf.core.domain.policies.concrete import ConstantAllocationPolicy
from fbf.core.domain.policies.glidepath import GlidepathAllocationPolicy

__all__ = [
    "Part20Strategy",
    "part20_strategy_universe",
    "PART20_STRATEGY_COUNT",
    "PART20_STATIC_COUNT",
    "PART20_GLIDEPATH_COUNT",
]


@dataclass(frozen=True, slots=True)
class Part20Strategy:
    """One allocation strategy in the Part 20 universe.

    Exactly one of the static or glidepath field groups is populated,
    selected by ``kind``.
    """

    id: str
    kind: str  # "static" | "glidepath"
    equity_allocation: Decimal | None = None
    start_equity: Decimal | None = None
    end_equity: Decimal | None = None
    slope: Decimal | None = None
    mode: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("static", "glidepath"):
            raise ValueError(f"Part20Strategy.kind must be static|glidepath, got {self.kind!r}")
        if self.kind == "static":
            if self.equity_allocation is None:
                raise ValueError(f"static strategy {self.id!r} requires equity_allocation")
        else:
            if (
                self.start_equity is None
                or self.end_equity is None
                or self.slope is None
                or self.mode is None
            ):
                raise ValueError(
                    f"glidepath strategy {self.id!r} requires start/end/slope/mode"
                )

    @property
    def is_static(self) -> bool:
        return self.kind == "static"

    @property
    def is_active(self) -> bool:
        return self.kind == "glidepath" and self.mode == "active"

    def build_allocation_policy(self) -> AllocationPolicy:
        """Build the concrete domain allocation policy for this strategy."""
        if self.kind == "static":
            assert self.equity_allocation is not None
            return ConstantAllocationPolicy(equity_allocation=self.equity_allocation)
        assert (
            self.start_equity is not None
            and self.end_equity is not None
            and self.slope is not None
            and self.mode is not None
        )
        return GlidepathAllocationPolicy(
            start_equity=self.start_equity,
            end_equity=self.end_equity,
            slope=self.slope,
            mode=self.mode,
        )


def _static(equity_pct: int) -> Part20Strategy:
    alloc = Decimal(equity_pct) / Decimal("100")
    return Part20Strategy(
        id=f"static_{equity_pct:03d}",
        kind="static",
        equity_allocation=alloc,
    )


def _glidepath(
    start_pct: int,
    end_pct: int,
    slope: str,
    mode: str,
) -> Part20Strategy:
    return Part20Strategy(
        id=f"gp_{start_pct:03d}_{end_pct:03d}_{slope}_{mode}",
        kind="glidepath",
        start_equity=Decimal(start_pct) / Decimal("100"),
        end_equity=Decimal(end_pct) / Decimal("100"),
        slope=Decimal(slope),
        mode=mode,
    )


# Part 19 glidepaths (24): 6 start/end combos × 2 slopes × 2 modes.
_PART19_GLIDEPATHS: tuple[Part20Strategy, ...] = (
    _glidepath(60, 80, "0.002", "passive"),
    _glidepath(60, 80, "0.003", "passive"),
    _glidepath(60, 80, "0.002", "active"),
    _glidepath(60, 80, "0.003", "active"),
    _glidepath(40, 80, "0.003", "passive"),
    _glidepath(40, 80, "0.004", "passive"),
    _glidepath(40, 80, "0.003", "active"),
    _glidepath(40, 80, "0.004", "active"),
    _glidepath(20, 80, "0.004", "passive"),
    _glidepath(20, 80, "0.005", "passive"),
    _glidepath(20, 80, "0.004", "active"),
    _glidepath(20, 80, "0.005", "active"),
    _glidepath(80, 100, "0.002", "passive"),
    _glidepath(80, 100, "0.003", "passive"),
    _glidepath(80, 100, "0.002", "active"),
    _glidepath(80, 100, "0.003", "active"),
    _glidepath(60, 100, "0.003", "passive"),
    _glidepath(60, 100, "0.004", "passive"),
    _glidepath(60, 100, "0.003", "active"),
    _glidepath(60, 100, "0.004", "active"),
    _glidepath(40, 100, "0.004", "passive"),
    _glidepath(40, 100, "0.005", "passive"),
    _glidepath(40, 100, "0.004", "active"),
    _glidepath(40, 100, "0.005", "active"),
)

# Part 20 additions (8): passive-only Kitces/Pfau-inspired slopes.
_PART20_GLIDEPATHS: tuple[Part20Strategy, ...] = (
    _glidepath(30, 70, "0.00111", "passive"),
    _glidepath(30, 70, "0.002", "passive"),
    _glidepath(30, 70, "0.003", "passive"),
    _glidepath(30, 70, "0.004", "passive"),
    _glidepath(20, 60, "0.00111", "passive"),
    _glidepath(20, 60, "0.002", "passive"),
    _glidepath(20, 60, "0.003", "passive"),
    _glidepath(20, 60, "0.004", "passive"),
)

PART20_STATIC_COUNT = 21
PART20_GLIDEPATH_COUNT = 32
PART20_STRATEGY_COUNT = PART20_STATIC_COUNT + PART20_GLIDEPATH_COUNT


def part20_strategy_universe() -> tuple[Part20Strategy, ...]:
    """Return the documented 53-strategy Part 20 universe.

    21 static equity allocations (0%–100% in 5% steps) followed by
    32 glidepaths (24 inherited from Part 19 + 8 Part 20 additions).
    Order is stable: static ascending, then Part 19 glidepaths in
    documented order, then Part 20 additions.
    """
    statics = tuple(_static(pct) for pct in range(0, 105, 5))
    universe = statics + _PART19_GLIDEPATHS + _PART20_GLIDEPATHS
    if len(universe) != PART20_STRATEGY_COUNT:
        raise AssertionError(
            f"strategy universe size {len(universe)} != {PART20_STRATEGY_COUNT}"
        )
    ids = [s.id for s in universe]
    if len(set(ids)) != len(ids):
        raise AssertionError("strategy universe contains duplicate ids")
    return universe
