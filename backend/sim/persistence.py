"""
Saving and reloading a whole civilization (specification section 39).

The world is one object graph, so it is saved as one document rather than as
normalized rows per entity. Two reasons:

* **Consistency.** A city half-written — buildings saved, the agents living in
  them not — is worse than no save at all. One document is one atomic write.
* **Shape churn.** The simulation model is still moving; a schema with a column
  per agent attribute would need a migration every time a need or emotion is
  added, and there are dozens of them.

Queryable history — events, presidential decisions, the level and population
curve over time — is written to real tables alongside the snapshot, because
that is what the dashboard and the debug panel actually query. See
`database/models.py`.

The correctness bar is `test_persistence.py`: a city saved, reloaded and run
forward must produce the same future as the city that was never interrupted.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from .agents.generator import AgentFactory
from .agents.models import Agent
from .buildings.construction import ConstructionManager
from .buildings.models import Building
from .city.levels import CityLevel
from .clock import Clock
from .codec import decode_dataclass, encode
from .economy.model import Economy
from .events.model import Emergency, EventLog
from .families.model import FamilyRegistry
from .pathfinding.astar import PathCache
from .player import PlayerOffice
from .president.models import President
from .rng import RngRegistry
from .state import SimulationConfig, WorldState
from .weather.model import Weather
from .urban.state import UrbanState
from .world.plans import DistrictPlan
from .world.tiles import Grid

#: Bumped whenever the snapshot layout changes incompatibly.
SNAPSHOT_VERSION = 1


def dump_world(state: WorldState) -> dict:
    """The entire world as JSON-compatible data."""
    return {
        "version": SNAPSHOT_VERSION,
        "config": _dump_config(state.config),
        "rng": state.rng.snapshot(),
        "clock": state.clock.snapshot(),
        "grid": state.grid.snapshot(),
        "district_plans": [encode(plan) for plan in state.district_plans],
        "economy": state.economy.snapshot(),
        "events": state.events.snapshot(),
        "families": state.families.snapshot(),
        "weather": encode(state.weather),
        "emergency": encode(state.emergency) if state.emergency else None,
        "agents": [encode(agent) for agent in state.agents.values()],
        "buildings": [encode(building) for building in state.buildings.values()],
        "president": encode(state.president) if state.president else None,
        "player": encode(state.player),
        "city_level": int(state.city_level),
        # Clients refetch tiles when this changes; resuming from a lower number
        # than a connected client already holds would leave it on a stale map.
        "map_version": state.map_version,
        "next_ids": {
            "agent": state.agent_factory.next_id,
            "building": state.construction.next_id,
        },
        "cooldowns": {
            "last_tax_change_day": state.last_tax_change_day,
            "last_expansion_day": state.last_expansion_day,
        },
        "view": {
            "camera_focus": list(state.camera_focus),
            "followed_agent_id": state.followed_agent_id,
        },
        "counters": {"ticks_processed": state.ticks_processed},
        "urban": state.urban.snapshot(),
    }


def load_world(data: dict) -> WorldState:
    """A world equivalent to the one `dump_world` was given."""
    version = data.get("version")
    if version != SNAPSHOT_VERSION:
        raise ValueError(f"snapshot version {version} is not supported (expected {SNAPSHOT_VERSION})")

    config = _load_config(data["config"])
    rng = RngRegistry.restore(data["rng"])

    state = WorldState(
        config=config,
        rng=rng,
        clock=Clock.restore(data["clock"]),
        grid=Grid.restore(data["grid"]),
        district_plans=[decode_dataclass(DistrictPlan, item) for item in data["district_plans"]],
        urban=UrbanState.restore(data.get("urban")),
        economy=Economy.restore(data["economy"]),
        events=EventLog.restore(data["events"]),
        families=FamilyRegistry.restore(data["families"]),
        construction=ConstructionManager(),
        agent_factory=AgentFactory(rng),
        # Deliberately not persisted: a pure cache, and a stale one would be a
        # correctness risk after the map changes.
        paths=PathCache(),
    )

    for item in data["agents"]:
        agent = decode_dataclass(Agent, item)
        state.agents[agent.id] = agent
    for item in data["buildings"]:
        building = decode_dataclass(Building, item)
        state.buildings[building.id] = building

    if data.get("president"):
        state.president = decode_dataclass(President, data["president"])
    if data.get("player"):
        state.player = decode_dataclass(PlayerOffice, data["player"])

    state.weather = decode_dataclass(Weather, data["weather"])
    if data.get("emergency"):
        state.emergency = decode_dataclass(Emergency, data["emergency"])

    state.city_level = CityLevel(data["city_level"])
    state.map_version = int(data.get("map_version", 1))

    next_ids = data.get("next_ids", {})
    state.agent_factory.sync_next_id(int(next_ids.get("agent", 1)))
    state.construction.sync_next_id(int(next_ids.get("building", 1)))

    cooldowns = data.get("cooldowns", {})
    state.last_tax_change_day = int(cooldowns.get("last_tax_change_day", -9_999))
    state.last_expansion_day = int(cooldowns.get("last_expansion_day", -9_999))

    view = data.get("view", {})
    focus = view.get("camera_focus") or [0.0, 0.0]
    state.camera_focus = (float(focus[0]), float(focus[1]))
    state.followed_agent_id = view.get("followed_agent_id")

    state.ticks_processed = int(data.get("counters", {}).get("ticks_processed", 0))

    # Older saves lack urban state — rebuild from the grid.
    from .urban.egregoria_network import URBAN_NETWORK_VERSION
    from .urban.migrate import upgrade_grid_roads

    saved_version = int(state.urban.network_version)
    if upgrade_grid_roads(state.grid, rng=state.rng.stream("migrate"), version=saved_version):
        state.urban.refresh_from_grid(state.grid)
        state.urban.network_version = URBAN_NETWORK_VERSION
        state.map_version += 1
        state.invalidate_paths()
    elif not data.get("urban"):
        state.urban.refresh_from_grid(state.grid)
    elif not state.urban.intersections:
        state.urban.refresh_from_grid(state.grid)

    # Stats are derived, so they are recomputed rather than stored; that also
    # guarantees a reloaded city cannot start from a stale analysis.
    state.refresh_stats()
    return state


def _dump_config(config: SimulationConfig) -> dict:
    return {field.name: encode(getattr(config, field.name)) for field in dataclass_fields(config)}


def _load_config(data: dict) -> SimulationConfig:
    return decode_dataclass(SimulationConfig, data)
