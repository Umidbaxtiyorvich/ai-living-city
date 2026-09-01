"""Urban planning and realistic city structure tests (spec section 54)."""

from sim.engine import Engine
from sim.rng import RngRegistry
from sim.state import SimulationConfig, WorldState
from sim.urban.roads import RoadLevel
from sim.urban.zones import CityZone
from sim.world.tiles import TileType


def test_initial_city_has_road_hierarchy():
    state = WorldState.create(SimulationConfig(seed=42, map_size=100))
    levels = {tile.road_level for tile in state.grid if tile.road_level > 0}
    assert RoadLevel.HIGHWAY.value in levels
    assert RoadLevel.MAIN_AVENUE.value in levels
    assert RoadLevel.DISTRICT_ROAD.value in levels


def test_master_plan_districts_cover_core_zones():
    state = WorldState.create(SimulationConfig(seed=7, map_size=100))
    zones = {plan.zone for plan in state.district_plans if plan.zone}
    assert CityZone.CITY_CENTER in zones
    assert CityZone.GOVERNMENT in zones or CityZone.CITY_CENTER in zones
    assert any(
        z in zones
        for z in (
            CityZone.MEDIUM_DENSITY_RESIDENTIAL,
            CityZone.LOW_DENSITY_RESIDENTIAL,
        )
    )


def test_expansion_generates_roads_on_new_land():
    state = WorldState.create(SimulationConfig(seed=3, map_size=80, max_map_size=120))
    engine = Engine(state)
    engine.found_city()
    before_roads = sum(1 for t in state.grid if t.road_level > 0)
    state.grid.expand_to(100, 100)
    from sim.urban.expansion import expand_map_with_infrastructure

    expand_map_with_infrastructure(
        state.grid, new_width=100, new_height=100, rng=state.rng.stream("urban")
    )
    state.urban.refresh_from_grid(state.grid)
    after_roads = sum(1 for t in state.grid if t.road_level > 0)
    assert after_roads > before_roads


def test_new_district_gets_internal_roads():
    state = WorldState.create(SimulationConfig(seed=11, map_size=100))
    engine = Engine(state)
    engine.found_city()
    from sim.urban.district_generator import create_district

    plan = create_district(
        state.grid,
        x=10,
        y=10,
        size=24,
        zone=CityZone.MEDIUM_DENSITY_RESIDENTIAL,
        rng=RngRegistry(11).stream("urban"),
    )
    region_roads = sum(
        1
        for tile in state.grid.region(plan.x, plan.y, plan.width, plan.height)
        if tile.road_level > 0
    )
    assert region_roads > 0
    assert plan.zone is CityZone.MEDIUM_DENSITY_RESIDENTIAL


def test_full_city_lifecycle():
    """Spec section 54 — founding through growth."""
    config = SimulationConfig(seed=99, map_size=80, founding_population=40)
    state = WorldState.create(config)
    engine = Engine(state)
    engine.found_city()

    assert state.president is not None
    assert len(state.buildings) >= 8
    assert state.population >= 30

    for _ in range(1440 * 30):
        engine.tick()

    state.refresh_stats()
    assert state.population > 0
    assert state.urban.intersections or state.urban.street_lights
    assert any(tile.type is TileType.ROAD for tile in state.grid)
