"""
Database tests.

The interesting claims are that the schema the migrations build is the schema
the code expects, that history accumulates instead of duplicating, and that a
city written to the database comes back as the same city.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.db import repository
from app.db.models import World, WorldDecision, WorldEvent, WorldMetric, WorldSnapshot
from app.db.schema import upgrade_to_head
from app.db.session import session_scope
from sim.clock import MINUTES_PER_DAY
from sim.engine import Engine
from sim.state import SimulationConfig, WorldState

CONFIG = SimulationConfig(seed=5, map_size=60, founding_population=25)


def build_city() -> Engine:
    state = WorldState.create(CONFIG)
    engine = Engine(state)
    engine.found_city()
    return engine


def test_migrations_create_the_schema(isolated_database):
    upgrade_to_head(isolated_database)

    with session_scope() as session:
        # A query against every table is the honest check that the migration
        # and the ORM models agree on names and columns.
        for model in (World, WorldSnapshot, WorldEvent, WorldDecision, WorldMetric):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_saving_and_reloading_a_city(isolated_database):
    upgrade_to_head(isolated_database)
    engine = build_city()
    engine.run(4 * MINUTES_PER_DAY)

    with session_scope() as session:
        repository.save_world(session, engine.state, name="Test City", reason="manual")

    with session_scope() as session:
        reloaded = repository.load_latest(session, "Test City")

    assert reloaded is not None
    assert reloaded.tick == engine.state.tick
    assert reloaded.population == engine.state.population
    assert reloaded.president is not None


def test_history_accumulates_without_duplicating(isolated_database):
    upgrade_to_head(isolated_database)
    engine = build_city()

    for _ in range(3):
        engine.run(2 * MINUTES_PER_DAY)
        with session_scope() as session:
            repository.save_world(session, engine.state, name="Test City")

    with session_scope() as session:
        world = session.scalar(select(World).where(World.name == "Test City"))
        assert world is not None

        event_rows = session.scalar(
            select(func.count()).select_from(WorldEvent).where(WorldEvent.world_id == world.id)
        )
        distinct_events = session.scalar(
            select(func.count(func.distinct(WorldEvent.event_id))).where(
                WorldEvent.world_id == world.id
            )
        )
        assert event_rows == distinct_events > 0

        metrics = repository.metrics_series(session, world.id)
        assert [row["day"] for row in metrics] == sorted(row["day"] for row in metrics)
        assert len(metrics) == 3


def test_old_snapshots_are_pruned(isolated_database):
    upgrade_to_head(isolated_database)
    engine = build_city()

    for _ in range(4):
        engine.run(MINUTES_PER_DAY)
        with session_scope() as session:
            repository.save_world(session, engine.state, name="Test City", history_limit=2)

    with session_scope() as session:
        kept = session.scalars(select(WorldSnapshot.tick)).all()

    assert len(kept) == 2
    assert max(kept) == engine.state.tick


def test_decision_review_updates_the_stored_row(isolated_database):
    upgrade_to_head(isolated_database)
    engine = build_city()
    engine.run(2 * MINUTES_PER_DAY)

    president = engine.state.president
    assert president is not None
    if not president.decisions:
        engine.run(3 * MINUTES_PER_DAY)
    assert president.decisions, "the president made no decision to store"

    with session_scope() as session:
        repository.save_world(session, engine.state, name="Test City")

    decision = president.decisions[0]
    decision.severity_at_review = 0.11

    with session_scope() as session:
        repository.save_world(session, engine.state, name="Test City")

    with session_scope() as session:
        stored = session.scalar(
            select(WorldDecision).where(WorldDecision.decision_id == decision.id)
        )
        assert stored is not None
        assert stored.severity_at_review == 0.11
