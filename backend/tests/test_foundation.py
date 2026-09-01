"""
Tests for the simulation foundation: clock, grid, pathfinding, generation,
economy and the president's analysis.

These cover the layers everything else is built on, so a regression here would
show up as inexplicable behaviour much further downstream.
"""

from __future__ import annotations

import pytest

from sim.agents.generator import AgentFactory
from sim.agents.models import Gender, LifeStage
from sim.buildings.catalog import CATALOG, BuildingType
from sim.buildings.models import Building, BuildingStatus
from sim.city.stats import analyse
from sim.clock import MINUTES_PER_DAY, Clock, Speed
from sim.economy.model import Economy
from sim.jobs.professions import PROFESSIONS, Profession
from sim.pathfinding.astar import PathCache, find_path
from sim.president.brain import BrainContext, PresidentBrain, approval_from
from sim.president.models import ActionKind, ConcernCode, Priority
from sim.rng import RngRegistry
from sim.world.generator import generate_world
from sim.world.tiles import District, Grid, TileType

WORLD_SEED = 20260831


@pytest.fixture
def registry() -> RngRegistry:
    return RngRegistry(WORLD_SEED)


# -- clock -----------------------------------------------------------------


def test_clock_calendar_advances():
    clock = Clock(start_year=1)
    clock.advance(MINUTES_PER_DAY * 45 + 8 * 60 + 30)

    now = clock.now
    assert now.hour == 8
    assert now.minute == 30
    assert now.total_days == 45
    assert now.month == 2
    assert now.day_of_month == 16


def test_clock_speed_controls_tick_rate():
    clock = Clock(speed=Speed.X1)
    assert clock.ticks_due(1_000.0) == 1

    clock.speed = Speed.X10
    assert clock.ticks_due(1_000.0) == 10

    clock.speed = Speed.PAUSED
    assert clock.ticks_due(10_000.0) == 0


def test_clock_caps_runaway_backlog():
    """A long stall must not queue an unbounded number of ticks."""
    clock = Clock(speed=Speed.X100)
    assert clock.ticks_due(600_000.0) == 12


def test_clock_survives_a_round_trip():
    clock = Clock(start_year=3, speed=Speed.X5)
    clock.advance(9_999)
    restored = Clock.restore(clock.snapshot())
    assert restored.tick == clock.tick
    assert restored.speed is Speed.X5
    assert restored.now.label == clock.now.label


def test_speed_rejects_unlisted_values():
    with pytest.raises(ValueError):
        Speed.parse(7)


# -- grid ------------------------------------------------------------------


def test_grid_placement_and_occupation():
    grid = Grid(10, 10)
    assert grid.can_place(2, 2, 3, 3)

    grid.occupy(2, 2, 3, 3, building_id=1)
    assert not grid.can_place(2, 2, 3, 3)
    assert grid.at(3, 3).type is TileType.BUILDING
    assert grid.at(3, 3).building_id == 1

    grid.release(1)
    assert grid.at(3, 3).building_id is None
    assert grid.can_place(2, 2, 3, 3)


def test_grid_rejects_footprint_crossing_the_edge():
    grid = Grid(6, 6)
    assert not grid.can_place(4, 4, 3, 3)


def test_grid_expansion_preserves_existing_tiles():
    grid = Grid(8, 8)
    grid.set_type(3, 3, TileType.ROAD)
    grid.zone(0, 0, 4, 4, District.RESIDENTIAL)

    grid.expand_to(16, 16)

    assert grid.width == 16 and grid.height == 16
    assert grid.at(3, 3).type is TileType.ROAD
    assert grid.at(1, 1).district is District.RESIDENTIAL
    # Newly added land starts blank.
    assert grid.at(12, 12).type is TileType.GRASS


def test_grid_cannot_shrink():
    grid = Grid(10, 10)
    with pytest.raises(ValueError):
        grid.expand_to(8, 8)


def test_find_free_plot_prefers_land_near_the_reference_point():
    grid = Grid(30, 30)
    grid.zone(0, 0, 30, 30, District.RESIDENTIAL)

    near = grid.find_free_plot(2, 2, district=District.RESIDENTIAL, near=(25, 25))
    assert near is not None
    # Should land in the far corner rather than at the origin.
    assert near[0] > 15 and near[1] > 15


# -- pathfinding -----------------------------------------------------------


