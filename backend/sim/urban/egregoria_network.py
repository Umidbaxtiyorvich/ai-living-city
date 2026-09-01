"""
Organic road network inspired by Egregoria (https://github.com/Uriopass/Egregoria).

Egregoria uses intersection graphs with splines instead of a rigid grid. This
module adapts that idea to the tile map: radial arterials, elliptical ring roads,
curved connectors and roundabouts — so the city reads like a real settlement
rather than a chessboard.
"""

from __future__ import annotations

import math

from ..rng import Rng
from ..world.tiles import District, Grid, TileType
from .roads import RoadLevel

#: Bump when the generation algorithm changes — triggers save migration.
URBAN_NETWORK_VERSION = 2


def generate_organic_network(
    grid: Grid,
    *,
    centre: tuple[int, int],
    rng: Rng,
) -> None:
    """Lays an Egregoria-style hierarchical network on the grid."""
    cx, cy = centre
    max_r = min(cx, cy, grid.width - cx - 1, grid.height - cy - 1) - 3
    if max_r < 12:
        _draw_cross(grid, cx, cy, max_r, RoadLevel.MAIN_AVENUE)
        return

    _draw_outer_highway(grid)
    _draw_ring_road(grid, cx, cy, int(max_r * 0.88), int(max_r * 0.82), RoadLevel.HIGHWAY, rng)

    ring_specs = (
        (0.20, 0.18, RoadLevel.MAIN_AVENUE),
        (0.34, 0.30, RoadLevel.MAIN_AVENUE),
        (0.50, 0.44, RoadLevel.MAIN_AVENUE),
        (0.66, 0.58, RoadLevel.DISTRICT_ROAD),
    )
    for rx_pct, ry_pct, level in ring_specs:
        rx = max(8, int(max_r * rx_pct))
        ry = max(8, int(max_r * ry_pct))
        _draw_ring_road(grid, cx, cy, rx, ry, level, rng)

    spokes = 10 + rng.integer(0, 2)
    for i in range(spokes):
        angle = (2.0 * math.pi * i / spokes) + rng.number(-0.12, 0.12)
        level = RoadLevel.HIGHWAY if i % 5 == 0 else RoadLevel.MAIN_AVENUE
        _draw_radial(grid, cx, cy, angle, max_r - 2, level, rng)

    _place_roundabouts(grid, cx, cy, max_r, rng)
    _connect_district_hubs(grid, cx, cy, max_r, rng)
    _fill_district_grid(grid, cx, cy, rng)
    _lay_local_streets(grid)


def clear_road_tiles(grid: Grid) -> None:
    """Strip roads before regenerating the network (migration helper)."""
    for tile in grid:
        if tile.type is TileType.ROAD:
            tile.type = TileType.GRASS if tile.district is District.UNZONED else TileType.BUILDABLE
            tile.road_level = 0
        elif tile.type is TileType.SIDEWALK:
            tile.type = TileType.GRASS if tile.district is District.UNZONED else TileType.BUILDABLE


