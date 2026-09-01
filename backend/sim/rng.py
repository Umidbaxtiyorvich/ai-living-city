"""
Seeded randomness.

The whole city derives from a single world seed. Each subsystem draws from its
own *named* stream rather than a shared generator, so adding a new subsystem
later cannot shift the numbers every existing one receives. That property is
what makes a bug reproducible from a seed alone.
"""

from __future__ import annotations

import random
from typing import Sequence, TypeVar

T = TypeVar("T")


class Rng:
    """A single named random stream."""

    __slots__ = ("_random", "name")

    def __init__(self, seed: int, name: str) -> None:
        self.name = name
        # Hashing seed and name together keeps streams independent.
        self._random = random.Random(f"{seed}:{name}")

    def chance(self, probability: float) -> bool:
        return self._random.random() < probability

    def integer(self, low: int, high: int) -> int:
        """Inclusive on both ends."""
        return self._random.randint(low, high)

    def number(self, low: float, high: float) -> float:
        return self._random.uniform(low, high)

    def pick(self, options: Sequence[T]) -> T:
        if not options:
            raise ValueError(f"stream {self.name!r}: cannot pick from an empty sequence")
        return options[self._random.randrange(len(options))]

    def sample(self, options: Sequence[T], count: int) -> list[T]:
        """Up to `count` distinct items; fewer if the sequence is shorter."""
        return self._random.sample(list(options), min(count, len(options)))

    def weighted(self, options: Sequence[tuple[T, float]]) -> T:
        """Picks by relative weight. Zero-weight entries are never chosen."""
        total = sum(weight for _, weight in options if weight > 0)
        if total <= 0:
            raise ValueError(f"stream {self.name!r}: all weights are zero")

        roll = self._random.random() * total
        for value, weight in options:
            if weight <= 0:
                continue
            roll -= weight
            if roll <= 0:
                return value
        return options[-1][0]

    def shuffled(self, options: Sequence[T]) -> list[T]:
        items = list(options)
        self._random.shuffle(items)
        return items

    def gaussian(self, mean: float, deviation: float) -> float:
        return self._random.gauss(mean, deviation)

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> list:
        """
        The generator's internal state, JSON-safe.

        Saving the seed alone is not enough: a reloaded city must continue the
        same sequence it was drawing from, otherwise a save/restart silently
        changes the future and no long run is reproducible.
        """
        version, internal, gauss_next = self._random.getstate()
        return [version, list(internal), gauss_next]

    def restore_state(self, data: list) -> None:
        version, internal, gauss_next = data
        self._random.setstate((int(version), tuple(int(item) for item in internal), gauss_next))


class RngRegistry:
    """Hands out cached named streams for one world seed."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._streams: dict[str, Rng] = {}

    def stream(self, name: str) -> Rng:
        stream = self._streams.get(name)
        if stream is None:
            stream = Rng(self.seed, name)
            self._streams[name] = stream
        return stream

    def derived(self, name: str, key: str | int) -> Rng:
        """
        A throwaway stream tied to a specific entity.

        Used where the result must depend only on the entity, not on how many
        times the subsystem has been called before — agent appearance, for
        example, must survive a reload.
        """
        return Rng(self.seed, f"{name}:{key}")

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "seed": self.seed,
            "streams": {name: stream.snapshot() for name, stream in self._streams.items()},
        }

    @classmethod
    def restore(cls, data: dict) -> "RngRegistry":
        registry = cls(int(data["seed"]))
        for name, state in data.get("streams", {}).items():
            registry.stream(name).restore_state(state)
        return registry
