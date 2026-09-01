"""
End-to-end simulation tests.

These are the tests that answer the question the unit tests cannot: does the
city actually live? They found a city, run it for simulated months or years, and
assert that the loop produced the behaviour the specification promises —
citizens working and housed, the president noticing problems and fixing them,
the population turning over across generations.
"""

from __future__ import annotations

import pytest

from sim.agents.models import Activity, DetailLevel
from sim.buildings.catalog import BuildingCategory
from sim.buildings.models import BuildingStatus
from sim.clock import MINUTES_PER_DAY
from sim.economy.model import MAX_TAX_RATE
from sim.engine import Engine
from sim.events.model import EventType
from sim.president.models import DecisionStatus
from sim.state import SimulationConfig, WorldState

#: A smaller map keeps these tests fast; the logic is size-independent.
TEST_CONFIG = SimulationConfig(seed=7, map_size=60, founding_population=30)


def build_city(config: SimulationConfig | None = None) -> Engine:
    state = WorldState.create(config or TEST_CONFIG)
    engine = Engine(state)
    engine.found_city()
    return engine


def run_days(engine: Engine, days: int) -> None:
    engine.run(days * MINUTES_PER_DAY)


# -- founding --------------------------------------------------------------


def test_founding_produces_a_working_city():
    engine = build_city()
    state = engine.state

    assert state.president is not None
    assert state.population == 30
    assert len(state.buildings) > 10

    # The palace and city hall must exist; the president needs somewhere to be.
    types = {building.type for building in state.buildings.values()}
    assert "presidential_palace" in {t.value for t in types}
    assert "city_hall" in {t.value for t in types}

    # Founding buildings open immediately.
    assert all(
        building.status is BuildingStatus.OPEN for building in state.buildings.values()
    )


def test_founding_houses_and_employs_citizens():
    engine = build_city()
    state = engine.state

    housed = sum(1 for agent in state.living_agents if agent.home_id is not None)
    employed = sum(1 for agent in state.living_agents if agent.employed)

    # Nine houses hold 36, so everyone should have a bed on day one.
    assert housed == state.population
    # Not everyone can be employed — there are only so many founding jobs.
    assert employed > 0


def test_founding_is_deterministic():
    first = build_city().state
    second = build_city().state

    assert first.president.name == second.president.name
    assert [a.name for a in first.living_agents] == [a.name for a in second.living_agents]
    assert len(first.buildings) == len(second.buildings)


def test_two_seeds_produce_different_cities():
    a = build_city(SimulationConfig(seed=1, map_size=60, founding_population=20)).state
    b = build_city(SimulationConfig(seed=2, map_size=60, founding_population=20)).state

    assert [agent.name for agent in a.living_agents] != [
        agent.name for agent in b.living_agents
    ]


# -- the clock keeps running -----------------------------------------------


def test_a_simulated_day_advances_the_calendar():
    engine = build_city()
    run_days(engine, 1)

    assert engine.state.day == 1
    assert engine.state.ticks_processed == MINUTES_PER_DAY


def test_agents_change_activity_over_a_day():
    """
    A day must contain more than one kind of behaviour.

    If every agent sits in one state all day, the schedule is not working even
    though the clock is.
    """
    engine = build_city()
    state = engine.state
    state.camera_focus = (state.grid.width / 2, state.grid.height / 2)

    seen: set[Activity] = set()
    for _ in range(MINUTES_PER_DAY):
        engine.tick()
        seen.update(agent.activity for agent in state.living_agents)

    assert len(seen) >= 3
    assert Activity.SLEEPING in seen


def test_agents_actually_move():
    engine = build_city()
    state = engine.state
    state.camera_focus = (state.grid.width / 2, state.grid.height / 2)

    engine.tick()
    before = {agent.id: agent.position for agent in state.living_agents}

    run_days(engine, 1)
    after = {agent.id: agent.position for agent in state.living_agents}

    moved = sum(1 for agent_id, position in after.items() if before.get(agent_id) != position)
    assert moved > 0


# -- the president governs -------------------------------------------------


def test_president_makes_decisions():
    engine = build_city()
    run_days(engine, 20)

    president = engine.state.president
    assert president.decisions, "the president never decided anything"

    # Decisions must be recorded as events so the dashboard can show them.
    assert engine.state.events.of_type(EventType.PRESIDENT_DECISION)


