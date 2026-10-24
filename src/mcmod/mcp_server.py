"""MCP tools exposed over the REST API's JSON-RPC endpoint."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .client import McmodApiClient
from .config import Settings
from .errors import ApiClientError
from .parsers.common import extract_id


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _id(value: int | str, kind: str) -> int:
    parsed = extract_id(value, kind)
    if parsed is None:
        raise ToolError(f"invalid {kind} identifier: {value!r} (expected an id or mcmod URL)")
    return parsed


def build_server(
    *,
    settings: Settings | None = None,
    client: McmodApiClient | None = None,
) -> MCPServer:
    settings = settings or Settings()
    api = client or McmodApiClient(
        settings.api_base,
        timeout=settings.timeout + 15,
        api_key=settings.api_key or None,
    )

    def request(path: str, params: dict[str, Any] | None = None, refresh: bool = False) -> str:
        try:
            return _json(api.get(path, params=params, refresh=refresh))
        except ApiClientError as exc:
            suffix = f" ({exc.status_code})" if exc.status_code else ""
            raise ToolError(f"{exc.code}{suffix}: {exc.message}") from exc

    server = MCPServer(
        name="mcmod",
        title="MC百科 (mcmod.cn)",
        version=__version__,
        instructions=(
            "Read-only tools for MC百科 (mcmod.cn), the Chinese Minecraft mod wiki. "
            "Search mods, modpacks, items, tutorials and authors; fetch mod/item/modpack "
            "details, crafting recipes/usages, download metadata and filter options. "
            "All results come from SSR HTML parsed by the local API server, and include "
            "a `meta` block with cache status and freshness. IDs accept either a number "
            "or a full mcmod.cn URL."
        ),
        log_level="WARNING",
    )

    @server.tool(
        description="搜索 MC百科（模组/整合包/资料/教程/作者/用户/社群）。filter=all|mods|modpacks|items|tutorials|authors|users|community；mold=simple|full。"
    )
    def mcmod_search(
        query: str,
        filter: str = "all",
        mold: str = "simple",
        page: int = 1,
        refresh: bool = False,
    ) -> str:
        return request(
            "/api/v1/search",
            {"q": query, "filter": filter, "mold": mold, "page": page},
            refresh,
        )

    @server.tool(
        description="列出/筛选模组（modlist）。category、mcver、platform、loader、status、mode 可使用数字 ID 或名称（如 forge/fabric、active/stopped、client/server）；sort=default|created|edited。"
    )
    def mcmod_list_mods(
        category: int | None = None,
        mc_version: str | None = None,
        platform: str | None = None,
        loader: str | None = None,
        status: str | None = None,
        mode: str | None = None,
        keyword: str | None = None,
        sort: str = "default",
        page: int = 1,
        refresh: bool = False,
    ) -> str:
        return request(
            "/api/v1/mods",
            {
                "category": category,
                "mcver": mc_version,
                "platform": platform,
                "loader": loader,
                "status": status,
                "mode": mode,
                "keyword": keyword,
                "sort": sort,
                "page": page,
            },
            refresh,
        )

    @server.tool(description="获取模组详情：状态、分类、加载器、版本、作者、评分、简介、物品类型、教程、依赖关系、下载统计等。")
    def mcmod_get_mod(mod: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/mods/{_id(mod, 'mod')}", refresh=refresh)

    @server.tool(description="获取模组资料列表（默认 type_id=1 即物品/方块），可按名称关键词过滤。type_id 来自模组详情 item_types。")
    def mcmod_get_mod_items(
        mod: int | str,
        type_id: int = 1,
        keyword: str | None = None,
        refresh: bool = False,
    ) -> str:
        return request(
            f"/api/v1/mods/{_id(mod, 'mod')}/items",
            {"type_id": type_id, "q": keyword},
            refresh,
        )

    @server.tool(description="获取模组下载文件元数据（文件名、加载器、MC 版本、大小、下载量、哈希）。不会触发文件下载。")
    def mcmod_get_mod_downloads(mod: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/mods/{_id(mod, 'mod')}/downloads", refresh=refresh)

    @server.tool(description="获取物品/方块/实体等资料详情：注册命令、矿物词典、属性表、正文、相关物品。")
    def mcmod_get_item(item: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/items/{_id(item, 'item')}", refresh=refresh)

    @server.tool(description="获取物品的完整合成表与用途（材料、产出、工作台、备注、版本限制）。")
    def mcmod_get_item_recipes(item: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/items/{_id(item, 'item')}/recipes", refresh=refresh)

    @server.tool(
        description="列出/筛选整合包。pack_type=native|modded；loader/packaging 可用数字或名称；sort=default|created|edited。"
    )
    def mcmod_list_modpacks(
        category: int | None = None,
        mc_version: str | None = None,
        pack_type: str | None = None,
        loader: str | None = None,
        packaging: str | None = None,
        sort: str = "default",
        page: int = 1,
        refresh: bool = False,
    ) -> str:
        return request(
            "/api/v1/modpacks",
            {
                "category": category,
                "mcver": mc_version,
                "mold": pack_type,
                "loader": loader,
                "pack": packaging,
                "sort": sort,
                "page": page,
            },
            refresh,
        )

    @server.tool(description="获取整合包详情：介绍、分类、团队、支持的 MC 版本、包含的模组（按分类）等。")
    def mcmod_get_modpack(pack: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/modpacks/{_id(pack, 'modpack')}", refresh=refresh)

    @server.tool(description="获取整合包更新日志（版本号、日期、更新内容）。")
    def mcmod_get_modpack_versions(pack: int | str, refresh: bool = False) -> str:
        return request(
            f"/api/v1/modpacks/{_id(pack, 'modpack')}/versions",
            refresh=refresh,
        )

    @server.tool(description="获取教程/讨论文章：作者、浏览量、时间、授权协议、正文 HTML/纯文本、引用到的模组与物品。")
    def mcmod_get_post(post: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/posts/{_id(post, 'post')}", refresh=refresh)

    @server.tool(description="获取作者/开发团队资料：简介、团队成员、合作作者、参与项目。")
    def mcmod_get_author(author: int | str, refresh: bool = False) -> str:
        return request(f"/api/v1/authors/{_id(author, 'author')}", refresh=refresh)

    @server.tool(description="获取检索筛选项（分类、MC 版本、加载器、状态、运行环境、排序等）。kind=mod|modpack。")
    def mcmod_get_filters(kind: str = "mod", refresh: bool = False) -> str:
        return request("/api/v1/meta/filters", {"kind": kind}, refresh)

    @server.tool(description="查看 API 结果缓存的条目数、未过期/已过期数量和累计命中次数。")
    def mcmod_cache_stats() -> str:
        try:
            return _json(api.get("/api/v1/cache/stats"))
        except ApiClientError as exc:
            raise ToolError(f"{exc.code}: {exc.message}") from exc

    return server
