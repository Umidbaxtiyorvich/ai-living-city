"""
Urban planning orchestrator — ties generators together.

Specification section 53: modular API entry point for city structure.
"""

from __future__ import annotations

from ..rng import Rng
from ..world.plans import DistrictPlan
from ..world.tiles import Grid, TileType
from .district_generator import create_district
from .master_plan import MasterPlan, plan_initial_city
from .road_generator import generate_road_network
from .state import UrbanState
from .zones import CityZone


class UrbanPlanner:
    """Generates and extends realistic city structure."""

    @staticmethod
    def generate_initial(width: int, height: int, rng: Rng) -> tuple[Grid, list[DistrictPlan], UrbanState]:
        grid = Grid(width, height)
        urban = UrbanState()

        _carve_river(grid, rng)
        _scatter_forest(grid, rng)

        master = plan_initial_city(width, height, rng)
        _apply_plans(grid, master.districts)

        centre = (master.centre_x, master.centre_y)
        generate_road_network(grid, centre=centre, rng=rng)

        from .egregoria_network import URBAN_NETWORK_VERSION

        urban.refresh_from_grid(grid)
        urban.network_version = URBAN_NETWORK_VERSION
        _add_landmarks(urban, master)

        return grid, list(master.districts), urban

    @staticmethod
    def after_map_change(grid: Grid, urban: UrbanState) -> None:
        urban.refresh_from_grid(grid)

    @staticmethod
    def open_district(
        grid: Grid,
        urban: UrbanState,
        *,
        x: int,
        y: int,
        size: int,
        zone: CityZone,
        rng: Rng,
    ) -> DistrictPlan:
        plan = create_district(grid, x=x, y=y, size=size, zone=zone, rng=rng)
        urban.refresh_from_grid(grid)
        return plan


def _apply_plans(grid: Grid, plans: tuple[DistrictPlan, ...]) -> None:
    for plan in plans:
        for tile in grid.region(plan.x, plan.y, plan.width, plan.height):
            if tile.type in (TileType.WATER, TileType.FOREST):
                continue
            tile.district = plan.district
            tile.type = TileType.BUILDABLE


def _carve_river(grid: Grid, rng: Rng) -> None:
    x = int(grid.width * 0.82)
    for y in range(grid.height):
        x += rng.integer(-1, 1)
        x = max(int(grid.width * 0.74), min(int(grid.width * 0.9), x))
        for offset in range(rng.integer(2, 3)):
            tile = grid.get(x + offset, y)
            if tile is not None:
                tile.type = TileType.WATER


def _scatter_forest(grid: Grid, rng: Rng) -> None:
    clumps = max(4, (grid.width * grid.height) // 2_000)
    for _ in range(clumps):
        cx = rng.integer(0, grid.width - 1)
        cy = rng.integer(0, grid.height - 1)
        if 0.25 < cx / grid.width < 0.75 and 0.25 < cy / grid.height < 0.75:
            continue
        radius = rng.integer(3, 7)
        for tile in grid.region(cx - radius, cy - radius, radius * 2, radius * 2):
            if tile.type != TileType.GRASS:
                continue
            distance = ((tile.x - cx) ** 2 + (tile.y - cy) ** 2) ** 0.5
            if distance <= radius and rng.chance(1.0 - distance / (radius + 1)):
                tile.type = TileType.FOREST


def _add_landmarks(urban: UrbanState, master: MasterPlan) -> None:
    urban.landmarks = [
        {
            "kind": "central_square",
            "x": master.centre_x,
            "y": master.centre_y,
            "label": "Markaziy maydon",
        },
        {
            "kind": "city_gate",
            "x": master.width // 2,
            "y": master.height - 4,
            "label": "Shahar darvozasi",
        },
    ]
