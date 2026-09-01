"""
Building instances.

A `Building` is one physical structure on the grid. It tracks its own
construction progress, who lives in it and who works in it; the catalogue holds
the immutable facts about its type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..jobs.professions import Profession
from .catalog import BuildingSpec, BuildingType, spec_for


class BuildingStatus(StrEnum):
    """Specification section 16."""

    PLANNED = "planned"
    UNDER_CONSTRUCTION = "under_construction"
    OPEN = "open"
    #: Kept as a state rather than deleting the record, so the event log and
    #: agent memories can still refer to a building that no longer stands.
    DEMOLISHED = "demolished"


@dataclass(slots=True)
class Building:
    id: int
    type: BuildingType
    x: int
    y: int
    status: BuildingStatus = BuildingStatus.PLANNED
    #: Simulated days of work completed.
    progress_days: float = 0.0
    #: Agent ids living here.
    residents: list[int] = field(default_factory=list)
    #: Agent ids employed here, by profession.
    staff: dict[Profession, list[int]] = field(default_factory=dict)
    #: Tick the building opened, for the event log.
    opened_tick: int | None = None

    @property
    def spec(self) -> BuildingSpec:
        return spec_for(self.type)

    # -- geometry ----------------------------------------------------------

    @property
    def width(self) -> int:
        return self.spec.width

    @property
    def height(self) -> int:
        return self.spec.height

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def entrance(self) -> tuple[int, int]:
        """
        Where agents walk to. The tile just below the footprint, because the
        generator lays roads along the southern edge of every plot.
        """
        return self.x + self.width // 2, self.y + self.height

    # -- construction ------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.status is BuildingStatus.OPEN

    @property
    def construction_fraction(self) -> float:
        if self.status is BuildingStatus.OPEN:
            return 1.0
        return min(1.0, self.progress_days / self.spec.build_days)

    # -- housing -----------------------------------------------------------

    @property
    def housing_capacity(self) -> int:
        return self.spec.residents

    @property
    def free_beds(self) -> int:
        return max(0, self.spec.residents - len(self.residents))

    def add_resident(self, agent_id: int) -> bool:
        if self.free_beds <= 0 or agent_id in self.residents:
            return False
        self.residents.append(agent_id)
        return True

    def remove_resident(self, agent_id: int) -> None:
        if agent_id in self.residents:
            self.residents.remove(agent_id)

    # -- employment --------------------------------------------------------

    def capacity_for(self, profession: Profession) -> int:
        return self.spec.jobs.get(profession, 0)

    def filled_for(self, profession: Profession) -> int:
        return len(self.staff.get(profession, ()))

    def vacancies_for(self, profession: Profession) -> int:
        return max(0, self.capacity_for(profession) - self.filled_for(profession))

    def vacancies(self) -> dict[Profession, int]:
        """Only professions with at least one opening."""
        return {
            profession: self.capacity_for(profession) - self.filled_for(profession)
            for profession in self.spec.jobs
            if self.vacancies_for(profession) > 0
        }

    def hire(self, agent_id: int, profession: Profession) -> bool:
        if not self.is_open or self.vacancies_for(profession) <= 0:
            return False
        self.staff.setdefault(profession, []).append(agent_id)
        return True

    def dismiss(self, agent_id: int) -> None:
        for holders in self.staff.values():
            if agent_id in holders:
                holders.remove(agent_id)
                return

    @property
    def total_staff(self) -> int:
        return sum(len(holders) for holders in self.staff.values())

    @property
    def total_job_slots(self) -> int:
        return sum(self.spec.jobs.values())

    # -- output ------------------------------------------------------------

    @property
    def staffing_ratio(self) -> float:
        """
        How fully staffed the building is. Output scales with this, which is what
        makes a hospital with no doctors genuinely useless rather than
        cosmetically understaffed.
        """
        slots = self.total_job_slots
        if slots == 0:
            return 1.0
        return min(1.0, self.total_staff / slots)

    def effective(self, amount: int) -> int:
        """Scales a capacity figure by how well the building is staffed."""
        if not self.is_open:
            return 0
        return int(amount * self.staffing_ratio)

    @property
    def hospital_beds(self) -> int:
        return self.effective(self.spec.hospital_beds)

    @property
    def school_seats(self) -> int:
        return self.effective(self.spec.school_seats)

    @property
    def food_output(self) -> int:
        return self.effective(self.spec.food_output)

    @property
    def power_output(self) -> int:
        return self.effective(self.spec.power_output)

    @property
    def retail_capacity(self) -> int:
        return self.effective(self.spec.retail_capacity)
