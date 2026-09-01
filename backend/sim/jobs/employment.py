"""
Hiring and housing allocation.

Both are matching problems solved greedily: rank the openings, rank the
candidates, pair them off. Greedy is the right call here because the pool
changes every day and an optimal assignment would be both slower and
indistinguishable to an observer.

Candidates are ranked by the skill the job actually needs, so a city with
plenty of engineers and no doctors visibly fails to staff its hospital.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..agents.models import Agent
from ..buildings.catalog import BuildingCategory
from ..buildings.models import Building
from ..memory.model import MemoryKind
from .professions import PROFESSIONS, Education, Profession

#: Minimum skill to be considered at all, so unqualified agents are not hired
#: into jobs they would be useless in.
MIN_SKILL = 20.0

#: How much commuting distance counts against a candidate, per tile.
DISTANCE_PENALTY = 0.15

#: Hires processed per day, so a large city fills posts over weeks rather than
#: instantly. Without it, a new factory is fully staffed the moment it opens.
MAX_HIRES_PER_DAY = 12

#: Housing moves processed per day.
MAX_MOVES_PER_DAY = 20


@dataclass(slots=True)
class Hire:
    agent_id: int
    building_id: int
    profession: Profession
    salary: int
    score: float


@dataclass(slots=True)
class Move:
    agent_id: int
    building_id: int


def _candidate_score(agent: Agent, profession: Profession, building: Building) -> float | None:
    """
    How suitable this agent is, or None if ineligible.

    Combines the relevant skill with a distance penalty so people tend to work
    near where they live, which is what produces recognisable commutes rather
    than agents criss-crossing the map.
    """
    spec = PROFESSIONS[profession]
    if agent.education < spec.education:
        return None

    skill = agent.skill_for(spec.key_skill)
    if skill < MIN_SKILL:
        return None

    score = skill
    # Ambition makes an agent more willing to take a demanding post.
    score += agent.personality.get("ambition", 0.5) * 10.0

    ax, ay = agent.tile
    bx, by = building.center
    distance = abs(ax - bx) + abs(ay - by)
    score -= distance * DISTANCE_PENALTY

    # Emotional state affects whether they pursue work at all.
    score *= agent.emotions.decision_bias()["seek_job"]
    return score


def run_hiring(
    tick: int,
    agents: dict[int, Agent],
    buildings: dict[int, Building],
    limit: int = MAX_HIRES_PER_DAY,
) -> list[Hire]:
    """
    Fills open posts from the pool of unemployed adults.

    Vacancies are processed highest-salary first: the city competes for the same
    people, and letting the best-paid roles pick first is both realistic and
    keeps critical public posts (doctors) from losing out to shop work.
    """
    seekers = [
        agent
        for agent in agents.values()
        if agent.alive and agent.can_work and not agent.employed
    ]
    if not seekers:
        return []

    openings: list[tuple[int, Building, Profession]] = []
    for building in buildings.values():
        if not building.is_open:
            continue
        for profession, count in building.vacancies().items():
            salary = PROFESSIONS[profession].base_salary
            openings.extend([(salary, building, profession)] * count)

    if not openings:
        return []

    openings.sort(key=lambda item: item[0], reverse=True)

    hires: list[Hire] = []
    taken: set[int] = set()

    for salary, building, profession in openings:
        if len(hires) >= limit:
            break

        best: tuple[float, Agent] | None = None
        for agent in seekers:
            if agent.id in taken:
                continue
            score = _candidate_score(agent, profession, building)
            if score is None:
                continue
            if best is None or score > best[0]:
                best = (score, agent)

        if best is None:
            continue

        score, agent = best
        if not building.hire(agent.id, profession):
            continue

        agent.profession = profession
        agent.workplace_id = building.id
        agent.salary = salary
        taken.add(agent.id)

        agent.emotions.adjust(happiness=8.0, confidence=6.0, stress=-5.0)
        agent.memory.record(
            tick,
            MemoryKind.WORK,
            f"{profession} sifatida ishga qabul qilindi",
            importance=0.7,
            building_id=building.id,
            salary=salary,
        )
        hires.append(Hire(agent.id, building.id, profession, salary, score))

    return hires


def hire_specialist(
    tick: int,
    agent: Agent,
    profession: Profession,
    buildings: dict[int, Building],
) -> Hire | None:
    """Places a prepared specialist into the first matching vacancy."""
    spec = PROFESSIONS[profession]
    salary = spec.base_salary
    for building in buildings.values():
        if not building.hire(agent.id, profession):
            continue
        agent.profession = profession
        agent.workplace_id = building.id
        agent.salary = salary
        agent.emotions.adjust(happiness=8.0, confidence=6.0, stress=-5.0)
        agent.memory.record(
            tick,
            MemoryKind.WORK,
            f"{profession} sifatida ishga qabul qilindi",
            importance=0.7,
            building_id=building.id,
            salary=salary,
        )
        return Hire(agent.id, building.id, profession, salary, 100.0)
    return None


def dismiss(tick: int, agent: Agent, buildings: dict[int, Building], reason: str) -> None:
    """Removes an agent from their post and records why."""
    building = buildings.get(agent.workplace_id) if agent.workplace_id else None
    if building is not None:
        building.dismiss(agent.id)

    agent.profession = None
    agent.workplace_id = None
    agent.salary = 0
    agent.emotions.adjust(happiness=-12.0, stress=14.0, confidence=-10.0)
    agent.memory.record(
        tick, MemoryKind.WORK, f"Ishdan ayrildi: {reason}", importance=0.8, reason=reason
    )


def assign_housing(
    tick: int,
    agents: dict[int, Agent],
    buildings: dict[int, Building],
    limit: int = MAX_MOVES_PER_DAY,
) -> list[Move]:
    """
    Moves homeless agents into free beds.

    Families are kept together by preferring a home a relative already lives in;
    otherwise the nearest free bed wins, which keeps neighbourhoods coherent.
    """
    homeless = [
        agent for agent in agents.values() if agent.alive and agent.home_id is None
    ]
    if not homeless:
        return []

    available = [
        building
        for building in buildings.values()
        if building.is_open
        and building.spec.category is BuildingCategory.RESIDENTIAL
        and building.free_beds > 0
    ]
    if not available:
        return []

    moves: list[Move] = []

    # Children and partners first, so families reunite before strangers are
    # placed into the beds they would have used.
    homeless.sort(key=lambda agent: (agent.is_adult, agent.id))

    for agent in homeless:
        if len(moves) >= limit:
            break

        home = _preferred_home(agent, agents, available)
        if home is None:
            continue
        if not home.add_resident(agent.id):
            continue

        agent.home_id = home.id
        # Newly housed agents start at the door of their new home.
        agent.position = (float(home.entrance[0]), float(home.entrance[1]))
        agent.emotions.adjust(happiness=10.0, stress=-8.0, fear=-5.0)
        agent.memory.record(
            tick, MemoryKind.LONG_TERM, "Yangi uyga ko'chib o'tdi", importance=0.7,
            building_id=home.id,
        )
        moves.append(Move(agent.id, home.id))

        if home.free_beds == 0:
            available.remove(home)

    return moves


def _preferred_home(
    agent: Agent, agents: dict[int, Agent], available: list[Building]
) -> Building | None:
    """A relative's home if there is room, otherwise the closest free bed."""
    relatives = [*agent.parent_ids, *agent.children_ids]
    if agent.partner_id is not None:
        relatives.append(agent.partner_id)

    for relative_id in relatives:
        relative = agents.get(relative_id)
        if relative is None or relative.home_id is None:
            continue
        for building in available:
            if building.id == relative.home_id and building.free_beds > 0:
                return building

    if not available:
        return None

    ax, ay = agent.tile
    return min(
        available,
        key=lambda building: abs(building.center[0] - ax) + abs(building.center[1] - ay),
    )


