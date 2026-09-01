"""
Intersections and traffic lights.

Specification sections 7–8: major crossings get signals tied to the traffic
simulation loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .roads import RoadLevel


class IntersectionKind(StrEnum):
    T_INTERSECTION = "t_intersection"
    CROSS_INTERSECTION = "cross_intersection"
    ROUNDABOUT = "roundabout"
    HIGHWAY_EXIT = "highway_exit"
    BRIDGE = "bridge_intersection"


class SignalState(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class PedestrianSignal(StrEnum):
    WALK = "walk"
    STOP = "stop"


@dataclass(slots=True)
class TrafficLight:
    x: int
    y: int
    vehicle: SignalState = SignalState.GREEN
    pedestrian: PedestrianSignal = PedestrianSignal.WALK
    cycle_tick: int = 0
    green_ticks: int = 120
    yellow_ticks: int = 20
    red_ticks: int = 100

    def step(self, tick: int) -> None:
        phase = (tick + self.cycle_tick) % (self.green_ticks + self.yellow_ticks + self.red_ticks)
        if phase < self.green_ticks:
            self.vehicle = SignalState.GREEN
            self.pedestrian = PedestrianSignal.STOP
        elif phase < self.green_ticks + self.yellow_ticks:
            self.vehicle = SignalState.YELLOW
            self.pedestrian = PedestrianSignal.STOP
        else:
            self.vehicle = SignalState.RED
            self.pedestrian = PedestrianSignal.WALK


@dataclass(slots=True)
class Intersection:
    x: int
    y: int
    kind: IntersectionKind
    roads: list[RoadLevel] = field(default_factory=list)
    traffic_light: TrafficLight | None = None
    has_crosswalk: bool = True

    def as_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "kind": self.kind.value,
            "has_traffic_light": self.traffic_light is not None,
            "vehicle_signal": self.traffic_light.vehicle.value if self.traffic_light else None,
            "pedestrian_signal": (
                self.traffic_light.pedestrian.value if self.traffic_light else None
            ),
        }
