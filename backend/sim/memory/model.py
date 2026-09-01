"""
Memory.

Agents remember what happened to them, and the president additionally remembers
what the city did (specification section 24). Memory is bounded — an unbounded
log across a thousand agents over simulated decades would exhaust RAM — so each
category keeps only its most important entries.

Importance, not recency, decides what survives: a wedding should outlive a
thousand commutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MemoryKind(StrEnum):
    """Categories from specification section 24."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EMOTIONAL = "emotional"
    SOCIAL = "social"
    FAMILY = "family"
    WORK = "work"
    CITY = "city"
    # President-only.
    GOVERNMENT = "government"
    POLICY = "policy"
    DEVELOPMENT = "development"
    CITIZEN = "citizen"
    CRISIS = "crisis"


#: How many entries each category retains.
CAPACITY: dict[MemoryKind, int] = {
    MemoryKind.SHORT_TERM: 20,
    MemoryKind.LONG_TERM: 60,
    MemoryKind.EMOTIONAL: 30,
    MemoryKind.SOCIAL: 40,
    MemoryKind.FAMILY: 40,
    MemoryKind.WORK: 30,
    MemoryKind.CITY: 30,
    MemoryKind.GOVERNMENT: 120,
    MemoryKind.POLICY: 80,
    MemoryKind.DEVELOPMENT: 200,
    MemoryKind.CITIZEN: 120,
    MemoryKind.CRISIS: 80,
}

#: Entries at or above this importance are promoted to long-term memory.
LONG_TERM_THRESHOLD = 0.6


@dataclass(slots=True)
class MemoryEntry:
    tick: int
    kind: MemoryKind
    text: str
    #: 0..1. Drives retention and, for the president, how much a past outcome
    #: influences the next similar decision.
    importance: float = 0.3
    #: Free-form detail: agent ids, building ids, amounts.
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "tick": self.tick,
            "kind": self.kind,
            "text": self.text,
            "importance": round(self.importance, 3),
            "data": self.data,
        }


class Memory:
    """Per-category bounded stores."""

    def __init__(self) -> None:
        self._stores: dict[MemoryKind, list[MemoryEntry]] = {}

    def record(
        self,
        tick: int,
        kind: MemoryKind,
        text: str,
        importance: float = 0.3,
        **data,
    ) -> MemoryEntry:
        entry = MemoryEntry(tick=tick, kind=kind, text=text, importance=importance, data=data)
        self._append(kind, entry)

        # Anything significant is also filed as long-term, so it survives the
        # rapid churn of the short-term store.
        if importance >= LONG_TERM_THRESHOLD and kind is not MemoryKind.LONG_TERM:
            self._append(MemoryKind.LONG_TERM, entry)

        return entry

    def _append(self, kind: MemoryKind, entry: MemoryEntry) -> None:
        store = self._stores.setdefault(kind, [])
        store.append(entry)

        limit = CAPACITY.get(kind, 40)
        if len(store) > limit:
            # Drop the least important; ties break toward the older entry.
            store.sort(key=lambda item: (item.importance, item.tick))
            del store[: len(store) - limit]
            store.sort(key=lambda item: item.tick)

    # -- reading -----------------------------------------------------------

    def of(self, kind: MemoryKind) -> list[MemoryEntry]:
        return list(self._stores.get(kind, ()))

    def recent(self, kind: MemoryKind, count: int = 5) -> list[MemoryEntry]:
        return self.of(kind)[-count:]

    def recent_all(self, count: int = 5) -> list[MemoryEntry]:
        """Most recent entries across every category, newest last."""
        everything = [entry for store in self._stores.values() for entry in store]
        everything.sort(key=lambda item: item.tick)
        return everything[-count:]

    def search(self, needle: str, kind: MemoryKind | None = None) -> list[MemoryEntry]:
        needle = needle.lower()
        pools = [kind] if kind is not None else list(self._stores)
        found: list[MemoryEntry] = []
        for pool in pools:
            found.extend(
                entry for entry in self._stores.get(pool, ()) if needle in entry.text.lower()
            )
        found.sort(key=lambda item: item.tick)
        return found

    @property
    def size(self) -> int:
        return sum(len(store) for store in self._stores.values())

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            kind: [entry.as_dict() for entry in store] for kind, store in self._stores.items()
        }

    @classmethod
    def restore(cls, data: dict) -> "Memory":
        memory = cls()
        for kind, entries in (data or {}).items():
            memory._stores[MemoryKind(kind)] = [
                MemoryEntry(
                    tick=item["tick"],
                    kind=MemoryKind(item["kind"]),
                    text=item["text"],
                    importance=item.get("importance", 0.3),
                    data=item.get("data", {}),
                )
                for item in entries
            ]
        return memory