def test_pathfinding_crosses_open_ground():
    grid = Grid(12, 12)
    result = find_path(grid, (0, 0), (5, 5))
    assert result.found
    # Manhattan distance is the shortest possible on a 4-connected grid.
    assert len(result.tiles) == 10
    assert result.tiles[-1] == (5, 5)


def test_pathfinding_routes_around_water():
    grid = Grid(9, 9)
    # A wall of water with a single gap at the top.
    for y in range(1, 9):
        grid.set_type(4, y, TileType.WATER)

    result = find_path(grid, (1, 4), (7, 4))
    assert result.found
    assert (4, 0) in result.tiles


def test_pathfinding_reports_failure_when_walled_in():
    grid = Grid(9, 9)
    for y in range(9):
        grid.set_type(4, y, TileType.WATER)

    result = find_path(grid, (1, 4), (7, 4))
    assert not result.found
    assert result.tiles == []


def test_pathfinding_accepts_an_unwalkable_destination():
    """Buildings are the usual destination and are not walkable themselves."""
    grid = Grid(9, 9)
    grid.occupy(5, 5, 1, 1, building_id=7)

    result = find_path(grid, (1, 1), (5, 5))
    assert result.found
    assert result.tiles[-1] == (5, 5)


def test_pathfinding_prefers_sidewalks_over_grass():
    grid = Grid(20, 5)
    for x in range(20):
        grid.set_type(x, 1, TileType.SIDEWALK)

    result = find_path(grid, (0, 1), (19, 1))
    assert result.found
    # The straight sidewalk run must be cheaper than the same distance on grass.
    grass = Grid(20, 5)
    on_grass = find_path(grass, (0, 1), (19, 1))
    assert result.cost < on_grass.cost


def test_path_cache_serves_repeat_requests():
    grid = Grid(20, 20)
    cache = PathCache()

    first = cache.route(grid, (0, 0), (9, 9))
    second = cache.route(grid, (0, 0), (9, 9))

    assert first is second
    assert cache.stats["hits"] == 1
    assert cache.stats["misses"] == 1

    cache.invalidate()
    cache.route(grid, (0, 0), (9, 9))
    assert cache.stats["misses"] == 2


# -- world generation ------------------------------------------------------


def test_generated_world_is_deterministic(registry):
    grid_a, plans_a, _ = generate_world(80, 80, RngRegistry(WORLD_SEED).stream("world"))
    grid_b, plans_b, _ = generate_world(80, 80, RngRegistry(WORLD_SEED).stream("world"))

    assert [(t.x, t.y, t.type, t.district) for t in grid_a] == [
        (t.x, t.y, t.type, t.district) for t in grid_b
    ]
    assert plans_a == plans_b


def test_generated_world_has_the_expected_features(registry):
    grid, plans, urban = generate_world(100, 100, registry.stream("world"))
    counts = grid.count_by_type()

    assert counts.get(TileType.ROAD, 0) > 0
    assert counts.get(TileType.SIDEWALK, 0) > 0
    assert counts.get(TileType.WATER, 0) > 0

    districts = {plan.district for plan in plans}
    for required in (District.CITY_CENTER, District.RESIDENTIAL, District.INDUSTRIAL, District.FARM):
        assert required in districts

    # Buildable land must exist in the residential zone or nothing can be built.
    assert grid.free_land(District.RESIDENTIAL) > 0


def test_generated_city_is_walkable_end_to_end(registry):
    """
    The road lattice must actually connect the map.

    A city where agents cannot reach their workplace looks alive but is not, and
    the failure is silent, so it is worth asserting directly.
    """
    grid, _, _ = generate_world(100, 100, registry.stream("world"))
    result = find_path(grid, (1, 1), (60, 60))
    assert result.found


# -- catalogue and professions --------------------------------------------


def test_every_building_type_fits_on_a_generated_map(registry):
    """
    Every catalogue entry must be placeable on a freshly generated map.

    The road lattice and its sidewalks decide how much contiguous land a block
    contains, and a footprint larger than that can never be built — silently,
    because the president simply keeps deferring the decision.
    """
    grid, _, _ = generate_world(100, 100, registry.stream("world"))

    unplaceable = []
    for building_type in BuildingType:
        spec = CATALOG[building_type]
        if grid.find_free_plot(spec.width, spec.height) is None:
            unplaceable.append(f"{building_type} ({spec.width}x{spec.height})")

    assert not unplaceable, f"no room on the map for: {', '.join(unplaceable)}"


