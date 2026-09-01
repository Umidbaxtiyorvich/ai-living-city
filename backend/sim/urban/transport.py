"""
Public transport — bus routes and network.

Specification sections 11–12. Architecture is ready for metro/tram/BRT later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..world.tiles import District


class TransportMode(StrEnum):
    BUS = "bus"
    TAXI = "taxi"
    TRAIN = "train"
    METRO = "metro"  # future
    TRAM = "tram"  # future
    BRT = "brt"  # future


@dataclass(slots=True)
class BusStop:
    building_id: int | None
    x: int
    y: int
    name: str = ""


@dataclass(slots=True)
class BusRoute:
    id: int
    name: str
    stops: list[tuple[int, int]]
    districts: list[District]
    mode: TransportMode = TransportMode.BUS
    active: bool = True
    ridership: int = 0

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "stops": self.stops,
            "districts": [d.value for d in self.districts],
            "mode": self.mode.value,
            "active": self.active,
            "ridership": self.ridership,
        }


@dataclass
class TransportNetwork:
    routes: list[BusRoute] = field(default_factory=list)
    stops: list[BusStop] = field(default_factory=list)
    _next_route_id: int = 1

    def add_route(
        self,
        name: str,
        stops: list[tuple[int, int]],
        districts: list[District],
        *,
        mode: TransportMode = TransportMode.BUS,
    ) -> BusRoute:
        route = BusRoute(
            id=self._next_route_id,
            name=name,
            stops=stops,
            districts=districts,
            mode=mode,
        )
        self._next_route_id += 1
        self.routes.append(route)
        return route

    def coverage_ratio(self, *, population: int) -> float:
        if population <= 0:
            return 1.0
        served = sum(route.ridership for route in self.routes if route.active)
        return min(1.0, served / max(1, population * 0.4))

    def snapshot(self) -> dict:
        return {
            "routes": [route.as_dict() for route in self.routes],
            "stops": [
                {
                    "building_id": stop.building_id,
                    "x": stop.x,
                    "y": stop.y,
                    "name": stop.name,
                }
                for stop in self.stops
            ],
            "next_route_id": self._next_route_id,
        }

    @classmethod
    def restore(cls, data: dict) -> "TransportNetwork":
        network = cls()
        network._next_route_id = int(data.get("next_route_id", 1))
        for item in data.get("routes", []):
            network.routes.append(
                BusRoute(
                    id=int(item["id"]),
                    name=item["name"],
                    stops=[tuple(stop) for stop in item["stops"]],
                    districts=[District(d) for d in item["districts"]],
                    mode=TransportMode(item.get("mode", "bus")),
                    active=bool(item.get("active", True)),
                    ridership=int(item.get("ridership", 0)),
                )
            )
        for item in data.get("stops", []):
            network.stops.append(
                BusStop(
                    building_id=item.get("building_id"),
                    x=int(item["x"]),
                    y=int(item["y"]),
                    name=item.get("name", ""),
                )
            )
        return network
