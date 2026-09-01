"""
Reading and writing a city.

The repository is the only place that knows both the simulation and the
database. `sim/` stays free of SQLAlchemy, which is what keeps the whole
civilization testable without a database at all.

Writes are incremental where it matters: events, decisions and daily metrics
are appended by simulation id, so an autosave every day does not rewrite a
decade of history. The snapshot is the exception — it is the world, and it is
replaced wholesale.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from sim.persistence import dump_world, load_world
from sim.president.brain import approval_from
from sim.state import WorldState

from .models import World, WorldDecision, WorldEvent, WorldMetric, WorldSnapshot


def get_or_create_world(session: Session, name: str, seed: int) -> World:
    world = session.scalar(select(World).where(World.name == name))
    if world is not None:
        return world
    world = World(name=name, seed=seed)
    session.add(world)
    session.flush()
    return world


def latest_snapshot(session: Session, world_id: int) -> WorldSnapshot | None:
    return session.scalar(
        select(WorldSnapshot)
        .where(WorldSnapshot.world_id == world_id)
        .order_by(WorldSnapshot.tick.desc(), WorldSnapshot.id.desc())
        .limit(1)
    )


def load_latest(session: Session, name: str) -> WorldState | None:
    """The most recent save of this city, or None if it has never been saved."""
    world = session.scalar(select(World).where(World.name == name))
    if world is None:
        return None
    snapshot = latest_snapshot(session, world.id)
    if snapshot is None:
        return None
    return load_world(snapshot.payload)


@dataclass(slots=True)
class Capture:
    """
    Everything a save needs, extracted from the live world in one pass.

    Separating capture from writing lets the simulation loop hold its lock only
    long enough to read the world, and hand plain data to a worker thread for
    the slow part.
    """

    seed: int
    tick: int
    day: int
    city_level: int
    population: int
    budget: float
    document: dict
    events: list[dict]
    decisions: list[dict]
    metric: dict


def capture(state: WorldState) -> Capture:
    """Reads the world. Touches no database and mutates nothing."""
    stats = state.stats
    approval = (
        state.president.approval_rating
        if state.president is not None
        else approval_from(stats, state.economy)
    )

    return Capture(
        seed=state.config.seed,
        tick=state.tick,
        day=state.day,
        city_level=int(state.city_level),
        population=state.population,
        budget=state.economy.budget,
        document=dump_world(state),
        events=[
            {
                "event_id": event.id,
                "tick": event.tick,
                "day": event.day,
                "type": str(event.type),
                "severity": str(event.severity),
                "text": event.text,
                "data": dict(event.data),
            }
            for event in state.events.recent(count=state.events.memory_limit)
        ],
        decisions=[
            {
                "decision_id": decision.id,
                "tick": decision.tick,
                "concern": str(decision.concern.code),
                "action": decision.concern.action.describe(),
                "status": str(decision.status),
                "cost": decision.cost,
                "severity": decision.concern.severity,
                "severity_at_review": decision.severity_at_review,
                "rationale": decision.rationale,
            }
            for decision in (state.president.decisions if state.president else [])
        ],
        metric={
            "day": state.day,
            "population": stats.population,
            "happiness": stats.happiness,
            "employment_rate": stats.employment_rate,
            "housing_shortage": stats.housing_shortage,
            "budget": state.economy.budget,
            "gdp": state.economy.gdp,
            "approval_rating": approval,
            "city_level": int(state.city_level),
        },
    )


def save_world(
    session: Session,
    state: WorldState,
    *,
    name: str,
    reason: str = "autosave",
    history_limit: int = 12,
) -> WorldSnapshot:
    """Convenience wrapper for callers holding a live world."""
    return write_capture(
        session, capture(state), name=name, reason=reason, history_limit=history_limit
    )


def write_capture(
    session: Session,
    data: Capture,
    *,
    name: str,
    reason: str = "autosave",
    history_limit: int = 12,
) -> WorldSnapshot:
    """Writes the snapshot, then appends whatever history is new."""
    world = get_or_create_world(session, name, data.seed)

    world.tick = data.tick
    world.day = data.day
    world.city_level = data.city_level
    world.population = data.population
    world.budget = data.budget

    snapshot = WorldSnapshot(
        world_id=world.id,
        tick=data.tick,
        day=data.day,
        version=data.document["version"],
        reason=reason,
        payload=data.document,
    )
    session.add(snapshot)
    session.flush()

    _append_events(session, world.id, data.events)
    _append_decisions(session, world.id, data.decisions)
    _record_metrics(session, world.id, data.metric)
    _prune_snapshots(session, world.id, history_limit)

    return snapshot


def _append_events(session: Session, world_id: int, events: list[dict]) -> None:
    highest = (
        session.scalar(
            select(func.max(WorldEvent.event_id)).where(WorldEvent.world_id == world_id)
        )
        or 0
    )
    for event in events:
        if event["event_id"] <= highest:
            continue
        session.add(WorldEvent(world_id=world_id, **event))


def _append_decisions(session: Session, world_id: int, decisions: list[dict]) -> None:
    existing = set(
        session.scalars(
            select(WorldDecision.decision_id).where(WorldDecision.world_id == world_id)
        )
    )
    for decision in decisions:
        if decision["decision_id"] in existing:
            # Review outcomes arrive months later, so an already-stored decision
            # is updated rather than skipped.
            stored = session.scalar(
                select(WorldDecision).where(
                    WorldDecision.world_id == world_id,
                    WorldDecision.decision_id == decision["decision_id"],
                )
            )
            if stored is not None:
                stored.status = decision["status"]
                stored.severity_at_review = decision["severity_at_review"]
            continue

        session.add(WorldDecision(world_id=world_id, **decision))


def _record_metrics(session: Session, world_id: int, metric: dict) -> None:
    existing = session.scalar(
        select(WorldMetric).where(
            WorldMetric.world_id == world_id, WorldMetric.day == metric["day"]
        )
    )
    target = existing or WorldMetric(world_id=world_id, day=metric["day"])
    for name, value in metric.items():
        if name != "day":
            setattr(target, name, value)
    if existing is None:
        session.add(target)


def _prune_snapshots(session: Session, world_id: int, keep: int) -> None:
    """
    Drops old snapshots.

    Each one is a full copy of the city, so an unbounded history would grow by
    megabytes a day. A handful of recent saves is enough to recover from a bad
    one; the permanent record is in the history tables.
    """
    if keep <= 0:
        return
    doomed = session.scalars(
        select(WorldSnapshot.id)
        .where(WorldSnapshot.world_id == world_id)
        .order_by(WorldSnapshot.tick.desc(), WorldSnapshot.id.desc())
        .offset(keep)
    ).all()
    if doomed:
        session.execute(delete(WorldSnapshot).where(WorldSnapshot.id.in_(doomed)))


def metrics_series(session: Session, world_id: int, limit: int = 365) -> list[dict]:
    """Daily indicators, oldest first — the dashboard's charts."""
    rows = session.scalars(
        select(WorldMetric)
        .where(WorldMetric.world_id == world_id)
        .order_by(WorldMetric.day.desc())
        .limit(limit)
    ).all()
    return [
        {
            "day": row.day,
            "population": row.population,
            "happiness": round(row.happiness, 2),
            "employment_rate": round(row.employment_rate, 4),
            "housing_shortage": row.housing_shortage,
            "budget": round(row.budget, 2),
            "gdp": round(row.gdp, 2),
            "approval_rating": round(row.approval_rating, 2),
            "city_level": row.city_level,
        }
        for row in reversed(rows)
    ]
