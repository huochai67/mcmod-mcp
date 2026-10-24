"""Persistent API-result cache backed by SQLite or MariaDB."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .db import ApiCache

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = "v1"


class CacheError(RuntimeError):
    """The cache backend failed; callers may continue without caching."""


@dataclass(frozen=True)
class CacheHit:
    payload: dict[str, Any]
    source_url: str
    fetched_at: int
    expires_at: int
    ttl: int


def cache_key(resource: str, params: dict[str, Any]) -> str:
    """Return a stable key for a resource and its query parameters."""

    cleaned = {
        str(key): value
        for key, value in params.items()
        if value is not None and value != "" and value is not False
    }
    canonical = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw = f"{CACHE_SCHEMA_VERSION}:{resource}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CacheStore:
    def __init__(self, session_factory: sessionmaker, *, enabled: bool = True) -> None:
        self._session_factory = session_factory
        self.enabled = enabled

    def get(self, key: str) -> CacheHit | None:
        if not self.enabled:
            return None
        now = int(time.time())
        try:
            with self._session_factory() as session:
                row = session.get(ApiCache, key)
                if row is None:
                    return None
                if row.expires_at <= now:
                    session.delete(row)
                    session.commit()
                    return None
                payload = json.loads(row.payload)
                session.execute(
                    update(ApiCache)
                    .where(ApiCache.key == key)
                    .values(hits=ApiCache.hits + 1, last_hit_at=now)
                )
                session.commit()
                return CacheHit(
                    payload=payload,
                    source_url=row.source_url,
                    fetched_at=row.fetched_at,
                    expires_at=row.expires_at,
                    ttl=row.ttl,
                )
        except (SQLAlchemyError, json.JSONDecodeError) as exc:
            logger.warning("cache read failed: %s", exc)
            raise CacheError(str(exc)) from exc

    def set(
        self,
        key: str,
        *,
        resource: str,
        source_url: str,
        payload: dict[str, Any],
        ttl: int,
    ) -> bool:
        if not self.enabled or ttl <= 0:
            return False
        now = int(time.time())
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        row = ApiCache(
            key=key,
            resource=resource,
            source_url=source_url,
            payload=encoded,
            fetched_at=now,
            expires_at=now + ttl,
            ttl=ttl,
            hits=0,
            last_hit_at=None,
            size_bytes=len(encoded.encode("utf-8")),
        )
        try:
            with self._session_factory() as session:
                existing = session.get(ApiCache, key)
                if existing is None:
                    session.add(row)
                else:
                    existing.resource = row.resource
                    existing.source_url = row.source_url
                    existing.payload = row.payload
                    existing.fetched_at = row.fetched_at
                    existing.expires_at = row.expires_at
                    existing.ttl = row.ttl
                    existing.size_bytes = row.size_bytes
                session.commit()
            return True
        except SQLAlchemyError as exc:
            logger.warning("cache write failed: %s", exc)
            raise CacheError(str(exc)) from exc

    def purge_expired(self) -> int:
        if not self.enabled:
            return 0
        now = int(time.time())
        try:
            with self._session_factory() as session:
                result = session.execute(delete(ApiCache).where(ApiCache.expires_at <= now))
                session.commit()
                return int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            logger.warning("cache purge failed: %s", exc)
            raise CacheError(str(exc)) from exc

    def clear(self) -> int:
        try:
            with self._session_factory() as session:
                result = session.execute(delete(ApiCache))
                session.commit()
                return int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            raise CacheError(str(exc)) from exc

    def stats(self) -> dict[str, int]:
        now = int(time.time())
        try:
            with self._session_factory() as session:
                entries = session.scalar(select(func.count()).select_from(ApiCache)) or 0
                expired = (
                    session.scalar(
                        select(func.count())
                        .select_from(ApiCache)
                        .where(ApiCache.expires_at <= now)
                    )
                    or 0
                )
                hits = session.scalar(select(func.coalesce(func.sum(ApiCache.hits), 0))) or 0
                size = session.scalar(select(func.coalesce(func.sum(ApiCache.size_bytes), 0))) or 0
                return {
                    "entries": int(entries),
                    "expired": int(expired),
                    "hits": int(hits),
                    "size_bytes": int(size),
                }
        except SQLAlchemyError as exc:
            raise CacheError(str(exc)) from exc
