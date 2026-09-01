"""
City development levels (specification section 13).

A level is a gate, not a score: reaching one unlocks the buildings the president
may then choose from. That is what makes a village grow into a metropolis in
recognisable stages instead of building a power plant on day two.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ..buildings.catalog import BuildingType


class CityLevel(IntEnum):
    VILLAGE = 1
    SMALL_TOWN = 2
    TOWN = 3
    CITY = 4
    LARGE_CITY = 5
    METROPOLIS = 6


@dataclass(frozen=True, slots=True)
class LevelSpec:
    level: CityLevel
    name: str
    #: Population needed to reach this level.
    population: int
    #: Buildings unlocked at this level, on top of everything below it.
    unlocks: tuple[BuildingType, ...]


_LEVELS: tuple[LevelSpec, ...] = (
    LevelSpec(
        CityLevel.VILLAGE,
        "Qishloq",
        0,
        (
            BuildingType.HOUSE,
            BuildingType.FARM,
            BuildingType.SHOP,
            BuildingType.CLINIC,
            BuildingType.KINDERGARTEN,
            BuildingType.PARK,
            BuildingType.PRESIDENTIAL_PALACE,
            BuildingType.CITY_HALL,
        ),
    ),
    LevelSpec(
        CityLevel.SMALL_TOWN,
        "Kichik shaharcha",
        60,
        (
            BuildingType.TOWNHOUSE,
            BuildingType.SCHOOL,
            BuildingType.CAFE,
            BuildingType.MARKET,
            BuildingType.PHARMACY,
            BuildingType.POLICE_STATION,
            BuildingType.BUS_STOP,
        ),
    ),
    LevelSpec(
        CityLevel.TOWN,
        "Shaharcha",
        200,
        (
            BuildingType.APARTMENT,
            BuildingType.OFFICE,
            BuildingType.RESTAURANT,
            BuildingType.HOSPITAL,
            BuildingType.FIRE_STATION,
            BuildingType.WAREHOUSE,
            BuildingType.SPORT_CENTER,
        ),
    ),
    LevelSpec(
        CityLevel.CITY,
        "Shahar",
        600,
        (
            BuildingType.FACTORY,
            BuildingType.CINEMA,
            BuildingType.COURTHOUSE,
            BuildingType.POWER_PLANT,
        ),
    ),
    LevelSpec(
        CityLevel.LARGE_CITY,
        "Katta shahar",
        1_500,
        (BuildingType.UNIVERSITY, BuildingType.ZOO, BuildingType.TRAIN_STATION),
    ),
    LevelSpec(
        CityLevel.METROPOLIS,
        "Metropolis",
        4_000,
        (),
    ),
)

LEVELS: dict[CityLevel, LevelSpec] = {spec.level: spec for spec in _LEVELS}


def level_for_population(population: int) -> CityLevel:
    reached = CityLevel.VILLAGE
    for spec in _LEVELS:
        if population >= spec.population:
            reached = spec.level
    return reached


def unlocked_buildings(level: CityLevel) -> frozenset[BuildingType]:
    """Everything available at this level, including lower tiers."""
    available: set[BuildingType] = set()
    for spec in _LEVELS:
        if spec.level <= level:
            available.update(spec.unlocks)
    return frozenset(available)


def next_level_requirement(level: CityLevel) -> int | None:
    """Population needed for the next level, or None at the top."""
    for spec in _LEVELS:
        if spec.level == level + 1:
            return spec.population
    return None


def _sanity_check() -> None:
    """Every building must be unlocked by some level, or it is unreachable."""
    reachable = unlocked_buildings(CityLevel.METROPOLIS)
    missing = set(BuildingType) - reachable
    if missing:
        raise RuntimeError(f"buildings no level ever unlocks: {sorted(missing)}")


_sanity_check()
