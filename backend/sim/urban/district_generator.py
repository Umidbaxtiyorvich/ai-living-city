"""
New district generation — roads, zoning, parks, parking.

Specification section 34.
"""

from __future__ import annotations

from ..rng import Rng
from ..world.plans import DistrictPlan
from ..world.tiles import District, Grid, TileType
from .master_plan import pick_expansion_zone
from .road_generator import generate_district_roads
from .zones import CityZone, district_for, label_for, spec_for


def create_district(
    grid: Grid,
    *,
    x: int,
    y: int,
    size: int,
    zone: CityZone,
    rng: Rng | None = None,
) -> DistrictPlan:
    """
    Opens a new district: zone land, lay internal roads, reserve green/parking.

    Returns the plan record appended to world state.
    """
    district = district_for(zone)
    spec = spec_for(zone)

    for tile in grid.region(x, y, size, size):
        if tile.type in (TileType.WATER, TileType.FOREST, TileType.BUILDING):
            continue
        tile.district = district
        if tile.type == TileType.GRASS:
            tile.type = TileType.BUILDABLE

    generate_district_roads(grid, x, y, size, size, zone)

    # Green reserve inside residential and recreation zones.
    if spec.green_ratio >= 0.20 and rng is not None:
        _scatter_green(grid, x, y, size, spec.green_ratio, rng)

    return DistrictPlan(
        district=district,
        zone=zone,
        x=x,
        y=y,
        width=size,
        height=size,
        density=spec.building_density,
        road_density=spec.road_density,
    )


def create_district_at_distance(
    grid: Grid,
    *,
    plot: tuple[int, int],
    size: int,
    preferred: CityZone | None = None,
    rng: Rng | None = None,
) -> DistrictPlan:
    cx, cy = grid.width // 2, grid.height // 2
    zone = pick_expansion_zone(
        centre_x=cx,
        centre_y=cy,
        plot_x=plot[0],
        plot_y=plot[1],
        map_width=grid.width,
        map_height=grid.height,
        preferred=preferred,
    )
    return create_district(grid, x=plot[0], y=plot[1], size=size, zone=zone, rng=rng)


def zone_label(plan: DistrictPlan) -> str:
    if plan.zone is not None:
        return label_for(plan.zone)
    return plan.district.value


def _scatter_green(grid: Grid, x: int, y: int, size: int, ratio: float, rng: Rng) -> None:
    target = int(size * size * ratio * 0.3)
    placed = 0
    for _ in range(target * 3):
        if placed >= target:
            break
        tx = rng.integer(x + 2, x + size - 3)
        ty = rng.integer(y + 2, y + size - 3)
        tile = grid.get(tx, ty)
        if tile is None or tile.type != TileType.BUILDABLE or tile.road_level > 0:
            continue
        tile.type = TileType.PARK
        placed += 1