def enrol_children(
    tick: int, agents: dict[int, Agent], buildings: dict[int, Building]
) -> int:
    """
    Places school-age children in a school with a free seat.

    Seats are a shared resource, so this both fills the school and makes the
    education shortage the president reacts to a real constraint.
    """
    schools = [
        building
        for building in buildings.values()
        if building.is_open and building.spec.school_seats > 0
    ]
    if not schools:
        return 0

    # Seats already claimed by enrolled pupils.
    claimed: dict[int, int] = {}
    for agent in agents.values():
        if agent.school_id is not None:
            claimed[agent.school_id] = claimed.get(agent.school_id, 0) + 1

    enrolled = 0
    for agent in agents.values():
        if not agent.alive or agent.school_id is not None or not agent.is_school_age:
            continue

        ax, ay = agent.tile
        nearest = sorted(
            schools,
            key=lambda b: abs(b.center[0] - ax) + abs(b.center[1] - ay),
        )
        for school in nearest:
            if claimed.get(school.id, 0) >= school.school_seats:
                continue
            agent.school_id = school.id
            claimed[school.id] = claimed.get(school.id, 0) + 1
            agent.memory.record(
                tick, MemoryKind.LONG_TERM, "Maktabga qabul qilindi",
                importance=0.6, building_id=school.id,
            )
            enrolled += 1
            break

    return enrolled


def graduate(tick: int, agent: Agent) -> None:
    """
    A teenager finishing school gains the education their schooling allows.

    Called by the ageing step when an agent crosses into adulthood.
    """
    if agent.school_id is None:
        # No school was ever available; they enter adulthood unqualified.
        agent.education = max(agent.education, Education.SCHOOL)
    else:
        agent.education = max(agent.education, Education.VOCATIONAL)
        agent.school_id = None

    agent.memory.record(
        tick, MemoryKind.LONG_TERM, "O'qishni tamomladi", importance=0.75,
        education=int(agent.education),
    )
