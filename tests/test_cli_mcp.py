from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from typer.testing import CliRunner

import mcmod.cli as cli_module
from mcmod.auth import ApiKeyMiddleware
from mcmod.cli import app as cli_app
from mcmod.client import McmodApiClient
from mcmod.mcp_server import build_server

MOD_ENVELOPE = {
    "data": {
        "id": 2,
        "name": "工业时代2",
        "short_name": "[IC2]",
        "name_en": "Industrial Craft 2",
        "url": "https://www.mcmod.cn/class/2.html",
        "statuses": [{"kind": "status", "label": "停更", "description": None}],
        "categories": [{"id": 1, "name": "科技", "url": None, "main": True, "description": None}],
        "platforms": [],
        "loaders": [{"id": 1, "name": "Forge", "url": None, "main": False, "description": None}],
        "environment": [],
        "tags": ["工业"],
        "stats": {"score": 5.0, "rank": "名扬天下", "total_views_text": "2444.96万", "total_views": 24449626},
        "item_types": [{"id": 1, "name": "物品/方块", "count": 615, "url": "x"}],
        "tutorials_total": 105,
        "discussions_total": 46,
        "features_total": 12,
        "download_files_count": 226,
        "modpack_usage": 100,
        "intro_text": "工业时代2是围绕 Minecraft 生活现代化和生产自动化两个主题而展开的模组。",
        "links": [{"name": "GitHub", "url": "https://github.com/x", "description": None}],
        "versions": [{"platform": "Forge", "total": 1, "versions": [{"version": "1.12.2", "url": None}]}],
    },
    "meta": {
        "cache": "hit",
        "source": "https://www.mcmod.cn/class/2.html",
        "fetched_at": "2026-01-01T00:00:00Z",
        "ttl": 100,
        "backend": "sqlite",
    },
}

SEARCH_ENVELOPE = {
    "data": {
        "query": "工业化",
        "filter": "all",
        "mold": "simple",
        "counts": {"all": 2},
        "results": [
            {
                "title": "[MI] 现代工业化 (Modern Industrialization)",
                "url": "https://www.mcmod.cn/class/3472.html",
                "type": "mod",
                "snippet": "科技模组",
                "source": "MC百科主站",
                "snapshot_date": "2026-10-17",
                "categories": [],
            }
        ],
        "page_info": {"page": 1, "per_page": 15, "total_pages": 1, "total": 2},
    },
    "meta": {
        "cache": "miss",
        "source": "https://search.mcmod.cn/s?key=x",
        "fetched_at": "2026-01-01T00:00:00Z",
        "ttl": 100,
        "backend": "sqlite",
    },
}


class FakeApiClient:
    deleted = False
    last_kwargs: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        type(self).last_kwargs = kwargs

    def get(self, path: str, *, params=None, refresh: bool = False):
        if path == "/health":
            return {"status": "ok", "version": "0.1.0", "backend": "sqlite", "cache": {}}
        if path == "/api/v1/search":
            return SEARCH_ENVELOPE
        if path.startswith("/api/v1/mods/"):
            return MOD_ENVELOPE
        return {"data": {}, "meta": {}}

    def post(self, path: str, *, params=None):
        return {"deleted": 3}

    def delete(self, path: str, *, params=None):
        FakeApiClient.deleted = True
        return {"deleted": 5}

    def close(self) -> None:
        pass


@pytest.fixture()
def cli(monkeypatch):
    monkeypatch.setattr(cli_module, "McmodApiClient", FakeApiClient)
    return CliRunner()


