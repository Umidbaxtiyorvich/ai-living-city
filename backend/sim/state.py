"""
World state.

Everything the simulation owns, in memory. This is deliberately a plain
container: it holds no behaviour beyond bookkeeping, so the tick pipeline in
`engine.py` remains the single place where the world changes.

Nothing here imports FastAPI or SQLAlchemy. Persistence reads this object from
the outside, which is what lets the whole simulation be tested without a
database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agents.generator import AgentFactory
from .agents.models import Agent, Gender
from .buildings.construction import ConstructionManager
from .buildings.models import Building
from .city.levels import LEVELS, CityLevel, level_for_population, unlocked_buildings
from .city.stats import CityStats, analyse
from .clock import Clock, Speed
from .economy.model import Economy
from .events.model import Emergency, EventLog
from .families.model import FamilyRegistry
from .pathfinding.astar import PathCache
from .player import PlayerOffice
from .president.models import President
from .rng import RngRegistry
from .weather.model import Weather
from .urban import UrbanState
from .world.generator import generate_world
from .world.plans import DistrictPlan
from .world.tiles import Grid

#: Default starting map size (specification section 14).
DEFAULT_MAP_SIZE = 100

#: Largest map the city may grow to.
MAX_MAP_SIZE = 500

#: Citizens the city is founded with.
FOUNDING_POPULATION = 30


@dataclass
class SimulationConfig:
    seed: int = 20260831
    map_size: int = DEFAULT_MAP_SIZE
    max_map_size: int = MAX_MAP_SIZE
    founding_population: int = FOUNDING_POPULATION
    starting_budget: float = 8_000_000.0
    speed: Speed = Speed.X1
    #: Radius in tiles within which agents get full simulation.
    full_detail_radius: float = 65.0
    reduced_detail_radius: float = 130.0


@dataclass
class WorldState:
    """The whole city."""

    config: SimulationConfig
    rng: RngRegistry
    clock: Clock
    grid: Grid
    district_plans: list[DistrictPlan]
    urban: UrbanState

    economy: Economy
    events: EventLog
    families: FamilyRegistry
    construction: ConstructionManager
    agent_factory: AgentFactory
    paths: PathCache

    agents: dict[int, Agent] = field(default_factory=dict)
    buildings: dict[int, Building] = field(default_factory=dict)
    president: President | None = None
    player: PlayerOffice = field(default_factory=PlayerOffice)
    weather: Weather = field(default_factory=Weather)
    emergency: Emergency | None = None

    #: Latest analysis, refreshed every tick.
    stats: CityStats = field(default_factory=CityStats)
    city_level: CityLevel = CityLevel.VILLAGE

    #: Cooldown bookkeeping for the president's rate-limited levers.
    last_tax_change_day: int = -9_999
    last_expansion_day: int = -9_999

    #: Where the viewer is looking, used to pick simulation detail.
    camera_focus: tuple[float, float] = (0.0, 0.0)
    #: Agent the viewer is following, always simulated in full.
    followed_agent_id: int | None = None

    #: Rolling performance figures for the debug panel.
    last_tick_ms: float = 0.0
    ticks_processed: int = 0
    #: Bumped whenever the walkable map or zoning changes, so clients refetch tiles.
    map_version: int = 1

    # -- construction -----------------------------------------------------

    @classmethod
    def create(cls, config: SimulationConfig | None = None) -> "WorldState":
        config = config or SimulationConfig()
        rng = RngRegistry(config.seed)
        grid, plans, urban = generate_world(config.map_size, config.map_size, rng.stream("world"))

        return cls(
            config=config,
            rng=rng,
            clock=Clock(start_year=1, speed=config.speed),
            grid=grid,
            district_plans=plans,
            urban=urban,
            economy=Economy(starting_budget=config.starting_budget),
            events=EventLog(),
            families=FamilyRegistry(),
            construction=ConstructionManager(),
            agent_factory=AgentFactory(rng),
            paths=PathCache(),
        )

    # -- queries -----------------------------------------------------------

    @property
    def day(self) -> int:
        return self.clock.total_days

    @property
    def tick(self) -> int:
        return self.clock.tick

    @property
    def living_agents(self) -> list[Agent]:
        return [agent for agent in self.agents.values() if agent.alive]

    @property
    def population(self) -> int:
        return sum(1 for agent in self.agents.values() if agent.alive)

    @property
    def unlocked(self) -> frozenset:
        return unlocked_buildings(self.city_level)

    def building_at(self, x: int, y: int) -> Building | None:
        tile = self.grid.get(x, y)
        if tile is None or tile.building_id is None:
            return None
        return self.buildings.get(tile.building_id)

    def refresh_stats(self) -> CityStats:
        self.stats = analyse(self.agents, self.buildings, self.economy, self.grid)
        return self.stats

    def refresh_city_level(self) -> CityLevel | None:
        """Returns the new level if the city just advanced, else None."""
        reached = level_for_population(self.population)
        if reached > self.city_level:
            self.city_level = reached
            return reached
        return None

    # -- mutation helpers --------------------------------------------------

    def add_agent(self, agent: Agent) -> Agent:
        self.agents[agent.id] = agent
        self.agent_factory.sync_next_id(agent.id + 1)
        return agent

    def spawn_citizen(
        self,
        *,
        age_years: float | None = None,
        gender: Gender | None = None,
        surname: str | None = None,
    ) -> Agent:
        """
        Creates a citizen and places them at the city centre.

        New arrivals start on the map rather than inside a building, because
        they have no home yet — housing allocation places them later.
        """
        agent = self.agent_factory.create(
            age_years=age_years, gender=gender, surname=surname
        )
        centre = self.grid.width // 2, self.grid.height // 2
        agent.position = (float(centre[0]), float(centre[1]))
        return self.add_agent(agent)

    def invalidate_paths(self) -> None:
        """Called whenever the walkable map changes."""
        self.paths.invalidate()
        self.map_version += 1

    # -- serialisation for clients ----------------------------------------

    def world_summary(self) -> dict:
        """Static-ish data the client needs once, not every tick."""
        return {
            "seed": self.config.seed,
            "width": self.grid.width,
            "height": self.grid.height,
            "districts": [
                {
                    "district": plan.district,
                    "zone": plan.zone.value if plan.zone else None,
                    "x": plan.x,
                    "y": plan.y,
                    "width": plan.width,
                    "height": plan.height,
                    "density": plan.density,
                }
                for plan in self.district_plans
            ],
            "city_level": int(self.city_level),
        }

    def tile_payload(self) -> dict:
        """
        The tile map, run-length encoded along rows.

        A 500x500 map is 250 000 tiles; sending them individually would be
        megabytes per message. Cities are large areas of the same type, so RLE
        compresses it by an order of magnitude and the client expands it once.
        """
        runs: list[list] = []
        current_type: str | None = None
        current_district: str | None = None
        current_road: int | None = None
        length = 0

        for tile in self.grid.tiles:
            key_type, key_district, key_road = (
                tile.type.value,
                tile.district.value,
                tile.road_level,
            )
            if (
                key_type == current_type
                and key_district == current_district
                and key_road == current_road
            ):
                length += 1
                continue
            if current_type is not None:
                runs.append([current_type, current_district, current_road, length])
            current_type, current_district, current_road, length = (
                key_type,
                key_district,
                key_road,
                1,
            )

        if current_type is not None:
            runs.append([current_type, current_district, current_road, length])

        return {"width": self.grid.width, "height": self.grid.height, "runs": runs}

    def building_payload(self) -> list[dict]:
        return [
            {
                "id": building.id,
                "type": building.type,
                "category": building.spec.category,
                "x": building.x,
                "y": building.y,
                "width": building.width,
                "height": building.height,
                "levels": building.spec.levels,
                "status": building.status,
                "progress": round(building.construction_fraction, 3),
                "residents": len(building.residents),
                "capacity": building.housing_capacity,
                "staff": building.total_staff,
                "job_slots": building.total_job_slots,
            }
            for building in self.buildings.values()
            if building.status.value != "demolished"
        ]

    def agent_payload(self) -> list[dict]:
        return [agent.public_state() for agent in self.agents.values() if agent.alive]

    def dashboard_payload(self) -> dict:
        """Everything the president dashboard shows (specification section 33)."""
        stats = self.stats
        return {
            "time": {
                "tick": self.tick,
                "day": self.day,
                "label": self.clock.now.label,
                "hour": self.clock.now.hour,
                "speed": int(self.clock.speed),
                "is_night": self.clock.now.is_night,
            },
            "city_level": int(self.city_level),
            "city_level_name": LEVELS[self.city_level].name,
            "map_version": self.map_version,
            "events": [event.as_dict() for event in self.events.recent(18)],
            "stats": stats.as_dict(),
            "economy": self.economy.as_dict(),
            "weather": self.weather.as_dict(),
            "president": self.president.public_state() if self.president else None,
            "current_decision": (
                self.president.decisions[-1].as_dict()
                if self.president and self.president.decisions
                else None
            ),
            "emergency": self.emergency.as_dict() if self.emergency else None,
            "player": {
                **self.player.as_dict(),
                "desks": self.player.desks_snapshot(self.living_agents),
            },
            "performance": {
                "last_tick_ms": round(self.last_tick_ms, 3),
                "ticks_processed": self.ticks_processed,
                "agents": self.population,
                "buildings": len(self.buildings),
                "path_cache": self.paths.stats,
            },
            "urban": {
                **self.urban.urban_payload(),
                "parking": self.urban.parking.analyse(
                    population=stats.population,
                    employed=stats.employed,
                ),
                "traffic_congestion": round(
                    self.urban.estimate_road_traffic(self.grid, population=stats.population),
                    3,
                ),
                "utilities": self.urban.utilities.as_dict(),
            },
        }
