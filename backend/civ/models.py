"""People, the buildings they raise, and the settlements those buildings form."""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import BLUEPRINT_BY_KIND, Blueprint, Storage

#: Simulated minutes per tick. Short enough that walking looks continuous.
MINUTES_PER_TICK = 10
TICKS_PER_DAY = 24 * 60 // MINUTES_PER_TICK
#: A compressed year, so generations turn over while someone is watching.
DAYS_PER_YEAR = 12

ADULT_AGE = 16
ELDER_AGE = 55

#: Tiles walked per tick.
WALK_SPEED = 0.55


@dataclass
class Goal:
    kind: str
    text: str
    progress: float = 0.0
    done_day: int | None = None


@dataclass
class Person:
    id: int
    name: str
    surname: str
    gender: str
    age_days: float
    x: float
    y: float

    alive: bool = True
    died_day: int | None = None
    parent_ids: list[int] = field(default_factory=list)
    children_ids: list[int] = field(default_factory=list)
    partner_id: int | None = None
    home_id: int | None = None
    settlement_id: int | None = None

    #: What the person is doing and where.
    task: str = "idle"
    task_ticks: int = 0
    target: tuple[int, int] | None = None
    target_building: int | None = None
    path: list[tuple[int, int]] = field(default_factory=list)
    #: What is in their hands: resource name and amount.
    carry_kind: str = ""
    carry: float = 0.0

    # 0..100, high is good.
    hunger: float = 80.0
    energy: float = 85.0
    social: float = 60.0
    health: float = 95.0

    skills: dict[str, float] = field(default_factory=dict)
    personality: dict[str, float] = field(default_factory=dict)
    #: Learned value of each kind of work — the person's taste, earned by doing.
    likes: dict[str, float] = field(default_factory=dict)
    relationships: dict[int, float] = field(default_factory=dict)

    # The mind.
    awareness: float = 10.0
    wisdom: float = 0.0
    thought: str = ""
    goals: list[Goal] = field(default_factory=list)
    memories: list[str] = field(default_factory=list)
    #: Look, picked once at birth and inherited in part.
    skin: str = "#c68c5a"
    hair: str = "#2b1d14"
    clothes: str = "#3c6e9e"
    height: float = 1.0
    #: Days since a child was last born to this woman.
    last_birth_day: int = -9999
    discoveries: int = 0
    buildings_built: int = 0

    # -- derived -----------------------------------------------------------

    @property
    def age_years(self) -> float:
        return self.age_days / DAYS_PER_YEAR

    @property
    def adult(self) -> bool:
        return self.age_years >= ADULT_AGE

    @property
    def stage(self) -> str:
        years = self.age_years
        if years < 3:
            return "baby"
        if years < 12:
            return "child"
        if years < ADULT_AGE:
            return "teenager"
        if years < ELDER_AGE:
            return "adult"
        return "elder"

    @property
    def happiness(self) -> float:
        base = (self.hunger + self.energy + self.social + self.health) / 4.0
        if self.home_id is not None:
            base += 6
        if self.partner_id is not None:
            base += 5
        return max(0.0, min(100.0, base))

    def trait(self, name: str) -> float:
        return self.personality.get(name, 0.5)

    def skill(self, name: str) -> float:
        return self.skills.get(name, 5.0)

    def improve(self, name: str, hours: float) -> None:
        current = self.skills.get(name, 5.0)
        rate = 0.6 * (0.6 + self.trait("conscientiousness"))
        self.skills[name] = min(100.0, current + rate * hours * (1.0 - current / 105.0))

    def remember(self, text: str) -> None:
        self.memories.append(text)
        if len(self.memories) > 12:
            del self.memories[0]

    def bond(self, other_id: int, delta: float) -> float:
        value = max(-100.0, min(100.0, self.relationships.get(other_id, 0.0) + delta))
        self.relationships[other_id] = value
        return value

    # -- payloads ----------------------------------------------------------

    def compact(self) -> list:
        """One row streamed every frame: [id, x, y, task, stage, gender, carry]."""
        return [
            self.id,
            round(self.x, 2),
            round(self.y, 2),
            self.task,
            self.stage,
            self.gender[0],
            self.carry_kind if self.carry > 0 else "",
        ]

    def looks(self) -> dict:
        return {
            "id": self.id,
            "name": f"{self.name} {self.surname}",
            "skin": self.skin,
            "hair": self.hair,
            "clothes": self.clothes,
            "height": round(self.height, 2),
        }

    def detail(self) -> dict:
        return {
            **self.looks(),
            "gender": self.gender,
            "age": round(self.age_years, 1),
            "stage": self.stage,
            "task": self.task,
            "thought": self.thought,
            "awareness": round(self.awareness, 1),
            "wisdom": round(self.wisdom, 1),
            "needs": {
                "hunger": round(self.hunger),
                "energy": round(self.energy),
                "social": round(self.social),
                "health": round(self.health),
            },
            "happiness": round(self.happiness),
            "skills": {k: round(v) for k, v in sorted(self.skills.items(), key=lambda kv: -kv[1])[:6]},
            "likes": {k: round(v, 2) for k, v in sorted(self.likes.items(), key=lambda kv: -kv[1])[:4]},
            "goals": [
                {"kind": goal.kind, "text": goal.text, "progress": round(goal.progress, 2)}
                for goal in self.goals if goal.done_day is None
            ],
            "memories": self.memories[-6:],
            "partner_id": self.partner_id,
            "children": len(self.children_ids),
            "home_id": self.home_id,
            "settlement_id": self.settlement_id,
            "discoveries": self.discoveries,
            "buildings_built": self.buildings_built,
        }


