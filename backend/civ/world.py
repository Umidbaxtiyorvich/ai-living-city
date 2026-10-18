"""
The land.

A tile grid generated from layered value noise: lakes and a coastline where
the land is low, rock on the heights, forest where it is wet, fertile meadows
near water. Resources live on the tiles themselves — wood in forests, stone in
rock, berries on bushes, fish along the shore — and are depleted by the people
who gather them and slowly regrow.

Footfall is tracked per tile: where people walk often the grass wears into a
path, and paths are cheaper to walk on, so roads emerge from habit rather than
from planning.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from enum import IntEnum


class Terrain(IntEnum):
    WATER = 0
    SAND = 1
    GRASS = 2
    FOREST = 3
    ROCK = 4
    FERTILE = 5
    FIELD = 6
    PATH = 7
    BUILT = 8


#: Single-character codes streamed to the client.
TERRAIN_CODE = "wsgfrFpPb"

WALKABLE = frozenset(
    {Terrain.SAND, Terrain.GRASS, Terrain.FOREST, Terrain.FERTILE, Terrain.FIELD, Terrain.PATH, Terrain.BUILT}
)
#: Land a building may stand on (forest is cleared first, yielding wood).
BUILDABLE = frozenset({Terrain.SAND, Terrain.GRASS, Terrain.FERTILE, Terrain.PATH, Terrain.FOREST})

#: Movement cost per tile; paths make habitual routes cheaper.
STEP_COST = {
    Terrain.SAND: 1.2,
    Terrain.GRASS: 1.0,
    Terrain.FOREST: 1.8,
    Terrain.FERTILE: 1.0,
    Terrain.FIELD: 1.3,
    Terrain.PATH: 0.55,
    Terrain.BUILT: 0.8,
}

#: Footfall at which grass wears into a path.
PATH_THRESHOLD = 60.0

MAX_WOOD = 30.0
MAX_STONE = 80.0
MAX_BERRIES = 12.0


def _value_noise(width: int, height: int, rng: random.Random, scale: float) -> list[float]:
    """Smooth noise in 0..1 by bilinear interpolation of a coarse random lattice."""
    cells_x = max(2, int(width / scale) + 2)
    cells_y = max(2, int(height / scale) + 2)
    lattice = [[rng.random() for _ in range(cells_x)] for _ in range(cells_y)]
    out: list[float] = []
    for y in range(height):
        fy = y / scale
        y0 = int(fy)
        ty = fy - y0
        ty = ty * ty * (3 - 2 * ty)
        for x in range(width):
            fx = x / scale
            x0 = int(fx)
            tx = fx - x0
            tx = tx * tx * (3 - 2 * tx)
            a = lattice[y0][x0]
            b = lattice[y0][x0 + 1]
            c = lattice[y0 + 1][x0]
            d = lattice[y0 + 1][x0 + 1]
            top = a + (b - a) * tx
            bottom = c + (d - c) * tx
            out.append(top + (bottom - top) * ty)
    return out


def _layered(width: int, height: int, rng: random.Random, scales: tuple[float, ...]) -> list[float]:
    total = [0.0] * (width * height)
    weight_sum = 0.0
    weight = 1.0
    for scale in scales:
        layer = _value_noise(width, height, rng, scale)
        for i, value in enumerate(layer):
            total[i] += value * weight
        weight_sum += weight
        weight *= 0.5
    return [value / weight_sum for value in total]


@dataclass
class World:
    width: int
    height: int
    terrain: list[int]
    wood: list[float]
    stone: list[float]
    berries: list[float]
    footfall: list[float] = field(default_factory=list)
    #: Tile indices changed since the client last received them.
    dirty: set[int] = field(default_factory=set)
    version: int = 1

    # -- generation --------------------------------------------------------

    @classmethod
    def generate(cls, size: int, seed: int) -> "World":
        rng = random.Random(seed)
        width = height = size
        elevation = _layered(width, height, rng, (size / 2.2, size / 5.0, size / 11.0))
        moisture = _layered(width, height, rng, (size / 3.0, size / 8.0))

        terrain: list[int] = []
        wood: list[float] = []
        stone: list[float] = []
        berries: list[float] = []
        cx, cy = width / 2, height / 2
        for y in range(height):
            for x in range(width):
                i = y * width + x
                # Push the edges down so the world is an island in a sea.
                edge = math.hypot((x - cx) / cx, (y - cy) / cy)
                e = elevation[i] - max(0.0, edge - 0.72) * 0.9
                m = moisture[i]
                if e < 0.36:
                    t = Terrain.WATER
                elif e < 0.39:
                    t = Terrain.SAND
                elif e > 0.70:
                    t = Terrain.ROCK
                elif m > 0.56:
                    t = Terrain.FOREST
                elif m > 0.47:
                    t = Terrain.FERTILE
                else:
                    t = Terrain.GRASS
                terrain.append(int(t))
                wood.append(MAX_WOOD * (0.6 + rng.random() * 0.4) if t is Terrain.FOREST else 0.0)
                stone.append(MAX_STONE if t is Terrain.ROCK else 0.0)
                bush = t in (Terrain.GRASS, Terrain.FERTILE) and rng.random() < 0.05
                berries.append(MAX_BERRIES * rng.random() if bush else 0.0)

        # Scattered outcrops, so no part of the land is without stone for long.
        for _ in range(max(6, size * size // 450)):
            ox, oy = rng.randrange(3, width - 3), rng.randrange(3, height - 3)
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    i = (oy + dy) * width + ox + dx
                    if terrain[i] in (Terrain.GRASS, Terrain.FERTILE, Terrain.SAND) and rng.random() < 0.7:
                        terrain[i] = int(Terrain.ROCK)
                        stone[i] = MAX_STONE * 0.5
                        berries[i] = 0.0

        world = cls(width, height, terrain, wood, stone, berries, [0.0] * (width * height))
        return world

    # -- queries -----------------------------------------------------------

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def at(self, x: int, y: int) -> Terrain:
        return Terrain(self.terrain[y * self.width + x])

    def set(self, x: int, y: int, terrain: Terrain) -> None:
        i = y * self.width + x
        if self.terrain[i] != terrain:
            self.terrain[i] = int(terrain)
            self.dirty.add(i)

    def walkable(self, x: int, y: int) -> bool:
        return self.inside(x, y) and Terrain(self.terrain[y * self.width + x]) in WALKABLE

    def near_water(self, x: int, y: int, radius: int = 1) -> bool:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if self.inside(nx, ny) and self.terrain[ny * self.width + nx] == Terrain.WATER:
                    return True
        return False

    def nearest(
        self,
        x: float,
        y: float,
        predicate,
        radius: int = 18,
        skip: set[int] | None = None,
    ) -> tuple[int, int] | None:
        """Nearest tile within `radius` satisfying `predicate(index)`, by ring search."""
        ox, oy = int(round(x)), int(round(y))
        for r in range(radius + 1):
            best: tuple[float, int, int] | None = None
            for dy in range(-r, r + 1):
                for dx in (-r, r) if abs(dy) != r else range(-r, r + 1):
                    nx, ny = ox + dx, oy + dy
                    if not self.inside(nx, ny):
                        continue
                    i = ny * self.width + nx
                    if skip and i in skip:
                        continue
                    if predicate(i):
                        d = dx * dx + dy * dy
                        if best is None or d < best[0]:
                            best = (d, nx, ny)
            if best is not None:
                return best[1], best[2]
        return None

    # -- change ------------------------------------------------------------

    def walk_over(self, x: int, y: int) -> None:
        i = y * self.width + x
        self.footfall[i] += 1.0
        t = self.terrain[i]
        if (
            self.footfall[i] >= PATH_THRESHOLD
            and t in (Terrain.GRASS, Terrain.FERTILE, Terrain.SAND)
        ):
            self.terrain[i] = int(Terrain.PATH)
            self.dirty.add(i)

    def take_wood(self, i: int, amount: float) -> float:
        got = min(amount, self.wood[i])
        self.wood[i] -= got
        if self.wood[i] <= 0.5 and self.terrain[i] == Terrain.FOREST:
            self.wood[i] = 0.0
            self.terrain[i] = int(Terrain.GRASS)
            self.dirty.add(i)
        return got

    def take_stone(self, i: int, amount: float) -> float:
        got = min(amount, self.stone[i])
        self.stone[i] -= got
        if self.stone[i] <= 0.5 and self.terrain[i] == Terrain.ROCK:
            self.stone[i] = 0.0
            self.terrain[i] = int(Terrain.SAND)
            self.dirty.add(i)
        return got

    def take_berries(self, i: int, amount: float) -> float:
        got = min(amount, self.berries[i])
        self.berries[i] -= got
        if got > 0:
            self.dirty.add(i)
        return got

    def regrow(self, rng: random.Random) -> None:
        """Daily: bushes refill, forests spread a little, paths fade if unused."""
        w = self.width
        for i, value in enumerate(self.berries):
            if value > 0 or (self.terrain[i] in (Terrain.GRASS, Terrain.FERTILE) and rng.random() < 0.0008):
                before = value
                self.berries[i] = min(MAX_BERRIES, value + 0.9)
                if before == 0:
                    self.dirty.add(i)
        for i in range(len(self.terrain)):
            t = self.terrain[i]
            if t == Terrain.FOREST and self.wood[i] < MAX_WOOD:
                self.wood[i] = min(MAX_WOOD, self.wood[i] + 0.25)
            elif t == Terrain.GRASS and rng.random() < 0.004:
                x, y = i % w, i // w
                neighbours = sum(
                    1
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if self.inside(x + dx, y + dy) and self.terrain[(y + dy) * w + x + dx] == Terrain.FOREST
                )
                if neighbours >= 2 and self.footfall[i] < 5:
                    self.terrain[i] = int(Terrain.FOREST)
                    self.wood[i] = 4.0
                    self.dirty.add(i)
            if self.footfall[i] > 0:
                self.footfall[i] *= 0.97
                if t == Terrain.PATH and self.footfall[i] < PATH_THRESHOLD * 0.3:
                    self.terrain[i] = int(Terrain.GRASS)
                    self.dirty.add(i)

    # -- routing -----------------------------------------------------------

    def route(self, start: tuple[int, int], goal: tuple[int, int], limit: int = 6000) -> list[tuple[int, int]]:
        """A* over walkable tiles. Returns the tiles after `start`, or [] if unreachable."""
        if start == goal:
            return []
        if not self.walkable(*goal):
            return []
        w = self.width
        open_heap: list[tuple[float, int, int, int]] = [(0.0, 0, start[0], start[1])]
        came: dict[int, int] = {}
        cost: dict[int, float] = {start[1] * w + start[0]: 0.0}
        goal_i = goal[1] * w + goal[0]
        counter = 0
        expanded = 0
        while open_heap and expanded < limit:
            _, _, x, y = heapq.heappop(open_heap)
            i = y * w + x
            if i == goal_i:
                path: list[tuple[int, int]] = []
                while i in came:
                    path.append((i % w, i // w))
                    i = came[i]
                path.reverse()
                return path
            expanded += 1
            base = cost[i]
            for dx, dy, diag in (
                (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, 1.41), (1, -1, 1.41), (-1, 1, 1.41), (-1, -1, 1.41),
            ):
                nx, ny = x + dx, y + dy
                if not self.inside(nx, ny):
                    continue
                ni = ny * w + nx
                t = self.terrain[ni]
                if t not in WALKABLE:
                    continue
                if diag > 1 and (
                    self.terrain[y * w + nx] not in WALKABLE or self.terrain[ny * w + x] not in WALKABLE
                ):
                    continue
                new_cost = base + STEP_COST.get(Terrain(t), 1.0) * diag
                if new_cost < cost.get(ni, 1e18):
                    cost[ni] = new_cost
                    came[ni] = i
                    counter += 1
                    estimate = new_cost + math.hypot(goal[0] - nx, goal[1] - ny) * 0.55
                    heapq.heappush(open_heap, (estimate, counter, nx, ny))
        return []

    # -- payloads ----------------------------------------------------------

    def terrain_string(self) -> str:
        return "".join(TERRAIN_CODE[t] for t in self.terrain)

    def resource_payload(self) -> dict:
        """Trees, rocks and bushes the renderer instances, as flat index lists."""
        trees = [i for i, t in enumerate(self.terrain) if t == Terrain.FOREST and self.wood[i] > 0]
        tree_size = [round(min(1.0, self.wood[i] / MAX_WOOD), 2) for i in trees]
        bushes = [i for i, v in enumerate(self.berries) if v > 1.0]
        return {"trees": trees, "tree_size": tree_size, "bushes": bushes}

    def take_changes(self) -> list[list]:
        changes = [[i, TERRAIN_CODE[self.terrain[i]]] for i in sorted(self.dirty)]
        self.dirty.clear()
        if changes:
            self.version += 1
        return changes

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "terrain": self.terrain,
            "wood": [round(v, 2) for v in self.wood],
            "stone": [round(v, 2) for v in self.stone],
            "berries": [round(v, 2) for v in self.berries],
            "footfall": [round(v, 1) for v in self.footfall],
        }

    @classmethod
    def restore(cls, data: dict) -> "World":
        return cls(
            width=data["width"],
            height=data["height"],
            terrain=list(data["terrain"]),
            wood=list(data["wood"]),
            stone=list(data["stone"]),
            berries=list(data["berries"]),
            footfall=list(data.get("footfall") or [0.0] * (data["width"] * data["height"])),
        )
