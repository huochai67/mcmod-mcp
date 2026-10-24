"""FastAPI application exposing mcmod.cn data with a persistent result cache."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .cache import CacheError, CacheStore
from .config import Settings
from .db import create_engine_from_settings, init_database, make_session_factory, ping_database
from .errors import AuthenticationError, McmodError
from .http import McmodHttp
from .models import (
    AuthorDetail,
    CacheClearResult,
    CacheStats,
    DownloadsPage,
    Envelope,
    FilterOptions,
    HealthStatus,
    ItemDetail,
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
from .service import McmodService

logger = logging.getLogger(__name__)


def _service(request: Request) -> McmodService:
    return request.app.state.service


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _finish(response: Response, envelope: Envelope) -> Envelope:
    response.headers["X-Cache"] = envelope.meta.cache
    response.headers["Cache-Control"] = "no-store"
    return envelope


def _admin_dependency(request: Request, token: str | None = Header(default=None, alias="X-Admin-Token")):
    settings = _settings(request)
    if settings.admin_token and token != settings.admin_token:
        raise AuthenticationError("invalid or missing admin token")


def create_app(
    settings: Settings | None = None,
    service: McmodService | None = None,
) -> FastAPI:
    settings = settings or Settings()
    owns_resources = service is None
    engine = None
    http = None
    cache = None
    if service is None:
        engine = create_engine_from_settings(settings)
        init_database(engine)
        session_factory = make_session_factory(engine)
        cache = CacheStore(session_factory, enabled=settings.cache_enabled)
        http = McmodHttp(settings)
        service = McmodService(settings, http, cache)
    else:
        engine = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if cache is not None:
            try:
                cache.purge_expired()
            except CacheError as exc:
                logger.warning("could not purge expired cache rows: %s", exc)
        yield
        if owns_resources:
            if http is not None:
                http.close()
            if engine is not None:
                engine.dispose()

    app = FastAPI(
        title="mcmod.cn API",
        version=__version__,
        description=(
            "Unofficial read-only API for mcmod.cn (Minecraft Mod Wiki). "
            "Results are parsed from server-rendered HTML and cached in SQLite or MariaDB."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.service = service
    app.state.cache = cache
    app.state.engine = engine
    app.state.owns_resources = owns_resources

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    @app.exception_handler(McmodError)
    async def _mcmod_error(_request: Request, exc: McmodError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "detail": exc.detail,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "request validation failed",
                    "detail": exc.errors(),
                }
            },
        )

    @app.exception_handler(CacheError)
    async def _cache_error(_request: Request, exc: CacheError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "cache_unavailable",
                    "message": "cache backend is unavailable",
                    "detail": str(exc),
                }
            },
        )

    @app.get("/health", response_model=HealthStatus, tags=["system"])
    def health(request: Request) -> HealthStatus:
        current_settings = _settings(request)
        db_ok = True
        if request.app.state.engine is not None:
            db_ok = ping_database(request.app.state.engine)
        cache_error = None
        try:
            stats = _service(request).cache_stats()
        except CacheError as exc:
            cache_error = str(exc)
            stats = CacheStats(
                backend=current_settings.backend_name,
                enabled=current_settings.cache_enabled,
                entries=0,
                expired=0,
                hits=0,
                error=cache_error,
            )
        status: Literal["ok", "degraded"] = "ok" if db_ok and cache_error is None else "degraded"
        return HealthStatus(
            status=status,
            version=__version__,
            backend=current_settings.backend_name,
            cache=stats,
        )

    # ----------------------------------------------------------------- search
    @app.get("/api/v1/search", response_model=Envelope[SearchPage], tags=["search"])
    def search(
        response: Response,
        q: str = Query(..., min_length=1, max_length=120),
        filter_name: Literal[
            "all", "mods", "modpacks", "items", "tutorials", "authors", "users", "community"
        ] = Query("all", alias="filter"),
        mold: Literal["simple", "full"] = "simple",
        page: int = Query(1, ge=1, le=1000),
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[SearchPage]:
        return _finish(
            response,
            svc.search(q, filter_name=filter_name, mold=mold, page=page, refresh=refresh),
        )

    # ------------------------------------------------------------------- mods
    @app.get("/api/v1/mods", response_model=Envelope[ModListPage], tags=["mods"])
    def list_mods(
        response: Response,
        category: int | None = Query(None, ge=1),
        mcver: str | None = None,
        platform: str | None = None,
        loader: str | None = None,
        status: str | None = None,
        mode: str | None = None,
        keyword: str | None = Query(None, max_length=120),
        sort: Literal["default", "created", "edited"] = "default",
        page: int = Query(1, ge=1, le=2000),
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ModListPage]:
        return _finish(
            response,
            svc.list_mods(
                category=category,
                mc_version=mcver,
                platform=platform,
                loader=loader,
                status=status,
                mode=mode,
                keyword=keyword,
                sort=sort,
                page=page,
                refresh=refresh,
            ),
        )

    @app.get("/api/v1/mods/{mod_id}", response_model=Envelope[ModDetail], tags=["mods"])
    def get_mod(
        mod_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ModDetail]:
        return _finish(response, svc.get_mod(mod_id, refresh=refresh))

    @app.get(
        "/api/v1/mods/{mod_id}/items",
        response_model=Envelope[ModItemsPage],
        tags=["mods"],
    )
    def get_mod_items(
        mod_id: int,
        response: Response,
        type_id: int = Query(1, ge=1, le=100),
        q: str | None = Query(None, max_length=120),
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ModItemsPage]:
        return _finish(
            response, svc.get_mod_items(mod_id, type_id=type_id, query=q, refresh=refresh)
        )

    @app.get(
        "/api/v1/mods/{mod_id}/downloads",
        response_model=Envelope[DownloadsPage],
        tags=["mods"],
    )
    def get_mod_downloads(
        mod_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[DownloadsPage]:
        return _finish(response, svc.get_mod_downloads(mod_id, refresh=refresh))

    # ------------------------------------------------------------------ items
    @app.get("/api/v1/items/{item_id}", response_model=Envelope[ItemDetail], tags=["items"])
    def get_item(
        item_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ItemDetail]:
        return _finish(response, svc.get_item(item_id, refresh=refresh))

    @app.get(
        "/api/v1/items/{item_id}/recipes",
        response_model=Envelope[RecipesPage],
        tags=["items"],
    )
    def get_item_recipes(
        item_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[RecipesPage]:
        return _finish(response, svc.get_item_recipes(item_id, refresh=refresh))

    # --------------------------------------------------------------- modpacks
    @app.get("/api/v1/modpacks", response_model=Envelope[ModpackListPage], tags=["modpacks"])
    def list_modpacks(
        response: Response,
        category: int | None = Query(None, ge=1),
        mcver: str | None = None,
        pack_type: str | None = Query(None, alias="mold"),
        loader: str | None = None,
        packaging: str | None = Query(None, alias="pack"),
        sort: Literal["default", "created", "edited"] = "default",
        page: int = Query(1, ge=1, le=1000),
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ModpackListPage]:
        return _finish(
            response,
            svc.list_modpacks(
                category=category,
                mc_version=mcver,
                pack_type=pack_type,
                loader=loader,
                packaging=packaging,
                sort=sort,
                page=page,
                refresh=refresh,
            ),
        )

    @app.get(
        "/api/v1/modpacks/{pack_id}",
        response_model=Envelope[ModpackDetail],
        tags=["modpacks"],
    )
    def get_modpack(
        pack_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ModpackDetail]:
        return _finish(response, svc.get_modpack(pack_id, refresh=refresh))

    @app.get(
        "/api/v1/modpacks/{pack_id}/versions",
        response_model=Envelope[ModpackVersionsPage],
        tags=["modpacks"],
    )
    def get_modpack_versions(
        pack_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[ModpackVersionsPage]:
        return _finish(response, svc.get_modpack_versions(pack_id, refresh=refresh))

    # ------------------------------------------------------------ posts/authors
    @app.get("/api/v1/posts/{post_id}", response_model=Envelope[PostDetail], tags=["posts"])
    def get_post(
        post_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[PostDetail]:
        return _finish(response, svc.get_post(post_id, refresh=refresh))

    @app.get(
        "/api/v1/authors/{author_id}",
        response_model=Envelope[AuthorDetail],
        tags=["authors"],
    )
    def get_author(
        author_id: int,
        response: Response,
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[AuthorDetail]:
        return _finish(response, svc.get_author(author_id, refresh=refresh))

    # ------------------------------------------------------------------- meta
    @app.get("/api/v1/meta/filters", response_model=Envelope[FilterOptions], tags=["meta"])
    def get_filters(
        response: Response,
        kind: Literal["mod", "modpack"] = "mod",
        refresh: bool = False,
        svc: McmodService = Depends(_service),
    ) -> Envelope[FilterOptions]:
        return _finish(response, svc.get_filters(kind, refresh=refresh))

    # ------------------------------------------------------------------ cache
    @app.get("/api/v1/cache/stats", response_model=CacheStats, tags=["cache"])
    def cache_stats(svc: McmodService = Depends(_service)) -> CacheStats:
        return svc.cache_stats()

    @app.post(
        "/api/v1/cache/purge",
        response_model=CacheClearResult,
        tags=["cache"],
        dependencies=[Depends(_admin_dependency)],
    )
    def purge_cache(svc: McmodService = Depends(_service)) -> CacheClearResult:
        return CacheClearResult(deleted=svc.cache.purge_expired())

    @app.delete(
        "/api/v1/cache",
        response_model=CacheClearResult,
        tags=["cache"],
        dependencies=[Depends(_admin_dependency)],
    )
    def clear_cache(svc: McmodService = Depends(_service)) -> CacheClearResult:
        return CacheClearResult(deleted=svc.clear_cache())

    return app


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "mcmod.api:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    main()
