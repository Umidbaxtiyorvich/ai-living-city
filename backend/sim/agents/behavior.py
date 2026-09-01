"""
Agent behaviour.

Each agent picks an intention, walks to the building that satisfies it, and is
rewarded while it is there. Intentions come from three sources, in order of
authority:

1. **Urgent needs** — a need in the danger zone overrides everything.
2. **The clock** — sleep at night, work in working hours, school by day.
3. **Emotional bias** — what to do with free time.

That ordering is what keeps behaviour legible: an exhausted agent goes home even
during working hours, but a merely bored one still shows up to work.
"""

from __future__ import annotations

from ..buildings.catalog import BuildingCategory
from ..buildings.models import Building
from ..clock import MINUTES_PER_HOUR, TimeOfDay
from ..memory.model import MemoryKind
from ..pathfinding.astar import PathCache
from ..world.tiles import Grid
from .models import Activity, Agent, DetailLevel, Needs

#: Tiles an agent covers per simulated minute. ~8 km/h — clearly visible on the map.
WALK_SPEED_PER_MINUTE = 0.28

#: Need recovery per hour spent in the right place.
RECOVERY = {
    Activity.SLEEPING: {"energy": 12.0, "hygiene": -0.5},
    Activity.EATING: {"hunger": 40.0},
    Activity.SHOPPING: {"hunger": 22.0, "fun": 6.0},
    Activity.LEISURE: {"fun": 18.0, "social": 6.0},
    Activity.SOCIALISING: {"social": 24.0, "fun": 8.0},
    Activity.AT_HOSPITAL: {"health": 20.0},
    Activity.AT_SCHOOL: {"social": 6.0, "fun": 2.0},
    Activity.WORKING: {"social": 3.0, "fun": -2.0},
}

#: Which building category satisfies which intention.
VENUE_FOR: dict[Activity, tuple[BuildingCategory, ...]] = {
    Activity.SHOPPING: (BuildingCategory.BUSINESS,),
    Activity.LEISURE: (BuildingCategory.ENTERTAINMENT,),
    Activity.SOCIALISING: (BuildingCategory.BUSINESS, BuildingCategory.ENTERTAINMENT),
    Activity.AT_HOSPITAL: (BuildingCategory.HEALTH,),
}

#: Health below this sends an agent to a clinic.
HEALTH_ALARM = 45.0

#: Simulated minutes between physiological updates.
#:
#: Needs and emotions move on the scale of hours, so recomputing them every
#: simulated minute burned most of the tick budget to produce changes far below
#: what anyone could observe. Movement still runs every tick — that is the part
#: the viewer actually sees.
PHYSIOLOGY_INTERVAL_MINUTES = 15.0


def decide_activity(agent: Agent, now: TimeOfDay, laws: frozenset[str] | None = None) -> Activity:
    """The intention for this moment, before any movement happens."""
    if not agent.alive:
        return Activity.IDLE

    laws = laws or frozenset()

    # 1. Urgent physical needs.
    if agent.needs.health < HEALTH_ALARM:
        return Activity.AT_HOSPITAL

    if "curfew" in laws and (now.hour >= 22 or now.hour < 6):
        return Activity.GOING_HOME

    # Player orders outrank the daily rhythm, but not medical emergencies.
    if agent.player_order:
        try:
            return Activity(agent.player_order)
        except ValueError:
            pass

    urgent = agent.needs.most_urgent
    if urgent is not None:
        name, _ = urgent
        if name == "energy":
            return Activity.SLEEPING
        if name == "hunger":
            return Activity.EATING
        if name == "hygiene":
            return Activity.GOING_HOME
        if name == "social":
            return Activity.SOCIALISING
        if name == "fun":
            return Activity.LEISURE

    # 2. The daily rhythm.
    if now.is_night:
        return Activity.SLEEPING

    if agent.is_school_age:
        if agent.school_id is not None and 8 <= now.hour < 14:
            return Activity.AT_SCHOOL
        return Activity.LEISURE

    if agent.can_work:
        if "mandatory_work" in laws and 8 <= now.hour < 18:
            return Activity.WORKING
        if agent.desk and 8 <= now.hour < 18:
            return Activity.WORKING
        if agent.employed and now.is_working_hours:
            return Activity.WORKING
        if not agent.employed and 8 <= now.hour < 17:
            return Activity.SEEKING_JOB

    # 3. Free time, coloured by mood.
    bias = agent.emotions.decision_bias()
    if bias["socialise"] >= bias["leisure"]:
        return Activity.SOCIALISING
    return Activity.LEISURE


def _nearest_building(
    agent: Agent,
    buildings: dict[int, Building],
    categories: tuple[BuildingCategory, ...],
) -> Building | None:
    ax, ay = agent.tile
    options = [
        building
        for building in buildings.values()
        if building.is_open and building.spec.category in categories
    ]
    if not options:
        return None
    return min(options, key=lambda b: abs(b.center[0] - ax) + abs(b.center[1] - ay))


def _public_space(agent: Agent, buildings: dict[int, Building]) -> Building | None:
    """Parks and government buildings — where homeless citizens can go."""
    return _nearest_building(
        agent,
        buildings,
        (BuildingCategory.ENTERTAINMENT, BuildingCategory.GOVERNMENT),
    )


def target_building(
    agent: Agent, activity: Activity, buildings: dict[int, Building]
) -> Building | None:
    """Where the agent must be to satisfy `activity`."""
    if activity in (Activity.SLEEPING, Activity.GOING_HOME, Activity.EATING):
        home = buildings.get(agent.home_id) if agent.home_id else None
        if home is not None:
            return home
        if activity is Activity.EATING:
            shop = _nearest_building(agent, buildings, (BuildingCategory.BUSINESS,))
            return shop or _public_space(agent, buildings)
        return _public_space(agent, buildings)

    if activity is Activity.WORKING:
        workplace = buildings.get(agent.workplace_id) if agent.workplace_id else None
        if workplace is not None:
            return workplace
        if agent.desk:
            return _nearest_building(
                agent, buildings, (BuildingCategory.GOVERNMENT, BuildingCategory.BUSINESS),
            )
        return None

    if activity is Activity.SEEKING_JOB:
        return _nearest_building(
            agent,
            buildings,
            (BuildingCategory.GOVERNMENT, BuildingCategory.BUSINESS, BuildingCategory.INDUSTRY),
        )

    if activity is Activity.AT_SCHOOL:
        return buildings.get(agent.school_id) if agent.school_id else None

    categories = VENUE_FOR.get(activity)
    if categories is None:
        return None

    found = _nearest_building(agent, buildings, categories)
    if found is not None:
        return found
    return _public_space(agent, buildings)


def _at_destination(agent: Agent, building: Building | None) -> bool:
    if building is None:
        return False
    ax, ay = agent.tile
    ex, ey = building.entrance
    return abs(ax - ex) <= 1 and abs(ay - ey) <= 1


