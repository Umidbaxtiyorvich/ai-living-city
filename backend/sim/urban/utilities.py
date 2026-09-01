"""
Utilities — power, water and blackout simulation.

Specification sections 24–25.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UtilityGrid:
    """Abstract utility network — buildings draw from pooled capacity."""

    power_capacity: int = 0
    power_demand: int = 0
    water_capacity: int = 0
    water_demand: int = 0
    blackout: bool = False
    water_shortage: bool = False

    def refresh(
        self,
        *,
        power_output: int,
        power_needed: int,
        water_output: int,
        water_needed: int,
    ) -> None:
        self.power_capacity = power_output
        self.power_demand = power_needed
        self.water_capacity = water_output
        self.water_demand = water_needed
        self.blackout = power_needed > power_output
        self.water_shortage = water_needed > water_output

    @property
    def power_coverage(self) -> float:
        if self.power_demand <= 0:
            return 1.0
        return min(1.0, self.power_capacity / self.power_demand)

    @property
    def water_coverage(self) -> float:
        if self.water_demand <= 0:
            return 1.0
        return min(1.0, self.water_capacity / self.water_demand)

    def as_dict(self) -> dict:
        return {
            "power_capacity": self.power_capacity,
            "power_demand": self.power_demand,
            "power_coverage": round(self.power_coverage, 3),
            "water_capacity": self.water_capacity,
            "water_demand": self.water_demand,
            "water_coverage": round(self.water_coverage, 3),
            "blackout": self.blackout,
            "water_shortage": self.water_shortage,
        }

    def snapshot(self) -> dict:
        return {
            "power_capacity": self.power_capacity,
            "power_demand": self.power_demand,
            "water_capacity": self.water_capacity,
            "water_demand": self.water_demand,
            "blackout": self.blackout,
            "water_shortage": self.water_shortage,
        }

    @classmethod
    def restore(cls, data: dict) -> "UtilityGrid":
        grid = cls()
        grid.power_capacity = int(data.get("power_capacity", 0))
        grid.power_demand = int(data.get("power_demand", 0))
        grid.water_capacity = int(data.get("water_capacity", 0))
        grid.water_demand = int(data.get("water_demand", 0))
        grid.blackout = bool(data.get("blackout", False))
        grid.water_shortage = bool(data.get("water_shortage", False))
        return grid
