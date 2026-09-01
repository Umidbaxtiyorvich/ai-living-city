"""
The president and the shape of a government decision.

A decision is a record, not a function call: it names the concern that triggered
it, the action taken, what it cost, and — once the consequences arrive — whether
it worked. That trail is what lets the president learn from its own history
instead of rediscovering the same problem every month.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from ..agents.models import Gender
from ..buildings.catalog import BuildingType, label_for
from ..memory.model import Memory
from ..world.tiles import District


class Priority(IntEnum):
    """Specification section 25."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_severity(cls, severity: float) -> "Priority":
        if severity >= 0.75:
            return cls.CRITICAL
        if severity >= 0.5:
            return cls.HIGH
        if severity >= 0.25:
            return cls.MEDIUM
        return cls.LOW


class ConcernCode(StrEnum):
    """Every problem the analysis can detect."""

    HOUSING_SHORTAGE = "housing_shortage"
    UNEMPLOYMENT = "unemployment"
    WORKER_SHORTAGE = "worker_shortage"
    HEALTHCARE_SHORTAGE = "healthcare_shortage"
    EDUCATION_SHORTAGE = "education_shortage"
    FOOD_SHORTAGE = "food_shortage"
    POWER_SHORTAGE = "power_shortage"
    RETAIL_SHORTAGE = "retail_shortage"
    SECURITY_SHORTAGE = "security_shortage"
    BUDGET_DEFICIT = "budget_deficit"
    EXCESSIVE_TAXATION = "excessive_taxation"
    LOW_HAPPINESS = "low_happiness"
    NO_BUILDABLE_LAND = "no_buildable_land"
    TRAFFIC_CONGESTION = "traffic_congestion"
    PARKING_SHORTAGE = "parking_shortage"
    TRANSIT_SHORTAGE = "transit_shortage"
    PLAYER_DECREE = "player_decree"


class ActionKind(StrEnum):
    """What the president can actually do about a concern."""

    BUILD = "build"
    ZONE_DISTRICT = "zone_district"
    EXPAND_MAP = "expand_map"
    RECRUIT_WORKERS = "recruit_workers"
    SET_TAX = "set_tax"
    DECLARE_EMERGENCY = "declare_emergency"
    WAIT = "wait"


TAX_LABELS: dict[str, str] = {
    "income_tax": "daromad solig'i",
    "business_tax": "biznes solig'i",
    "property_tax": "mulk solig'i",
}


@dataclass(slots=True)
class Action:
    """A concrete instruction. Only the fields relevant to `kind` are set."""

    kind: ActionKind
    building_type: BuildingType | None = None
    quantity: int = 1
    district: District | None = None
    #: For SET_TAX: which rate, and its new value.
    tax_name: str | None = None
    tax_value: float | None = None
    #: For RECRUIT_WORKERS: what the city is hiring for.
    professions: list[str] = field(default_factory=list)
    #: For EXPAND_MAP.
    new_width: int = 0
    new_height: int = 0

    def describe(self) -> str:
        """One line in Uzbek. This text is shown to the player, not logged."""
        if self.kind is ActionKind.BUILD and self.building_type:
            return f"{self.quantity} × {label_for(self.building_type)}"
        if self.kind is ActionKind.SET_TAX:
            return f"{TAX_LABELS.get(self.tax_name or '', self.tax_name)} → {self.tax_value:.1%}"
        if self.kind is ActionKind.ZONE_DISTRICT and self.district:
            return f"yangi hudud: {self.district}"
        if self.kind is ActionKind.EXPAND_MAP:
            return f"xarita kengaytiriladi: {self.new_width}×{self.new_height}"
        if self.kind is ActionKind.RECRUIT_WORKERS:
            wanted = ", ".join(self.professions[:3]) or "umumiy"
            return f"{self.quantity} ishchi chaqiriladi ({wanted})"
        return self.kind.value


