"""Civilization mode: ten people grow a society on their own."""

from __future__ import annotations

import json

from civ.engine import Civilization
from civ.models import DAYS_PER_YEAR, TICKS_PER_DAY


def run_years(civ: Civilization, years: float) -> None:
    for _ in range(int(TICKS_PER_DAY * DAYS_PER_YEAR * years)):
        civ.step()


def test_genesis_starts_with_ten_people_and_a_fire():
    civ = Civilization(seed=3)
    civ.genesis()
    assert len(civ.living) == 10
    assert len(civ.settlements) == 1
    assert any(b.kind == "campfire" and b.complete for b in civ.buildings.values())
    assert {"fire", "shelter"} <= civ.known


def test_people_build_homes_marry_and_have_children():
    civ = Civilization(seed=7)
    civ.genesis()
    run_years(civ, 6)
    stats = civ.stats()
    assert stats["homes"] >= 2, "families should raise their own homes"
    assert stats["families"] >= 2, "people should pair up"
    assert civ.births >= 2, "the population should grow by itself"
    assert len(civ.known) > 2, "something should have been discovered"
    # Nobody's job is assigned: people chose different work.
    kinds = {entry.kind for entry in civ.chronicle}
    assert {"wedding", "birth", "discovery"} <= kinds


def test_paths_wear_where_people_walk():
    civ = Civilization(seed=7)
    civ.genesis()
    run_years(civ, 3)
    assert "P" in civ.world.terrain_string()


def test_a_saved_world_resumes():
    civ = Civilization(seed=5)
    civ.genesis()
    run_years(civ, 1)
    restored = Civilization.restore(json.loads(json.dumps(civ.snapshot())))
    assert restored.tick == civ.tick
    assert len(restored.living) == len(civ.living)
    assert len(restored.buildings) == len(civ.buildings)
    assert restored.known == civ.known
    run_years(restored, 0.5)
    assert len(restored.living) >= 1