def step_agent(
    agent: Agent,
    *,
    now: TimeOfDay,
    minutes: float,
    grid: Grid,
    buildings: dict[int, Building],
    paths: PathCache,
    tick: int,
    laws: frozenset[str] | None = None,
) -> None:
    """
    Advances one agent by `minutes` of simulated time.

    Called only for FULL and REDUCED detail agents; distant ones are moved
    statistically by the engine instead.
    """
    if not agent.alive:
        return

    agent.pending_minutes += minutes
    physiology_due = agent.pending_minutes >= PHYSIOLOGY_INTERVAL_MINUTES

    # Re-decide on the physiology beat, or immediately if the agent has nowhere
    # to be — otherwise a newly housed agent would stand still for a quarter of
    # an hour before noticing it has a home.
    # A destination is a consequence of the intention, so it only needs choosing
    # when the intention does. In between, the stored id is looked up directly,
    # which avoids scanning every building in the city on every tick.
    destination = (
        buildings.get(agent.destination_building_id)
        if agent.destination_building_id is not None
        else None
    )
    redecide = (
        physiology_due
        or agent.intent is Activity.IDLE
        # The building was demolished under the agent's feet.
        or (agent.destination_building_id is not None and destination is None)
    )

    if redecide:
        agent.intent = decide_activity(agent, now, laws)
        destination = target_building(agent, agent.intent, buildings)

    intention = agent.intent

    if destination is not None and not _at_destination(agent, destination):
        # Still travelling: the intention is the reason, commuting is the state.
        agent.destination_building_id = destination.id
        agent.activity = (
            Activity.GOING_HOME
            if intention in (Activity.SLEEPING, Activity.GOING_HOME)
            else Activity.COMMUTING
        )
        _walk_toward(agent, destination, grid=grid, paths=paths, minutes=minutes)
        arrived = False
    else:
        agent.activity = intention
        agent.path.clear()
        agent.destination_building_id = destination.id if destination else None
        arrived = True

    if not physiology_due:
        return

    elapsed = agent.pending_minutes
    agent.pending_minutes = 0.0
    hours = elapsed / MINUTES_PER_HOUR

    if arrived:
        _apply_recovery(agent, intention, hours)

    agent.needs.drain(hours)
    agent.emotions.decay(hours)
    _apply_emotional_pressure(agent, hours)

    # Homelessness and unemployment are felt, not just recorded.
    if agent.home_id is None:
        agent.emotions.adjust(stress=1.2 * hours, happiness=-0.8 * hours)
    if agent.unemployed:
        agent.emotions.adjust(stress=0.7 * hours, confidence=-0.4 * hours)


def _walk_toward(
    agent: Agent,
    destination: Building,
    *,
    grid: Grid,
    paths: PathCache,
    minutes: float,
) -> None:
    """Follows or recomputes a route, then advances along it."""
    goal = destination.entrance
    if not agent.path or agent.path[-1] != goal:
        result = paths.route(grid, agent.tile, goal)
        if not result.found:
            # Unreachable: stand still rather than teleport. The city being
            # disconnected is a real problem and should stay visible.
            agent.path = []
            return
        agent.path = list(result.tiles)

    remaining = WALK_SPEED_PER_MINUTE * minutes
    while remaining > 0 and agent.path:
        tx, ty = agent.path[0]
        x, y = agent.position
        dx, dy = tx - x, ty - y
        distance = (dx * dx + dy * dy) ** 0.5

        if distance <= remaining:
            agent.position = (float(tx), float(ty))
            agent.path.pop(0)
            remaining -= distance
        else:
            ratio = remaining / distance
            agent.position = (x + dx * ratio, y + dy * ratio)
            remaining = 0.0


def _apply_recovery(agent: Agent, activity: Activity, hours: float) -> None:
    recovery = RECOVERY.get(activity)
    if not recovery:
        return
    agent.needs.adjust(**{name: rate * hours for name, rate in recovery.items()})


def _apply_emotional_pressure(agent: Agent, hours: float) -> None:
    """
    Translates unmet needs into feelings.

    This is the link that makes needs matter beyond a progress bar: a hungry,
    lonely agent becomes measurably unhappy, which lowers city happiness, which
    the president sees and acts on.
    """
    needs = agent.needs

    if needs.hunger < 30.0:
        agent.emotions.adjust(stress=2.0 * hours, anger=1.0 * hours, happiness=-1.5 * hours)
    if needs.energy < 25.0:
        agent.emotions.adjust(stress=1.5 * hours, happiness=-1.0 * hours)
    if needs.social < 30.0:
        agent.emotions.adjust(loneliness=2.5 * hours, sadness=1.0 * hours)
    elif needs.social > 70.0:
        agent.emotions.adjust(loneliness=-2.0 * hours)
    if needs.fun < 30.0:
        agent.emotions.adjust(sadness=1.2 * hours, excitement=-1.5 * hours)
    if needs.health < 50.0:
        agent.emotions.adjust(pain=2.0 * hours, fear=1.2 * hours)
    elif needs.health > 85.0:
        agent.emotions.adjust(pain=-3.0 * hours)

    if needs.satisfaction > 75.0:
        agent.emotions.adjust(happiness=1.2 * hours)


def step_statistically(agent: Agent, *, minutes: float) -> None:
    """
    Cheap update for distant agents (specification section 41).

    Needs still drift and feelings still settle, so an agent the camera has not
    looked at for a simulated week has a plausible state when it returns. What
    is skipped is pathfinding, venue selection and position updates — the
    expensive parts nobody can see.
    """
    if not agent.alive:
        return

    # Batched on the same beat as full simulation, for the same reason: this
    # runs for the majority of the population in a large city.
    agent.pending_minutes += minutes
    if agent.pending_minutes < PHYSIOLOGY_INTERVAL_MINUTES:
        return

    minutes = agent.pending_minutes
    agent.pending_minutes = 0.0

    hours = minutes / MINUTES_PER_HOUR
    needs = agent.needs

    # Assume the agent broadly manages: needs drift toward a mediocre middle
    # rather than draining to zero, which is what would happen if we simply
    # applied the drain without the corresponding recovery.
    for name, target in (
        ("energy", 62.0), ("hunger", 60.0), ("hygiene", 62.0),
        ("social", 52.0), ("fun", 50.0),
    ):
        current = getattr(needs, name)
        setattr(needs, name, current + (target - current) * min(1.0, 0.05 * hours))

    if agent.home_id is None:
        needs.adjust(hygiene=-2.0 * hours, energy=-1.5 * hours)

    agent.emotions.decay(hours)
    agent.activity = Activity.IDLE if agent.home_id is None else Activity.SLEEPING


def resume_full_detail(agent: Agent, buildings: dict[int, Building]) -> None:
    """
    Restores a plausible position when an agent returns to full simulation.

    Without this, an agent that spent simulated months in statistical mode would
    pop back at the coordinates it left, possibly inside a building that has
    since been demolished.
    """
    anchor = buildings.get(agent.home_id) if agent.home_id else None
    if anchor is None:
        anchor = buildings.get(agent.workplace_id) if agent.workplace_id else None
    if anchor is not None:
        agent.position = (float(anchor.entrance[0]), float(anchor.entrance[1]))
    agent.path.clear()
    # Force a fresh decision rather than resuming a stale intention.
    agent.intent = Activity.IDLE
    agent.pending_minutes = 0.0
    agent.detail = DetailLevel.FULL


def apply_wage(agent: Agent, net_pay: float, tick: int) -> None:
    """Credits monthly pay and lets the agent notice it."""
    agent.money += net_pay
    if net_pay > 0:
        agent.emotions.adjust(confidence=2.0, stress=-2.0)
        agent.memory.record(
            tick, MemoryKind.WORK, f"Oylik oldi: {net_pay:.0f}", importance=0.25,
            amount=round(net_pay, 2),
        )


def charge_living_costs(agent: Agent, amount: float) -> None:
    """
    Monthly cost of living.

    Falling into debt is felt as stress rather than being silently absorbed, so
    poverty has a visible consequence in the happiness figures.
    """
    agent.money -= amount
    if agent.money < 0:
        agent.emotions.adjust(stress=6.0, happiness=-4.0, fear=3.0)
        agent.needs.adjust(hunger=-8.0)


def reset_needs_for_new_home(needs: Needs) -> None:
    """Called when an agent moves in; a home restores basic dignity."""
    needs.adjust(hygiene=25.0, energy=10.0)
