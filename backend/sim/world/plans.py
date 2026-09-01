"""District layout records shared by world generation and urban planning."""

from __future__ import annotations

from dataclasses import dataclass

from ..urban.zones import CityZone
from .tiles import District


@dataclass(frozen=True, slots=True)
class DistrictPlan:
    """A zoned rectangle, in tile coordinates."""

    district: District
    x: int
    y: int
    width: int
    height: int
    zone: CityZone | None = None
    density: float = 0.35
    road_density: float = 0.15
