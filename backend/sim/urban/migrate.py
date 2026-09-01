"""Upgrade older saves to the Egregoria-inspired road network."""



from __future__ import annotations



from ..rng import Rng

from ..world.tiles import Grid

from .egregoria_network import URBAN_NETWORK_VERSION, clear_road_tiles, generate_organic_network

from .road_generator import _lay_sidewalks





def upgrade_grid_roads(grid: Grid, *, rng: Rng | None = None, version: int = 0) -> bool:

    """

    Regenerates roads when the urban network version is outdated.



    Returns True when the grid was changed.

    """

    if version >= URBAN_NETWORK_VERSION:

        return False



    stream = rng or Rng(0, "migrate")

    centre = (grid.width // 2, grid.height // 2)

    clear_road_tiles(grid)

    generate_organic_network(grid, centre=centre, rng=stream)

    _lay_sidewalks(grid)

    return True


