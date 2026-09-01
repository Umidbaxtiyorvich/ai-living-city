"""
Parking — capacity tracking and shortage detection.

Specification section 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ParkingKind(StrEnum):
    STREET = "street_parking"
    PUBLIC = "public_parking"
    UNDERGROUND = "underground"
    BUILDING = "building_parking"


#: Spaces one parking tile provides.
SPACES_PER_TILE: dict[ParkingKind, int] = {
    ParkingKind.STREET: 4,
    ParkingKind.PUBLIC: 40,
    ParkingKind.UNDERGROUND: 80,
    ParkingKind.BUILDING: 20,
}


@dataclass(slots=True)
class ParkingLot:
    x: int
    y: int
    kind: ParkingKind
    capacity: int
    occupied: int = 0

    @property
    def free(self) -> int:
        return max(0, self.capacity - self.occupied)


@dataclass
class ParkingSystem:
    lots: list[ParkingLot] = field(default_factory=list)

    @property
    def total_capacity(self) -> int:
        return sum(lot.capacity for lot in self.lots)

    @property
    def total_occupied(self) -> int:
        return sum(lot.occupied for lot in self.lots)

    @property
    def shortage(self) -> int:
        """Positive when more vehicles than spaces."""
        return max(0, self.total_occupied - self.total_capacity)

    def estimate_demand(self, *, population: int, employed: int) -> int:
        """Rough parking demand from population and commuters."""
        return int(population * 0.35 + employed * 0.45)

    def analyse(self, *, population: int, employed: int) -> dict:
        demand = self.estimate_demand(population=population, employed=employed)
        capacity = self.total_capacity
        return {
            "capacity": capacity,
            "demand": demand,
            "shortage": max(0, demand - capacity),
            "utilization": min(1.0, demand / max(1, capacity)),
        }

    def snapshot(self) -> list[dict]:
        return [
            {
                "x": lot.x,
                "y": lot.y,
                "kind": lot.kind.value,
                "capacity": lot.capacity,
                "occupied": lot.occupied,
            }
            for lot in self.lots
        ]

    @classmethod
    def restore(cls, data: list[dict]) -> "ParkingSystem":
        system = cls()
        for item in data:
            system.lots.append(
                ParkingLot(
                    x=int(item["x"]),
                    y=int(item["y"]),
                    kind=ParkingKind(item["kind"]),
                    capacity=int(item["capacity"]),
                    occupied=int(item.get("occupied", 0)),
                )
            )
        return system
