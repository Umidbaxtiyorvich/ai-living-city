"""
Shared test setup.

Every test gets its own throwaway database. Without this the API tests would
write to the development `city.db` and — worse — resume the city one of them
saved earlier, so a test's result would depend on which tests ran before it.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.db import session as db_session


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test-city.db'}"
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    monkeypatch.setattr(settings, "world_name", "Test City", raising=False)
    db_session.reset(url)
    yield url
    db_session.reset()
