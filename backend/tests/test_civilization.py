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
    assert sum(1 for p in civ.living if not p.player) == 10
    assert civ.player is not None and civ.player.name == "Umid"
    assert civ.animals, "the land has wildlife"
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


def test_the_player_can_build_anything_and_start_a_family():
    civ = Civilization(seed=7)
    civ.genesis()
    me = civ.player
    s = civ.settlements[me.settlement_id]
    # Creative build: any building, ready at once, and it becomes home.
    result = civ.player_build("villa", s.x + 6, s.y + 6, creative=True)
    if not result["ok"]:
        result = civ.player_build("villa", s.x - 7, s.y - 7, creative=True)
    assert result["ok"], result
    assert me.home_id == result["id"]
    # Courtship: talk until she agrees, then marry.
    bride = next(p for p in civ.living if p.gender == "female" and p.adult)
    bride.x, bride.y = me.x, me.y
    for _ in range(6):
        civ.player_talk(bride.id)
    reply = civ.player_propose(bride.id)
    assert me.partner_id == bride.id, reply


def test_live_movement_is_continuous():
    civ = Civilization(seed=7)
    civ.genesis()
    civ.auto_move = False
    me = civ.player
    start = (me.x, me.y)
    civ.player_goto(me.x + 6, me.y)
    civ.move(3.0)  # three simulated seconds
    moved = ((me.x - start[0]) ** 2 + (me.y - start[1]) ** 2) ** 0.5
    assert 0.5 < moved < 1.5, moved
    horse = next(a for a in civ.animals.values())
    before = (horse.x, horse.y)
    for _ in range(600):
        civ.move(1.0)
    assert (horse.x, horse.y) != before
