"""Service layer: upstream fetch + parse + cache orchestration."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .cache import CacheError, CacheStore, cache_key
from .config import Settings
from .errors import InvalidRequestError
from .http import McmodHttp
from .models import (
    AuthorDetail,
    CacheStats,
    DownloadsPage,
    Envelope,
    FilterOptions,
    ItemDetail,
    Meta,
    ModDetail,
    ModItemsPage,
    ModListPage,
    ModpackDetail,
    ModpackListPage,
    ModpackVersionsPage,
    PostDetail,
    RecipesPage,
    SearchPage,
)
from .parsers import (
    parse_author,
    parse_downloads,
    parse_filters,
    parse_item_detail,
    parse_mod_detail,
    parse_mod_items,
    parse_mod_list,
    parse_modpack_detail,
    parse_modpack_list,
    parse_modpack_versions,
    parse_post,
    parse_recipes,
    parse_search,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

SEARCH_FILTERS = {
    "all": "0",
    "mods": "1",
    "modpacks": "2",
    "items": "3",
    "tutorials": "4",
    "authors": "5",
    "users": "6",
    "community": "7",
}

SEARCH_MOLDS = {"simple": "0", "full": "1"}

LOADER_IDS = {
    "forge": 1,
    "fabric": 2,
    "rift": 3,
    "liteloader": 4,
    "lite_loader": 4,
    "datapack": 5,
    "data_pack": 5,
    "command_block": 6,
    "file_override": 7,
    "behavior_pack": 8,
    "quilt": 11,
    "neoforge": 13,
    "nilloader": 14,
    "cleanroom": 15,
    "content_pack": 16,
    "javaagent": 17,
}

# The modpack filter uses a different ID space for loaders than the mod list.
MODPACK_LOADER_IDS = {
    "forge": 1,
    "fabric": 2,
    "quilt": 3,
    "datapack": 4,
    "data_pack": 4,
    "liteloader": 5,
    "lite_loader": 5,
    "rift": 6,
    "neoforge": 7,
    "behavior_pack": 8,
}

PACKAGING_IDS = {
    "curseforge": 1,
    "curseforge_managed": 1,
    "ftb": 2,
    "ftb_pack": 2,
    "other_launcher": 3,
    "launcher": 3,
    "manual": 4,
    "manual_trim": 4,
    "atlauncher": 5,
    "modrinth": 6,
    "other": 100,
}

PLATFORM_IDS = {"java": 1, "bedrock": 2}

STATUS_IDS = {"active": 1, "half": 2, "stopped": 3}

MODE_IDS = {
    "client": 1,
    "server": 2,
    "client_primary": 3,
    "server_primary": 4,
    "both_required": 5,
    "both_optional": 6,
}

SORT_IDS = {"default": None, "created": "createtime", "edited": "lastedittime"}


def _as_int(value: int | str | None, mapping: dict[str, int], name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    if text in mapping:
        return mapping[text]
    raise InvalidRequestError(f"unknown {name}: {value}")


class McmodService:
    def __init__(self, settings: Settings, http: McmodHttp, cache: CacheStore) -> None:
        self.settings = settings
        self.http = http
        self.cache = cache
        self._locks: dict[str, list] = {}
        self._locks_guard = threading.Lock()

    # ------------------------------------------------------------------ cache
    @contextmanager
    def _key_lock(self, key: str):
        with self._locks_guard:
            entry = self._locks.get(key)
            if entry is None:
                entry = [threading.Lock(), 0]
                self._locks[key] = entry
            entry[1] += 1
        entry[0].acquire()
        try:
            yield
        finally:
            entry[0].release()
            with self._locks_guard:
                entry[1] -= 1
                if entry[1] == 0:
                    self._locks.pop(key, None)

    def _envelope(
        self,
        data: T,
        *,
        cache_status: str,
        source: str,
        fetched_at: datetime,
        ttl: int | None,
    ) -> Envelope[T]:
        return Envelope[T](
            data=data,
            meta=Meta(
                cache=cache_status,  # type: ignore[arg-type]
                source=source,
                fetched_at=fetched_at,
                ttl=ttl,
                backend=self.settings.backend_name,
            ),
        )

    def _cached(
        self,
        resource: str,
        params: dict,
        *,
        ttl: int,
        model_cls: type[T],
        fetcher: Callable[[], tuple[T, str]],
        refresh: bool = False,
    ) -> Envelope[T]:
        key = cache_key(resource, params)
        cache_active = self.settings.cache_enabled and self.cache.enabled and ttl > 0
        if not cache_active:
            data, source = fetcher()
            return self._envelope(
                data, cache_status="disabled", source=source, fetched_at=datetime.now(UTC), ttl=None
            )

        if not refresh:
            hit = self._read_cache(key, model_cls)
            if hit is not None:
                return self._envelope(
                    hit[0],
                    cache_status="hit",
                    source=hit[1].source_url,
                    fetched_at=datetime.fromtimestamp(hit[1].fetched_at, UTC),
                    ttl=max(0, hit[1].expires_at - int(time.time())),
                )

        with self._key_lock(key):
            if not refresh:
                hit = self._read_cache(key, model_cls)
                if hit is not None:
                    return self._envelope(
                        hit[0],
                        cache_status="hit",
                        source=hit[1].source_url,
                        fetched_at=datetime.fromtimestamp(hit[1].fetched_at, UTC),
                        ttl=max(0, hit[1].expires_at - int(time.time())),
                    )
            data, source = fetcher()
            fetched_at = datetime.now(UTC)
            try:
                self.cache.set(
                    key,
                    resource=resource,
                    source_url=source,
                    payload=data.model_dump(mode="json"),
                    ttl=ttl,
                )
            except CacheError:
                pass
            return self._envelope(
                data,
                cache_status="bypass" if refresh else "miss",
                source=source,
                fetched_at=fetched_at,
                ttl=ttl,
            )

    def _read_cache(self, key: str, model_cls: type[T]):
        try:
            hit = self.cache.get(key)
        except CacheError:
            return None
        if hit is None:
            return None
        try:
            return model_cls.model_validate(hit.payload), hit
        except ValidationError as exc:
            logger.warning("discarding incompatible cache entry %s: %s", key[:12], exc)
            return None

    # ----------------------------------------------------------------- search
    def search(
        self,
        query: str,
        *,
        filter_name: str = "all",
        mold: str = "simple",
        page: int = 1,
        refresh: bool = False,
    ) -> Envelope[SearchPage]:
        if filter_name not in SEARCH_FILTERS:
            raise InvalidRequestError(f"unknown search filter: {filter_name}")
        if mold not in SEARCH_MOLDS:
            raise InvalidRequestError(f"unknown search mold: {mold}")

        def fetch() -> tuple[SearchPage, str]:
            result = self.http.get(
                "/s",
                host="search",
                params={
                    "key": query,
                    "filter": SEARCH_FILTERS[filter_name],
                    "mold": SEARCH_MOLDS[mold],
                    "page": page,
                },
            )
            data = parse_search(
                result.text,
                query=query,
                filter_name=filter_name,
                mold=mold,
                page=page,
            )
            return data, result.url

        return self._cached(
            "search",
            {"q": query, "filter": filter_name, "mold": mold, "page": page},
            ttl=self.settings.cache_ttl_search,
            model_cls=SearchPage,
            fetcher=fetch,
            refresh=refresh,
        )

    # ------------------------------------------------------------------- mods
    def list_mods(
        self,
        *,
        category: int | None = None,
        mc_version: str | None = None,
        platform: int | str | None = None,
        loader: int | str | None = None,
        status: int | str | None = None,
        mode: int | str | None = None,
        keyword: str | None = None,
        sort: str = "default",
        page: int = 1,
        refresh: bool = False,
    ) -> Envelope[ModListPage]:
        if sort not in SORT_IDS:
            raise InvalidRequestError(f"unknown sort: {sort}")
        params: dict[str, object] = {
            "category": category,
            "mcver": mc_version,
            "platform": _as_int(platform, PLATFORM_IDS, "platform"),
            "api": _as_int(loader, LOADER_IDS, "loader"),
            "status": _as_int(status, STATUS_IDS, "status"),
            "mode": _as_int(mode, MODE_IDS, "mode"),
            "key": keyword,
            "sort": SORT_IDS[sort],
            "page": page,
        }
        upstream = {key: value for key, value in params.items() if value not in (None, "")}

        def fetch() -> tuple[ModListPage, str]:
            result = self.http.get("/modlist.html", params=upstream)
            return parse_mod_list(result.text, page=page), result.url

        return self._cached(
            "mods",
            params,
            ttl=self.settings.cache_ttl_list,
            model_cls=ModListPage,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_mod(self, mod_id: int, *, refresh: bool = False) -> Envelope[ModDetail]:
        def fetch() -> tuple[ModDetail, str]:
            result = self.http.get(f"/class/{mod_id}.html")
            return parse_mod_detail(result.text, mod_id), result.url

        return self._cached(
            "mod",
            {"id": mod_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=ModDetail,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_mod_items(
        self,
        mod_id: int,
        *,
        type_id: int = 1,
        query: str | None = None,
        refresh: bool = False,
    ) -> Envelope[ModItemsPage]:
        def fetch() -> tuple[ModItemsPage, str]:
            result = self.http.get(f"/item/list/{mod_id}-{type_id}.html")
            return parse_mod_items(result.text, mod_id, type_id, query=query), result.url

        return self._cached(
            "mod-items",
            {"mod": mod_id, "type": type_id, "q": query},
            ttl=self.settings.cache_ttl_list,
            model_cls=ModItemsPage,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_mod_downloads(self, mod_id: int, *, refresh: bool = False) -> Envelope[DownloadsPage]:
        def fetch() -> tuple[DownloadsPage, str]:
            result = self.http.get(f"/download/{mod_id}.html")
            return parse_downloads(result.text, mod_id), result.url

        return self._cached(
            "downloads",
            {"mod": mod_id},
            ttl=self.settings.cache_ttl_list,
            model_cls=DownloadsPage,
            fetcher=fetch,
            refresh=refresh,
        )

    # ------------------------------------------------------------------ items
    def get_item(self, item_id: int, *, refresh: bool = False) -> Envelope[ItemDetail]:
        def fetch() -> tuple[ItemDetail, str]:
            result = self.http.get(f"/item/{item_id}.html")
            return parse_item_detail(result.text, item_id), result.url

        return self._cached(
            "item",
            {"id": item_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=ItemDetail,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_item_recipes(self, item_id: int, *, refresh: bool = False) -> Envelope[RecipesPage]:
        def fetch() -> tuple[RecipesPage, str]:
            result = self.http.get(f"/item/tab/{item_id}.html")
            return parse_recipes(result.text, item_id), result.url

        return self._cached(
            "item-recipes",
            {"id": item_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=RecipesPage,
            fetcher=fetch,
            refresh=refresh,
        )

    # --------------------------------------------------------------- modpacks
    def list_modpacks(
        self,
        *,
        category: int | None = None,
        mc_version: str | None = None,
        pack_type: int | str | None = None,
        loader: int | str | None = None,
        packaging: int | str | None = None,
        sort: str = "default",
        page: int = 1,
        refresh: bool = False,
    ) -> Envelope[ModpackListPage]:
        if sort not in SORT_IDS:
            raise InvalidRequestError(f"unknown sort: {sort}")
        params: dict[str, object] = {
            "category": category,
            "mcver": mc_version,
            "mold": _as_int(pack_type, {"native": 1, "modded": 2}, "pack_type"),
            "api": _as_int(loader, MODPACK_LOADER_IDS, "loader"),
            "pack": _as_int(packaging, PACKAGING_IDS, "packaging"),
            "sort": SORT_IDS[sort],
            "page": page,
        }
        upstream = {key: value for key, value in params.items() if value not in (None, "")}

        def fetch() -> tuple[ModpackListPage, str]:
            result = self.http.get("/modpack.html", params=upstream)
            return parse_modpack_list(result.text, page=page), result.url

        return self._cached(
            "modpacks",
            params,
            ttl=self.settings.cache_ttl_list,
            model_cls=ModpackListPage,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_modpack(self, pack_id: int, *, refresh: bool = False) -> Envelope[ModpackDetail]:
        def fetch() -> tuple[ModpackDetail, str]:
            result = self.http.get(f"/modpack/{pack_id}.html")
            return parse_modpack_detail(result.text, pack_id), result.url

        return self._cached(
            "modpack",
            {"id": pack_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=ModpackDetail,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_modpack_versions(
        self, pack_id: int, *, refresh: bool = False
    ) -> Envelope[ModpackVersionsPage]:
        def fetch() -> tuple[ModpackVersionsPage, str]:
            result = self.http.get(f"/modpack/version/{pack_id}.html")
            return parse_modpack_versions(result.text, pack_id), result.url

        return self._cached(
            "modpack-versions",
            {"id": pack_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=ModpackVersionsPage,
            fetcher=fetch,
            refresh=refresh,
        )

    # ------------------------------------------------------------ posts/authors
    def get_post(self, post_id: int, *, refresh: bool = False) -> Envelope[PostDetail]:
        def fetch() -> tuple[PostDetail, str]:
            result = self.http.get(f"/post/{post_id}.html")
            return parse_post(result.text, post_id), result.url

        return self._cached(
            "post",
            {"id": post_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=PostDetail,
            fetcher=fetch,
            refresh=refresh,
        )

    def get_author(self, author_id: int, *, refresh: bool = False) -> Envelope[AuthorDetail]:
        def fetch() -> tuple[AuthorDetail, str]:
            result = self.http.get(f"/author/{author_id}.html")
            return parse_author(result.text, author_id), result.url

        return self._cached(
            "author",
            {"id": author_id},
            ttl=self.settings.cache_ttl_detail,
            model_cls=AuthorDetail,
            fetcher=fetch,
            refresh=refresh,
        )

    # ------------------------------------------------------------------- meta
    def get_filters(self, kind: str = "mod", *, refresh: bool = False) -> Envelope[FilterOptions]:
        if kind not in {"mod", "modpack"}:
            raise InvalidRequestError(f"unknown filter kind: {kind}")
        path = "/modlist.html" if kind == "mod" else "/modpack.html"

        def fetch() -> tuple[FilterOptions, str]:
            result = self.http.get(path)
            return parse_filters(result.text, kind), result.url

        return self._cached(
            "filters",
            {"kind": kind},
            ttl=self.settings.cache_ttl_meta,
            model_cls=FilterOptions,
            fetcher=fetch,
            refresh=refresh,
        )

    # ------------------------------------------------------------------ cache
    def cache_stats(self) -> CacheStats:
        if not self.settings.cache_enabled or not self.cache.enabled:
            return CacheStats(
                backend=self.settings.backend_name, enabled=False, entries=0, expired=0, hits=0
            )
        stats = self.cache.stats()
        return CacheStats(
            backend=self.settings.backend_name,
            enabled=True,
            entries=stats["entries"],
            expired=stats["expired"],
            hits=stats["hits"],
            size_bytes=stats["size_bytes"],
        )

    def clear_cache(self) -> int:
        return self.cache.clear()
