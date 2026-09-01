"""
Grid pathfinding.

A* over walkable tiles with a Manhattan heuristic, which is admissible because
movement is 4-directional. Paths are cached: agents repeat the same home→work
trip every day, and recomputing it for a thousand agents each morning is the
single most expensive thing the simulation could do.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from ..world.tiles import WALK_COST, WALKABLE, Grid, TileType

Point = tuple[int, int]

#: Refuse to explore forever on an impossible request.
MAX_EXPANSIONS = 20_000


@dataclass(slots=True)
class PathResult:
    """Outcome of one search. `tiles` excludes the start tile."""

    tiles: list[Point] = field(default_factory=list)
    cost: float = 0.0
    found: bool = False
    expansions: int = 0

    def __bool__(self) -> bool:
        return self.found


def _heuristic(a: Point, b: Point) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def find_path(
    grid: Grid,
    start: Point,
    goal: Point,
    *,
    allowed: frozenset[TileType] | None = None,
    max_expansions: int = MAX_EXPANSIONS,
) -> PathResult:
    """
    Cheapest walkable route from `start` to `goal`.

    The goal tile is allowed to be unwalkable — buildings are the usual
    destination — so it is accepted on arrival without a passability check.
    """
    if start == goal:
        return PathResult(tiles=[], cost=0.0, found=True)

    if not grid.contains(*start) or not grid.contains(*goal):
        return PathResult()

    passable = allowed if allowed is not None else None

    def walkable(x: int, y: int) -> bool:
        tile = grid.get(x, y)
        if tile is None:
            return False
        if (x, y) == goal:
            return True
        if passable is not None:
            return tile.type in passable
        return tile.type in WALKABLE

    def step_cost(x: int, y: int) -> float:
        tile = grid.get(x, y)
        if tile is None:
            return 1.0
        # An unwalkable goal (a building entrance) costs a plain step.
        return WALK_COST.get(tile.type, 1.0)

    open_heap: list[tuple[float, Point]] = [(_heuristic(start, goal), start)]
    came_from: dict[Point, Point] = {}
    best_cost: dict[Point, float] = {start: 0.0}
    closed: set[Point] = set()
    expansions = 0

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct(came_from, start, goal, best_cost[goal], expansions)

        closed.add(current)
        expansions += 1
        if expansions > max_expansions:
            break

        cx, cy = current
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            neighbour = (nx, ny)
            if neighbour in closed or not walkable(nx, ny):
                continue

            tentative = best_cost[current] + step_cost(nx, ny)
            if tentative < best_cost.get(neighbour, float("inf")):
                best_cost[neighbour] = tentative
                came_from[neighbour] = current
                heapq.heappush(open_heap, (tentative + _heuristic(neighbour, goal), neighbour))

    return PathResult(expansions=expansions)


def _reconstruct(
    came_from: dict[Point, Point], start: Point, goal: Point, cost: float, expansions: int
) -> PathResult:
    tiles: list[Point] = []
    node = goal
    while node != start:
        tiles.append(node)
        node = came_from[node]
    tiles.reverse()
    return PathResult(tiles=tiles, cost=cost, found=True, expansions=expansions)


class PathCache:
    """
    Bounded cache of routes, keyed by endpoints.

    Invalidated wholesale whenever roads or buildings change, because a new road
    can make almost any cached path suboptimal and tracking which ones is not
    worth the bookkeeping.
    """

    def __init__(self, capacity: int = 4096) -> None:
        self.capacity = capacity
        self._entries: dict[tuple[Point, Point], PathResult] = {}
        self.hits = 0
        self.misses = 0

    def route(self, grid: Grid, start: Point, goal: Point) -> PathResult:
        key = (start, goal)
        cached = self._entries.get(key)
        if cached is not None:
            self.hits += 1
            return cached

        self.misses += 1
        result = find_path(grid, start, goal)

        if len(self._entries) >= self.capacity:
            # Plain eviction: the access pattern is dominated by daily commutes,
            # which are re-added immediately, so LRU bookkeeping earns little.
            self._entries.clear()
        self._entries[key] = result
        return result

    def invalidate(self) -> None:
        self._entries.clear()

    @property
    def stats(self) -> dict[str, int | float]:
        total = self.hits + self.misses
        return {
            "size": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }
