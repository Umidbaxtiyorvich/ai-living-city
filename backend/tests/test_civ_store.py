"""The world survives in a database when one is configured (free hosts have no disk)."""

from __future__ import annotations

import importlib

from civ.engine import Civilization


def test_world_round_trips_through_a_database(tmp_path, monkeypatch):
    # Any SQLAlchemy URL that is not the default local SQLite file counts as a database.
    monkeypatch.setenv("CIV_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'store.db'}")
    store = importlib.reload(importlib.import_module("app.civ_store"))
    monkeypatch.setattr(store, "database_url", lambda: f"sqlite+pysqlite:///{tmp_path / 'store.db'}")
    assert store.load() is None
    civ = Civilization(seed=3)
    civ.genesis()
    for _ in range(50):
        civ.step()
    store.save(civ.snapshot())
    store.save(civ.snapshot())  # saving twice keeps one row
    again = Civilization.restore(store.load())
    assert again.tick == civ.tick
    assert len(again.living) == len(civ.living)


def test_postgres_urls_get_a_driver(monkeypatch):
    store = importlib.import_module("app.civ_store")
    monkeypatch.delenv("CIV_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host:5432/db")
    assert store.database_url() == "postgresql+psycopg://u:p@host:5432/db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./city.db")
    assert store.database_url() is None
