"""
City expansion pipeline.

Specification section 33: population → housing → roads → utilities → district.
"""

from __future__ import annotations

from ..rng import Rng
from ..world.plans import DistrictPlan
from ..world.tiles import Grid
from .district_generator import create_district_at_distance
from .road_generator import generate_road_network
from .zones import CityZone


def expand_map_with_infrastructure(
    grid: Grid,
    *,
    new_width: int,
    new_height: int,
    rng: Rng,
) -> None:
    """
    Grows the map and generates roads/zoning on the new land.

    Existing tiles are untouched; only the added margin gets infrastructure.
    """
    old_w, old_h = grid.width, grid.height
    grid.expand_to(new_width, new_height)
    centre = (old_w // 2, old_h // 2)
    generate_road_network(grid, centre=centre, rng=rng)


def open_new_district(
    grid: Grid,
    *,
    plot: tuple[int, int],
    size: int,
    zone: CityZone | None,
    rng: Rng,
) -> DistrictPlan:
    """Full district opening: zone + internal roads + green space."""
    return create_district_at_distance(
        grid, plot=plot, size=size, preferred=zone, rng=rng
    )
