"""
The tile grid the city is built on.

The grid is the single source of truth for what exists where: pathfinding,
construction land checks and the 3D renderer all read from it. Tiles are stored
in one flat list rather than a nested one because every hot loop here is a
linear scan or an index lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TileType(StrEnum):
    """Specification section 3."""

    GRASS = "grass"
    ROAD = "road"
    SIDEWALK = "sidewalk"
    BUILDABLE = "buildable"
    WATER = "water"
    PARK = "park"
    BUILDING = "building"
    FOREST = "forest"
    RESERVED = "reserved"


class District(StrEnum):
    """Zoning. Decides what the president is allowed to build where."""

    UNZONED = "unzoned"
    CITY_CENTER = "city_center"
    RESIDENTIAL = "residential"
    BUSINESS = "business"
    INDUSTRIAL = "industrial"
    PARK = "park"
    ZOO = "zoo"
    SCHOOL = "school"
    HOSPITAL = "hospital"
    FARM = "farm"
    SHOPPING = "shopping"
    OFFICE = "office"


#: Tiles an agent on foot may cross. Vacant zoned land is included: it is an
#: empty lot, and excluding it strands any destination in the middle of a block
#: that no road has reached yet.
WALKABLE = frozenset(
    {
        TileType.ROAD,
        TileType.SIDEWALK,
        TileType.GRASS,
        TileType.PARK,
        TileType.BUILDABLE,
    }
)

#: Tiles a vehicle may cross.
DRIVABLE = frozenset({TileType.ROAD})

#: Tiles a new building may be placed on.
CONSTRUCTIBLE = frozenset({TileType.BUILDABLE, TileType.GRASS})

#: Relative cost of crossing a tile on foot. Sidewalks are cheapest so
#: pedestrians visibly use the infrastructure built for them, and open ground
#: costs most so they do not cut across every lot.
WALK_COST: dict[TileType, float] = {
    TileType.SIDEWALK: 1.0,
    TileType.PARK: 1.2,
    TileType.ROAD: 1.4,
    TileType.GRASS: 1.8,
    TileType.BUILDABLE: 1.9,
}


@dataclass(slots=True)
class Tile:
    x: int
    y: int
    type: TileType
    district: District = District.UNZONED
    #: Id of the building occupying this tile, if any.
    building_id: int | None = None
    #: Elevation in metres; used by the renderer and blocks water placement.
    elevation: float = 0.0
    #: Road hierarchy level (0 = not a road, 1 = highway … 4 = local street).
    road_level: int = 0


class Grid:
    """A rectangular tile map that can grow outward as the city expands."""

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("grid dimensions must be positive")
        self.width = width
        self.height = height
        self._tiles: list[Tile] = [
            Tile(x=index % width, y=index // width, type=TileType.GRASS)
            for index in range(width * height)
        ]
        #: Free-land counts per district, rebuilt lazily. The city analysis asks
        #: for these constantly while the grid changes only during construction,
        #: so scanning every tile on each query was pure waste.
        self._free_land_cache: dict[District | None, int] | None = None

    def _invalidate_cache(self) -> None:
        self._free_land_cache = None

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        """
        The map as parallel run-length encoded columns.

        A 500x500 map is a quarter of a million tiles. Storing one object per
        tile turns a save into tens of megabytes of near-identical JSON, so
        each attribute is encoded as runs of equal values — cities are wide
        stretches of the same thing.
        """
        return {
            "width": self.width,
            "height": self.height,
            "type": _runs(tile.type.value for tile in self._tiles),
            "district": _runs(tile.district.value for tile in self._tiles),
            "building_id": _runs(tile.building_id for tile in self._tiles),
            "elevation": _runs(tile.elevation for tile in self._tiles),
            "road_level": _runs(tile.road_level for tile in self._tiles),
        }

    @classmethod
    def restore(cls, data: dict) -> "Grid":
        grid = cls(int(data["width"]), int(data["height"]))
        types = list(_expand(data["type"]))
        districts = list(_expand(data["district"]))
        building_ids = list(_expand(data["building_id"]))
        elevations = list(_expand(data["elevation"]))
        road_levels = list(_expand(data.get("road_level", [[0, len(grid._tiles)]])))

        for tile, type_value, district, building_id, elevation, road_level in zip(
            grid._tiles, types, districts, building_ids, elevations, road_levels
        ):
            tile.type = TileType(type_value)
            tile.district = District(district)
            tile.building_id = building_id
            tile.elevation = float(elevation)
            tile.road_level = int(road_level)

        grid._invalidate_cache()
        return grid

    # -- access ------------------------------------------------------------

    def contains(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def at(self, x: int, y: int) -> Tile:
        if not self.contains(x, y):
            raise IndexError(f"tile ({x}, {y}) is outside a {self.width}x{self.height} grid")
        return self._tiles[y * self.width + x]

    def get(self, x: int, y: int) -> Tile | None:
        """Bounds-tolerant variant for neighbour scans."""
        if not self.contains(x, y):
            return None
        return self._tiles[y * self.width + x]

    @property
    def tiles(self) -> list[Tile]:
        return self._tiles

    def __iter__(self):
        return iter(self._tiles)

    # -- queries -----------------------------------------------------------

    def neighbours(self, x: int, y: int, *, diagonal: bool = False) -> list[Tile]:
        offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))
        if diagonal:
            offsets += ((1, 1), (1, -1), (-1, 1), (-1, -1))

        found = []
        for dx, dy in offsets:
            tile = self.get(x + dx, y + dy)
            if tile is not None:
                found.append(tile)
        return found

    def is_walkable(self, x: int, y: int) -> bool:
        tile = self.get(x, y)
        return tile is not None and tile.type in WALKABLE

    def region(self, x: int, y: int, width: int, height: int) -> list[Tile]:
        """Tiles in a rectangle, clipped to the grid."""
        found = []
        for ty in range(y, y + height):
            for tx in range(x, x + width):
                tile = self.get(tx, ty)
                if tile is not None:
                    found.append(tile)
        return found

    def can_place(self, x: int, y: int, width: int, height: int) -> bool:
        """True when a footprint fits entirely on free, constructible land."""
        if not self.contains(x, y) or not self.contains(x + width - 1, y + height - 1):
            return False
        return all(
            tile.type in CONSTRUCTIBLE and tile.building_id is None
            for tile in self.region(x, y, width, height)
        )

    def find_free_plot(
        self,
        width: int,
        height: int,
        *,
        district: District | None = None,
        near: tuple[int, int] | None = None,
    ) -> tuple[int, int] | None:
        """
        First footprint that fits, preferring plots close to `near`.

        Sorting candidates by distance keeps the city compact instead of
        scattering buildings across the map, which is what makes generated
        districts read as neighbourhoods.
        """
        origin_x, origin_y = near or (self.width // 2, self.height // 2)
        best: tuple[float, int, int] | None = None

        for tile in self._tiles:
            if district is not None and tile.district != district:
                continue

            # Distance is checked before the footprint test because it is far
            # cheaper, and most tiles lose on distance anyway.
            distance = (tile.x - origin_x) ** 2 + (tile.y - origin_y) ** 2
            if best is not None and distance >= best[0]:
                continue
            if not self.can_place(tile.x, tile.y, width, height):
                continue

            best = (distance, tile.x, tile.y)

        return (best[1], best[2]) if best else None

    # -- mutation ----------------------------------------------------------

    def set_type(self, x: int, y: int, tile_type: TileType) -> None:
        self.at(x, y).type = tile_type
        self._invalidate_cache()

    def zone(self, x: int, y: int, width: int, height: int, district: District) -> None:
        for tile in self.region(x, y, width, height):
            tile.district = district
            if tile.type == TileType.GRASS:
                tile.type = TileType.BUILDABLE
        self._invalidate_cache()

    def occupy(self, x: int, y: int, width: int, height: int, building_id: int) -> None:
        for tile in self.region(x, y, width, height):
            tile.type = TileType.BUILDING
            tile.building_id = building_id
        self._invalidate_cache()

    def release(self, building_id: int) -> None:
        """Frees every tile held by a demolished building."""
        for tile in self._tiles:
            if tile.building_id == building_id:
                tile.building_id = None
                tile.type = TileType.BUILDABLE
        self._invalidate_cache()

    def expand_to(self, width: int, height: int) -> None:
        """
        Grows the map, preserving existing tiles.

        Specification section 14: the city starts at 100x100 and the president
        opens new land as it grows. Shrinking is not supported — it would orphan
        buildings and agent destinations.
        """
        if width < self.width or height < self.height:
            raise ValueError("the map can only grow")
        if width == self.width and height == self.height:
            return

        grown: list[Tile] = []
        for y in range(height):
            for x in range(width):
                existing = self.get(x, y) if y < self.height and x < self.width else None
                grown.append(existing or Tile(x=x, y=y, type=TileType.GRASS))

        self._tiles = grown
        self.width = width
        self.height = height
        self._invalidate_cache()

    # -- statistics --------------------------------------------------------

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for tile in self._tiles:
            counts[tile.type] = counts.get(tile.type, 0) + 1
        return counts

    def free_land(self, district: District | None = None) -> int:
        """
        Buildable, unoccupied tiles, optionally within one district.

        Every district is counted in a single pass and cached, because callers
        ask for several of them in a row and the grid rarely changes between
        those calls.
        """
        if self._free_land_cache is None:
            counts: dict[District | None, int] = {None: 0}
            for tile in self._tiles:
                if tile.type not in CONSTRUCTIBLE or tile.building_id is not None:
                    continue
                counts[None] += 1
                counts[tile.district] = counts.get(tile.district, 0) + 1
            self._free_land_cache = counts

        return self._free_land_cache.get(district, 0)


# -- run-length coding for snapshots ---------------------------------------


def _runs(values) -> list:
    """`[value, count]` pairs for a sequence of mostly-repeating values."""
    encoded: list = []
    current = object()
    count = 0
    for value in values:
        if value == current and count:
            count += 1
            continue
        if count:
            encoded.append([current, count])
        current, count = value, 1
    if count:
        encoded.append([current, count])
    return encoded


def _expand(encoded: list):
    for value, count in encoded:
        for _ in range(count):
            yield value
