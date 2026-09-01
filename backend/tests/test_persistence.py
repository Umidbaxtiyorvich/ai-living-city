"""
Save/load tests.

The promise of specification section 39 is that the civilization survives a
restart. The only test that really checks that is a divergence test: save a
city, reload it, run both copies forward and require the same future. Comparing
field-by-field after a load would pass while a missed random-generator state
quietly changed everything from the next tick onwards.
"""

from __future__ import annotations

import json

from sim.clock import MINUTES_PER_DAY
from sim.engine import Engine
from sim.persistence import dump_world, load_world
from sim.state import SimulationConfig, WorldState

CONFIG = SimulationConfig(seed=11, map_size=60, founding_population=25)


def build_city() -> Engine:
    state = WorldState.create(CONFIG)
    engine = Engine(state)
    engine.found_city()
    return engine


def run_days(engine: Engine, days: int) -> None:
    engine.run(days * MINUTES_PER_DAY)


def fingerprint(state: WorldState) -> dict:
    """The figures that would differ if the world had diverged at all."""
    return {
        "tick": state.tick,
        "population": state.population,
        "buildings": len(state.buildings),
        "budget": round(state.economy.budget, 4),
        "happiness": round(state.stats.happiness, 4),
        "employed": state.stats.employed,
        "housing_shortage": state.stats.housing_shortage,
        "families": len(state.families.families),
        "events": state.events.total,
        "decisions": len(state.president.decisions) if state.president else 0,
        "map_version": state.map_version,
        # The player's own office is part of the world: standing orders and the
        # three ledgers are their work, and a save that drops them is a bug the
        # city-level figures would never reveal.
        "player": state.player.as_dict(),
        "desks": sorted(
            (agent.id, getattr(agent, "desk", "")) for agent in state.living_agents
        ),
        "positions": [
            (agent.id, round(agent.position[0], 3), round(agent.position[1], 3))
            for agent in sorted(state.living_agents, key=lambda item: item.id)[:40]
        ],
    }


def test_a_snapshot_is_json_serialisable():
    engine = build_city()
    run_days(engine, 3)

    text = json.dumps(dump_world(engine.state))
    # Round-tripping through text is what the database column actually does.
    assert json.loads(text)["version"] == 1


def test_reloading_preserves_the_city():
    engine = build_city()
    run_days(engine, 5)

    reloaded = load_world(json.loads(json.dumps(dump_world(engine.state))))

    assert fingerprint(reloaded) == fingerprint(engine.state)
    assert reloaded.president is not None
    assert reloaded.president.name == engine.state.president.name
    assert reloaded.grid.width == engine.state.grid.width
    assert reloaded.grid.free_land() == engine.state.grid.free_land()


def test_a_reloaded_city_has_the_same_future():
    """The point of the whole exercise: no divergence after a restart."""
    original = build_city()
    run_days(original, 5)

    resumed = Engine(load_world(json.loads(json.dumps(dump_world(original.state)))))

    run_days(original, 10)
    run_days(resumed, 10)

    assert fingerprint(resumed.state) == fingerprint(original.state)


def test_the_players_own_work_survives_a_reload():
    """Standing orders and ledgers are the player's work, not the city's."""
    engine = build_city()
    engine.set_player_role("prime_minister")
    engine.handle_player_command("2 ta maktab qur")
    engine.set_player_role("president")
    engine.handle_player_command("elektr hisobini excelda tayyorla")
    run_days(engine, 2)

    state = engine.state
    assert state.player.standing or state.player.tasks

    reloaded = load_world(json.loads(json.dumps(dump_world(state))))

    assert reloaded.player.as_dict() == state.player.as_dict()
    assert reloaded.player.role is state.player.role
    # The id counters must continue too, or the next order collides with an old one.
    assert reloaded.player.add_standing("x").id == state.player.add_standing("x").id


def test_agent_detail_survives_a_reload():
    engine = build_city()
    run_days(engine, 2)

    agent = next(iter(engine.state.living_agents))
    before = agent.detail_state()
    reloaded = load_world(dump_world(engine.state))
    assert reloaded.agents[agent.id].detail_state() == before
