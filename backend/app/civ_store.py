"""
Where the civilization is kept between runs.

A file on disk is enough locally and on hosts with a persistent volume. Free
hosting usually has neither a volume nor a disk that survives a redeploy, but
does offer a free Postgres — so when a database is configured, the world is
stored there instead: one row, compressed JSON.

Configured by `CIV_DATABASE_URL`, or by `DATABASE_URL` when it points at a real
database server rather than a local SQLite file.
"""

from __future__ import annotations

import base64
import json
import os
import time
import zlib

from sqlalchemy import Column, Float, MetaData, String, Table, Text, create_engine, delete, insert, select
from sqlalchemy.engine import Engine

_metadata = MetaData()
_worlds = Table(
    "civ_world",
    _metadata,
    Column("name", String(80), primary_key=True),
    Column("saved_at", Float, nullable=False),
    Column("data", Text, nullable=False),
)

WORLD_NAME = os.environ.get("WORLD_NAME", "AI Living City")


def database_url() -> str | None:
    url = os.environ.get("CIV_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not url or url.startswith("sqlite"):
        return None
    # Hosts hand out "postgres://"; SQLAlchemy wants the driver spelled out.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_engine: Engine | None = None


def _db() -> Engine | None:
    global _engine
    url = database_url()
    if url is None:
        return None
    if _engine is None:
        _engine = create_engine(url, pool_pre_ping=True, future=True)
        _metadata.create_all(_engine)
    return _engine


def enabled() -> bool:
    return database_url() is not None


def _pack(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(zlib.compress(raw, 6)).decode("ascii")


def _unpack(text: str) -> dict:
    return json.loads(zlib.decompress(base64.b64decode(text)).decode("utf-8"))


def load() -> dict | None:
    engine = _db()
    if engine is None:
        return None
    with engine.connect() as conn:
        row = conn.execute(select(_worlds.c.data).where(_worlds.c.name == WORLD_NAME)).first()
    return _unpack(row[0]) if row else None


def save(data: dict) -> None:
    engine = _db()
    if engine is None:
        raise RuntimeError("no database configured")
    packed = _pack(data)
    with engine.begin() as conn:
        conn.execute(delete(_worlds).where(_worlds.c.name == WORLD_NAME))
        conn.execute(insert(_worlds).values(name=WORLD_NAME, saved_at=time.time(), data=packed))
