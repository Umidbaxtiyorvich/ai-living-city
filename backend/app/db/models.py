"""
Database schema.

Two kinds of data live here, and they are shaped differently on purpose:

* **The snapshot** (`world_snapshots`) is the civilization itself — one JSON
  document per save, written atomically. See `sim/persistence.py` for why the
  world is not normalized into a column per attribute.
* **The history** (`world_events`, `world_decisions`, `world_metrics`) is what
  gets queried: the event feed, the president's record, and the curves the
  dashboard draws. These are real columns with real indexes, because filtering
  a decade of events by severity inside a JSON blob is not a query, it is a
  full scan.

Portable between SQLite and PostgreSQL: `JSON` maps to `jsonb`-compatible JSON
on Postgres and to a TEXT column with automatic encoding on SQLite, so
development needs no server and production loses nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class World(Base):
    """One city, across all of its saves."""

    __tablename__ = "worlds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    #: Denormalized headline figures so the save list can be shown without
    #: parsing a multi-megabyte snapshot per row.
    tick: Mapped[int] = mapped_column(Integer, default=0)
    day: Mapped[int] = mapped_column(Integer, default=0)
    city_level: Mapped[int] = mapped_column(Integer, default=1)
    population: Mapped[int] = mapped_column(Integer, default=0)
    budget: Mapped[float] = mapped_column(Float, default=0.0)

    snapshots: Mapped[list["WorldSnapshot"]] = relationship(
        back_populates="world", cascade="all, delete-orphan"
    )


class WorldSnapshot(Base):
    """A complete, self-contained state of one city at one tick."""

    __tablename__ = "world_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    world_id: Mapped[int] = mapped_column(
        ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Why this save exists: "autosave", "manual", "shutdown".
    reason: Mapped[str] = mapped_column(String(32), default="autosave")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    world: Mapped[World] = relationship(back_populates="snapshots")


class WorldEvent(Base):
    """City history, queryable (specification section 26)."""

    __tablename__ = "world_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    world_id: Mapped[int] = mapped_column(
        ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False
    )
    #: The simulation's own event id, so re-saving cannot duplicate a row.
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_world_events_world_event", "world_id", "event_id", unique=True),
        Index("ix_world_events_world_day", "world_id", "day"),
    )


class WorldDecision(Base):
    """The president's record, for review and for the approval history."""

    __tablename__ = "world_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    world_id: Mapped[int] = mapped_column(
        ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    concern: Mapped[str] = mapped_column(String(48), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    severity_at_review: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_world_decisions_world_decision", "world_id", "decision_id", unique=True),
    )


class WorldMetric(Base):
    """A daily row of headline indicators — the dashboard's charts."""

    __tablename__ = "world_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    world_id: Mapped[int] = mapped_column(
        ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    population: Mapped[int] = mapped_column(Integer, default=0)
    happiness: Mapped[float] = mapped_column(Float, default=0.0)
    employment_rate: Mapped[float] = mapped_column(Float, default=0.0)
    housing_shortage: Mapped[int] = mapped_column(Integer, default=0)
    budget: Mapped[float] = mapped_column(Float, default=0.0)
    gdp: Mapped[float] = mapped_column(Float, default=0.0)
    approval_rating: Mapped[float] = mapped_column(Float, default=0.0)
    city_level: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (Index("ix_world_metrics_world_day", "world_id", "day", unique=True),)