@dataclass
class Building:
    id: int
    kind: str
    x: int
    y: int
    settlement_id: int
    owner_id: int | None = None
    #: Resources still to be delivered before work can finish.
    need_wood: float = 0.0
    need_stone: float = 0.0
    work_done: float = 0.0
    complete: bool = False
    residents: list[int] = field(default_factory=list)
    built_day: int | None = None
    wall: str = "#d9c7a3"
    roof: str = "#8a3b2e"
    #: Small per-building variation the renderer uses (rotation, porch, etc.).
    style: int = 0
    #: Crop growth for fields, 0..1.
    growth: float = 0.0
    demolished: bool = False

    @property
    def blueprint(self) -> Blueprint:
        return BLUEPRINT_BY_KIND[self.kind]

    @property
    def progress(self) -> float:
        if self.complete:
            return 1.0
        return min(0.99, self.work_done / max(1.0, self.blueprint.work))

    @property
    def supplied(self) -> bool:
        return self.need_wood <= 0.01 and self.need_stone <= 0.01

    @property
    def center(self) -> tuple[float, float]:
        bp = self.blueprint
        return self.x + (bp.width - 1) / 2, self.y + (bp.height - 1) / 2

    @property
    def door(self) -> tuple[int, int]:
        bp = self.blueprint
        return self.x + bp.width // 2, self.y + bp.height

    def payload(self) -> dict:
        bp = self.blueprint
        return {
            "id": self.id,
            "kind": self.kind,
            "name": bp.name,
            "x": self.x,
            "y": self.y,
            "w": bp.width,
            "h": bp.height,
            "levels": bp.levels,
            "category": bp.category,
            "progress": round(self.progress, 3),
            "complete": self.complete,
            "wall": self.wall,
            "roof": self.roof,
            "style": self.style,
            "growth": round(self.growth, 2),
            "residents": len(self.residents),
            "settlement": self.settlement_id,
        }


@dataclass
class Settlement:
    id: int
    name: str
    x: int
    y: int
    founded_day: int
    storage: Storage = field(default_factory=Storage)
    leader_id: int | None = None
    #: Ids of people who founded it, for the chronicle.
    founders: list[int] = field(default_factory=list)
    population: int = 0
    rank: str = "Qarorgoh"
    abandoned: bool = False

    def payload(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "founded_day": self.founded_day,
            "population": self.population,
            "rank": self.rank,
            "storage": self.storage.as_dict(),
            "leader_id": self.leader_id,
        }