def test_every_building_has_a_complete_spec():
    for building_type in BuildingType:
        spec = CATALOG[building_type]
        assert spec.construction_cost > 0
        assert spec.build_days > 0
        assert spec.width > 0 and spec.height > 0


def test_every_profession_has_a_spec():
    for profession in Profession:
        assert PROFESSIONS[profession].base_salary > 0


def test_building_jobs_reference_real_professions():
    for spec in CATALOG.values():
        for profession in spec.jobs:
            assert profession in PROFESSIONS


# -- building instances ---------------------------------------------------


def test_building_staffing_scales_output():
    hospital = Building(id=1, type=BuildingType.HOSPITAL, x=0, y=0, status=BuildingStatus.OPEN)
    assert hospital.hospital_beds == 0  # No staff yet.

    for index, profession in enumerate(
        [Profession.DOCTOR] * 10 + [Profession.NURSE] * 20 + [Profession.CLEANER] * 6
    ):
        assert hospital.hire(index + 1, profession)

    assert hospital.staffing_ratio == 1.0
    assert hospital.hospital_beds == CATALOG[BuildingType.HOSPITAL].hospital_beds


def test_building_refuses_to_overfill_a_role():
    clinic = Building(id=2, type=BuildingType.CLINIC, x=0, y=0, status=BuildingStatus.OPEN)
    capacity = CATALOG[BuildingType.CLINIC].jobs[Profession.DOCTOR]

    for index in range(capacity):
        assert clinic.hire(index + 1, Profession.DOCTOR)
    assert not clinic.hire(999, Profession.DOCTOR)


def test_unopened_building_produces_nothing():
    hospital = Building(id=3, type=BuildingType.HOSPITAL, x=0, y=0)
    hospital.staff[Profession.DOCTOR] = list(range(10))
    assert hospital.hospital_beds == 0


def test_housing_capacity_is_respected():
    house = Building(id=4, type=BuildingType.HOUSE, x=0, y=0, status=BuildingStatus.OPEN)
    capacity = CATALOG[BuildingType.HOUSE].residents

    for index in range(capacity):
        assert house.add_resident(index + 1)
    assert not house.add_resident(999)
    assert house.free_beds == 0


# -- agent generation ------------------------------------------------------


def test_agent_generation_is_deterministic():
    first = AgentFactory(RngRegistry(WORLD_SEED)).create(agent_id=42)
    second = AgentFactory(RngRegistry(WORLD_SEED)).create(agent_id=42)

    assert first.name == second.name
    assert first.gender == second.gender
    assert first.skills == second.skills
    assert first.personality == second.personality


def test_agents_differ_from_each_other(registry):
    factory = AgentFactory(registry)
    agents = [factory.create() for _ in range(60)]

    assert len({agent.name for agent in agents}) > 30
    assert len({agent.gender for agent in agents}) == 2
    assert len({agent.life_stage for agent in agents}) >= 2


def test_children_have_no_education_or_savings(registry):
    factory = AgentFactory(registry)
    child = factory.create_child(surname="Karimov", parent_ids=[1, 2])

    assert child.life_stage is LifeStage.BABY
    assert child.money == 0.0
    assert int(child.education) == 0
    assert child.parent_ids == [1, 2]
    assert not child.can_work


def test_education_never_exceeds_what_age_allows(registry):
    factory = AgentFactory(registry)
    for _ in range(50):
        teenager = factory.create(age_years=15.0)
        # A 15-year-old cannot hold a university degree.
        assert int(teenager.education) <= 1


