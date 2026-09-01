"""
Construction.

Implements the pipeline from specification section 16:

    plan → check budget → check land → hire workers → build → complete → open

Cost is charged when the project is approved, not when it finishes, so the
treasury reflects commitments the city has already made. Progress depends on how
many builders the city employs: a city with no builders can approve projects and
watch them stall, which is a real constraint the president has to solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..agents.models import Agent
from ..economy.model import Economy
from ..jobs.professions import Profession
from ..world.tiles import District, Grid
from .catalog import CATALOG, BuildingType
from .models import Building, BuildingStatus

#: Days of progress one builder contributes per simulated day.
PROGRESS_PER_BUILDER = 0.25

#: Progress a project makes with no builders at all, representing contracted
#: work. Small enough that staffing the trades visibly matters.
BASE_PROGRESS_PER_DAY = 0.15

#: Cap so a huge workforce cannot finish a hospital overnight.
MAX_PROGRESS_PER_DAY = 3.0

#: How many projects may be under construction at once. Beyond this the city is
#: spreading its trades too thin to finish anything.
MAX_CONCURRENT_PROJECTS = 8


class RejectionReason(StrEnum):
    NO_BUDGET = "no_budget"
    NO_LAND = "no_land"
    TOO_MANY_PROJECTS = "too_many_projects"


@dataclass(slots=True)
class ConstructionResult:
    """Outcome of one approval attempt."""

    approved: bool
    building: Building | None = None
    reason: RejectionReason | None = None
    cost: float = 0.0

    def __bool__(self) -> bool:
        return self.approved


class ConstructionManager:
    """Owns building ids, plot selection and progress."""

    def __init__(self, first_id: int = 1) -> None:
        self._next_id = first_id

    @property
    def next_id(self) -> int:
        return self._next_id

    def sync_next_id(self, value: int) -> None:
        self._next_id = max(self._next_id, value)

    # -- approval ----------------------------------------------------------

    def request(
        self,
        building_type: BuildingType,
        *,
        grid: Grid,
        economy: Economy,
        buildings: dict[int, Building],
        near: tuple[int, int] | None = None,
        instant: bool = False,
        cost_multiplier: float = 1.0,
    ) -> ConstructionResult:
        """
        Runs the approval pipeline for a single building.

        `instant` skips construction time and is used only for the city
        bootstrap, where the founding buildings must exist before day one.

        `cost_multiplier` prices work the city is not ready for: building ahead
        of the development level means importing the expertise, so the player
        pays a premium rather than being refused outright.
        """
        spec = CATALOG[building_type]
        cost = round(spec.construction_cost * max(1.0, cost_multiplier))

        in_flight = sum(
            1 for b in buildings.values() if b.status is BuildingStatus.UNDER_CONSTRUCTION
        )
        if not instant and in_flight >= MAX_CONCURRENT_PROJECTS:
            return ConstructionResult(False, reason=RejectionReason.TOO_MANY_PROJECTS)

        if not economy.can_afford(cost):
            return ConstructionResult(False, reason=RejectionReason.NO_BUDGET)

        plot = self._find_plot(grid, spec.width, spec.height, spec.district, near)
        if plot is None:
            return ConstructionResult(False, reason=RejectionReason.NO_LAND)

        if not economy.spend(cost, "construction"):
            return ConstructionResult(False, reason=RejectionReason.NO_BUDGET)

        building = Building(
            id=self._reserve_id(),
            type=building_type,
            x=plot[0],
            y=plot[1],
            status=BuildingStatus.OPEN if instant else BuildingStatus.UNDER_CONSTRUCTION,
        )
        if instant:
            building.progress_days = float(spec.build_days)

        grid.occupy(plot[0], plot[1], spec.width, spec.height, building.id)
        buildings[building.id] = building

        return ConstructionResult(True, building=building, cost=float(cost))

    def _reserve_id(self) -> int:
        building_id = self._next_id
        self._next_id += 1
        return building_id

    @staticmethod
    def _find_plot(
        grid: Grid,
        width: int,
        height: int,
        preferred: District,
        near: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        """
        Land in the preferred district, falling back to anywhere buildable.

        The fallback matters: without it a city whose residential zone is full
        simply stops growing, even with open land one tile outside the zone.
        """
        if preferred is not District.UNZONED:
            plot = grid.find_free_plot(width, height, district=preferred, near=near)
            if plot is not None:
                return plot

        return grid.find_free_plot(width, height, near=near)

    # -- progress ----------------------------------------------------------

    def advance_day(
        self,
        tick: int,
        buildings: dict[int, Building],
        agents: dict[int, Agent],
    ) -> list[Building]:
        """
        Advances every project by one day. Returns the buildings that opened.

        The whole builder workforce contributes to every active project rather
        than being assigned to one each. That is a simplification, but it makes
        the relationship the player can observe — more builders, faster city —
        direct and immediate.
        """
        active = [
            building
            for building in buildings.values()
            if building.status is BuildingStatus.UNDER_CONSTRUCTION
        ]
        if not active:
            return []

        builders = sum(
            1
            for agent in agents.values()
            if agent.alive and agent.profession is Profession.BUILDER
        )
        per_project = min(
            MAX_PROGRESS_PER_DAY,
            BASE_PROGRESS_PER_DAY + builders * PROGRESS_PER_BUILDER / max(1, len(active)),
        )

        opened: list[Building] = []
        for building in active:
            building.progress_days += per_project
            if building.progress_days >= building.spec.build_days:
                building.status = BuildingStatus.OPEN
                building.opened_tick = tick
                opened.append(building)

        return opened

    # -- demolition --------------------------------------------------------

    @staticmethod
    def demolish(
        building: Building,
        *,
        grid: Grid,
        agents: dict[int, Agent],
    ) -> None:
        """
        Removes a building and detaches everyone attached to it.

        Residents and staff must be released explicitly, otherwise they keep a
        home or workplace id pointing at nothing and never seek a replacement.
        """
        for agent in agents.values():
            if agent.home_id == building.id:
                agent.home_id = None
            if agent.workplace_id == building.id:
                agent.workplace_id = None
                agent.profession = None
                agent.salary = 0
            if agent.school_id == building.id:
                agent.school_id = None

        grid.release(building.id)
        building.status = BuildingStatus.DEMOLISHED
        building.residents.clear()
        building.staff.clear()
