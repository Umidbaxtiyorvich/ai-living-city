"""
The agent — one citizen of the city.

Physical needs live on a 0..100 scale where 100 is fully satisfied, so every
need reads the same way: low is bad. Behaviour is a small state machine driven
by needs, the daily schedule and emotional bias; it lives in `behavior.py` so
this module stays a data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..clock import DAYS_PER_YEAR
from ..emotions.model import Emotions
from ..jobs.professions import Education, Profession
from ..memory.model import Memory

Point = tuple[int, int]


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


class LifeStage(StrEnum):
    """Specification section 21."""

    BABY = "baby"
    TODDLER = "toddler"
    CHILD = "child"
    TEENAGER = "teenager"
    ADULT = "adult"
    SENIOR = "senior"


#: Upper age bound in years for each stage, in order.
STAGE_BOUNDS: tuple[tuple[LifeStage, int], ...] = (
    (LifeStage.BABY, 2),
    (LifeStage.TODDLER, 5),
    (LifeStage.CHILD, 12),
    (LifeStage.TEENAGER, 18),
    (LifeStage.ADULT, 65),
    (LifeStage.SENIOR, 200),
)


def stage_for_age(age_years: float) -> LifeStage:
    for stage, upper in STAGE_BOUNDS:
        if age_years < upper:
            return stage
    return LifeStage.SENIOR


class Activity(StrEnum):
    """What the agent is doing right now."""

    IDLE = "idle"
    SLEEPING = "sleeping"
    COMMUTING = "commuting"
    WORKING = "working"
    AT_SCHOOL = "at_school"
    SHOPPING = "shopping"
    EATING = "eating"
    LEISURE = "leisure"
    SOCIALISING = "socialising"
    AT_HOSPITAL = "at_hospital"
    SEEKING_JOB = "seeking_job"
    GOING_HOME = "going_home"


class DetailLevel(StrEnum):
    """Simulation fidelity, per specification section 41."""

    FULL = "full"
    REDUCED = "reduced"
    STATISTICAL = "statistical"


#: Need drain per simulated hour while awake.
NEED_DRAIN_PER_HOUR: dict[str, float] = {
    "energy": 4.2,
    "hunger": 5.0,
    "hygiene": 3.0,
    "social": 2.4,
    "fun": 2.8,
}

#: Below this, a need becomes urgent and overrides the daily schedule.
URGENT_THRESHOLD = 25.0


@dataclass(slots=True)
class Needs:
    energy: float = 80.0
    hunger: float = 80.0
    hygiene: float = 80.0
    social: float = 70.0
    fun: float = 70.0
    health: float = 95.0

    def as_dict(self) -> dict[str, float]:
        return {
            "energy": round(self.energy, 1),
            "hunger": round(self.hunger, 1),
            "hygiene": round(self.hygiene, 1),
            "social": round(self.social, 1),
            "fun": round(self.fun, 1),
            "health": round(self.health, 1),
        }

    def adjust(self, **deltas: float) -> None:
        for name, delta in deltas.items():
            current = getattr(self, name)
            setattr(self, name, max(0.0, min(100.0, current + delta)))

    def drain(self, hours: float) -> None:
        for name, rate in NEED_DRAIN_PER_HOUR.items():
            setattr(self, name, max(0.0, getattr(self, name) - rate * hours))

    @property
    def most_urgent(self) -> tuple[str, float] | None:
        """The lowest need, if any has fallen into urgent territory."""
        candidates = [
            (name, getattr(self, name))
            for name in ("energy", "hunger", "hygiene", "health", "social", "fun")
        ]
        name, value = min(candidates, key=lambda item: item[1])
        return (name, value) if value < URGENT_THRESHOLD else None

    @property
    def satisfaction(self) -> float:
        """Mean of the five drivable needs; health is tracked separately."""
        return (self.energy + self.hunger + self.hygiene + self.social + self.fun) / 5.0


@dataclass(slots=True)
class Agent:
    id: int
    name: str
    gender: Gender
    #: Age in simulated days. Days rather than years so children visibly grow.
    age_days: int

    #: Deterministic seed for the 3D avatar; never regenerated on reload.
    avatar_seed: str = ""
    #: Appearance overrides resolved by the frontend avatar generator.
    appearance: dict = field(default_factory=dict)

    education: Education = Education.NONE
    #: Aptitude 0..100 per skill name, used when ranking job candidates.
    skills: dict[str, float] = field(default_factory=dict)
    #: Stable temperament 0..1, influencing emotional baselines and choices.
    personality: dict[str, float] = field(default_factory=dict)

    profession: Profession | None = None
    workplace_id: int | None = None
    salary: int = 0
    home_id: int | None = None
    school_id: int | None = None

    money: float = 0.0
    needs: Needs = field(default_factory=Needs)
    emotions: Emotions = field(default_factory=Emotions)
    memory: Memory = field(default_factory=Memory)

    #: Continuous position, so movement is smooth between tile centres.
    position: tuple[float, float] = (0.0, 0.0)
    #: Remaining tiles of the current route.
    path: list[Point] = field(default_factory=list)
    destination_building_id: int | None = None

    activity: Activity = Activity.IDLE
    #: The goal behind the current activity, re-decided on the physiology beat
    #: rather than every tick. Commuting for ten minutes is one intention, not
    #: six hundred identical decisions.
    intent: Activity = Activity.IDLE
    #: Simulated minutes accumulated since needs and emotions last advanced.
    pending_minutes: float = 0.0
    detail: DetailLevel = DetailLevel.STATISTICAL

    family_id: int | None = None
    partner_id: int | None = None
    children_ids: list[int] = field(default_factory=list)
    parent_ids: list[int] = field(default_factory=list)
    #: Agent id → affinity in -100..100.
    relationships: dict[int, float] = field(default_factory=dict)

    #: Lasting order from the player (activity name). Survives while the player is offline.
    player_order: str | None = None
    player_order_note: str = ""
    #: Cabinet desk this agent staffs (electricity, accounting, media, ...).
    desk: str = ""

    alive: bool = True
    #: Tick of death, kept so the event log and family memories stay coherent.
    died_tick: int | None = None

    # -- age ---------------------------------------------------------------

    @property
    def age_years(self) -> float:
        return self.age_days / DAYS_PER_YEAR

    @property
    def life_stage(self) -> LifeStage:
        return stage_for_age(self.age_years)

    @property
    def is_adult(self) -> bool:
        return self.life_stage in (LifeStage.ADULT, LifeStage.SENIOR)

    @property
    def is_school_age(self) -> bool:
        return self.life_stage in (LifeStage.TODDLER, LifeStage.CHILD, LifeStage.TEENAGER)

    @property
    def can_work(self) -> bool:
        return self.life_stage is LifeStage.ADULT and self.alive

    # -- employment --------------------------------------------------------

    @property
    def employed(self) -> bool:
        return self.workplace_id is not None and self.profession is not None

    @property
    def unemployed(self) -> bool:
        return self.can_work and not self.employed

    def skill_for(self, skill: str) -> float:
        return self.skills.get(skill, 0.0)

    # -- state -------------------------------------------------------------

    @property
    def tile(self) -> Point:
        return int(round(self.position[0])), int(round(self.position[1]))

    @property
    def happiness(self) -> float:
        """
        Blend of how well needs are met and how the agent feels.

        Both matter: an agent with a full fridge and no friends is not happy,
        and neither is a beloved agent who is starving.
        """
        return round(self.needs.satisfaction * 0.45 + self.emotions.wellbeing * 0.55, 2)

    def relationship_with(self, other_id: int) -> float:
        return self.relationships.get(other_id, 0.0)

    def adjust_relationship(self, other_id: int, delta: float) -> float:
        value = max(-100.0, min(100.0, self.relationship_with(other_id) + delta))
        self.relationships[other_id] = value
        return value

    # -- serialisation -----------------------------------------------------

    def public_state(self) -> dict:
        """Compact form streamed to the client every tick."""
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "age": round(self.age_years, 1),
            "stage": self.life_stage,
            "activity": self.activity,
            "x": round(self.position[0], 2),
            "y": round(self.position[1], 2),
            "profession": self.profession,
            "happiness": self.happiness,
            "detail": self.detail,
            "avatar_seed": self.avatar_seed,
            "appearance": self.appearance,
            "player_order": self.player_order,
            "player_order_note": self.player_order_note,
            "desk": self.desk or None,
        }

    def detail_state(self) -> dict:
        """Everything the inspector panel shows for a selected agent."""
        return {
            **self.public_state(),
            "education": int(self.education),
            "skills": {name: round(value, 1) for name, value in self.skills.items()},
            "personality": {name: round(value, 2) for name, value in self.personality.items()},
            "needs": self.needs.as_dict(),
            "emotions": self.emotions.as_dict(),
            "money": round(self.money, 2),
            "salary": self.salary,
            "home_id": self.home_id,
            "workplace_id": self.workplace_id,
            "school_id": self.school_id,
            "family_id": self.family_id,
            "partner_id": self.partner_id,
            "children_ids": list(self.children_ids),
            "relationships": {str(k): round(v, 1) for k, v in self.relationships.items()},
            "recent_memories": [entry.as_dict() for entry in self.memory.recent_all(5)],
        }
