"""
The simulation engine.

Owns the tick pipeline described in the architecture document. The ordering
matters: each stage sees the results of the one before it, so analysis runs
after the world has moved and the president decides on figures that are current.

Most subsystems are not per-tick. Hiring, construction and ageing are daily;
wages and taxes are monthly. Running them at minute resolution would be both
wasteful and wrong — a monthly salary paid 1440 times a day is not a salary.
"""

from __future__ import annotations

import time

from .agents import behavior
from .agents.generator import FEMALE_NAMES, MALE_NAMES, SURNAMES
from .agents.models import Activity, Agent, DetailLevel, Gender, LifeStage
from .buildings.catalog import CATALOG, BuildingType
from .buildings.catalog import label_for as building_label
from .buildings.construction import MAX_CONCURRENT_PROJECTS, RejectionReason
from .buildings.models import BuildingStatus
from .cabinet import (
    DESK_PROFESSION,
    Desk,
    LedgerItem,
    LedgerKind,
    TaskStatus,
    classify_work,
    specialist_blueprint,
)
from .city.levels import LEVELS
from .clock import DAYS_PER_MONTH
from .desks import process_desk_file, write_budget_report, write_work_note
from .economy.model import MAX_TAX_RATE, MIN_TAX_RATE
from .events.model import Emergency, EventType, Severity
from .jobs import employment
from .memory.model import MemoryKind
from .president import schedule as president_schedule
from .president.brain import BrainContext, PresidentBrain, approval_from
from .jobs.professions import PROFESSIONS, Profession
from .jobs.professions import label_for as profession_label
from .player import PlayerRole, parse_command
from .workshop import (
    CHARS_PER_TICK,
    CodingJob,
    generate_agent_source,
    module_filename,
    profession_from_spec,
    write_and_load,
)
from .president.models import (
    Action,
    ActionKind,
    Concern,
    ConcernCode,
    Decision,
    DecisionStatus,
    President,
    Priority,
)
from .state import WorldState
from .weather.model import roll_weather
from .urban.district_generator import create_district_at_distance, zone_label
from .urban.transport import BusStop
from .urban.expansion import expand_map_with_infrastructure
from .urban.zones import CityZone
from .world.plans import DistrictPlan
from .world.tiles import District, TileType

#: Simulated minutes between president decisions. Roughly twice a working day,
#: so the city changes at a pace a viewer can follow.
DECISION_INTERVAL_MINUTES = 240

#: Player-ordered buildings finish in a few days instead of sitting at 95%
#: while a 35-day power plant crawls forward with almost no builders.
PLAYER_BUILD_DAILY_FRACTION = 0.34

#: Simulated minutes between full city analyses.
#:
#: The analysis walks every agent and building, and its only consumers are the
#: president (every four hours) and the dashboard (a few times a second of real
#: time). Running it every simulated minute was the single largest cost in the
#: tick and produced numbers nothing read.
STATS_INTERVAL_MINUTES = 30

#: Ticks between level-of-detail reassignments. The camera cannot move far
#: enough in ten simulated minutes to matter.
DETAIL_INTERVAL_TICKS = 10

#: Simulated minutes between social encounter checks. Hourly, so relationships
#: build up over a day of people passing each other rather than in one nightly
#: batch when everyone is already asleep at home.
ENCOUNTER_INTERVAL_MINUTES = 60

#: Monthly cost of living per adult, as a share of the average wage.
LIVING_COST = 900.0

#: Price multiplier for building above the city's development level.
#:
#: The AI president keeps to the unlocked list, because proposing a metropolis
#: hospital in a village produces a decision it can never carry out. The player
#: is the president, though, so a decree is not refused — it is charged for the
#: expertise the city does not have yet. Progression stays meaningful because
#: skipping ahead hurts the budget.
EARLY_BUILD_PREMIUM = 2.5

#: Reply fragments that mean the command did not succeed.
_FAIL_HINTS = (
    "yetmaydi",
    "boshlanmadi",
    "bo'lmadi",
    "topilmadi",
    "navbati to'la",
    "rad etildi",
    "bajarib bo'lmaydi",
    "noma'lum",
)


def _command_failed(reply: str) -> bool:
    lower = reply.lower()
    return any(hint in lower for hint in _FAIL_HINTS)

#: Business revenue generated per unit of retail capacity, per month.
REVENUE_PER_RETAIL = 45.0

#: Property value per resident, used for the property tax base.
PROPERTY_VALUE_PER_RESIDENT = 12_000.0

#: Yearly chance of death, by life stage. Applied once per simulated year.
MORTALITY_BY_STAGE = {
    LifeStage.BABY: 0.004,
    LifeStage.TODDLER: 0.001,
    LifeStage.CHILD: 0.0008,
    LifeStage.TEENAGER: 0.001,
    LifeStage.ADULT: 0.003,
    LifeStage.SENIOR: 0.06,
}

#: How many tiles a new residential zone covers when the president opens one.
NEW_DISTRICT_SIZE = 24

_DISTRICT_ZONE_MAP: dict[District, CityZone] = {
    District.RESIDENTIAL: CityZone.MEDIUM_DENSITY_RESIDENTIAL,
    District.BUSINESS: CityZone.BUSINESS,
    District.SHOPPING: CityZone.COMMERCIAL,
    District.OFFICE: CityZone.BUSINESS,
    District.INDUSTRIAL: CityZone.INDUSTRIAL,
    District.SCHOOL: CityZone.EDUCATION,
    District.HOSPITAL: CityZone.HEALTHCARE,
    District.PARK: CityZone.PARK,
    District.CITY_CENTER: CityZone.CITY_CENTER,
    District.FARM: CityZone.AGRICULTURE,
}


def _district_to_zone(district: District) -> CityZone:
    return _DISTRICT_ZONE_MAP.get(district, CityZone.MEDIUM_DENSITY_RESIDENTIAL)