def test_agent_skills_have_specialities(registry):
    factory = AgentFactory(registry)
    agent = factory.create(age_years=35.0)
    values = sorted(agent.skills.values(), reverse=True)
    # The best skill must stand clearly above the median, or hiring is arbitrary.
    assert values[0] > values[len(values) // 2] + 10


def test_gender_can_be_pinned(registry):
    factory = AgentFactory(registry)
    assert factory.create(gender=Gender.FEMALE).gender is Gender.FEMALE
    assert factory.create(gender=Gender.MALE).gender is Gender.MALE


# -- economy ---------------------------------------------------------------


def test_economy_refuses_to_overspend():
    economy = Economy(starting_budget=1_000.0)
    assert economy.spend(400.0, "construction")
    assert not economy.spend(10_000.0, "construction")
    assert economy.budget == 600.0


def test_monthly_settlement_collects_tax_and_pays_wages():
    economy = Economy(starting_budget=100_000.0)
    economy.taxes.income_tax = 0.20

    result = economy.settle_month(
        day=30,
        public_wages=10_000.0,
        private_wages=40_000.0,
        business_revenue=60_000.0,
        property_value=200_000.0,
        upkeep=5_000.0,
        service_costs={"healthcare": 1_000.0},
    )

    expected_tax = 50_000.0 * 0.20 + 60_000.0 * 0.15 + 200_000.0 * 0.01
    assert result.tax_collected == pytest.approx(expected_tax)
    assert result.expenses == pytest.approx(16_000.0)
    assert economy.budget == pytest.approx(100_000.0 + expected_tax - 16_000.0)
    assert economy.last_month is not None


def test_tax_policy_is_clamped_to_the_legal_range():
    economy = Economy()
    economy.taxes.income_tax = 5.0
    assert economy.taxes.clamped().income_tax == 0.5

    economy.taxes.income_tax = -1.0
    assert economy.taxes.clamped().income_tax == 0.0


def test_higher_tax_lowers_the_happiness_modifier():
    economy = Economy()
    economy.taxes.income_tax = 0.05
    generous = economy.taxes.happiness_modifier

    economy.taxes.income_tax = 0.45
    punitive = economy.taxes.happiness_modifier

    assert generous > 0 > punitive


def test_economy_survives_a_round_trip():
    economy = Economy(starting_budget=750_000.0)
    economy.taxes.income_tax = 0.22
    economy.settle_month(
        day=30, public_wages=1_000.0, private_wages=2_000.0,
        business_revenue=5_000.0, property_value=10_000.0,
        upkeep=500.0, service_costs={},
    )

    restored = Economy.restore(economy.snapshot())
    assert restored.budget == pytest.approx(economy.budget)
    assert restored.taxes.income_tax == pytest.approx(0.22)
    assert len(restored.ledger) == 1


# -- city analysis ---------------------------------------------------------


def _city(registry, *, population: int, houses: int) -> tuple[dict, dict, Economy, Grid]:
    """A minimal city: some adults and some housing, nothing else."""
    grid = Grid(40, 40)
    grid.zone(0, 0, 40, 40, District.RESIDENTIAL)

    factory = AgentFactory(registry)
    agents = {}
    for _ in range(population):
        agent = factory.create(age_years=30.0)
        agents[agent.id] = agent

    buildings = {}
    for index in range(houses):
        building = Building(
            id=index + 1, type=BuildingType.HOUSE,
            x=index * 3, y=0, status=BuildingStatus.OPEN,
        )
        buildings[building.id] = building

    return agents, buildings, Economy(starting_budget=1_000_000.0), grid


def test_analysis_counts_population_and_unemployment(registry):
    agents, buildings, economy, grid = _city(registry, population=20, houses=2)
    stats = analyse(agents, buildings, economy, grid)

    assert stats.population == 20
    assert stats.adults == 20
    assert stats.unemployed == 20
    assert stats.unemployment_rate == 1.0
    assert stats.employment_rate == 0.0


def test_analysis_detects_a_housing_shortage(registry):
    agents, buildings, economy, grid = _city(registry, population=20, houses=2)
    stats = analyse(agents, buildings, economy, grid)

    # Two houses hold eight people; twelve are left without.
    assert stats.housing_capacity == 8
    assert stats.housing_shortage == 12


def test_analysis_reports_full_coverage_when_nothing_is_needed(registry):
    agents, buildings, economy, grid = _city(registry, population=0, houses=0)
    stats = analyse(agents, buildings, economy, grid)

    assert stats.population == 0
    assert stats.education_coverage == 1.0
    assert stats.food_coverage == 1.0


# -- president -------------------------------------------------------------


def _context(stats, economy, buildings=None, *, day=1, tick=1440) -> BrainContext:
    return BrainContext(
        tick=tick,
        day=day,
        stats=stats,
        economy=economy,
        buildings=buildings or {},
        grid_width=100,
        grid_height=100,
        max_grid_size=500,
        last_tax_change_day=-999,
        last_expansion_day=-999,
    )


def test_president_detects_housing_shortage_and_proposes_housing(registry):
    agents, buildings, economy, grid = _city(registry, population=40, houses=1)
    stats = analyse(agents, buildings, economy, grid)
    brain = PresidentBrain()

    concerns = brain.assess(_context(stats, economy, buildings))
    codes = [concern.code for concern in concerns]

    assert ConcernCode.HOUSING_SHORTAGE in codes
    housing = next(c for c in concerns if c.code is ConcernCode.HOUSING_SHORTAGE)
    assert housing.action.kind is ActionKind.BUILD
    assert CATALOG[housing.action.building_type].residents > 0


def test_president_prefers_apartments_for_a_large_shortage(registry):
    agents, buildings, economy, grid = _city(registry, population=200, houses=0)
    stats = analyse(agents, buildings, economy, grid)

    concern = next(
        c for c in PresidentBrain().assess(_context(stats, economy)) if c.code is ConcernCode.HOUSING_SHORTAGE
    )
    assert concern.action.building_type is BuildingType.APARTMENT


def test_president_ignores_a_solved_city(registry):
    """A city with no problems must produce no concerns."""
    grid = Grid(60, 60)
    grid.zone(0, 0, 60, 60, District.RESIDENTIAL)
    economy = Economy(starting_budget=5_000_000.0)
    stats = analyse({}, {}, economy, grid)

    concerns = PresidentBrain().assess(_context(stats, economy))
    # An empty city still needs nothing; population-driven needs are all zero.
    assert ConcernCode.HOUSING_SHORTAGE not in [c.code for c in concerns]
    assert ConcernCode.UNEMPLOYMENT not in [c.code for c in concerns]


def test_president_discounts_a_concern_already_under_construction(registry):
    agents, buildings, economy, grid = _city(registry, population=40, houses=1)
    stats = analyse(agents, buildings, economy, grid)
    brain = PresidentBrain()

    before = next(
        c for c in brain.assess(_context(stats, economy, buildings)) if c.code is ConcernCode.HOUSING_SHORTAGE
    ).severity

    buildings[99] = Building(
        id=99, type=BuildingType.APARTMENT, x=20, y=20,
        status=BuildingStatus.UNDER_CONSTRUCTION,
    )
    after = next(
        c for c in brain.assess(_context(stats, economy, buildings)) if c.code is ConcernCode.HOUSING_SHORTAGE
    ).severity

    assert after < before


def test_president_skips_an_unaffordable_concern_for_one_it_can_fund(registry):
    """
    The worst problem is not always the one to act on.

    With 300 homeless and no money for apartments, spending what it has on
    something useful beats saving up while doing nothing.
    """
    agents, buildings, economy, grid = _city(registry, population=300, houses=0)
    economy.budget = 150_000.0
    stats = analyse(agents, buildings, economy, grid)
    brain = PresidentBrain()

    context = _context(stats, economy, buildings)
    concerns = brain.assess(context)
    chosen = brain.choose(context, concerns)

    assert chosen is not None
    assert brain.estimated_cost(chosen) <= brain.spendable_budget(economy)
    # Housing is the most severe concern but cannot be funded, so it is skipped.
    assert concerns[0].code is ConcernCode.HOUSING_SHORTAGE
    assert chosen.code is not ConcernCode.HOUSING_SHORTAGE


def test_president_reports_the_worst_concern_when_nothing_is_affordable(registry):
    """
    Broke, but still aware.

    The caller records this as deferred rather than acting, so the dashboard can
    explain why nothing is happening.
    """
    agents, buildings, economy, grid = _city(registry, population=300, houses=0)
    economy.budget = 5_000.0
    stats = analyse(agents, buildings, economy, grid)
    brain = PresidentBrain()

    context = _context(stats, economy, buildings)
    concerns = brain.assess(context)
    chosen = brain.choose(context, concerns)

    assert chosen is concerns[0]
    assert brain.estimated_cost(chosen) > brain.spendable_budget(economy)


def test_president_raises_tax_when_the_treasury_runs_short(registry):
    """
    Solvency is the treasury measured against monthly obligations, so the
    scenario is a small reserve against a large wage and upkeep bill.
    """
    agents, buildings, economy, grid = _city(registry, population=10, houses=10)
    economy.budget = 30_000.0

    stats = analyse(agents, buildings, economy, grid)
    # Four months of runway: enough to notice, not yet a crisis.
    stats.public_wage_bill = 6_000.0
    stats.total_upkeep = 1_500.0

    concerns = PresidentBrain().assess(_context(stats, economy))
    deficit = [c for c in concerns if c.code is ConcernCode.BUDGET_DEFICIT]

    assert deficit
    assert deficit[0].action.kind is ActionKind.SET_TAX
    assert deficit[0].action.tax_value > economy.taxes.income_tax


def test_a_comfortable_treasury_raises_no_budget_concern(registry):
    agents, buildings, economy, grid = _city(registry, population=10, houses=10)
    economy.budget = 5_000_000.0

    stats = analyse(agents, buildings, economy, grid)
    stats.public_wage_bill = 6_000.0
    stats.total_upkeep = 1_500.0

    concerns = PresidentBrain().assess(_context(stats, economy))
    assert not [c for c in concerns if c.code is ConcernCode.BUDGET_DEFICIT]


def test_president_notices_an_empty_treasury_despite_healthy_books(registry):
    """
    Construction is charged upfront and never enters the monthly ledger, so the
    books can show a surplus while the treasury is empty. Judging solvency on
    the ledger alone let the city spend itself broke unnoticed.
    """
    agents, buildings, economy, grid = _city(registry, population=20, houses=5)
    # A comfortable month on paper...
    economy.settle_month(
        day=30, public_wages=5_000.0, private_wages=20_000.0,
        business_revenue=50_000.0, property_value=100_000.0,
        upkeep=1_000.0, service_costs={},
    )
    assert not economy.in_deficit
    # ...but the money went into buildings.
    economy.budget = 4_000.0

    stats = analyse(agents, buildings, economy, grid)
    stats.public_wage_bill = 5_000.0
    stats.total_upkeep = 1_000.0

    concerns = PresidentBrain().assess(_context(stats, economy))
    deficit = [c for c in concerns if c.code is ConcernCode.BUDGET_DEFICIT]

    assert deficit, "an empty treasury went unnoticed"
    assert deficit[0].action.kind is ActionKind.SET_TAX


def test_tax_cooldown_yields_to_a_solvency_crisis(registry):
    """
    The cooldown must not gag the president while the city runs out of money.

    With weeks of runway left, waiting two more months for the rate limit to
    expire leaves the city frozen and unable to fund anything.
    """
    agents, buildings, economy, grid = _city(registry, population=20, houses=5)
    economy.budget = 2_000.0

    stats = analyse(agents, buildings, economy, grid)
    stats.public_wage_bill = 8_000.0
    stats.total_upkeep = 2_000.0

    brain = PresidentBrain()

    # Barely any runway, and the lever was pulled yesterday.
    crisis = _context(stats, economy, day=100)
    crisis.last_tax_change_day = 99
    assert [c for c in brain.assess(crisis) if c.code is ConcernCode.BUDGET_DEFICIT]

    # A merely thin reserve does respect the cooldown.
    economy.budget = 80_000.0
    comfortable = analyse(agents, buildings, economy, grid)
    comfortable.public_wage_bill = 8_000.0
    comfortable.total_upkeep = 2_000.0
    settled = _context(comfortable, economy, day=100)
    settled.last_tax_change_day = 99
    assert not [
        c for c in brain.assess(settled) if c.code is ConcernCode.BUDGET_DEFICIT
    ]


def test_president_will_not_recruit_into_a_housing_shortage(registry):
    """
    Importing workers the city cannot house made every indicator worse at once.
    Recruitment must wait until there are beds.
    """
    grid = Grid(40, 40)
    economy = Economy(starting_budget=2_000_000.0)

    factory = AgentFactory(registry)
    agents = {}
    for _ in range(6):
        agent = factory.create(age_years=30.0)
        agent.profession = Profession.FACTORY_WORKER
        agent.workplace_id = 2
        agent.home_id = None  # Nobody is housed.
        agents[agent.id] = agent

    workplace = Building(
        id=2, type=BuildingType.FACTORY, x=10, y=10, status=BuildingStatus.OPEN
    )
    workplace.staff[Profession.FACTORY_WORKER] = list(agents)

    buildings = {2: workplace}
    stats = analyse(agents, buildings, economy, grid)
    assert stats.open_vacancies > 0
    assert stats.housing_shortage > 0

    concerns = PresidentBrain().assess(_context(stats, economy, buildings))
    assert not [c for c in concerns if c.code is ConcernCode.WORKER_SHORTAGE]


def test_president_only_proposes_unlocked_buildings(registry):
    """
    A village cannot build apartments. Proposing one produces a decision that
    can never be carried out, which stalled the city indefinitely.
    """
    from sim.city.levels import CityLevel, unlocked_buildings

    agents, buildings, economy, grid = _city(registry, population=200, houses=0)
    stats = analyse(agents, buildings, economy, grid)

    context = _context(stats, economy)
    context.unlocked = unlocked_buildings(CityLevel.VILLAGE)

    for concern in PresidentBrain().assess(context):
        if concern.action.kind is ActionKind.BUILD:
            assert concern.action.building_type in context.unlocked


def test_housing_concern_survives_projects_already_under_way(registry):
    """
    An in-flight project must discount a concern, not erase it. The exponential
    discount once collapsed a 68-person shortage to nothing because five
    townhouses were being built.
    """
    agents, buildings, economy, grid = _city(registry, population=100, houses=1)
    stats = analyse(agents, buildings, economy, grid)
    brain = PresidentBrain()

    for building_id in range(50, 56):
        buildings[building_id] = Building(
            id=building_id, type=BuildingType.TOWNHOUSE, x=0, y=0,
            status=BuildingStatus.UNDER_CONSTRUCTION,
        )

    concerns = brain.assess(_context(stats, economy, buildings))
    housing = [c for c in concerns if c.code is ConcernCode.HOUSING_SHORTAGE]

    assert housing, "a real housing shortage was discounted out of existence"
    assert housing[0].severity > 0.1


def test_president_recruits_when_jobs_outnumber_workers(registry):
    """Vacancies with nobody to fill them must trigger recruitment, not building."""
    grid = Grid(40, 40)
    economy = Economy(starting_budget=2_000_000.0)

    factory = AgentFactory(registry)
    agents = {}
    house = Building(id=1, type=BuildingType.APARTMENT, x=0, y=0, status=BuildingStatus.OPEN)
    for _ in range(4):
        agent = factory.create(age_years=30.0)
        agent.home_id = 1
        house.residents.append(agent.id)
        agents[agent.id] = agent

    factory_building = Building(
        id=2, type=BuildingType.FACTORY, x=10, y=10, status=BuildingStatus.OPEN
    )
    # Employ everyone so nobody is unemployed, leaving the rest of the slots open.
    for agent in agents.values():
        agent.profession = Profession.FACTORY_WORKER
        agent.workplace_id = 2
        agent.salary = PROFESSIONS[Profession.FACTORY_WORKER].base_salary
        factory_building.staff.setdefault(Profession.FACTORY_WORKER, []).append(agent.id)

    buildings = {1: house, 2: factory_building}
    stats = analyse(agents, buildings, economy, grid)
    assert stats.unemployed == 0
    assert stats.open_vacancies > 0

    concerns = PresidentBrain().assess(_context(stats, economy, buildings))
    recruitment = [c for c in concerns if c.code is ConcernCode.WORKER_SHORTAGE]

    assert recruitment
    assert recruitment[0].action.kind is ActionKind.RECRUIT_WORKERS
    assert recruitment[0].action.quantity > 0


def test_priority_scales_with_severity():
    assert Priority.from_severity(0.9) is Priority.CRITICAL
    assert Priority.from_severity(0.6) is Priority.HIGH
    assert Priority.from_severity(0.3) is Priority.MEDIUM
    assert Priority.from_severity(0.1) is Priority.LOW


def test_approval_rewards_a_well_run_city(registry):
    agents, buildings, economy, grid = _city(registry, population=8, houses=4)
    for agent in agents.values():
        agent.profession = Profession.SHOPKEEPER
        agent.workplace_id = 1
        agent.home_id = 1
        agent.emotions.happiness = 90.0

    good = analyse(agents, buildings, economy, grid)

    poor_agents, poor_buildings, poor_economy, poor_grid = _city(
        registry, population=80, houses=1
    )
    for agent in poor_agents.values():
        agent.emotions.happiness = 10.0
        agent.emotions.stress = 90.0
    poor = analyse(poor_agents, poor_buildings, poor_economy, poor_grid)

    assert approval_from(good, economy) > approval_from(poor, poor_economy)


def test_approval_stays_within_bounds(registry):
    agents, buildings, economy, grid = _city(registry, population=500, houses=0)
    economy.taxes.income_tax = 0.5
    stats = analyse(agents, buildings, economy, grid)

    rating = approval_from(stats, economy)
    assert 0.0 <= rating <= 100.0