def test_cli_search_json(cli: CliRunner) -> None:
    result = cli.invoke(cli_app, ["--json", "search", "工业化"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["results"][0]["type"] == "mod"
    assert payload["meta"]["cache"] == "miss"


def test_cli_mod_human_output(cli: CliRunner) -> None:
    result = cli.invoke(cli_app, ["mod", "https://www.mcmod.cn/class/2.html"])
    assert result.exit_code == 0, result.output
    assert "工业时代2" in result.output
    assert "名扬天下" in result.output
    assert "Forge" in result.output


def test_cli_cache_commands(cli: CliRunner) -> None:
    FakeApiClient.deleted = False
    result = cli.invoke(cli_app, ["cache", "clear", "--yes"])
    assert result.exit_code == 0
    assert "deleted 5" in result.output
    assert FakeApiClient.deleted is True

    result = cli.invoke(cli_app, ["cache", "purge"])
    assert result.exit_code == 0
    assert "deleted 3" in result.output


def test_cli_help() -> None:
    result = CliRunner().invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output


def test_cli_api_key_option(cli: CliRunner) -> None:
    FakeApiClient.last_kwargs = None
    result = cli.invoke(cli_app, ["--api-key", "secret", "health"])
    assert result.exit_code == 0, result.output
    assert FakeApiClient.last_kwargs is not None
    assert FakeApiClient.last_kwargs["api_key"] == "secret"


def _mcp_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v1/mods/2":
        return httpx.Response(200, json=MOD_ENVELOPE)
    return httpx.Response(
        404,
        json={"error": {"code": "not_found", "message": "page not found", "detail": None}},
    )


def test_mcp_tools_and_call() -> None:
    api = McmodApiClient("http://test", transport=httpx.MockTransport(_mcp_handler))

    async def run() -> None:
        server = build_server(client=api)
        tools = await server.list_tools()
        names = {tool.name for tool in tools}
        assert {
            "mcmod_search",
            "mcmod_get_mod",
            "mcmod_get_item",
            "mcmod_get_item_recipes",
            "mcmod_get_modpack",
            "mcmod_get_post",
            "mcmod_get_author",
            "mcmod_get_filters",
        } <= names

        result = await server.call_tool("mcmod_get_mod", {"mod": 2})
        text = result.content[0].text
        assert "工业时代2" in text
        assert '"cache": "hit"' in text

        result = await server.call_tool(
            "mcmod_get_mod", {"mod": "https://www.mcmod.cn/class/2.html"}
        )
        assert "工业时代2" in result.content[0].text

        with pytest.raises(ToolError):
            await server.call_tool("mcmod_get_mod", {"mod": 999})

        with pytest.raises(ToolError):
            await server.call_tool("mcmod_get_mod", {"mod": "not-an-id"})

    asyncio.run(run())


def test_api_client_sends_shared_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {}, "meta": {}})

    api = McmodApiClient(
        "http://test",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    assert api.get("/api/v1/mods/2") == {"data": {}, "meta": {}}
    assert seen[0].headers["authorization"] == "Bearer secret"


def test_mcp_http_json_rpc_and_shared_key() -> None:
    api = McmodApiClient("http://test", transport=httpx.MockTransport(_mcp_handler))
    server = build_server(client=api)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
    app.add_middleware(ApiKeyMiddleware, api_key="secret")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    accept = {"Accept": "application/json, text/event-stream", "Host": "127.0.0.1:8000"}

    with TestClient(app) as client:
        denied = client.post("/mcp", json=payload, headers=accept)
        assert denied.status_code == 401

        allowed = client.post(
            "/mcp",
            json=payload,
            headers={**accept, "Authorization": "Bearer secret"},
        )
        assert allowed.status_code == 200
        assert allowed.headers["content-type"] == "application/json"
        assert "mcp-session-id" not in allowed.headers
        result = allowed.json()
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert any(tool["name"] == "mcmod_search" for tool in result["result"]["tools"])

        called = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "mcmod_get_mod", "arguments": {"mod": 2}},
            },
            headers={**accept, "Authorization": "Bearer secret"},
        )
        assert called.status_code == 200
        text = called.json()["result"]["content"][0]["text"]
        assert "工业时代2" in text

        via_header = client.post(
            "/mcp",
            json=payload,
            headers={**accept, "X-API-Key": "secret"},
        )
        assert via_header.status_code == 200
        assert via_header.json()["jsonrpc"] == "2.0"
