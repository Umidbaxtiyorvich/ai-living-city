"""
Relationships, marriage and children (specification sections 20 and 21).

Child creation is modelled abstractly, as the specification requires:
`FAMILY_PLANNING → WAITING → NEW_CHILD`. A couple decides to plan, waits a fixed
period, and a child is added to the household. There is no depiction of
anything beyond that transition.

Partnering is driven by proximity and accumulated affinity, which is why
relationships have to be built up by agents actually meeting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..agents.models import Agent, Gender, LifeStage
from ..clock import DAYS_PER_MONTH, MINUTES_PER_DAY
from ..codec import decode_dataclass, encode
from ..memory.model import MemoryKind
from ..rng import Rng

#: Affinity needed before a couple will marry.
MARRIAGE_AFFINITY = 65.0

#: Affinity gained per encounter, and the distance that counts as one.
ENCOUNTER_BONUS = 3.0
ENCOUNTER_DISTANCE = 2

#: Marriageable age range.
MIN_MARRIAGE_AGE = 20.0
MAX_MARRIAGE_AGE = 70.0

#: Simulated days a pregnancy takes.
GESTATION_DAYS = 9 * DAYS_PER_MONTH

#: Monthly chance a settled couple decides to plan a child.
PLANNING_CHANCE = 0.06

#: Children a family will plan for at most.
MAX_CHILDREN = 4

#: Household savings needed before planning a child.
PLANNING_SAVINGS = 3_000.0


class PlanningStage(StrEnum):
    NONE = "none"
    PLANNING = "family_planning"
    WAITING = "waiting"


@dataclass(slots=True)
class Family:
    id: int
    partner_ids: list[int] = field(default_factory=list)
    children_ids: list[int] = field(default_factory=list)
    home_id: int | None = None
    surname: str = ""
    formed_day: int = 0

    stage: PlanningStage = PlanningStage.NONE
    #: Day the current wait began.
    waiting_since_day: int | None = None

    @property
    def size(self) -> int:
        return len(self.partner_ids) + len(self.children_ids)

    @property
    def can_plan_more(self) -> bool:
        return len(self.children_ids) < MAX_CHILDREN

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "surname": self.surname,
            "partner_ids": list(self.partner_ids),
            "children_ids": list(self.children_ids),
            "home_id": self.home_id,
            "stage": self.stage,
            "formed_day": self.formed_day,
        }


class FamilyRegistry:
    """Owns families and the transitions between relationship states."""

    def __init__(self, first_id: int = 1) -> None:
        self.families: dict[int, Family] = {}
        self._next_id = first_id

    def _reserve_id(self) -> int:
        family_id = self._next_id
        self._next_id += 1
        return family_id

    def sync_next_id(self, value: int) -> None:
        self._next_id = max(self._next_id, value)

    # -- meeting -----------------------------------------------------------

    def register_encounters(self, agents: dict[int, Agent], tick: int) -> int:
        """
        Builds affinity between agents who are near each other.

        Only adults are considered and only a bounded number of pairs is
        checked, because a naive all-pairs scan is quadratic and would dominate
        the tick cost in a large city.
        """
        nearby = [
            agent
            for agent in agents.values()
            if agent.alive and agent.is_adult and agent.detail.value != "statistical"
        ]
        if len(nearby) < 2:
            return 0

        # Bucket by coarse grid cell so only plausible neighbours are compared.
        buckets: dict[tuple[int, int], list[Agent]] = {}
        for agent in nearby:
            key = (int(agent.position[0]) // 4, int(agent.position[1]) // 4)
            buckets.setdefault(key, []).append(agent)

        encounters = 0
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            for index, first in enumerate(bucket):
                for second in bucket[index + 1 :]:
                    dx = abs(first.position[0] - second.position[0])
                    dy = abs(first.position[1] - second.position[1])
                    if dx > ENCOUNTER_DISTANCE or dy > ENCOUNTER_DISTANCE:
                        continue

                    bonus = ENCOUNTER_BONUS * (
                        0.5 + first.personality.get("agreeableness", 0.5)
                    )
                    first.adjust_relationship(second.id, bonus)
                    second.adjust_relationship(
                        first.id,
                        ENCOUNTER_BONUS * (0.5 + second.personality.get("agreeableness", 0.5)),
                    )
                    first.needs.adjust(social=1.5)
                    second.needs.adjust(social=1.5)
                    encounters += 1

        return encounters

    # -- marriage ----------------------------------------------------------

    def try_marriages(
        self, agents: dict[int, Agent], tick: int, day: int, rng: Rng
    ) -> list[tuple[Agent, Agent, Family]]:
        """Marries mutually attached, eligible, unpartnered couples."""
        eligible = [
            agent
            for agent in agents.values()
            if self._marriageable(agent)
        ]
        weddings: list[tuple[Agent, Agent, Family]] = []
        married_now: set[int] = set()

        for agent in eligible:
            if agent.id in married_now or agent.partner_id is not None:
                continue

            best: tuple[float, Agent] | None = None
            for other_id, affinity in agent.relationships.items():
                if affinity < MARRIAGE_AFFINITY or other_id in married_now:
                    continue
                other = agents.get(other_id)
                if other is None or not self._marriageable(other):
                    continue
                # Mutual, and the pairing model is heterosexual couples with
                # children; same-gender friendships stay friendships.
                if other.gender is agent.gender:
                    continue
                if other.relationship_with(agent.id) < MARRIAGE_AFFINITY:
                    continue
                if best is None or affinity > best[0]:
                    best = (affinity, other)

            if best is None:
                continue

            partner = best[1]
            family = self._form_family(agent, partner, day, rng)
            married_now.update({agent.id, partner.id})
            weddings.append((agent, partner, family))

            for one, two in ((agent, partner), (partner, agent)):
                one.partner_id = two.id
                one.family_id = family.id
                one.emotions.adjust(love=30.0, happiness=20.0, loneliness=-30.0)
                one.memory.record(
                    tick, MemoryKind.FAMILY, f"{two.name} bilan turmush qurdi",
                    importance=0.95, partner_id=two.id,
                )

        return weddings

    @staticmethod
    def _marriageable(agent: Agent) -> bool:
        return (
            agent.alive
            and agent.partner_id is None
            and MIN_MARRIAGE_AGE <= agent.age_years <= MAX_MARRIAGE_AGE
            and agent.life_stage in (LifeStage.ADULT, LifeStage.SENIOR)
        )

    def _form_family(self, first: Agent, second: Agent, day: int, rng: Rng) -> Family:
        # The shared surname comes from one partner, chosen deterministically.
        surname = (first if rng.chance(0.5) else second).name.split()[-1]
        family = Family(
            id=self._reserve_id(),
            partner_ids=[first.id, second.id],
            surname=surname,
            formed_day=day,
            home_id=first.home_id or second.home_id,
        )
        self.families[family.id] = family
        return family

    # -- children ----------------------------------------------------------

    def advance_planning(
        self, agents: dict[int, Agent], day: int, rng: Rng
    ) -> list[Family]:
        """
        Moves families through the planning cycle. Returns those ready for a
        child, so the caller can create the agent.

        Requirements are deliberate: a home, savings and a mother of childbearing
        age. A city that cannot house its people therefore stops growing from
        within, which is a consequence the president has to fix.
        """
        ready: list[Family] = []

        for family in self.families.values():
            if not family.can_plan_more:
                continue

            partners = [agents.get(pid) for pid in family.partner_ids]
            if any(partner is None or not partner.alive for partner in partners):
                continue

            if family.stage is PlanningStage.WAITING:
                if family.waiting_since_day is None:
                    family.waiting_since_day = day
                elif day - family.waiting_since_day >= GESTATION_DAYS:
                    ready.append(family)
                continue

            if not self._may_plan(family, partners, day):
                continue

            if rng.chance(PLANNING_CHANCE):
                family.stage = PlanningStage.WAITING
                family.waiting_since_day = day

        return ready

    @staticmethod
    def _may_plan(family: Family, partners: list[Agent], day: int) -> bool:
        if family.home_id is None:
            return False

        mother = next((p for p in partners if p.gender is Gender.FEMALE), None)
        if mother is None or not (18.0 <= mother.age_years <= 42.0):
            return False

        household_savings = sum(partner.money for partner in partners)
        if household_savings < PLANNING_SAVINGS:
            return False

        # A settled couple only; newly-weds wait a while.
        return day - family.formed_day >= DAYS_PER_MONTH

    def register_child(self, family: Family, child: Agent, agents: dict[int, Agent], tick: int) -> None:
        """Attaches a newborn to its family and resets the planning cycle."""
        family.children_ids.append(child.id)
        family.stage = PlanningStage.NONE
        family.waiting_since_day = None

        child.family_id = family.id
        child.parent_ids = list(family.partner_ids)
        child.home_id = family.home_id

        for parent_id in family.partner_ids:
            parent = agents.get(parent_id)
            if parent is None:
                continue
            parent.children_ids.append(child.id)
            parent.emotions.adjust(happiness=25.0, love=20.0, excitement=15.0, stress=8.0)
            parent.memory.record(
                tick, MemoryKind.FAMILY, f"Farzandi tug'ildi: {child.name}",
                importance=1.0, child_id=child.id,
            )

    # -- dissolution -------------------------------------------------------

    def handle_death(self, agent: Agent, agents: dict[int, Agent], tick: int) -> None:
        """Detaches a dead agent, leaving the family record intact as history."""
        if agent.partner_id is not None:
            widow = agents.get(agent.partner_id)
            if widow is not None:
                widow.partner_id = None
                widow.emotions.adjust(sadness=45.0, loneliness=35.0, happiness=-30.0, love=-15.0)
                widow.memory.record(
                    tick, MemoryKind.FAMILY, f"{agent.name} vafot etdi",
                    importance=1.0, partner_id=agent.id,
                )

        for child_id in agent.children_ids:
            child = agents.get(child_id)
            if child is not None:
                child.emotions.adjust(sadness=40.0, happiness=-25.0)

        family = self.families.get(agent.family_id) if agent.family_id else None
        if family is not None and agent.id in family.partner_ids:
            family.partner_ids.remove(agent.id)
            family.stage = PlanningStage.NONE

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        # `encode` rather than `as_dict`: the latter is the client-facing view
        # and deliberately omits internal fields a reload needs.
        return {
            "next_id": self._next_id,
            "families": [encode(family) for family in self.families.values()],
        }

    @classmethod
    def restore(cls, data: dict) -> "FamilyRegistry":
        registry = cls(first_id=int(data.get("next_id", 1)))
        for item in data.get("families", []):
            family = decode_dataclass(Family, item)
            registry.families[family.id] = family
        return registry