def test_president_builds_in_response_to_growth():
    """
    The specification's headline scenario: population grows, housing runs short,
    the president builds.
    """
    engine = build_city()
    state = engine.state

    # More citizens than the founding houses can hold.
    for _ in range(40):
        state.spawn_citizen(age_years=30.0)
    state.refresh_stats()
    assert state.stats.housing_shortage > 0

    run_days(engine, 30)

    residential = [
        building
        for building in state.buildings.values()
        if building.spec.category is BuildingCategory.RESIDENTIAL
    ]
    # Nine founding houses; the president must have ordered more.
    assert len(residential) > 9
    assert state.events.of_type(EventType.BUILDING_STARTED)


def test_construction_takes_time_and_completes():
    engine = build_city()
    state = engine.state

    for _ in range(40):
        state.spawn_citizen(age_years=30.0)

    run_days(engine, 10)
    started = state.events.of_type(EventType.BUILDING_STARTED)
    assert started, "no construction was ever started"

    # Nothing should complete instantly after founding.
    run_days(engine, 32)
    assert state.events.of_type(EventType.BUILDING_COMPLETE)


def test_president_approval_reflects_a_failing_city():
    """A city that cannot house or employ anyone must cost the president."""
    engine = build_city()
    state = engine.state

    for _ in range(70):
        state.spawn_citizen(age_years=30.0)
    # Remove the treasury so nothing can be fixed.
    state.economy.budget = 0.0

    run_days(engine, 25)
    assert state.president.approval_rating < 60.0


def test_president_defers_when_it_cannot_pay():
    engine = build_city()
    state = engine.state

    for _ in range(40):
        state.spawn_citizen(age_years=30.0)
    state.economy.budget = 0.0
    # Tax is already at the ceiling, so the one free lever is gone and every
    # remaining answer costs money the city does not have.
    state.economy.taxes.income_tax = MAX_TAX_RATE

    run_days(engine, 10)

    statuses = {decision.status for decision in state.president.decisions}
    assert DecisionStatus.DEFERRED in statuses


def test_president_reviews_its_own_decisions():
    engine = build_city()
    state = engine.state

    for _ in range(50):
        state.spawn_citizen(age_years=30.0)

    run_days(engine, 45)

    reviewed = [d for d in state.president.decisions if d.reviewed_tick is not None]
    assert reviewed, "no decision was ever reviewed"
    assert any(d.worked is not None for d in reviewed)


# -- employment and housing ------------------------------------------------


def test_new_buildings_get_staffed():
    engine = build_city()
    state = engine.state

    for _ in range(40):
        state.spawn_citizen(age_years=30.0)

    run_days(engine, 45)

    opened_later = [
        building
        for building in state.buildings.values()
        if building.opened_tick is not None and building.total_job_slots > 0
    ]
    if opened_later:
        assert any(building.total_staff > 0 for building in opened_later)


def test_unemployment_falls_as_the_city_develops():
    engine = build_city()
    state = engine.state

    for _ in range(40):
        state.spawn_citizen(age_years=30.0)
    state.refresh_stats()
    before = state.stats.unemployment_rate

    run_days(engine, 60)
    state.refresh_stats()

    assert state.stats.unemployment_rate <= before


def test_homeless_citizens_eventually_get_housed():
    engine = build_city()
    state = engine.state

    for _ in range(30):
        state.spawn_citizen(age_years=30.0)
    state.refresh_stats()
    assert state.stats.homeless > 0

    run_days(engine, 50)
    state.refresh_stats()

    # Not necessarily zero, but the city must have made progress.
    assert state.stats.homeless < 30


# -- economy ---------------------------------------------------------------


def test_wages_and_taxes_move_money():
    engine = build_city()
    state = engine.state
    run_days(engine, 31)

    assert state.economy.ledger, "no month was ever settled"
    entry = state.economy.last_month
    assert entry.income > 0 or entry.expenses > 0

    # Employed citizens must have been paid.
    earners = [agent for agent in state.living_agents if agent.employed]
    assert any(agent.money > 0 for agent in earners)


def test_construction_spending_is_recorded():
    engine = build_city()
    state = engine.state
    for _ in range(50):
        state.spawn_citizen(age_years=30.0)

    run_days(engine, 40)
    assert state.economy.total_construction_spend > 0