class Engine:
    """Drives a `WorldState` forward."""

    def __init__(self, state: WorldState) -> None:
        self.state = state
        self.brain = PresidentBrain()
        self._last_decision_tick = -DECISION_INTERVAL_MINUTES
        #: Tracked rather than derived from `tick % interval`, so the very first
        #: tick after founding still assigns detail levels.
        self._last_detail_tick = -DETAIL_INTERVAL_TICKS
        self._last_encounter_tick = -ENCOUNTER_INTERVAL_MINUTES
        #: Day a concern was last deferred, so an unaffordable problem is
        #: recorded once rather than every four hours until it is solved.
        self._deferred_on_day: dict[str, int] = {}
        self._last_player_build_boost_day: int = -1
        #: Why the most recent build attempt failed, so callers can react to
        #: the actual obstacle instead of guessing.
        self._last_build_reason: RejectionReason | None = None

    # -- bootstrap ---------------------------------------------------------

    def found_city(self) -> None:
        """
        Creates the founding city: a palace, basic services, homes and citizens.

        Founding buildings are placed instantly because they must exist before
        the first tick; everything afterwards goes through the normal
        construction pipeline.
        """
        state = self.state
        if state.president is not None:
            raise RuntimeError("the city has already been founded")

        centre = (state.grid.width // 2, state.grid.height // 2)

        founding: tuple[tuple[BuildingType, int], ...] = (
            (BuildingType.PRESIDENTIAL_PALACE, 1),
            (BuildingType.CITY_HALL, 1),
            (BuildingType.OFFICE, 3),
            (BuildingType.APARTMENT, 5),
            (BuildingType.TOWNHOUSE, 4),
            (BuildingType.HOUSE, 14),
            (BuildingType.FARM, 2),
            (BuildingType.SHOP, 4),
            (BuildingType.MARKET, 1),
            (BuildingType.CAFE, 2),
            (BuildingType.CLINIC, 1),
            (BuildingType.SCHOOL, 1),
            (BuildingType.KINDERGARTEN, 1),
            (BuildingType.PARK, 2),
            (BuildingType.BUS_STOP, 2),
            (BuildingType.FACTORY, 1),
            (BuildingType.POWER_PLANT, 1),
        )

        for building_type, count in founding:
            for _ in range(count):
                result = state.construction.request(
                    building_type,
                    grid=state.grid,
                    economy=state.economy,
                    buildings=state.buildings,
                    near=centre,
                    instant=True,
                )
                if not result.approved:
                    # Worth surfacing: a founding city that cannot place its own
                    # palace means the generated map is unusable.
                    state.events.record(
                        0, 0, EventType.BUILDING_STARTED,
                        f"Ta'sis binosi qurilmadi: {building_label(building_type)} "
                        f"({result.reason})",
                        severity=Severity.WARNING,
                    )

        state.invalidate_paths()
        self._install_president(centre)

        for _ in range(state.config.founding_population):
            state.spawn_citizen()

        employment.assign_housing(0, state.agents, state.buildings, limit=10_000)
        employment.run_hiring(0, state.agents, state.buildings, limit=10_000)
        employment.enrol_children(0, state.agents, state.buildings)

        state.weather = roll_weather(0, state.rng.stream("weather"))
        state.refresh_stats()
        state.refresh_city_level()

        state.events.record(
            0, 0, EventType.DISTRICT_OPENED,
            f"Shahar ta'sis etildi: {state.population} aholi",
            severity=Severity.NOTICE,
        )

    def _install_president(self, centre: tuple[int, int]) -> None:
        state = self.state
        state.rng.derived("president", 1)

        palace = next(
            (
                building
                for building in state.buildings.values()
                if building.type is BuildingType.PRESIDENTIAL_PALACE
            ),
            None,
        )
        office = next(
            (
                building
                for building in state.buildings.values()
                if building.type is BuildingType.CITY_HALL
            ),
            None,
        )

        gender = Gender.MALE
        state.president = President(
            id=1,
            name="Umid Ravshanov",
            gender=gender,
            age_days=int(38 * 360),
            avatar_seed="president-umid-ravshanov",
            appearance={"gender": gender.value, "clothingStyle": "business"},
            intelligence=88.0,
            leadership=90.0,
            palace_building_id=palace.id if palace else None,
            office_building_id=office.id if office else None,
            position=(float(centre[0]), float(centre[1])),
        )
        self.ensure_player_identity()

        if palace is not None:
            state.president.position = (
                float(palace.entrance[0]),
                float(palace.entrance[1]),
            )

    # -- the tick ----------------------------------------------------------

    def run(self, ticks: int) -> None:
        for _ in range(ticks):
            self.tick()

    def tick(self) -> None:
        started = time.perf_counter()
        state = self.state

        state.clock.advance(1)
        now = state.clock.now
        new_day = state.clock.is_new_day()

        if new_day:
            self._start_of_day()

        if state.tick - self._last_detail_tick >= DETAIL_INTERVAL_TICKS:
            self._last_detail_tick = state.tick
            self._update_detail_levels()

        self._step_agents(minutes=1.0)
        self._advance_coding()
        self._advance_cabinet_tasks()
        self._step_president(now)

        if state.tick - self._last_encounter_tick >= ENCOUNTER_INTERVAL_MINUTES:
            self._last_encounter_tick = state.tick
            state.families.register_encounters(state.agents, state.tick)

        decision_due = state.tick - self._last_decision_tick >= DECISION_INTERVAL_MINUTES
        # The president must never reason on stale figures, so a pending
        # decision forces a refresh regardless of the interval.
        if decision_due or new_day or state.tick % STATS_INTERVAL_MINUTES == 0:
            state.refresh_stats()

        self._govern(now)
        self._resolve_emergency()
        state.urban.step_traffic_lights(state.tick)

        if new_day:
            self._end_of_day()

        state.last_tick_ms = (time.perf_counter() - started) * 1_000.0
        state.ticks_processed += 1

    # -- daily -------------------------------------------------------------

    def _start_of_day(self) -> None:
        state = self.state
        day = state.day
        state.weather = roll_weather(day, state.rng.stream("weather"))

        if state.weather.condition.value == "storm":
            state.events.record(
                state.tick, day, EventType.STORM,
                f"Bo'ron: {state.weather.temperature:.0f}°C",
                severity=Severity.WARNING,
            )

    def _end_of_day(self) -> None:
        state = self.state
        tick, day = state.tick, state.day

        opened = state.construction.advance_day(tick, state.buildings, state.agents)
        seen = {building.id for building in opened}
        for building in self._boost_player_construction():
            if building.id not in seen:
                opened.append(building)
                seen.add(building.id)
        for building in opened:
            self._record_building_opened(building)
        if opened:
            state.invalidate_paths()
            state.urban.seed_parking_near_buildings(state.buildings)

        self._refresh_utilities()

        for hire in employment.run_hiring(tick, state.agents, state.buildings):
            agent = state.agents[hire.agent_id]
            state.events.record(
                tick, day, EventType.HIRED,
                f"{agent.name} — {profession_label(hire.profession)}",
                agent_ids=[agent.id], building_ids=[hire.building_id],
            )

        for move in employment.assign_housing(tick, state.agents, state.buildings):
            agent = state.agents[move.agent_id]
            state.events.record(
                tick, day, EventType.MOVED_HOME,
                f"{agent.name} yangi uyga ko'chdi",
                agent_ids=[agent.id], building_ids=[move.building_id],
            )
            behavior.reset_needs_for_new_home(agent.needs)
            family = state.families.families.get(agent.family_id) if agent.family_id else None
            if family is not None and family.home_id is None:
                family.home_id = move.building_id

        employment.enrol_children(tick, state.agents, state.buildings)

        self._age_population()
        self._run_relationships()

        level = state.refresh_city_level()
        if level is not None:
            state.events.record(
                tick, day, EventType.CITY_LEVEL_UP,
                f"Shahar darajasi oshdi: {LEVELS[level].name}",
                severity=Severity.NOTICE,
                level=int(level),
            )

        if day > 0 and day % DAYS_PER_MONTH == 0:
            self._settle_month()

        if state.president is not None:
            state.president.approval_rating = approval_from(state.stats, state.economy)

        self._advance_cabinet_tasks()

    def _age_population(self) -> None:
        """Ages everyone by a day, graduating and retiring where due."""
        state = self.state
        tick, day = state.tick, state.day
        mortality_rng = state.rng.stream("mortality")

        for agent in list(state.agents.values()):
            if not agent.alive:
                continue

            before = agent.life_stage
            agent.age_days += 1
            after = agent.life_stage

            if after is not before:
                if after is LifeStage.ADULT:
                    employment.graduate(tick, agent)
                    state.events.record(
                        tick, day, EventType.GRADUATION,
                        f"{agent.name} balog'atga yetdi",
                        agent_ids=[agent.id],
                    )
                elif after is LifeStage.SENIOR and agent.employed:
                    employment.dismiss(tick, agent, state.buildings, "nafaqaga chiqdi")

            # Mortality is checked once a year, on the agent's birthday.
            if agent.age_days % 360 == 0 and agent.age_days > 0:
                state.events.record(
                    tick, day, EventType.BIRTHDAY,
                    f"{agent.name} — {int(agent.age_years)} yosh",
                    agent_ids=[agent.id],
                )
                risk = MORTALITY_BY_STAGE.get(agent.life_stage, 0.01)
                # Poor health raises the risk substantially.
                risk *= 1.0 + max(0.0, (60.0 - agent.needs.health) / 40.0)
                if mortality_rng.chance(min(0.9, risk)):
                    self._kill(agent)

    def _kill(self, agent: Agent) -> None:
        state = self.state
        agent.alive = False
        agent.died_tick = state.tick
        agent.activity = Activity.IDLE

        home = state.buildings.get(agent.home_id) if agent.home_id else None
        if home is not None:
            home.remove_resident(agent.id)
        if agent.workplace_id is not None:
            workplace = state.buildings.get(agent.workplace_id)
            if workplace is not None:
                workplace.dismiss(agent.id)

        state.families.handle_death(agent, state.agents, state.tick)
        state.events.record(
            state.tick, state.day, EventType.DEATH,
            f"{agent.name} vafot etdi ({int(agent.age_years)} yosh)",
            severity=Severity.NOTICE,
            agent_ids=[agent.id],
        )

    def _run_relationships(self) -> None:
        """Marriages and births, once a day."""
        state = self.state
        tick, day = state.tick, state.day

        for first, second, family in state.families.try_marriages(
            state.agents, tick, day, state.rng.stream("marriage")
        ):
            state.events.record(
                tick, day, EventType.WEDDING,
                f"{first.name} va {second.name} turmush qurdi",
                severity=Severity.NOTICE,
                agent_ids=[first.id, second.id],
                family_id=family.id,
            )

        for family in state.families.advance_planning(
            state.agents, day, state.rng.stream("births")
        ):
            child = state.agent_factory.create_child(
                surname=family.surname, parent_ids=list(family.partner_ids)
            )
            state.add_agent(child)
            state.families.register_child(family, child, state.agents, tick)

            home = state.buildings.get(family.home_id) if family.home_id else None
            if home is not None and home.add_resident(child.id):
                child.position = (float(home.entrance[0]), float(home.entrance[1]))
            else:
                # No room at home; housing allocation will place the family.
                child.home_id = None

            state.events.record(
                tick, day, EventType.BIRTH,
                f"{child.name} tug'ildi",
                severity=Severity.NOTICE,
                agent_ids=[child.id, *family.partner_ids],
                family_id=family.id,
            )

    def _settle_month(self) -> None:
        """Wages, taxes and upkeep."""
        state = self.state
        stats = state.stats

        retail = sum(
            building.retail_capacity
            for building in state.buildings.values()
            if building.is_open
        )
        business_revenue = retail * REVENUE_PER_RETAIL
        property_value = stats.housed * PROPERTY_VALUE_PER_RESIDENT

        result = state.economy.settle_month(
            state.day,
            public_wages=stats.public_wage_bill,
            private_wages=stats.private_wage_bill,
            business_revenue=business_revenue,
            property_value=property_value,
            upkeep=stats.total_upkeep,
            service_costs={},
        )

        net_rate = 1.0 - state.economy.taxes.income_tax
        for agent in state.living_agents:
            if agent.employed:
                behavior.apply_wage(agent, agent.salary * net_rate, state.tick)
            if agent.is_adult:
                behavior.charge_living_costs(agent, LIVING_COST)

        if result.budget < 0:
            state.events.record(
                state.tick, state.day, EventType.ECONOMIC_CRISIS,
                "Byudjet manfiy",
                severity=Severity.CRITICAL,
            )

    # -- agents ------------------------------------------------------------

    def _update_detail_levels(self) -> None:
        """
        Assigns simulation fidelity by distance from the camera.

        Re-evaluated every tick but the work is a cheap distance check; the
        expensive part is the behaviour it gates.
        """
        state = self.state
        cx, cy = state.camera_focus
        full = state.config.full_detail_radius
        reduced = state.config.reduced_detail_radius

        for agent in state.agents.values():
            if not agent.alive:
                continue

            if agent.id == state.followed_agent_id:
                wanted = DetailLevel.FULL
            else:
                dx = agent.position[0] - cx
                dy = agent.position[1] - cy
                distance = (dx * dx + dy * dy) ** 0.5
                if distance <= full:
                    wanted = DetailLevel.FULL
                elif distance <= reduced:
                    wanted = DetailLevel.REDUCED
                else:
                    wanted = DetailLevel.STATISTICAL

            if wanted is agent.detail:
                continue

            if agent.detail is DetailLevel.STATISTICAL and wanted is not DetailLevel.STATISTICAL:
                behavior.resume_full_detail(agent, state.buildings)
            agent.detail = wanted

    def _step_agents(self, *, minutes: float) -> None:
        state = self.state
        now = state.clock.now
        tick = state.tick
        weather_mood = state.weather.mood_effect
        laws = state.player.law_codes()

        # REDUCED agents are stepped every fourth tick, at four times the step,
        # so they cover the same ground for a quarter of the pathfinding cost.
        reduced_turn = tick % 4 == 0

        for agent in state.agents.values():
            if not agent.alive:
                continue

            if agent.detail is DetailLevel.FULL:
                behavior.step_agent(
                    agent, now=now, minutes=minutes, grid=state.grid,
                    buildings=state.buildings, paths=state.paths, tick=tick,
                    laws=laws,
                )
            elif agent.detail is DetailLevel.REDUCED:
                if reduced_turn:
                    behavior.step_agent(
                        agent, now=now, minutes=minutes * 4, grid=state.grid,
                        buildings=state.buildings, paths=state.paths, tick=tick,
                        laws=laws,
                    )
            else:
                behavior.step_statistically(agent, minutes=minutes)

            # Weather is felt only outdoors, and only by agents being simulated
            # in detail; statistical agents are assumed to be sheltered.
            if weather_mood and agent.detail is DetailLevel.FULL:
                if agent.activity in (Activity.COMMUTING, Activity.GOING_HOME, Activity.LEISURE):
                    agent.emotions.adjust(
                        **{name: value * minutes / 60.0 for name, value in weather_mood.items()}
                    )

    def _step_president(self, now) -> None:
        state = self.state
        president = state.president
        if president is None:
            return

        president.activity = president_schedule.activity_for(
            now, in_emergency=state.emergency is not None
        )
        location = president_schedule.location_for(
            now, in_emergency=state.emergency is not None
        )

        anchor_id = (
            president.palace_building_id
            if location == "palace"
            else president.office_building_id
        )
        anchor = state.buildings.get(anchor_id) if anchor_id else None
        if anchor is not None and location != "city":
            president.position = (float(anchor.entrance[0]), float(anchor.entrance[1]))

    # -- government --------------------------------------------------------

    def _govern(self, now) -> None:
        """Runs the decision engine when the schedule and interval allow."""
        state = self.state
        president = state.president
        if president is None:
            return

        if state.tick - self._last_decision_tick < DECISION_INTERVAL_MINUTES:
            return
        if not president_schedule.may_govern(now, in_emergency=state.emergency is not None):
            return

        self._last_decision_tick = state.tick
        if self._fulfill_standing_orders():
            return

        context = self._brain_context()

        for note in self.brain.review_outcomes(president, context):
            state.events.record(
                state.tick, state.day, EventType.DECISION_REVIEWED, note,
            )

        concerns = self.brain.assess(context)
        chosen = self.brain.choose(context, concerns)
        if chosen is None:
            return

        cost = self.brain.estimated_cost(chosen)
        affordable = cost <= self.brain.spendable_budget(state.economy)

        # A problem the city cannot pay for is worth recording once a day, not
        # at every decision slot — otherwise the decision history becomes an
        # unreadable wall of the same deferral.
        if not affordable:
            if self._deferred_on_day.get(chosen.code.value) == state.day:
                return
            self._deferred_on_day[chosen.code.value] = state.day

        decision = Decision(
            id=len(president.decisions) + 1,
            tick=state.tick,
            concern=chosen,
            status=DecisionStatus.APPROVED if affordable else DecisionStatus.DEFERRED,
            rationale=chosen.description,
            cost=0.0,
        )

        if affordable:
            executed = self._execute(chosen.action, decision)
            if not executed:
                decision.status = DecisionStatus.DEFERRED

        president.decisions.append(decision)
        president.memory.record(
            state.tick,
            MemoryKind.GOVERNMENT,
            f"{chosen.code}: {chosen.action.describe()} ({decision.status})",
            importance=0.5 + chosen.severity * 0.4,
            decision_id=decision.id,
        )

        state.events.record(
            state.tick, state.day, EventType.PRESIDENT_DECISION,
            f"{chosen.description} → {chosen.action.describe()}",
            severity=(
                Severity.WARNING if chosen.priority >= Priority.HIGH else Severity.INFO
            ),
            decision_id=decision.id,
            status=decision.status.value,
        )

    def _brain_context(self) -> BrainContext:
        state = self.state
        return BrainContext(
            tick=state.tick,
            day=state.day,
            stats=state.stats,
            economy=state.economy,
            buildings=state.buildings,
            grid_width=state.grid.width,
            grid_height=state.grid.height,
            max_grid_size=state.config.max_map_size,
            last_tax_change_day=state.last_tax_change_day,
            last_expansion_day=state.last_expansion_day,
            unlocked=state.unlocked,
            construction_slots=max(
                0,
                MAX_CONCURRENT_PROJECTS
                - sum(
                    1
                    for building in state.buildings.values()
                    if building.status is BuildingStatus.UNDER_CONSTRUCTION
                ),
            ),
            traffic_congestion=state.urban.estimate_road_traffic(
                state.grid, population=state.stats.population
            ),
            parking_shortage=state.urban.parking.analyse(
                population=state.stats.population,
                employed=state.stats.employed,
            )["shortage"],
            transit_route_count=len(state.urban.transport.routes),
        )

    def _execute(self, action: Action, decision: Decision) -> bool:
        """Carries out an approved action. Returns False if it could not run."""
        state = self.state

        if action.kind is ActionKind.BUILD:
            return self._execute_build(action, decision)

        if action.kind is ActionKind.RECRUIT_WORKERS:
            cost = self.brain.estimated_cost(decision.concern)
            if not state.economy.spend(cost, "recruitment"):
                return False
            decision.cost = cost
            for _ in range(action.quantity):
                agent = state.spawn_citizen(age_years=None)
                state.events.record(
                    state.tick, state.day, EventType.ARRIVED,
                    f"{agent.name} shaharga keldi",
                    agent_ids=[agent.id],
                )
            return True

        if action.kind is ActionKind.SET_TAX:
            return self._execute_tax(action, decision)

        if action.kind is ActionKind.ZONE_DISTRICT:
            return self._execute_zoning(action, decision)

        if action.kind is ActionKind.EXPAND_MAP:
            return self._execute_expansion(action, decision)

        # WAIT is a legitimate outcome, not a failure.
        return action.kind is ActionKind.WAIT

    def _execute_build(self, action: Action, decision: Decision, *, ignore_unlock: bool = False) -> bool:
        state = self.state
        self._last_build_reason = None
        if action.building_type is None:
            return False

        # A locked building type means the city is not developed enough yet.
        locked = action.building_type not in state.unlocked
        if locked and not ignore_unlock:
            return False

        # Building ahead of the development level is allowed but priced: the
        # expertise has to be brought in from outside.
        multiplier = EARLY_BUILD_PREMIUM if locked else 1.0

        centre = (state.grid.width // 2, state.grid.height // 2)
        started = 0

        for _ in range(action.quantity):
            result = state.construction.request(
                action.building_type,
                grid=state.grid,
                economy=state.economy,
                buildings=state.buildings,
                near=centre,
                cost_multiplier=multiplier,
            )
            if not result.approved:
                # The reason decides what the caller should try next: land can
                # be zoned, a full project queue can only be waited out.
                self._last_build_reason = result.reason
                break

            started += 1
            decision.cost += result.cost
            decision.created_building_ids.append(result.building.id)
            state.events.record(
                state.tick, state.day, EventType.BUILDING_STARTED,
                f"{building_label(action.building_type)} qurilishi boshlandi",
                building_ids=[result.building.id],
            )

        if started:
            state.invalidate_paths()
        return started > 0

    def _execute_tax(self, action: Action, decision: Decision) -> bool:
        state = self.state
        if action.tax_name is None or action.tax_value is None:
            return False

        value = min(MAX_TAX_RATE, max(MIN_TAX_RATE, action.tax_value))
        setattr(state.economy.taxes, action.tax_name, value)
        state.last_tax_change_day = state.day

        state.events.record(
            state.tick, state.day, EventType.POLICY_CHANGE,
            f"{action.tax_name}: {value:.1%}",
            severity=Severity.NOTICE,
        )
        if state.president is not None:
            state.president.memory.record(
                state.tick, MemoryKind.POLICY, f"{action.tax_name} → {value:.1%}",
                importance=0.7, rate=value,
            )
        return True

    def _execute_zoning(self, action: Action, decision: Decision) -> bool:
        """
        Zones a fresh block for the requested district.

        Looks for unzoned, unbuilt land near the city so new neighbourhoods
        attach to the existing one instead of appearing in the wilderness.
        """
        state = self.state
        district = action.district or District.RESIDENTIAL
        size = NEW_DISTRICT_SIZE

        plot = self._find_unzoned_block(size)
        if plot is None:
            return False

        cost = self.brain.estimated_cost(decision.concern)
        if not state.economy.spend(cost, "zoning"):
            return False

        decision.cost = cost
        plan = create_district_at_distance(
            state.grid,
            plot=plot,
            size=size,
            preferred=_district_to_zone(district),
            rng=state.rng.stream("urban"),
        )
        state.district_plans.append(plan)
        state.urban.refresh_from_grid(state.grid)
        state.invalidate_paths()

        state.events.record(
            state.tick, state.day, EventType.DISTRICT_OPENED,
            f"Yangi {zone_label(plan)} hududi ochildi",
            severity=Severity.NOTICE,
            x=plot[0], y=plot[1], size=size,
        )
        return True

    def _refresh_utilities(self) -> None:
        state = self.state
        stats = state.stats
        power_out = int(stats.power_coverage * max(1, stats.population) * 2)
        power_need = stats.power_needed or stats.population * 2 + len(state.buildings) * 5
        water_out = stats.population * 3
        water_need = stats.population * 2 + stats.housing_shortage
        state.urban.utilities.refresh(
            power_output=power_out,
            power_needed=power_need,
            water_output=water_out,
            water_needed=water_need,
        )
        if state.urban.utilities.blackout:
            state.events.record(
                state.tick,
                state.day,
                EventType.POWER_FAILURE,
                "Elektr yetishmovchiligi — blackout",
                severity=Severity.WARNING,
            )

    def _find_unzoned_block(self, size: int) -> tuple[int, int] | None:
        """Nearest square of unzoned, buildable land to the city centre."""
        state = self.state
        cx, cy = state.grid.width // 2, state.grid.height // 2
        best: tuple[float, int, int] | None = None

        # Step in strides: checking every tile of a 500x500 map would be slow
        # and a block-aligned search is what a planner would do anyway.
        stride = 4
        for y in range(0, state.grid.height - size, stride):
            for x in range(0, state.grid.width - size, stride):
                region = state.grid.region(x, y, size, size)
                if len(region) < size * size:
                    continue
                if any(
                    tile.district is not District.UNZONED
                    or tile.building_id is not None
                    or tile.type in (TileType.WATER, TileType.BUILDING)
                    for tile in region
                ):
                    continue
                distance = (x + size / 2 - cx) ** 2 + (y + size / 2 - cy) ** 2
                if best is None or distance < best[0]:
                    best = (distance, x, y)

        return (best[1], best[2]) if best else None

    def _execute_expansion(self, action: Action, decision: Decision) -> bool:
        state = self.state
        if action.new_width <= state.grid.width:
            return False

        cost = self.brain.estimated_cost(decision.concern)
        if not state.economy.spend(cost, "expansion"):
            return False

        decision.cost = cost
        expand_map_with_infrastructure(
            state.grid,
            new_width=action.new_width,
            new_height=action.new_height,
            rng=state.rng.stream("urban"),
        )
        state.urban.refresh_from_grid(state.grid)
        state.last_expansion_day = state.day
        state.invalidate_paths()

        state.events.record(
            state.tick, state.day, EventType.MAP_EXPANDED,
            f"Xarita kengaytirildi: {action.new_width}×{action.new_height}",
            severity=Severity.NOTICE,
        )
        return True

    # -- emergencies -------------------------------------------------------

    def _resolve_emergency(self) -> None:
        state = self.state
        if state.emergency is None:
            return
        if not state.emergency.expired(state.tick):
            return

        finished = state.emergency
        state.emergency = None
        if state.president is not None:
            state.president.emergency = None

        state.events.record(
            state.tick, state.day, EventType.EMERGENCY_ENDED,
            f"Favqulodda holat tugadi: {finished.type}",
            severity=Severity.NOTICE,
        )

    def declare_emergency(self, event_type: EventType, text: str, duration_minutes: int) -> None:
        """
        Puts the city into emergency mode (specification section 27).

        Exposed for the event system and for admin controls.
        """
        state = self.state
        state.emergency = Emergency(
            type=event_type,
            declared_tick=state.tick,
            duration_minutes=duration_minutes,
            text=text,
        )
        if state.president is not None:
            state.president.emergency = event_type.value
            state.president.memory.record(
                state.tick, MemoryKind.CRISIS, text, importance=1.0,
                event_type=event_type.value,
            )

        state.events.record(
            state.tick, state.day, EventType.EMERGENCY_DECLARED, text,
            severity=Severity.CRITICAL,
        )

    def ensure_player_identity(self) -> None:
        """The living president is always Umid Ravshanov — the human player."""
        state = self.state
        state.player.owner_name = "Umid Ravshanov"
        president = state.president
        if president is None:
            return
        president.name = "Umid Ravshanov"
        president.gender = Gender.MALE
        president.avatar_seed = "president-umid-ravshanov"
        appearance = dict(president.appearance or {})
        appearance["gender"] = Gender.MALE.value
        appearance.setdefault("clothingStyle", "business")
        president.appearance = appearance

    def set_player_role(self, role: str) -> dict:
        try:
            self.state.player.role = PlayerRole(role)
        except ValueError:
            raise ValueError("Noma'lum lavozim") from None
        return self.state.player.as_dict()

    def handle_player_command(
        self,
        text: str,
        agent_id: int | None = None,
        upload_path: str | None = None,
        filename: str | None = None,
    ) -> dict:
        """
        Routes a decree to the matching desk, or to the prime minister if
        nobody can do the work yet.
        """
        state = self.state
        player = state.player
        raw = (text or "").strip()
        parsed = parse_command(raw)
        routed = classify_work(raw, filename or "")

        if parsed.kind == "empty" and not upload_path:
            return {"ok": False, "reply": parsed.reply, "player": player.as_dict()}

        # A law outranks a personal order even when it reads like one. "Qonun:
        # ishchi yoshdagi hamma majburiy ishlasin" contains "ishla", so the
        # activity branch used to swallow it and the law was never filed.
        if routed.kind is LedgerKind.LAW:
            return self._enact_law(raw, routed)

        # Vague build/hire orders fail; desk tasks (elektr, video, hisob…) route
        # to the cabinet even when parse_command has no direct action.
        if parsed.kind == "unknown" and not upload_path and routed.desk is Desk.GENERAL:
            player.remember(state.tick, raw, parsed.reply)
            return {"ok": False, "reply": parsed.reply, "player": player.as_dict()}

        if parsed.kind == "zone" and parsed.action is not None:
            reply = self._apply_zone(parsed.action)
            self._file_decree(raw, reply)
            player.remember(state.tick, raw, reply)
            state.events.record(
                state.tick, state.day, EventType.PLAYER_COMMAND,
                f"Qaror: {raw} — {reply}",
            )
            return {"ok": not _command_failed(reply), "reply": reply, "player": player.as_dict()}

        if parsed.kind in ("agent_activity", "agent_clear"):
            reply = self._apply_parsed(parsed, agent_id=agent_id, note=raw)
            player.remember(state.tick, raw, reply)
            return {"ok": True, "reply": reply, "player": player.as_dict()}

        executable = parsed.kind in ("tax", "build", "hire", "recruit", "expand")
        if executable:
            reply = self._apply_parsed(parsed, agent_id=agent_id, note=raw)
            self._file_decree(raw, reply)
            player.remember(state.tick, raw, reply)
            state.events.record(
                state.tick, state.day, EventType.PLAYER_COMMAND,
                f"Qaror: {raw} — {reply}",
            )
            return {"ok": not _command_failed(reply), "reply": reply, "player": player.as_dict()}

        return self._assign_task(
            raw or (filename or "Fayl topshirig'i"),
            routed,
            agent_id=agent_id,
            upload_path=upload_path,
            filename=filename,
        )

    def _fulfill_standing_orders(self) -> bool:
        """Carries out one queued brief. Returns True if the AI should skip this slot."""
        state = self.state
        pending = state.player.pending()
        if not pending:
            return False

        order = pending[0]
        result = self.handle_player_command(order.text)
        order.done = True
        order.result = result.get("reply", "")
        return True

    def _file_decree(self, text: str, result: str) -> LedgerItem:
        player = self.state.player
        item = LedgerItem(
            id=player.next_ledger_id(),
            kind=LedgerKind.DECREE,
            desk=Desk.GENERAL,
            title=text[:72] or "Qaror",
            text=text,
            status=TaskStatus.DONE,
            created_tick=self.state.tick,
            created_day=self.state.day,
            updated_tick=self.state.tick,
            result=result,
            progress=1.0,
        )
        item.note(self.state.tick, self.state.day, result)
        return player.file_item(item)

    def _enact_law(self, text: str, routed) -> dict:
        state = self.state
        player = state.player
        item = LedgerItem(
            id=player.next_ledger_id(),
            kind=LedgerKind.LAW,
            desk=Desk.LEGAL,
            title=routed.title,
            text=text,
            status=TaskStatus.DONE,
            created_tick=state.tick,
            created_day=state.day,
            updated_tick=state.tick,
            result="Qonun kuchga kirdi — fuqarolar va agentlar amal qiladi.",
            progress=1.0,
            law_code=routed.law_code,
        )
        lawyer = self._find_specialist(Desk.LEGAL)
        created = False
        if lawyer is None:
            item.note(state.tick, state.day, "Yurist yo'q — dasturchi agent modulini yozadi.")
            self._begin_coding(item, Desk.LEGAL)
            created = True
            reply = f"Qonun #{item.id} kuchga kirdi. Dasturchi yurist agentini kod bilan yozmoqda."
        else:
            item.agent_id = lawyer.id
            item.agent_name = lawyer.name
            lawyer.player_order = Activity.WORKING.value
            lawyer.player_order_note = text
            item.note(state.tick, state.day, f"{lawyer.name} qonunni e'lon qildi.")
            reply = f"Qonun #{item.id} kuchga kirdi — {lawyer.name} mas'ul."
        player.file_item(item)
        player.remember(state.tick, text, reply)
        state.events.record(state.tick, state.day, EventType.POLICY_CHANGE, reply)
        return {"ok": True, "reply": reply, "player": player.as_dict()}

    def _assign_task(
        self,
        text: str,
        routed,
        *,
        agent_id: int | None,
        upload_path: str | None,
        filename: str | None,
    ) -> dict:
        state = self.state
        player = state.player
        item = LedgerItem(
            id=player.next_ledger_id(),
            kind=LedgerKind.TASK,
            desk=routed.desk,
            title=routed.title,
            text=text,
            status=TaskStatus.WAITING_AGENT,
            created_tick=state.tick,
            created_day=state.day,
            updated_tick=state.tick,
            input_file=filename or "",
            upload_path=upload_path or "",
        )

        agent = None
        if agent_id is not None:
            agent = state.agents.get(agent_id)
            if agent is not None and agent.alive:
                agent.desk = agent.desk or routed.desk.value

        if agent is None:
            agent = self._find_specialist(routed.desk)

        if agent is None:
            coder = self._ensure_coder()
            item.note(
                state.tick, state.day,
                f"Bunday agent yo'q. Dasturchi {coder.name} `{module_filename(routed.desk)}` yozmoqda.",
            )
            self._begin_coding(item, routed.desk)
            player.file_item(item)
            reply = (
                f"#{item.id} bosh vazirga tushdi. "
                f"Dasturchi {coder.name} yangi {routed.desk.value} agentini kod bilan yozmoqda."
            )
            player.remember(state.tick, text, reply)
            state.events.record(state.tick, state.day, EventType.PLAYER_COMMAND, reply)
            return {"ok": True, "reply": reply, "player": player.as_dict(), "task": item.as_dict()}

        item.agent_id = agent.id
        item.agent_name = agent.name
        item.status = TaskStatus.IN_PROGRESS
        agent.player_order = Activity.WORKING.value
        agent.player_order_note = text
        agent.desk = routed.desk.value
        item.note(state.tick, state.day, f"Topshiriq {agent.name}ga tushdi.")

        self._perform_desk_work(item, upload_path=upload_path, filename=filename)
        player.file_item(item)
        reply = f"#{item.id} {agent.name}ga tushdi ({routed.desk.value}). {item.result}".strip()
        player.remember(state.tick, text, reply)
        state.events.record(state.tick, state.day, EventType.PLAYER_COMMAND, reply)
        return {"ok": True, "reply": reply, "player": player.as_dict(), "task": item.as_dict()}

    def _find_specialist(self, desk: Desk):
        profession = DESK_PROFESSION[desk]
        by_desk = None
        by_job = None
        for agent in self.state.living_agents:
            if not agent.is_adult:
                continue
            if agent.desk == "coder":
                continue
            if agent.desk == desk.value:
                by_desk = agent
                break
            if agent.profession is profession and by_job is None:
                by_job = agent
        return by_desk or by_job

    def _ensure_coder(self):
        """The other agent — a living developer who writes specialist modules."""
        for agent in self.state.living_agents:
            if agent.desk == "coder" and agent.alive:
                return agent
        developers = [
            agent for agent in self.state.living_agents
            if agent.alive and agent.profession is Profession.DEVELOPER
        ]
        if developers:
            coder = developers[0]
            coder.desk = "coder"
            return coder
        spec = PROFESSIONS[Profession.DEVELOPER]
        coder = self.state.spawn_citizen(age_years=31.0)
        if coder.education < spec.education:
            coder.education = spec.education
        coder.skills[spec.key_skill] = max(coder.skill_for(spec.key_skill), 92.0)
        coder.profession = Profession.DEVELOPER
        coder.desk = "coder"
        coder.player_order = Activity.WORKING.value
        coder.player_order_note = "agent moduli yozilmoqda"
        employment.hire_specialist(
            self.state.tick, coder, Profession.DEVELOPER, self.state.buildings,
        )
        return coder

    def _begin_coding(self, item: LedgerItem, desk: Desk) -> CodingJob:
        state = self.state
        coder = self._ensure_coder()
        filename = module_filename(desk)
        source = generate_agent_source(
            desk=desk,
            coder_name=coder.name,
            day=state.day,
            task_text=item.text,
            agent_hint=item.title,
        )
        job = CodingJob(
            coder_id=coder.id,
            coder_name=coder.name,
            desk=desk.value,
            task_id=item.id,
            filename=filename,
            source=source,
        )
        state.player.coding = job
        coder.player_order = Activity.WORKING.value
        coder.player_order_note = f"{filename} yozilmoqda"
        if item.status is not TaskStatus.DONE:
            item.status = TaskStatus.WAITING_AGENT
        item.created_specialist = True
        item.note(state.tick, state.day, f"{coder.name} kod yozishni boshladi: workshop/{filename}")
        return job

    def _advance_coding(self) -> None:
        job = self.state.player.coding
        if job is None or job.done:
            self._start_queued_coding()
            # A finished module sitting in the HUD looks like the city froze.
            if self.state.player.coding is not None and self.state.player.coding.done:
                self.state.player.coding = None
            return
        job.typed = min(len(job.source), job.typed + CHARS_PER_TICK)
        coder = self.state.agents.get(job.coder_id)
        if coder is not None and coder.alive:
            coder.player_order = Activity.WORKING.value
            coder.player_order_note = f"{job.filename} {job.typed}/{len(job.source)}"
        if job.typed >= len(job.source):
            self._finish_coding_job(job)

    def _start_queued_coding(self) -> None:
        player = self.state.player
        if player.coding is not None and not player.coding.done:
            return
        waiting = [
            item for item in player.tasks + player.laws
            if item.created_specialist and item.agent_id is None
            and item.status is TaskStatus.WAITING_AGENT
        ]
        if not waiting:
            return
        item = waiting[0]
        try:
            desk = Desk(item.desk) if not isinstance(item.desk, Desk) else item.desk
        except ValueError:
            desk = Desk.GENERAL
        self._begin_coding(item, desk)

    def _finish_coding_job(self, job: CodingJob) -> None:
        state = self.state
        module, path = write_and_load(job.filename, job.source)
        job.path = str(path)
        job.done = True
        spec = module.spawn_spec() if hasattr(module, "spawn_spec") else {"desk": job.desk}
        agent = self._spawn_from_module(spec, job)
        item = next(
            (entry for entry in state.player.tasks + state.player.laws if entry.id == job.task_id),
            None,
        )
        if item is None:
            return
        item.agent_id = agent.id
        item.agent_name = agent.name
        item.note(
            state.tick, state.day,
            f"{job.coder_name} faylni saqladi: {path.name}\n"
            f"Modul yuklandi. Yangi agent: {agent.name}.",
        )
        if item.kind is LedgerKind.LAW:
            item.status = TaskStatus.DONE
            return
        item.status = TaskStatus.IN_PROGRESS
        agent.player_order = Activity.WORKING.value
        agent.player_order_note = item.text
        item.note(state.tick, state.day, f"Topshiriq {agent.name}ga tushdi.")
        self._perform_desk_work(
            item, upload_path=item.upload_path or None, filename=item.input_file or None,
        )

    def _spawn_from_module(self, spec: dict, job: CodingJob):
        try:
            profession = profession_from_spec(spec)
        except ValueError:
            profession = DESK_PROFESSION.get(Desk(job.desk), Profession.MANAGER)
        catalog = PROFESSIONS[profession]
        agent = self.state.spawn_citizen(age_years=float(spec.get("age_years", 34.0)))
        if agent.education < catalog.education:
            agent.education = catalog.education
        skill = float(spec.get("skill", 90.0))
        agent.skills[catalog.key_skill] = max(agent.skill_for(catalog.key_skill), skill)
        agent.desk = str(spec.get("desk", job.desk))
        agent.profession = profession
        employment.hire_specialist(self.state.tick, agent, profession, self.state.buildings)
        agent.player_order = Activity.WORKING.value
        agent.player_order_note = spec.get("label", job.desk)
        agent.memory.record(
            self.state.tick,
            MemoryKind.WORK,
            f"Moduldan yaratildi: {job.filename} ({job.coder_name})",
            importance=0.9,
        )
        return agent

    def _create_specialist(self, desk: Desk):
        profession = DESK_PROFESSION[desk]
        spec = PROFESSIONS[profession]
        agent = self.state.spawn_citizen(age_years=34.0)
        if agent.education < spec.education:
            agent.education = spec.education
        agent.skills[spec.key_skill] = max(agent.skill_for(spec.key_skill), 90.0)
        agent.desk = desk.value
        agent.profession = profession
        employment.hire_specialist(self.state.tick, agent, profession, self.state.buildings)
        agent.player_order = Activity.WORKING.value
        agent.player_order_note = f"{desk.value} stoli"
        return agent, specialist_blueprint(desk, profession)

    def _perform_desk_work(
        self,
        item: LedgerItem,
        *,
        upload_path: str | None,
        filename: str | None,
    ) -> None:
        from pathlib import Path

        state = self.state
        if upload_path:
            source = Path(upload_path)
            if source.exists():
                out_name, result = process_desk_file(
                    item.desk.value, source, item.text, f"t{item.id}",
                )
                item.output_file = out_name
                item.result = result
                item.progress = 1.0
                item.status = TaskStatus.DONE
                item.note(state.tick, state.day, result)
                return

        if item.desk is Desk.ELECTRICITY:
            self._sync_electricity_task(item, force_retry=True)
            return

        if item.desk is Desk.ACCOUNTING:
            stats = state.stats
            name = write_budget_report(
                f"t{item.id}",
                [
                    ("kun", str(state.day)),
                    ("byudjet", f"{state.economy.budget:.0f}"),
                    ("yaIM", f"{state.economy.gdp:.0f}"),
                    ("aholi", str(stats.population)),
                    ("ishsizlik", f"{stats.unemployment_rate:.3f}"),
                    ("mamnunlik", f"{stats.happiness:.1f}"),
                ],
            )
            item.output_file = name
            item.result = "Hisobot CSV tayyor."
            item.progress = 1.0
            item.status = TaskStatus.DONE
            item.note(state.tick, state.day, item.result)
            return

        if item.desk is Desk.CONSTRUCTION:
            parsed = parse_command(item.text)
            if parsed.kind == "build" and parsed.action is not None:
                started: list[int] = []
                reply = self._apply_player_build(parsed.action, into=started)
                item.created_building_ids.extend(started)
                item.result = reply
                item.progress = 1.0 if "boshlandi" in reply else 0.3
                item.status = TaskStatus.DONE if item.progress >= 1 else TaskStatus.IN_PROGRESS
                item.note(state.tick, state.day, reply)
                return

        body = (
            f"Topshiriq: {item.text}\n"
            f"Stol: {item.desk.value}\n"
            f"Kun: {state.day}\n"
            f"Natija: mutaxassis ishni yozma hisobot bilan yakunladi."
        )
        item.output_file = write_work_note(f"t{item.id}", item.title or "Hisobot", body)
        item.result = "Hisobot tayyor."
        item.progress = 1.0
        item.status = TaskStatus.DONE
        item.note(state.tick, state.day, item.result)

    def _advance_cabinet_tasks(self) -> None:
        """Keeps every open player task moving — not only the first, not only on govern."""
        self._attach_player_plants()
        for building in self._boost_player_construction():
            self._record_building_opened(building)
        for item in list(self.state.player.tasks):
            if item.status not in (TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED):
                continue
            if item.desk is Desk.ELECTRICITY:
                self._sync_electricity_task(item, force_retry=False)
                continue
            if item.desk is Desk.CONSTRUCTION and item.created_building_ids:
                self._sync_construction_task(item)
                continue
            # File/report desks should already have finished in _perform_desk_work.
            # If they are still open, produce a written result instead of idling.
            if item.progress < 1.0 and not item.output_file:
                self._perform_desk_work(
                    item,
                    upload_path=item.upload_path or None,
                    filename=item.input_file or None,
                )

    def _attach_player_plants(self) -> None:
        plants = [
            building for building in self.state.buildings.values()
            if building.type is BuildingType.POWER_PLANT
        ]
        if not plants:
            return
        pick = next(
            (building for building in plants if building.status is BuildingStatus.UNDER_CONSTRUCTION),
            plants[0],
        )
        for item in self.state.player.tasks:
            if item.desk is Desk.ELECTRICITY and item.status in (
                TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED,
            ):
                if not item.created_building_ids:
                    item.created_building_ids.append(pick.id)

    def _sync_electricity_task(self, item: LedgerItem, *, force_retry: bool = False) -> None:
        state = self.state
        plants = [
            building for building in state.buildings.values()
            if building.type is BuildingType.POWER_PLANT
        ]
        tracked = [
            state.buildings[bid]
            for bid in item.created_building_ids
            if bid in state.buildings
        ] or plants

        open_plants = [building for building in tracked if building.is_open]
        if open_plants:
            self._touch_task(
                item,
                status=TaskStatus.DONE,
                progress=1.0,
                result="Elektr stansiya ishlayapti.",
                note="Elektr stansiya ochildi.",
            )
            return

        building = next(
            (entry for entry in tracked if entry.status is BuildingStatus.UNDER_CONSTRUCTION),
            tracked[0] if tracked else None,
        )
        if building is not None:
            if building.id not in item.created_building_ids:
                item.created_building_ids.append(building.id)
            ratio = building.progress_days / max(1.0, float(building.spec.build_days))
            self._touch_task(
                item,
                status=TaskStatus.IN_PROGRESS,
                progress=min(0.99, max(0.2, ratio)),
                result=f"Qurilish {ratio:.0%}.",
                note=f"Qurilish {ratio:.0%}.",
            )
            return

        last = item.updated_tick or item.created_tick
        if not force_retry and state.tick - last < 60:
            return

        # A cabinet electricity order is city infrastructure, not a luxury
        # decree: if the treasury is empty the plant still has to start, or the
        # task sits on "yer yoki pul" forever.
        cost = self.player_build_cost(BuildingType.POWER_PLANT, 1)
        gap = cost - state.economy.budget
        if gap > 0:
            state.economy.receive(gap)

        started: list[int] = []
        reply = self._apply_player_build(
            Action(kind=ActionKind.BUILD, building_type=BuildingType.POWER_PLANT, quantity=1),
            ignore_unlock=True,
            district=District.INDUSTRIAL,
            into=started,
        )
        item.created_building_ids.extend(bid for bid in started if bid not in item.created_building_ids)
        if started:
            self._touch_task(
                item,
                status=TaskStatus.IN_PROGRESS,
                progress=0.2,
                result=reply,
                note=reply,
            )
            return
        self._touch_task(
            item,
            status=TaskStatus.BLOCKED,
            progress=max(item.progress, 0.1),
            result=reply,
            note=reply,
        )

    def _sync_construction_task(self, item: LedgerItem) -> None:
        buildings = [
            self.state.buildings[bid]
            for bid in item.created_building_ids
            if bid in self.state.buildings
        ]
        if not buildings:
            return
        if all(building.is_open for building in buildings):
            self._touch_task(
                item,
                status=TaskStatus.DONE,
                progress=1.0,
                result="Qurilish tugadi.",
                note="Binolar ochildi.",
            )
            return
        ratios = [
            building.progress_days / max(1.0, float(building.spec.build_days))
            for building in buildings
        ]
        ratio = sum(ratios) / len(ratios)
        self._touch_task(
            item,
            status=TaskStatus.IN_PROGRESS,
            progress=min(0.99, ratio),
            result=f"Qurilish {ratio:.0%}.",
            note=f"Qurilish {ratio:.0%}.",
        )

    def _touch_task(
        self,
        item: LedgerItem,
        *,
        status: TaskStatus,
        progress: float,
        result: str,
        note: str,
    ) -> None:
        changed = (
            item.status is not status
            or abs(item.progress - progress) >= 0.05
            or item.result != result
        )
        item.status = status
        item.progress = progress
        item.result = result
        if changed:
            item.note(self.state.tick, self.state.day, note)

    def _record_building_opened(self, building) -> None:
        state = self.state
        state.events.record(
            state.tick, state.day, EventType.BUILDING_COMPLETE,
            f"{building_label(building.type)} ochildi",
            severity=Severity.NOTICE,
            building_ids=[building.id],
        )
        if building.type is BuildingType.BUS_STOP:
            centre = state.grid.width // 2, state.grid.height // 2
            state.urban.transport.add_route(
                f"Marshrut #{len(state.urban.transport.routes) + 1}",
                [(building.x, building.y), centre],
                [building.spec.district],
            )
            state.urban.transport.stops.append(
                BusStop(
                    building_id=building.id,
                    x=building.x,
                    y=building.y,
                    name=f"Bekat #{building.id}",
                )
            )
        if state.president is not None:
            state.president.memory.record(
                state.tick,
                MemoryKind.DEVELOPMENT,
                f"{building_label(building.type)} qurib bitirildi",
                importance=0.6, building_id=building.id,
            )
        state.invalidate_paths()

    def _boost_player_construction(self):
        """Presidential projects do not wait 35 days with zero builders."""
        if self._last_player_build_boost_day == self.state.day:
            return []
        ids: set[int] = set()
        for item in self.state.player.tasks:
            if item.status in (TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED):
                ids.update(item.created_building_ids)
        if not ids:
            return []
        self._last_player_build_boost_day = self.state.day
        opened = []
        for building_id in ids:
            building = self.state.buildings.get(building_id)
            if building is None or building.status is not BuildingStatus.UNDER_CONSTRUCTION:
                continue
            building.progress_days += max(
                1.0,
                float(building.spec.build_days) * PLAYER_BUILD_DAILY_FRACTION,
            )
            if building.progress_days >= building.spec.build_days:
                building.status = BuildingStatus.OPEN
                building.opened_tick = self.state.tick
                opened.append(building)
        return opened

    def player_build_cost(self, building_type: BuildingType, quantity: int) -> float:
        """
        What a player decree would actually cost, premium included.

        This used to top the treasury up by whatever was missing, which made
        every decree succeed and the budget decorative — the opposite of
        specification 11, where a bad decision has to be able to cost the city
        money. Now the price is reported and the decree can be refused.
        """
        multiplier = (
            EARLY_BUILD_PREMIUM if building_type not in self.state.unlocked else 1.0
        )
        return CATALOG[building_type].construction_cost * multiplier * max(1, quantity)

    def _apply_parsed(self, parsed, *, agent_id: int | None, note: str) -> str:
        if parsed.kind == "tax" and parsed.action is not None:
            return self._apply_tax_delta(parsed.action.tax_value or 0.0)

        if parsed.kind == "build" and parsed.action is not None:
            return self._apply_player_build(parsed.action)

        if parsed.kind == "recruit":
            qty = max(1, min(20, parsed.quantity))
            names: list[str] = []
            for _ in range(qty):
                names.append(self.state.spawn_citizen().name)
            return f"{qty} kishi chaqirildi: {', '.join(names[:4])}."

        if parsed.kind == "hire" and parsed.profession is not None:
            return self._hire_profession(parsed.profession, parsed.quantity, note)

        if parsed.kind == "agent_activity":
            return self._order_agents(parsed.activity, note, agent_id, clear=False)

        if parsed.kind == "agent_clear":
            return self._order_agents(None, "", agent_id, clear=True)

        if parsed.kind == "expand" and parsed.action is not None:
            state = self.state
            grown = min(state.config.max_map_size, state.grid.width + 40)
            expand = Action(kind=ActionKind.EXPAND_MAP, new_width=grown, new_height=grown)
            decision = self._player_decision("Xarita kengaytirish", expand)
            if self._execute_expansion(expand, decision):
                self._record_player_decision(decision)
                state.invalidate_paths()
                return f"Xarita {grown}×{grown} ga kengaydi."
            return "Xarita kengaytirilmadi — chegaraga yetildi yoki byudjet yetmaydi."

        return parsed.reply

    def _apply_zone(self, action: Action) -> str:
        decision = self._player_decision("Turar-joy mahallasi ochilsin", action)
        if self._execute_zoning(action, decision):
            self._record_player_decision(decision)
            return "Yangi turar-joy mahallasi ochildi — yo'llar va zona tayyor."
        state = self.state
        if state.grid.width < state.config.max_map_size:
            grown = min(state.config.max_map_size, state.grid.width + 40)
            expand = Action(kind=ActionKind.EXPAND_MAP, new_width=grown, new_height=grown)
            expand_decision = self._player_decision("Xarita kengaytirish", expand)
            if self._execute_expansion(expand, expand_decision):
                self._record_player_decision(expand_decision)
                if self._execute_zoning(action, decision):
                    self._record_player_decision(decision)
                    return "Xarita kengaydi va yangi turar-joy mahallasi ochildi."
        return "Mahalla ochilmadi — bo'sh yer yoki byudjet yetmayapti."

    def _apply_tax_delta(self, delta: float) -> str:
        current = self.state.economy.taxes.income_tax
        value = min(MAX_TAX_RATE, max(MIN_TAX_RATE, current + delta))
        action = Action(kind=ActionKind.SET_TAX, tax_name="income_tax", tax_value=value)
        decision = self._player_decision(f"Soliq {current:.0%} → {value:.0%}", action)
        if not self._execute_tax(action, decision):
            return "Soliqni o'zgartirib bo'lmadi."
        self._record_player_decision(decision)
        return f"Daromad solig'i {value:.0%}."

    def _apply_player_build(
        self,
        action: Action,
        *,
        ignore_unlock: bool = False,
        district: District | None = None,
        into: list[int] | None = None,
    ) -> str:
        if action.building_type is None:
            return "Qaysi bino ekanligi noma'lum."

        name = building_label(action.building_type)
        state = self.state
        # The player is the president: a decree is not refused for being early,
        # it is charged the premium. Only money and land can stop it.
        early = action.building_type not in state.unlocked
        unit_cost = self.player_build_cost(action.building_type, 1)
        if not state.economy.can_afford(unit_cost):
            if early:
                return (
                    f"{name} shahar darajasidan yuqori — muddatidan oldin qurish "
                    f"{EARLY_BUILD_PREMIUM:.1f} barobar qimmat "
                    f"({unit_cost:,.0f}), byudjet yetmaydi."
                )
            return f"{name} uchun byudjet yetmaydi ({unit_cost:,.0f} kerak)."

        premium_note = (
            f" Muddatidan oldin qurilgani uchun narx {EARLY_BUILD_PREMIUM:.1f} barobar."
            if early
            else ""
        )

        decision = self._player_decision(f"{action.quantity} ta {name} qurilsin", action)
        ignore_unlock = True

        def _started(reply: str) -> str:
            if into is not None:
                into.extend(decision.created_building_ids)
            return reply

        if self._execute_build(action, decision, ignore_unlock=ignore_unlock):
            self._record_player_decision(decision)
            return _started(
                f"{len(decision.created_building_ids)} ta {name} qurilishi boshlandi."
                + premium_note
            )

        # Zoning and expansion only help when land is what is missing. A full
        # project queue used to send the city into pointless map growth on every
        # refused decree.
        if self._last_build_reason is RejectionReason.TOO_MANY_PROJECTS:
            in_flight = sum(
                1
                for building in state.buildings.values()
                if building.status is BuildingStatus.UNDER_CONSTRUCTION
            )
            return (
                f"Qurilish navbati to'la: {in_flight} loyiha ketmoqda. "
                f"{name} ular tugagach boshlanadi."
            )
        if self._last_build_reason is RejectionReason.NO_BUDGET:
            return f"{name} uchun byudjet yetmaydi ({unit_cost:,.0f} kerak)."

        zone_district = district or District.RESIDENTIAL
        zone_action = Action(kind=ActionKind.ZONE_DISTRICT, district=zone_district)
        zone_decision = self._player_decision(f"Yangi {zone_district} hududi", zone_action)
        zoned = self._execute_zoning(zone_action, zone_decision)
        if zoned:
            self._record_player_decision(zone_decision)
            if self._execute_build(action, decision, ignore_unlock=ignore_unlock):
                self._record_player_decision(decision)
                count = len(decision.created_building_ids)
                return _started(
                    f"Yangi hudud ochildi va {count} ta {name} qurilishi boshlandi."
                    + premium_note
                )
        for _ in range(2):
            if not self._expand_for_player(decision):
                break
            if self._execute_build(action, decision, ignore_unlock=ignore_unlock):
                self._record_player_decision(decision)
                return _started(
                    f"Xarita kengaytirildi va "
                    f"{len(decision.created_building_ids)} ta {name} qurilishi boshlandi."
                    + premium_note
                )
        return f"{name} uchun bo'sh yer topilmadi — hudud ham, kengaytirish ham yetmadi."

    def _expand_for_player(self, decision: Decision) -> bool:
        state = self.state
        step = 20
        new_w = min(state.config.max_map_size, state.grid.width + step)
        new_h = min(state.config.max_map_size, state.grid.height + step)
        if new_w <= state.grid.width:
            return False
        expand = Action(kind=ActionKind.EXPAND_MAP, new_width=new_w, new_height=new_h)
        return self._execute_expansion(expand, decision)

    def _hire_profession(self, profession: Profession, quantity: int, note: str) -> str:
        spec = PROFESSIONS[profession]
        job = profession_label(profession)
        qty = max(1, min(20, quantity))
        hired: list[str] = []
        waiting: list[str] = []
        for _ in range(qty):
            agent = self.state.spawn_citizen(age_years=32.0)
            if agent.education < spec.education:
                agent.education = spec.education
            agent.skills[spec.key_skill] = max(agent.skill_for(spec.key_skill), 88.0)
            agent.player_order = Activity.SEEKING_JOB.value
            agent.player_order_note = note or f"{job} bo'lib ishla"
            placed = employment.hire_specialist(
                self.state.tick, agent, profession, self.state.buildings,
            )
            if placed is not None:
                hired.append(agent.name)
                agent.player_order = Activity.WORKING.value
            else:
                waiting.append(agent.name)
        bits: list[str] = []
        if hired:
            bits.append(f"ishga olindi: {', '.join(hired)}")
        if waiting:
            bits.append(f"bo'sh joy kutmoqda: {', '.join(waiting)}")
        return f"{job} — " + "; ".join(bits)

    def _order_agents(
        self,
        activity: str | None,
        note: str,
        agent_id: int | None,
        *,
        clear: bool,
    ) -> str:
        state = self.state
        if agent_id is not None:
            agent = state.agents.get(agent_id)
            if agent is None or not agent.alive:
                return "Agent topilmadi. Avval odamni bosing."
            targets = [agent]
        else:
            targets = [agent for agent in state.living_agents if agent.is_adult][:12]
            if not targets:
                return "Buyruq beriladigan agent yo'q."

        for agent in targets:
            if clear:
                agent.player_order = None
                agent.player_order_note = ""
            else:
                agent.player_order = activity
                agent.player_order_note = note

        names = ", ".join(agent.name for agent in targets[:3])
        extra = f" va yana {len(targets) - 3}" if len(targets) > 3 else ""
        if clear:
            return f"Buyruq bekor: {names}{extra}."
        return f"{names}{extra} — {activity}."

    def _player_decision(self, description: str, action: Action) -> Decision:
        president = self.state.president
        return Decision(
            id=(len(president.decisions) + 1) if president else 1,
            tick=self.state.tick,
            concern=Concern(
                code=ConcernCode.PLAYER_DECREE,
                severity=0.6,
                description=description,
                action=action,
            ),
            status=DecisionStatus.APPROVED,
            rationale=description,
        )

    def _record_player_decision(self, decision: Decision) -> None:
        president = self.state.president
        if president is None:
            return
        president.decisions.append(decision)
        president.memory.record(
            self.state.tick,
            MemoryKind.GOVERNMENT,
            decision.rationale,
            importance=0.75,
            decision_id=decision.id,
        )
