"""
Initial map generation entry point.

Buildings are not placed here — the city bootstrap does that through the
normal construction path.
"""

from __future__ import annotations

from ..rng import Rng
from ..urban.state import UrbanState
from .plans import DistrictPlan
from .tiles import Grid

#: Kept for tests that guard footprint vs block size.
BLOCK_SIZE = 12


def generate_world(
    width: int, height: int, rng: Rng
) -> tuple[Grid, list[DistrictPlan], UrbanState]:
    """Builds the starting grid with hierarchical roads and master plan."""
    from ..urban.planner import UrbanPlanner

    grid, plans, urban = UrbanPlanner.generate_initial(width, height, rng)
    return grid, plans, urban


def road_tiles(grid: Grid) -> list[tuple[int, int]]:
    return [(tile.x, tile.y) for tile in grid if tile.road_level > 0]


def district_bounds(plans: list[DistrictPlan], district) -> DistrictPlan | None:
    for plan in plans:
        if plan.district is district:
            return plan
    return None