# -- population dynamics ---------------------------------------------------


def test_citizens_age():
    engine = build_city()
    state = engine.state
    before = {agent.id: agent.age_days for agent in state.living_agents}

    run_days(engine, 12)

    for agent in state.living_agents:
        if agent.id in before:
            assert agent.age_days == before[agent.id] + 12


def test_relationships_form_between_citizens():
    engine = build_city()
    state = engine.state
    # Keep everyone in full detail so encounters are registered.
    state.config.full_detail_radius = 1_000.0
    state.camera_focus = (state.grid.width / 2, state.grid.height / 2)

    run_days(engine, 20)

    with_ties = sum(1 for agent in state.living_agents if agent.relationships)
    assert with_ties > 0


@pytest.mark.slow
def test_generations_turn_over():
    """
    The long game: over simulated years the city must see births and deaths,
    and children must grow into the workforce.
    """
    engine = build_city(SimulationConfig(seed=11, map_size=60, founding_population=40))
    state = engine.state
    state.config.full_detail_radius = 1_000.0
    state.camera_focus = (state.grid.width / 2, state.grid.height / 2)

    run_days(engine, 360 * 4)

    assert state.events.of_type(EventType.WEDDING), "nobody ever married"
    assert state.events.of_type(EventType.BIRTH), "no child was ever born"

    # Somebody born during the run must exist.
    newborns = [agent for agent in state.agents.values() if agent.parent_ids]
    assert newborns


# -- performance and level of detail ---------------------------------------


def test_distant_agents_drop_to_statistical_detail():
    engine = build_city()
    state = engine.state
    state.camera_focus = (0.0, 0.0)
    state.config.full_detail_radius = 5.0
    state.config.reduced_detail_radius = 10.0

    engine.tick()

    levels = {agent.detail for agent in state.living_agents}
    assert DetailLevel.STATISTICAL in levels


def test_followed_agent_stays_in_full_detail():
    engine = build_city()
    state = engine.state
    state.camera_focus = (0.0, 0.0)
    state.config.full_detail_radius = 1.0
    state.config.reduced_detail_radius = 2.0

    target = state.living_agents[0]
    state.followed_agent_id = target.id
    engine.tick()

    assert target.detail is DetailLevel.FULL


def test_statistical_agents_still_have_plausible_needs():
    """An agent nobody watched for a simulated month must not be starving."""
    engine = build_city()
    state = engine.state
    state.camera_focus = (-500.0, -500.0)

    run_days(engine, 14)

    for agent in state.living_agents:
        if agent.detail is DetailLevel.STATISTICAL and agent.home_id is not None:
            assert agent.needs.hunger > 20.0
            assert agent.needs.energy > 20.0


def test_tick_cost_stays_reasonable():
    """
    A rough performance guard.

    Not a benchmark — it only catches a change that makes the tick pathologically
    slow, which would otherwise show up as an unplayable frontend much later.
    """
    engine = build_city()
    state = engine.state
    state.config.full_detail_radius = 1_000.0
    state.camera_focus = (state.grid.width / 2, state.grid.height / 2)

    run_days(engine, 2)
    assert state.last_tick_ms < 100.0


# -- payloads --------------------------------------------------------------


def test_payloads_are_serialisable():
    import json

    engine = build_city()
    run_days(engine, 3)
    state = engine.state

    for payload in (
        state.world_summary(),
        state.tile_payload(),
        state.building_payload(),
        state.agent_payload(),
        state.dashboard_payload(),
    ):
        json.dumps(payload)


def test_tile_payload_round_trips_to_the_full_map():
    """Run-length encoding must reproduce the grid exactly."""
    engine = build_city()
    state = engine.state
    payload = state.tile_payload()

    expanded: list[tuple[str, str]] = []
    for tile_type, district, length in payload["runs"]:
        expanded.extend([(tile_type, district)] * length)

    assert len(expanded) == state.grid.width * state.grid.height
    for index, tile in enumerate(state.grid.tiles):
        assert expanded[index] == (tile.type.value, tile.district.value)


def test_dashboard_reports_the_president_and_city():
    engine = build_city()
    run_days(engine, 35)
    payload = engine.state.dashboard_payload()

    assert payload["president"]["name"]
    assert payload["stats"]["population"] > 0
    assert payload["economy"]["budget"] is not None
    assert payload["time"]["day"] == 35
