"""
Urban simulation state — roads, intersections, parking, transport, utilities.

Held on `WorldState.urban` and persisted alongside the grid snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..buildings.models import Building
from ..world.tiles import Grid, TileType
from .intersections import Intersection, IntersectionKind, TrafficLight
from .parking import ParkingKind, ParkingLot, ParkingSystem
from .roads import RoadLevel
from .transport import TransportNetwork
from .utilities import UtilityGrid


@dataclass
class UrbanState:
    parking: ParkingSystem = field(default_factory=ParkingSystem)
    transport: TransportNetwork = field(default_factory=TransportNetwork)
    utilities: UtilityGrid = field(default_factory=UtilityGrid)
    intersections: list[Intersection] = field(default_factory=list)
    street_lights: list[tuple[int, int]] = field(default_factory=list)
    landmarks: list[dict] = field(default_factory=list)
    network_version: int = 0

    def refresh_from_grid(self, grid: Grid) -> None:
        """Rebuild derived road infrastructure from the tile map."""
        self.intersections.clear()
        self.street_lights.clear()
        road_tiles: list[tuple[int, int, RoadLevel]] = []

        for tile in grid:
            if tile.road_level <= 0:
                continue
            level = RoadLevel(tile.road_level)
            road_tiles.append((tile.x, tile.y, level))
            if level.value <= RoadLevel.MAIN_AVENUE.value:
                self.street_lights.append((tile.x, tile.y))

        self._detect_intersections(grid, road_tiles)

    def _detect_intersections(
        self,
        grid: Grid,
        road_tiles: list[tuple[int, int, RoadLevel]],
    ) -> None:
        road_set = {(x, y) for x, y, _ in road_tiles}
        for x, y, level in road_tiles:
            neighbours = sum(
                1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (x + dx, y + dy) in road_set
            )
            if neighbours < 3:
                continue
            kind = (
                IntersectionKind.CROSS_INTERSECTION
                if neighbours >= 4
                else IntersectionKind.T_INTERSECTION
            )
            light = None
            if level.value <= RoadLevel.MAIN_AVENUE.value:
                light = TrafficLight(x=x, y=y)
            self.intersections.append(
                Intersection(x=x, y=y, kind=kind, traffic_light=light)
            )

    def step_traffic_lights(self, tick: int) -> None:
        for intersection in self.intersections:
            if intersection.traffic_light is not None:
                intersection.traffic_light.step(tick)

    def estimate_road_traffic(self, grid: Grid, *, population: int) -> float:
        """Average congestion across the road network."""
        levels = [tile.road_level for tile in grid if tile.road_level > 0]
        if not levels:
            return 0.0
        # Rough model: traffic scales with population per road tile.
        per_road = population / max(1, len(levels))
        congestions = []
        for level_int in levels:
            level = RoadLevel(level_int)
            from .roads import CAPACITY

            traffic = int(per_road * 8 * (5 - level.value))
            congestions.append(min(1.0, traffic / max(1, CAPACITY[level])))
        return sum(congestions) / len(congestions)

    def seed_parking_near_buildings(self, buildings: dict[int, Building]) -> None:
        """Places building parking for large commercial/industrial structures."""
        existing = {(lot.x, lot.y) for lot in self.parking.lots}
        for building in buildings.values():
            if not building.is_open:
                continue
            if building.spec.retail_capacity <= 0 and building.total_job_slots < 10:
                continue
            spot = (building.x + building.width, building.y)
            if spot in existing:
                continue
            self.parking.lots.append(
                ParkingLot(
                    x=spot[0],
                    y=spot[1],
                    kind=ParkingKind.BUILDING,
                    capacity=max(10, building.total_job_slots // 2),
                )
            )
            existing.add(spot)

    def urban_payload(self) -> dict:
        return {
            "parking": self.parking.analyse(population=0, employed=0),
            "transport": {
                "routes": len(self.transport.routes),
                "stops": len(self.transport.stops),
            },
            "utilities": self.utilities.as_dict(),
            "intersections": len(self.intersections),
            "street_lights": len(self.street_lights),
            "landmarks": self.landmarks,
            "network_version": self.network_version,
        }

    def snapshot(self) -> dict:
        return {
            "parking": self.parking.snapshot(),
            "transport": self.transport.snapshot(),
            "utilities": self.utilities.snapshot(),
            "intersections": [item.as_dict() for item in self.intersections],
            "street_lights": self.street_lights,
            "landmarks": self.landmarks,
            "network_version": self.network_version,
        }

    @classmethod
    def restore(cls, data: dict | None) -> "UrbanState":
        if not data:
            return cls()
        state = cls()
        state.parking = ParkingSystem.restore(data.get("parking", []))
        state.transport = TransportNetwork.restore(data.get("transport", {}))
        state.utilities = UtilityGrid.restore(data.get("utilities", {}))
        state.street_lights = [tuple(item) for item in data.get("street_lights", [])]
        state.landmarks = list(data.get("landmarks", []))
        state.network_version = int(data.get("network_version", 0))
        return state