@dataclass(slots=True)
class Concern:
    """A detected problem, scored so it can be ranked against others."""

    code: ConcernCode
    #: 0..1. How badly the city is failing on this axis.
    severity: float
    #: Human-readable, shown on the dashboard.
    description: str
    action: Action
    #: The numbers that produced the score, for the debug panel.
    evidence: dict = field(default_factory=dict)

    @property
    def priority(self) -> Priority:
        return Priority.from_severity(self.severity)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": round(self.severity, 3),
            "priority": int(self.priority),
            "priority_name": self.priority.name,
            "description": self.description,
            "action": self.action.describe(),
            "evidence": self.evidence,
        }


class DecisionStatus(StrEnum):
    APPROVED = "approved"
    #: Recognised the problem but could not act — usually no money.
    DEFERRED = "deferred"
    REJECTED = "rejected"


@dataclass(slots=True)
class Decision:
    """A decision and, later, its measured outcome."""

    id: int
    tick: int
    concern: Concern
    status: DecisionStatus
    rationale: str
    cost: float = 0.0
    #: Ids of anything the decision produced, for follow-up.
    created_building_ids: list[int] = field(default_factory=list)
    #: Severity of the same concern when the outcome was reviewed.
    severity_at_review: float | None = None
    reviewed_tick: int | None = None

    @property
    def worked(self) -> bool | None:
        """
        Whether the concern eased after the decision.

        `None` until reviewed. Comparing severity before and after is crude but
        honest: it measures the thing the decision was meant to fix.
        """
        if self.severity_at_review is None:
            return None
        return self.severity_at_review < self.concern.severity

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tick": self.tick,
            "status": self.status,
            "rationale": self.rationale,
            "cost": round(self.cost, 2),
            "concern": self.concern.as_dict(),
            "created_building_ids": list(self.created_building_ids),
            "worked": self.worked,
            "reviewed_tick": self.reviewed_tick,
        }


@dataclass(slots=True)
class President:
    """
    The single head of government.

    Shares the agent avatar system (specification section 23) but is not an
    `Agent`: it has no job search, no household needs driving its schedule, and
    its memory categories are different.
    """

    id: int
    name: str
    gender: Gender
    age_days: int

    avatar_seed: str = "president-1"
    appearance: dict = field(default_factory=dict)

    #: 0..100 competence traits feeding decision quality.
    intelligence: float = 70.0
    leadership: float = 70.0

    approval_rating: float = 60.0
    health: float = 95.0
    energy: float = 90.0
    #: Personal money, distinct from the city budget.
    money: float = 50_000.0

    palace_building_id: int | None = None
    office_building_id: int | None = None
    position: tuple[float, float] = (0.0, 0.0)
    path: list[tuple[int, int]] = field(default_factory=list)
    #: What the palace schedule says it should be doing.
    activity: str = "sleeping"

    memory: Memory = field(default_factory=Memory)
    decisions: list[Decision] = field(default_factory=list)
    #: Term bounds, so an election system can be added without reshaping this.
    term_start_day: int = 0
    term_length_days: int = 4 * 360

    #: Set while a crisis overrides the daily routine.
    emergency: str | None = None

    @property
    def in_emergency(self) -> bool:
        return self.emergency is not None

    def term_remaining_days(self, current_day: int) -> int:
        return max(0, self.term_start_day + self.term_length_days - current_day)

    def recent_decisions(self, count: int = 10) -> list[Decision]:
        return self.decisions[-count:]

    def decisions_for(self, code: ConcernCode) -> list[Decision]:
        return [d for d in self.decisions if d.concern.code is code]

    def public_state(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "age": round(self.age_days / 360, 1),
            "activity": self.activity,
            "x": round(self.position[0], 2),
            "y": round(self.position[1], 2),
            "approval_rating": round(self.approval_rating, 1),
            "health": round(self.health, 1),
            "energy": round(self.energy, 1),
            "emergency": self.emergency,
            "avatar_seed": self.avatar_seed,
            "appearance": self.appearance,
        }
