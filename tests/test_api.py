from __future__ import annotations

from fastapi.testclient import TestClient

from mcmod.api import create_app
from mcmod.config import Settings
from mcmod.service import McmodService


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["backend"] == "sqlite"
    assert payload["cache"]["enabled"] is True


def test_mod_detail_cache_hit_and_refresh(client: TestClient) -> None:
    first = client.get("/api/v1/mods/2")
    assert first.status_code == 200
    assert first.headers["x-cache"] == "miss"
    body = first.json()
    assert body["data"]["name"] == "工业时代2"
    assert body["meta"]["cache"] == "miss"
    assert body["meta"]["backend"] == "sqlite"
    assert body["meta"]["source"].endswith("/class/2.html")

    second = client.get("/api/v1/mods/2")
    assert second.status_code == 200
    assert second.headers["x-cache"] == "hit"
    assert second.json()["data"] == body["data"]
    assert second.json()["meta"]["cache"] == "hit"

    refreshed = client.get("/api/v1/mods/2", params={"refresh": "true"})
    assert refreshed.status_code == 200
    assert refreshed.headers["x-cache"] == "bypass"
    assert refreshed.json()["meta"]["cache"] == "bypass"


def test_all_read_endpoints(client: TestClient) -> None:
    cases = [
        ("/api/v1/search", {"q": "工业化"}),
        ("/api/v1/mods", {"loader": "forge", "status": "stopped"}),
        ("/api/v1/mods/2", {}),
        ("/api/v1/mods/2/items", {"type_id": 1}),
        ("/api/v1/mods/2/items", {"type_id": 1, "q": "金粉"}),
        ("/api/v1/mods/2/downloads", {}),
        ("/api/v1/items/233", {}),
        ("/api/v1/items/233/recipes", {}),
        ("/api/v1/modpacks", {}),
        ("/api/v1/modpacks/1026", {}),
        ("/api/v1/modpacks/1026/versions", {}),
        ("/api/v1/posts/3339", {}),
        ("/api/v1/authors/21425", {}),
        ("/api/v1/meta/filters", {"kind": "mod"}),
        ("/api/v1/meta/filters", {"kind": "modpack"}),
    ]
    for path, params in cases:
        response = client.get(path, params=params)
        assert response.status_code == 200, (path, response.text)
        payload = response.json()
        assert "data" in payload and "meta" in payload
        assert payload["meta"]["cache"] in {"miss", "hit"}


def test_mcp_json_rpc_on_same_port(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Host": "127.0.0.1:8000"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert "mcp-session-id" not in response.headers
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert any(tool["name"] == "mcmod_search" for tool in payload["result"]["tools"])


def test_not_found_and_validation_errors(client: TestClient) -> None:
    missing = client.get("/api/v1/mods/99999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    invalid = client.get("/api/v1/search")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"

    invalid_filter = client.get("/api/v1/search", params={"q": "x", "filter": "nope"})
    assert invalid_filter.status_code == 422
    assert invalid_filter.json()["error"]["code"] == "invalid_request"


def test_api_key_protects_data_and_cache(settings: Settings, service: McmodService) -> None:
    settings = settings.model_copy(update={"api_key": "secret"})
    app = create_app(settings, service)
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app) as client:
        denied = client.get("/api/v1/mods/2")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "unauthorized"
        assert denied.headers["www-authenticate"].startswith("Bearer")
        assert client.get(
            "/api/v1/mods/2", headers={"Authorization": "Bearer wrong"}
        ).status_code == 401

        assert client.get("/api/v1/mods/2", headers=headers).status_code == 200
        stats = client.get("/api/v1/cache/stats", headers=headers).json()
        assert stats["entries"] >= 1
        assert stats["hits"] == 0

        assert client.get("/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200

        mcp_payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        mcp_host = {"Host": "127.0.0.1:8000"}
        assert (
            client.post("/mcp", json=mcp_payload, headers=mcp_host).status_code == 401
        )
        mcp_allowed = client.post(
            "/mcp",
            json=mcp_payload,
            headers={**mcp_host, "Authorization": "Bearer secret"},
        )
        assert mcp_allowed.status_code == 200
        assert mcp_allowed.headers["content-type"] == "application/json"

        denied = client.delete("/api/v1/cache")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "unauthorized"

        allowed = client.delete("/api/v1/cache", headers=headers)
        assert allowed.status_code == 200
        assert allowed.json()["deleted"] >= 1
        assert client.get("/api/v1/cache/stats", headers=headers).json()["entries"] == 0

        purge = client.post(
            "/api/v1/cache/purge", headers={"X-API-Key": "secret"}
        )
        assert purge.status_code == 200


def test_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/search" in paths
    assert "/api/v1/mods/{mod_id}" in paths
    assert "/api/v1/items/{item_id}/recipes" in paths
    assert "/api/v1/modpacks/{pack_id}/versions" in paths


def test_modpack_filters_use_their_own_id_space(service, fake_http) -> None:
    pack = service.list_modpacks(loader="neoforge", packaging="modrinth", refresh=True)
    assert pack.data.page_info.page == 1
    _, path, params = fake_http.requests[-1]
    assert path == "/modpack.html"
    assert params["api"] == 7
    assert params["pack"] == 6

    mods = service.list_mods(loader="neoforge", refresh=True)
    assert mods.data.items
    _, path, params = fake_http.requests[-1]
    assert path == "/modlist.html"
    assert params["api"] == 13

    pack = service.list_modpacks(pack_type="modded", refresh=True)
    assert fake_http.requests[-1][2]["mold"] == 2


def test_cache_unavailable_returns_503_and_degrades_health(client, service, monkeypatch) -> None:
    from mcmod.cache import CacheError

    def boom():
        raise CacheError("database is down")

    monkeypatch.setattr(service.cache, "stats", boom)
    stats = client.get("/api/v1/cache/stats")
    assert stats.status_code == 503
    assert stats.json()["error"]["code"] == "cache_unavailable"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "degraded"
    assert "database is down" in health.json()["cache"]["error"]
