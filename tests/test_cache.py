from __future__ import annotations

import time

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from mcmod.cache import CacheStore, cache_key
from mcmod.config import Settings
from mcmod.db import ApiCache


def test_cache_key_is_order_insensitive_and_ignores_empty() -> None:
    first = cache_key("mod", {"id": 2, "refresh": False, "q": None})
    second = cache_key("mod", {"q": "", "id": 2})
    assert first == second
    assert first != cache_key("item", {"id": 2})


def test_cache_roundtrip_and_stats(cache: CacheStore) -> None:
    key = cache_key("mod", {"id": 2})
    assert cache.get(key) is None
    cache.set(
        key,
        resource="mod",
        source_url="https://www.mcmod.cn/class/2.html",
        payload={"name": "工业时代2"},
        ttl=60,
    )
    hit = cache.get(key)
    assert hit is not None
    assert hit.payload == {"name": "工业时代2"}
    assert hit.source_url.endswith("/class/2.html")
    stats = cache.stats()
    assert stats["entries"] == 1
    assert stats["expired"] == 0
    assert stats["hits"] == 1
    assert stats["size_bytes"] > 0


def test_cache_expiry_and_purge(cache: CacheStore, monkeypatch) -> None:
    key = cache_key("mod", {"id": 2})
    now = 1_700_000_000
    monkeypatch.setattr(time, "time", lambda: now)
    cache.set(key, resource="mod", source_url="x", payload={"a": 1}, ttl=10)
    assert cache.get(key) is not None
    monkeypatch.setattr(time, "time", lambda: now + 11)
    assert cache.get(key) is None
    assert cache.stats()["expired"] == 0

    key2 = cache_key("mod", {"id": 3})
    cache.set(key2, resource="mod", source_url="x", payload={"a": 1}, ttl=10)
    monkeypatch.setattr(time, "time", lambda: now + 30)
    assert cache.purge_expired() == 1
    assert cache.stats()["entries"] == 0


def test_cache_clear(cache: CacheStore) -> None:
    for mod_id in (2, 3):
        cache.set(
            cache_key("mod", {"id": mod_id}),
            resource="mod",
            source_url="x",
            payload={"a": 1},
            ttl=60,
        )
    assert cache.clear() == 2
    assert cache.stats()["entries"] == 0


def test_cache_overwrite_preserves_hits(cache: CacheStore) -> None:
    key = cache_key("mod", {"id": 2})
    cache.set(key, resource="mod", source_url="x", payload={"a": 1}, ttl=60)
    cache.get(key)
    cache.get(key)
    cache.set(key, resource="mod", source_url="x", payload={"a": 2}, ttl=60)
    assert cache.get(key).payload == {"a": 2}
    assert cache.stats()["hits"] == 3


def test_mariadb_url_normalisation_and_ddl() -> None:
    settings = Settings(database_url="mariadb://user:pass@db.example:3306/mcmod")
    assert settings.database_url == "mysql+pymysql://user:pass@db.example:3306/mcmod"
    assert settings.backend_name == "mariadb"

    ddl = str(CreateTable(ApiCache.__table__).compile(dialect=mysql.dialect()))
    assert "api_cache" in ddl
    assert "MEDIUMTEXT" in ddl
    assert "expires_at" in ddl


@pytest.mark.parametrize("url", ["sqlite:///./x.db", "sqlite:////tmp/x.db"])
def test_sqlite_backend_name(url: str) -> None:
    settings = Settings(database_url=url)
    assert settings.backend_name == "sqlite"
    assert settings.is_sqlite
