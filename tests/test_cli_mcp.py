from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from typer.testing import CliRunner

import mcmod.cli as cli_module
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

    def __init__(self, *args, **kwargs) -> None:
        pass

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
