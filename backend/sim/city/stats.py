"""
City analysis.

Turns the raw world into the indicator set the president reasons over
(specification sections 5, 7 and 33). This module deliberately takes plain
collections rather than the world state object, so it can be tested with a
handful of hand-built agents and stays free of import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..agents.models import Agent, LifeStage
from ..buildings.catalog import BuildingCategory
from ..buildings.models import Building
from ..economy.model import Economy
from ..jobs.professions import PROFESSIONS, Profession
from ..world.tiles import District, Grid

#: Food units one citizen consumes per month.
FOOD_PER_CITIZEN = 1.0

#: Power units one citizen consumes per month.
POWER_PER_CITIZEN = 2.0

#: Hospital beds considered adequate per 1000 citizens.
BEDS_PER_1000 = 30.0

#: Retail throughput considered adequate per citizen.
RETAIL_PER_CITIZEN = 0.8

#: Police officers considered adequate per 1000 citizens.
POLICE_PER_1000 = 4.0


@dataclass(slots=True)
class CityStats:
    """One snapshot of every indicator the government tracks."""

    # Population
    population: int = 0
    adults: int = 0
    children: int = 0
    seniors: int = 0
    school_age: int = 0

    # Employment
    employed: int = 0
    unemployed: int = 0
    unemployment_rate: float = 0.0
    open_vacancies: int = 0
    vacancies_by_profession: dict[Profession, int] = field(default_factory=dict)

    # Housing
    housing_capacity: int = 0
    housed: int = 0
    homeless: int = 0
    housing_shortage: int = 0

    # Services
    hospital_beds: int = 0
    beds_needed: int = 0
    school_seats: int = 0
    seats_needed: int = 0
    retail_capacity: int = 0
    retail_needed: int = 0
    police_officers: int = 0
    police_needed: int = 0

    # Resources
    food_output: int = 0
    food_needed: int = 0
    power_output: int = 0
    power_needed: int = 0

    # Wellbeing
    happiness: float = 0.0
    average_health: float = 0.0

    # Economy
    budget: float = 0.0
    gdp: float = 0.0
    monthly_net: float = 0.0
    public_wage_bill: float = 0.0
    private_wage_bill: float = 0.0
    total_upkeep: float = 0.0

    # World
    buildings_open: int = 0
    buildings_under_construction: int = 0
    free_land: int = 0
    free_residential_land: int = 0

    # -- derived ratios ----------------------------------------------------

    @property
    def employment_rate(self) -> float:
        workforce = self.employed + self.unemployed
        return self.employed / workforce if workforce else 0.0

    @property
    def housing_pressure(self) -> float:
        """0 when everyone is housed, approaching 1 when nobody is."""
        return self.homeless / self.population if self.population else 0.0

    def coverage(self, supplied: int, needed: int) -> float:
        """Fraction of a need that is met; 1.0 when nothing is needed."""
        if needed <= 0:
            return 1.0
        return min(1.0, supplied / needed)

    @property
    def healthcare_coverage(self) -> float:
        return self.coverage(self.hospital_beds, self.beds_needed)

    @property
    def education_coverage(self) -> float:
        return self.coverage(self.school_seats, self.seats_needed)

    @property
    def retail_coverage(self) -> float:
        return self.coverage(self.retail_capacity, self.retail_needed)

    @property
    def food_coverage(self) -> float:
        return self.coverage(self.food_output, self.food_needed)

    @property
    def power_coverage(self) -> float:
        return self.coverage(self.power_output, self.power_needed)

    @property
    def security_coverage(self) -> float:
        return self.coverage(self.police_officers, self.police_needed)

    def as_dict(self) -> dict:
        return {
            "population": self.population,
            "adults": self.adults,
            "children": self.children,
            "seniors": self.seniors,
            "employed": self.employed,
            "unemployed": self.unemployed,
            "unemployment_rate": round(self.unemployment_rate, 4),
            "open_vacancies": self.open_vacancies,
            "housing_capacity": self.housing_capacity,
            "homeless": self.homeless,
            "housing_shortage": self.housing_shortage,
            "happiness": round(self.happiness, 2),
            "average_health": round(self.average_health, 2),
            "budget": round(self.budget, 2),
            "gdp": round(self.gdp, 2),
            "monthly_net": round(self.monthly_net, 2),
            "buildings_open": self.buildings_open,
            "buildings_under_construction": self.buildings_under_construction,
            "free_land": self.free_land,
            "coverage": {
                "healthcare": round(self.healthcare_coverage, 3),
                "education": round(self.education_coverage, 3),
                "retail": round(self.retail_coverage, 3),
                "food": round(self.food_coverage, 3),
                "power": round(self.power_coverage, 3),
                "security": round(self.security_coverage, 3),
            },
            "capacity": {
                "hospital_beds": self.hospital_beds,
                "beds_needed": self.beds_needed,
                "school_seats": self.school_seats,
                "seats_needed": self.seats_needed,
                "police_officers": self.police_officers,
                "police_needed": self.police_needed,
            },
        }


def analyse(
    agents: dict[int, Agent],
    buildings: dict[int, Building],
    economy: Economy,
    grid: Grid,
) -> CityStats:
    """Computes every indicator in one pass over agents and buildings."""
    stats = CityStats()

    living = [agent for agent in agents.values() if agent.alive]
    stats.population = len(living)

    happiness_total = 0.0
    health_total = 0.0

    for agent in living:
        happiness_total += agent.happiness
        health_total += agent.needs.health

        stage = agent.life_stage
        if stage is LifeStage.SENIOR:
            stats.seniors += 1
            stats.adults += 1
        elif stage is LifeStage.ADULT:
            stats.adults += 1
        else:
            stats.children += 1

        if agent.is_school_age:
            stats.school_age += 1

        if agent.can_work:
            if agent.employed:
                stats.employed += 1
                spec = PROFESSIONS[agent.profession]
                if spec.public_sector:
                    stats.public_wage_bill += agent.salary
                else:
                    stats.private_wage_bill += agent.salary
            else:
                stats.unemployed += 1

        if agent.home_id is None:
            stats.homeless += 1

    workforce = stats.employed + stats.unemployed
    stats.unemployment_rate = stats.unemployed / workforce if workforce else 0.0
    stats.housed = stats.population - stats.homeless

    if living:
        stats.happiness = happiness_total / len(living)
        stats.average_health = health_total / len(living)

    for building in buildings.values():
        if building.status.value == "under_construction":
            stats.buildings_under_construction += 1
            continue
        if not building.is_open:
            continue

        stats.buildings_open += 1
        stats.total_upkeep += building.spec.upkeep

        if building.spec.category is BuildingCategory.RESIDENTIAL:
            stats.housing_capacity += building.housing_capacity

        stats.hospital_beds += building.hospital_beds
        stats.school_seats += building.school_seats
        stats.retail_capacity += building.retail_capacity
        stats.food_output += building.food_output
        stats.power_output += building.power_output
        stats.police_officers += building.filled_for(Profession.POLICE)

        for profession, count in building.vacancies().items():
            stats.open_vacancies += count
            stats.vacancies_by_profession[profession] = (
                stats.vacancies_by_profession.get(profession, 0) + count
            )

    # Needs derived from population size.
    stats.beds_needed = int(stats.population * BEDS_PER_1000 / 1000) + 1
    stats.seats_needed = stats.school_age
    stats.retail_needed = int(stats.population * RETAIL_PER_CITIZEN)
    stats.food_needed = int(stats.population * FOOD_PER_CITIZEN)
    stats.power_needed = int(stats.population * POWER_PER_CITIZEN)
    stats.police_needed = int(stats.population * POLICE_PER_1000 / 1000) + 1

    # Housing shortage counts beds, not buildings, so the president can size the
    # response instead of always building one house.
    stats.housing_shortage = max(0, stats.population - stats.housing_capacity)

    stats.budget = economy.budget
    stats.gdp = economy.gdp
    stats.monthly_net = economy.monthly_net

    stats.free_land = grid.free_land()
    stats.free_residential_land = grid.free_land(District.RESIDENTIAL)

    return stats
