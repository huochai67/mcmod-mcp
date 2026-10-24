"""Optional MariaDB integration test.

Run with a disposable server:

    MCMOD_TEST_MARIADB_URL='mariadb://root:secret@127.0.0.1:3307/mcmod' \
        uv run pytest tests/test_mariadb.py -q

The test is skipped when the environment variable is absent so the default
suite stays offline and does not require Docker.
"""

from __future__ import annotations

import os

import pytest

from mcmod.cache import CacheStore, cache_key
from mcmod.config import Settings
from mcmod.db import create_engine_from_settings, init_database, make_session_factory, ping_database

MARIADB_URL = os.environ.get("MCMOD_TEST_MARIADB_URL")

pytestmark = pytest.mark.skipif(
    not MARIADB_URL, reason="set MCMOD_TEST_MARIADB_URL to run MariaDB integration tests"
)


def test_mariadb_cache_roundtrip() -> None:
    settings = Settings(database_url=MARIADB_URL, min_interval=0)
    assert settings.backend_name == "mariadb"
    engine = create_engine_from_settings(settings)
    try:
        init_database(engine)
        assert ping_database(engine)
        cache = CacheStore(make_session_factory(engine))
        key = cache_key("mariadb-test", {"id": 1})
        cache.clear()
        cache.set(key, resource="mariadb-test", source_url="https://example.test", payload={"中文": "ok", "n": 1}, ttl=60)
        hit = cache.get(key)
        assert hit is not None
        assert hit.payload == {"中文": "ok", "n": 1}
        assert cache.stats()["entries"] == 1
        assert cache.clear() == 1
    finally:
        engine.dispose()
