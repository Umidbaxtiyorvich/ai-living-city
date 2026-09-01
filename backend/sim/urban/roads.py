"""
Road hierarchy — highways through local streets.

Road level is stored on each tile (`Tile.road_level`). Level 0 means not a road.
Levels 1–4 follow specification section 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RoadLevel(IntEnum):
    """Specification section 6 — four road tiers."""

    HIGHWAY = 1
    MAIN_AVENUE = 2
    DISTRICT_ROAD = 3
    LOCAL_STREET = 4


LANES: dict[RoadLevel, int] = {
    RoadLevel.HIGHWAY: 6,
    RoadLevel.MAIN_AVENUE: 4,
    RoadLevel.DISTRICT_ROAD: 3,
    RoadLevel.LOCAL_STREET: 2,
}

SPEED_KMH: dict[RoadLevel, int] = {
    RoadLevel.HIGHWAY: 100,
    RoadLevel.MAIN_AVENUE: 60,
    RoadLevel.DISTRICT_ROAD: 40,
    RoadLevel.LOCAL_STREET: 30,
}

CAPACITY: dict[RoadLevel, int] = {
    RoadLevel.HIGHWAY: 2400,
    RoadLevel.MAIN_AVENUE: 1200,
    RoadLevel.DISTRICT_ROAD: 600,
    RoadLevel.LOCAL_STREET: 300,
}

LABELS: dict[RoadLevel, str] = {
    RoadLevel.HIGHWAY: "magistral",
    RoadLevel.MAIN_AVENUE: "asosiy ko'cha",
    RoadLevel.DISTRICT_ROAD: "tuman ko'chasi",
    RoadLevel.LOCAL_STREET: "mahalla ko'chasi",
}


@dataclass(slots=True)
class RoadSegment:
    """One road tile with traffic state."""

    x: int
    y: int
    level: RoadLevel
    traffic: int = 0  # vehicles per hour (simulated)
    has_crosswalk: bool = False
    has_traffic_light: bool = False
    has_street_light: bool = False

    @property
    def capacity(self) -> int:
        return CAPACITY[self.level]

    @property
    def congestion(self) -> float:
        if self.capacity <= 0:
            return 0.0
        return min(1.0, self.traffic / self.capacity)

    @property
    def average_speed(self) -> float:
        return max(5.0, SPEED_KMH[self.level] * (1.0 - 0.7 * self.congestion))


def level_from_int(value: int) -> RoadLevel | None:
    if value <= 0:
        return None
    try:
        return RoadLevel(value)
    except ValueError:
        return None
