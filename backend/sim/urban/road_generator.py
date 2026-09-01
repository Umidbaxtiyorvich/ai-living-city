"""

Hierarchical road generation with sidewalks and street furniture.



Uses an Egregoria-inspired organic network (radial rings + curved arterials)

instead of a flat grid lattice.

"""



from __future__ import annotations



from ..rng import Rng

from ..world.tiles import Grid, TileType

from .egregoria_network import generate_organic_network

from .roads import RoadLevel

from .zones import CityZone, ZoneSpec, spec_for



#: Minimum block interior for largest building footprint.

BLOCK_SIZE = 12





def generate_road_network(

    grid: Grid,

    *,

    centre: tuple[int, int] | None = None,

    rng: Rng | None = None,

) -> None:

    """

    Lays the full hierarchical road network on an existing grid.



    Safe to call after expansion — only touches grass/buildable tiles for

    new roads, never overwrites water or buildings.

    """

    cx, cy = centre or (grid.width // 2, grid.height // 2)

    stream = rng or Rng(0, "roads")

    generate_organic_network(grid, centre=(cx, cy), rng=stream)

    _lay_sidewalks(grid)

    _mark_street_lights(grid)





def generate_district_roads(

    grid: Grid,

    x: int,

    y: int,

    width: int,

    height: int,

    zone: CityZone,

) -> None:

    """Roads inside one newly zoned district block."""

    spec = spec_for(zone)

    step = max(BLOCK_SIZE, spec.block_size)

    for ly in range(y, y + height, step):

        for lx in range(x, x + width):

            _set_road(grid, lx, ly, RoadLevel.DISTRICT_ROAD)

    for lx in range(x, x + width, step):

        for ly in range(y, y + height):

            _set_road(grid, lx, ly, RoadLevel.DISTRICT_ROAD)

    _lay_sidewalks_in_region(grid, x, y, width, height)





def _set_road(

    grid: Grid,

    x: int,

    y: int,

    level: RoadLevel,

    *,

    allow_upgrade: bool = True,

) -> None:

    tile = grid.get(x, y)

    if tile is None or tile.type in (TileType.WATER, TileType.BUILDING):

        return

    if not allow_upgrade and tile.road_level > 0:

        return

    if allow_upgrade and tile.road_level > 0 and int(level) >= tile.road_level:

        return

    tile.type = TileType.ROAD

    tile.road_level = int(level)





def _lay_sidewalks(grid: Grid) -> None:

    for tile in list(grid):

        if tile.road_level <= 0:

            continue

        for neighbour in grid.neighbours(tile.x, tile.y):

            if neighbour.type in (TileType.BUILDABLE, TileType.GRASS):

                neighbour.type = TileType.SIDEWALK





def _lay_sidewalks_in_region(grid: Grid, x: int, y: int, w: int, h: int) -> None:

    for tile in grid.region(x, y, w, h):

        if tile.road_level <= 0:

            continue

        for neighbour in grid.neighbours(tile.x, tile.y):

            if neighbour.type in (TileType.BUILDABLE, TileType.GRASS):

                neighbour.type = TileType.SIDEWALK





def _mark_street_lights(grid: Grid) -> None:

    """Street lights on main roads — positions collected by UrbanState.refresh_from_grid()."""

    pass


