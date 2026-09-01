"""
Bringing the database up to date.

Startup runs the Alembic migrations rather than `create_all`, so a development
database and a production one arrive at the same schema by the same path — the
migration scripts are exercised on every run instead of only when somebody
remembers to test them.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from ..config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str | None = None) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url or settings.database_url)
    return config


def upgrade_to_head(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")