def _draw_outer_highway(grid: Grid) -> None:
    margin = max(3, min(grid.width, grid.height) // 12)
    for x in range(grid.width):
        _set_road(grid, x, margin, RoadLevel.HIGHWAY)
        _set_road(grid, x, grid.height - margin - 1, RoadLevel.HIGHWAY)
    for y in range(grid.height):
        _set_road(grid, margin, y, RoadLevel.HIGHWAY)
        _set_road(grid, grid.width - margin - 1, y, RoadLevel.HIGHWAY)


def _draw_ring_road(
    grid: Grid,
    cx: int,
    cy: int,
    rx: int,
    ry: int,
    level: RoadLevel,
    rng: Rng,
) -> None:
    steps = max(48, int(2 * math.pi * max(rx, ry) / 1.8))
    points: list[tuple[int, int]] = []
    for i in range(steps):
        angle = 2.0 * math.pi * i / steps
        wobble = 1.0 + rng.number(-0.07, 0.07)
        x = int(cx + rx * math.cos(angle) * wobble)
        y = int(cy + ry * math.sin(angle) * wobble)
        if 1 <= x < grid.width - 1 and 1 <= y < grid.height - 1:
            points.append((x, y))
    for i in range(len(points)):
        _draw_segment(grid, points[i], points[(i + 1) % len(points)], level, width=2)


def _draw_radial(
    grid: Grid,
    cx: int,
    cy: int,
    angle: float,
    length: int,
    level: RoadLevel,
    rng: Rng,
) -> None:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    perp_x, perp_y = -sin_a, cos_a
    prev: tuple[int, int] | None = None
    for dist in range(4, length):
        wobble = math.sin(dist * 0.22) * rng.number(1.0, 2.2)
        x = int(cx + dist * cos_a + wobble * perp_x)
        y = int(cy + dist * sin_a + wobble * perp_y)
        if not (0 <= x < grid.width and 0 <= y < grid.height):
            break
        cur = (x, y)
        if prev is not None:
            _draw_segment(grid, prev, cur, level, width=1 if level.value > 1 else 2)
        else:
            _set_road(grid, x, y, level)
        prev = cur


def _draw_cross(grid: Grid, cx: int, cy: int, half: int, level: RoadLevel) -> None:
    for d in range(-half, half + 1):
        _set_road(grid, cx + d, cy, level)
        _set_road(grid, cx, cy + d, level)


def _place_roundabouts(grid: Grid, cx: int, cy: int, max_r: int, rng: Rng) -> None:
    radii = (0.22, 0.38, 0.54)
    for ring_i, pct in enumerate(radii):
        r = int(max_r * pct)
        count = 6 + ring_i * 2
        for i in range(count):
            angle = 2.0 * math.pi * i / count + rng.number(-0.15, 0.15)
            x = int(cx + r * math.cos(angle))
            y = int(cy + r * math.sin(angle))
            _carve_roundabout(grid, x, y, radius=2 if ring_i == 0 else 1)


def _carve_roundabout(grid: Grid, cx: int, cy: int, *, radius: int) -> None:
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius + 1:
                _set_road(grid, cx + dx, cy + dy, RoadLevel.MAIN_AVENUE)


def _connect_district_hubs(grid: Grid, cx: int, cy: int, max_r: int, rng: Rng) -> None:
    """Curved boulevards between quadrant hubs (Egregoria-style connectors)."""
    hubs = [
        (cx - int(max_r * 0.42), cy - int(max_r * 0.35)),
        (cx + int(max_r * 0.38), cy - int(max_r * 0.30)),
        (cx - int(max_r * 0.35), cy + int(max_r * 0.40)),
        (cx + int(max_r * 0.45), cy + int(max_r * 0.38)),
    ]
    for i, hub in enumerate(hubs):
        if not (0 <= hub[0] < grid.width and 0 <= hub[1] < grid.height):
            continue
        target = hubs[(i + 2) % len(hubs)]
        elbow = (
            int((hub[0] + target[0]) / 2 + rng.integer(-6, 6)),
            int((hub[1] + target[1]) / 2 + rng.integer(-6, 6)),
        )
        _draw_curved(grid, hub, elbow, target, RoadLevel.DISTRICT_ROAD)


def _draw_curved(
    grid: Grid,
    start: tuple[int, int],
    elbow: tuple[int, int],
    end: tuple[int, int],
    level: RoadLevel,
) -> None:
    _draw_segment(grid, start, elbow, level, width=1)
    _draw_segment(grid, elbow, end, level, width=1)


def _fill_district_grid(grid: Grid, cx: int, cy: int, rng: Rng) -> None:
    """Light internal grid — irregular spacing so blocks aren't uniform squares."""
    spacing = 14
    offset = rng.integer(3, 8)
    for y in range(offset, grid.height, spacing):
        if abs(y - cy) < 4:
            continue
        for x in range(grid.width):
            _set_road(grid, x, y, RoadLevel.DISTRICT_ROAD, allow_upgrade=False)
    for x in range(offset + rng.integer(0, 5), grid.width, spacing):
        if abs(x - cx) < 4:
            continue
        for y in range(grid.height):
            _set_road(grid, x, y, RoadLevel.DISTRICT_ROAD, allow_upgrade=False)


def _lay_local_streets(grid: Grid) -> None:
    """Residential access roads inside blocks."""
    from .road_generator import BLOCK_SIZE

    half = BLOCK_SIZE // 2
    for y in range(half, grid.height, BLOCK_SIZE):
        for x in range(grid.width):
            tile = grid.get(x, y)
            if tile is None or tile.type in (TileType.WATER, TileType.BUILDING):
                continue
            if tile.road_level == 0:
                _set_road(grid, x, y, RoadLevel.LOCAL_STREET)
    for x in range(half, grid.width, BLOCK_SIZE):
        for y in range(grid.height):
            tile = grid.get(x, y)
            if tile is None or tile.type in (TileType.WATER, TileType.BUILDING):
                continue
            if tile.road_level == 0:
                _set_road(grid, x, y, RoadLevel.LOCAL_STREET)


def _draw_segment(
    grid: Grid,
    a: tuple[int, int],
    b: tuple[int, int],
    level: RoadLevel,
    *,
    width: int = 1,
) -> None:
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        for ox in range(-width // 2, width // 2 + 1):
            for oy in range(-width // 2, width // 2 + 1):
                _set_road(grid, x + ox, y + oy, level)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


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
