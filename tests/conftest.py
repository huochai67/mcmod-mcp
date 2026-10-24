from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mcmod.api import create_app
from mcmod.cache import CacheStore
from mcmod.config import Settings
from mcmod.db import create_engine_from_settings, init_database, make_session_factory
from mcmod.errors import NotFoundError
from mcmod.http import FetchResult
from mcmod.service import McmodService

FIXTURE_DIR = Path(__file__).parent / "fixtures"

PAGE_FIXTURES = {
    "/modlist.html": "modlist.html",
    "/modpack.html": "modpack_list.html",
    "/class/2.html": "mod_2.html",
    "/item/list/2-1.html": "item_list_2_1.html",
    "/download/2.html": "download_2.html",
    "/item/233.html": "item_233.html",
    "/item/tab/233.html": "item_tab_233.html",
    "/modpack/1026.html": "modpack_1026.html",
    "/modpack/version/1026.html": "modpack_version_1026.html",
    "/post/3339.html": "post_3339.html",
    "/author/21425.html": "author_21425.html",
}


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8", errors="ignore")


class FakeHttp:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict | None]] = []

    def get(self, path: str, *, host: str = "main", params: dict | None = None) -> FetchResult:
        self.requests.append((host, path, params))
        if host == "search":
            return FetchResult(
                read_fixture("search_industrialization.html"),
                "https://search.mcmod.cn/s?key=x",
                200,
            )
        fixture = PAGE_FIXTURES.get(path)
        if fixture is None:
            raise NotFoundError(f"no fixture for {path}")
        return FetchResult(read_fixture(fixture), f"https://www.mcmod.cn{path}", 200)

    def close(self) -> None:
        pass


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        min_interval=0,
        cache_enabled=True,
    )


@pytest.fixture()
def engine(settings: Settings):
    engine = create_engine_from_settings(settings)
    init_database(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def fake_http() -> FakeHttp:
    return FakeHttp()


@pytest.fixture()
def cache(engine) -> CacheStore:
    return CacheStore(make_session_factory(engine))


@pytest.fixture()
def service(settings: Settings, fake_http: FakeHttp, cache: CacheStore) -> McmodService:
    return McmodService(settings, fake_http, cache)


@pytest.fixture()
def client(settings: Settings, service: McmodService) -> TestClient:
    app = create_app(settings, service)
    with TestClient(app) as test_client:
        yield test_client
