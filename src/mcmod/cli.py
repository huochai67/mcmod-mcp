"""Typer CLI client for the mcmod REST API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import typer
import uvicorn
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client import McmodApiClient
from .config import Settings
from .errors import ApiClientError

app = typer.Typer(
    name="mcmod",
    help="MC百科 (mcmod.cn) API 客户端：检索模组、整合包、资料、教程。",
    no_args_is_help=True,
    add_completion=False,
)
cache_app = typer.Typer(help="管理 API 结果缓存。", no_args_is_help=True)
app.add_typer(cache_app, name="cache")

console = Console()
stdout = Console(highlight=False)


@dataclass
class CliState:
    client: McmodApiClient
    json_output: bool


def _state(ctx: typer.Context) -> CliState:
    return ctx.obj


def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(exc: ApiClientError) -> None:
    console.print(f"[red]错误[/red] {exc.code}: {exc.message}")
    if exc.detail:
        console.print(f"[dim]{exc.detail}[/dim]")
    raise typer.Exit(1)


def _meta_caption(envelope: dict[str, Any]) -> str:
    meta = envelope.get("meta") or {}
    cache = meta.get("cache", "?")
    fetched = meta.get("fetched_at", "?")
    source = meta.get("source", "")
    return f"cache={cache}  fetched={fetched}  source={source}"


def _short(value: str | None, length: int = 80) -> str:
    if not value:
        return ""
    value = " ".join(value.split())
    return value if len(value) <= length else value[: length - 1] + "…"


def _page_caption(envelope: dict[str, Any]) -> str:
    page_info = envelope.get("data", {}).get("page_info") or {}
    if not page_info:
        return _meta_caption(envelope)
    return (
        f"page {page_info.get('page')}/{page_info.get('total_pages')}  "
        f"total {page_info.get('total')}  |  {_meta_caption(envelope)}"
    )


@app.callback()
def _callback(
    ctx: typer.Context,
    api: str = typer.Option(
        None,
        "--api",
        envvar="MCMOD_API_BASE",
        help="API 服务地址（默认 http://127.0.0.1:8000）",
    ),
    json_output: bool = typer.Option(False, "--json", help="输出原始 JSON（含 meta）"),
    admin_token: str = typer.Option(
        None, "--admin-token", envvar="MCMOD_ADMIN_TOKEN", help="缓存管理令牌"
    ),
) -> None:
    settings = Settings()
    client = McmodApiClient(
        api or settings.api_base,
        timeout=settings.timeout + 15,
        admin_token=admin_token or settings.admin_token or None,
    )
    ctx.obj = CliState(client=client, json_output=json_output)


@app.command()
def serve(
    host: str = typer.Option(None, help="监听地址，默认读取 MCMOD_API_HOST"),
    port: int = typer.Option(None, help="监听端口，默认读取 MCMOD_API_PORT"),
    reload: bool = typer.Option(False, "--reload", help="开发模式自动重载"),
) -> None:
    """启动 REST API 服务。"""
    settings = Settings()
    uvicorn.run(
        "mcmod.api:create_app",
        factory=True,
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
    )


@app.command()
def health(ctx: typer.Context) -> None:
    """检查 API、数据库和缓存状态。"""
    try:
        payload = _state(ctx).client.get("/health")
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    table = Table(title="mcmod API health", box=box.SIMPLE)
    table.add_column("field")
    table.add_column("value")
    for key, value in payload.items():
        if key == "cache" and isinstance(value, dict):
            for cache_key, cache_value in value.items():
                table.add_row(f"cache.{cache_key}", str(cache_value))
        else:
            table.add_row(str(key), str(value))
    console.print(table)


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="搜索关键词"),
    filter: str = typer.Option("all", "--filter", help="all|mods|modpacks|items|tutorials|authors|users|community"),
    mold: str = typer.Option("simple", "--mold", help="simple|full"),
    page: int = typer.Option(1, min=1),
    refresh: bool = typer.Option(False, help="绕过缓存重新抓取"),
) -> None:
    """搜索模组、整合包、资料、教程等。"""
    try:
        payload = _state(ctx).client.get(
            "/api/v1/search",
            params={"q": query, "filter": filter, "mold": mold, "page": page},
            refresh=refresh,
        )
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    table = Table(title=f"搜索：{data['query']}", caption=_page_caption(payload), box=box.SIMPLE)
    table.add_column("类型", width=8)
    table.add_column("标题", min_width=28)
    table.add_column("摘要", min_width=40)
    table.add_column("URL", min_width=30)
    for hit in data["results"]:
        table.add_row(
            hit["type"],
            _short(hit["title"], 60),
            _short(hit.get("snippet"), 80),
            hit["url"],
        )
    console.print(table)
    console.print(f"[dim]分类计数：{data.get('counts', {})}[/dim]")


@app.command()
def mods(
    ctx: typer.Context,
    category: int = typer.Option(None, help="模组元素 ID（见 mcmod filters mod）"),
    mcver: str = typer.Option(None, help="MC 版本，如 1.20.1"),
    platform: str = typer.Option(None, help="java|bedrock|1|2"),
    loader: str = typer.Option(None, help="forge|fabric|neoforge|quilt 或数字 ID"),
    status: str = typer.Option(None, help="active|half|stopped 或数字 ID"),
    mode: str = typer.Option(None, help="client|server|client_primary|server_primary|both_required|both_optional"),
    keyword: str = typer.Option(None, help="关键词"),
    sort: str = typer.Option("default", help="default|created|edited"),
    page: int = typer.Option(1, min=1),
    refresh: bool = typer.Option(False),
) -> None:
    """按条件列出模组。"""
    try:
        payload = _state(ctx).client.get(
            "/api/v1/mods",
            params={
                "category": category,
                "mcver": mcver,
                "platform": platform,
                "loader": loader,
                "status": status,
                "mode": mode,
                "keyword": keyword,
                "sort": sort,
                "page": page,
            },
            refresh=refresh,
        )
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    table = Table(caption=_page_caption(payload), box=box.SIMPLE)
    table.add_column("ID", justify="right", width=7)
    table.add_column("名称", min_width=20)
    table.add_column("英文名", min_width=20)
    table.add_column("简介", min_width=40)
    for item in payload["data"]["items"]:
        name = f"{item.get('short_name') or ''}{item['name']}"
        table.add_row(str(item["id"]), name, item.get("name_en") or "", _short(item.get("description"), 80))
    console.print(table)


@app.command()
def mod(
    ctx: typer.Context,
    mod_id: str = typer.Argument(..., help="模组 ID 或 URL"),
    refresh: bool = typer.Option(False),
) -> None:
    """查看模组详情。"""
    mod_id = _numeric_id(mod_id, "mod")
    try:
        payload = _state(ctx).client.get(f"/api/v1/mods/{mod_id}", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    console.print(
        Panel(
            f"[bold]{data['short_name'] or ''}{data['name']}[/bold]  {data.get('name_en') or ''}\n"
            f"{data['url']}\n{_meta_caption(payload)}",
            title=f"mod {data['id']}",
        )
    )
    table = Table(box=box.SIMPLE)
    table.add_column("field")
    table.add_column("value")
    fields = {
        "状态": ", ".join(s["label"] for s in data.get("statuses", [])),
        "分类": ", ".join(c["name"] for c in data.get("categories", [])),
        "平台": ", ".join(c["name"] for c in data.get("platforms", [])),
        "加载器": ", ".join(c["name"] for c in data.get("loaders", [])),
        "运行环境": ", ".join(data.get("environment", [])),
        "评分": f"{data['stats'].get('score')} / {data['stats'].get('rank') or ''}",
        "总浏览": f"{data['stats'].get('total_views_text') or ''} ({data['stats'].get('total_views') or '?'})",
        "收录/编辑": f"{data.get('created') or '?'} / {data.get('last_edit') or '?'}",
        "标签": ", ".join(data.get("tags", [])),
        "资料": f"{data.get('item_count') or 0} 条",
        "教程/讨论/特性": f"{data.get('tutorials_total') or 0} / {data.get('discussions_total') or 0} / {data.get('features_total') or 0}",
        "整合包引用": str(data.get("modpack_usage") or 0),
        "下载文件": str(data.get("download_files_count") or 0),
    }
    for key, value in fields.items():
        table.add_row(key, str(value))
    console.print(table)
    if data.get("versions"):
        console.print("[bold]支持版本[/bold]")
        for group in data["versions"]:
            versions = ", ".join(v["version"] for v in group["versions"])
            console.print(f"  {group['platform']} ({group.get('total') or '?'}): {_short(versions, 300)}")
    if data.get("links"):
        console.print("[bold]相关链接[/bold]")
        for link in data["links"]:
            console.print(f"  {link['name']}: {link['url']}")
    if data.get("item_types"):
        console.print("[bold]资料类型[/bold]")
        for item_type in data["item_types"]:
            console.print(f"  [{item_type['id']}] {item_type['name']} ({item_type.get('count') or 0})")
    if data.get("intro_text"):
        console.print(Panel(_short(data["intro_text"], 1500), title="简介"))


@app.command("mod-items")
def mod_items(
    ctx: typer.Context,
    mod_id: str = typer.Argument(..., help="模组 ID 或 URL"),
    type_id: int = typer.Option(1, help="资料类型 ID（默认 1=物品/方块）"),
    query: str = typer.Option(None, "--query", "-q", help="名称过滤"),
    refresh: bool = typer.Option(False),
) -> None:
    """列出模组的资料/物品。"""
    mod_id = _numeric_id(mod_id, "mod")
    try:
        payload = _state(ctx).client.get(
            f"/api/v1/mods/{mod_id}/items",
            params={"type_id": type_id, "q": query},
            refresh=refresh,
        )
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    table = Table(
        title=(
            f"{data['mod_name']} · {data.get('type_name') or data['type_id']} "
            f"({data['total']}/{data.get('declared_total') or data['total']})"
        ),
        caption=_meta_caption(payload),
        box=box.SIMPLE,
    )
    table.add_column("分类", width=12)
    table.add_column("ID", width=8)
    table.add_column("中文名", min_width=20)
    table.add_column("英文名", min_width=20)
    for category in data["categories"]:
        for item in category["items"]:
            table.add_row(category["name"], str(item.get("id") or ""), item["name"], item.get("name_en") or "")
    console.print(table)


@app.command("mod-downloads")
def mod_downloads(
    ctx: typer.Context,
    mod_id: str = typer.Argument(..., help="模组 ID 或 URL"),
    refresh: bool = typer.Option(False),
    limit: int = typer.Option(30, min=1, help="最多显示行数"),
) -> None:
    """查看模组下载文件元数据。"""
    mod_id = _numeric_id(mod_id, "mod")
    try:
        payload = _state(ctx).client.get(f"/api/v1/mods/{mod_id}/downloads", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    table = Table(title=f"{data['mod_name']} 下载文件 ({data['total']})", caption=_meta_caption(payload), box=box.SIMPLE)
    table.add_column("文件名", min_width=30)
    table.add_column("平台", width=8)
    table.add_column("加载器", width=10)
    table.add_column("MC 版本", width=10)
    table.add_column("大小", width=8)
    table.add_column("下载量", justify="right")
    table.add_column("上传时间")
    for file in data["files"][:limit]:
        table.add_row(
            file["filename"],
            file.get("platform") or "",
            file.get("loader") or "",
            file.get("version") or "",
            file.get("size") or "",
            str(file.get("downloads") or ""),
            file.get("uploaded") or "",
        )
    console.print(table)


@app.command()
def item(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="物品 ID 或 URL"),
    refresh: bool = typer.Option(False),
) -> None:
    """查看物品/资料详情。"""
    item_id = _numeric_id(item_id, "item")
    try:
        payload = _state(ctx).client.get(f"/api/v1/items/{item_id}", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    console.print(Panel(f"[bold]{data['name']}[/bold]  {data.get('name_en') or ''}\n{data['url']}\n{_meta_caption(payload)}", title=f"item {data['id']}"))
    table = Table(box=box.SIMPLE)
    table.add_column("field")
    table.add_column("value")
    table.add_row("所属模组", f"{data.get('mod_name') or ''} ({data.get('mod_id') or '?'})")
    table.add_row("资料类型", data.get("item_type") or "")
    table.add_row("物品命令", data.get("command") or "")
    table.add_row("矿物词典", ", ".join(o["name"] for o in data.get("ore_dict", [])))
    for key, value in data.get("properties", {}).items():
        table.add_row(key, value)
    console.print(table)
    if data.get("description_text"):
        console.print(Panel(_short(data["description_text"], 2000), title="正文"))
    if data.get("related_items"):
        console.print("[bold]相关物品[/bold]")
        for related in data["related_items"]:
            console.print(f"  {related['id']} {related['name']}")


@app.command("item-recipes")
def item_recipes(
    ctx: typer.Context,
    item_id: str = typer.Argument(..., help="物品 ID 或 URL"),
    refresh: bool = typer.Option(False),
    limit: int = typer.Option(20, min=1, help="每类最多显示行数"),
) -> None:
    """查看物品合成表与用途。"""
    item_id = _numeric_id(item_id, "item")
    try:
        payload = _state(ctx).client.get(f"/api/v1/items/{item_id}/recipes", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    console.print(Panel(f"{data['item_name']}\n{_meta_caption(payload)}", title="recipes"))

    def render(rows: list[dict[str, Any]], title: str) -> None:
        table = Table(title=f"{title} ({len(rows)})", box=box.SIMPLE)
        table.add_column("工作台", width=14)
        table.add_column("材料", min_width=30)
        table.add_column("产出", min_width=20)
        table.add_column("备注", min_width=20)
        for row in rows[:limit]:
            ingredients = " + ".join(
                f"{item['name']}×{item.get('count') or 1}" for item in row.get("ingredients", [])
            )
            outputs = " + ".join(
                f"{item['name']}×{item.get('count') or 1}" for item in row.get("outputs", [])
            )
            station = (row.get("station") or {}).get("name") or ""
            table.add_row(station, _short(ingredients, 120), _short(outputs, 80), _short(row.get("note"), 80))
        console.print(table)

    render(data.get("recipes", []), "物品合成")
    render(data.get("usages", []), "物品用途")


@app.command()
def modpacks(
    ctx: typer.Context,
    category: int = typer.Option(None),
    mcver: str = typer.Option(None),
    mold: str = typer.Option(None, help="native|modded|1|2"),
    loader: str = typer.Option(None),
    pack: str = typer.Option(None, help="打包方式 ID"),
    sort: str = typer.Option("default", help="default|created|edited"),
    page: int = typer.Option(1, min=1),
    refresh: bool = typer.Option(False),
) -> None:
    """按条件列出整合包。"""
    try:
        payload = _state(ctx).client.get(
            "/api/v1/modpacks",
            params={
                "category": category,
                "mcver": mcver,
                "mold": mold,
                "loader": loader,
                "pack": pack,
                "sort": sort,
                "page": page,
            },
            refresh=refresh,
        )
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    table = Table(caption=_page_caption(payload), box=box.SIMPLE)
    table.add_column("ID", width=7, justify="right")
    table.add_column("名称", min_width=20)
    table.add_column("英文名", min_width=20)
    table.add_column("简介", min_width=40)
    for item in payload["data"]["items"]:
        table.add_row(
            str(item["id"]),
            f"{item.get('short_name') or ''}{item['name']}",
            item.get("name_en") or "",
            _short(item.get("description"), 80),
        )
    console.print(table)


@app.command()
def modpack(
    ctx: typer.Context,
    pack_id: str = typer.Argument(..., help="整合包 ID 或 URL"),
    refresh: bool = typer.Option(False),
) -> None:
    """查看整合包详情。"""
    pack_id = _numeric_id(pack_id, "modpack")
    try:
        payload = _state(ctx).client.get(f"/api/v1/modpacks/{pack_id}", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    console.print(Panel(f"[bold]{data['short_name'] or ''}{data['name']}[/bold]  {data.get('name_en') or ''}\n{data['url']}\n{_meta_caption(payload)}", title=f"modpack {data['id']}"))
    table = Table(box=box.SIMPLE)
    table.add_column("field")
    table.add_column("value")
    table.add_row("分类", ", ".join(c["name"] for c in data.get("categories", [])))
    table.add_row("类型/运作/打包", f"{data.get('pack_type') or ''} / {data.get('loader') or ''} / {data.get('packaging') or ''}")
    table.add_row("标签", ", ".join(data.get("tags", [])))
    table.add_row("评分", f"{data['stats'].get('score')} / {data['stats'].get('rank') or ''}")
    table.add_row("包含模组", str(data.get("mods_total") or 0))
    table.add_row("版本", _short(", ".join(v["version"] for group in data.get("versions", []) for v in group["versions"]), 200))
    console.print(table)
    if data.get("mods"):
        console.print("[bold]包含模组（按分类）[/bold]")
        for group in data["mods"]:
            console.print(
                f"  {group.get('category_name') or group.get('category_id')}: "
                f"{len(group['mods'])} 个"
            )
    if data.get("intro_text"):
        console.print(Panel(_short(data["intro_text"], 2000), title="介绍"))


@app.command("modpack-versions")
def modpack_versions(
    ctx: typer.Context,
    pack_id: str = typer.Argument(..., help="整合包 ID 或 URL"),
    refresh: bool = typer.Option(False),
    limit: int = typer.Option(10, min=1),
) -> None:
    """查看整合包更新日志。"""
    pack_id = _numeric_id(pack_id, "modpack")
    try:
        payload = _state(ctx).client.get(f"/api/v1/modpacks/{pack_id}/versions", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    console.print(Panel(f"{data['modpack_name']}\n{_meta_caption(payload)}", title="更新日志"))
    for entry in data["entries"][:limit]:
        console.print(f"[bold]{entry['name']}[/bold]  {entry.get('date') or ''}")
        if entry.get("content_text"):
            console.print(_short(entry["content_text"], 500))


@app.command()
def post(
    ctx: typer.Context,
    post_id: str = typer.Argument(..., help="教程/讨论 ID 或 URL"),
    refresh: bool = typer.Option(False),
    full: bool = typer.Option(False, help="输出完整正文（默认截断）"),
) -> None:
    """查看教程/讨论文章。"""
    post_id = _numeric_id(post_id, "post")
    try:
        payload = _state(ctx).client.get(f"/api/v1/posts/{post_id}", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    author = (data.get("author") or {}).get("name") or ""
    console.print(Panel(f"[bold]{data['title']}[/bold]\n{author}  {data.get('created') or ''}  浏览 {data.get('views') or 0}\n{data['url']}\n{_meta_caption(payload)}", title=f"post {data['id']}"))
    if data.get("license"):
        console.print(f"[dim]协议：{data['license']}[/dim]")
    text = data.get("content_text") or ""
    console.print(text if full else _short(text, 4000))


@app.command()
def author(
    ctx: typer.Context,
    author_id: str = typer.Argument(..., help="作者 ID 或 URL"),
    refresh: bool = typer.Option(False),
) -> None:
    """查看作者/开发团队资料。"""
    author_id = _numeric_id(author_id, "author")
    try:
        payload = _state(ctx).client.get(f"/api/v1/authors/{author_id}", refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    console.print(Panel(f"[bold]{data['name']}[/bold]\n{data['url']}\n{_meta_caption(payload)}", title=f"author {data['id']}"))
    console.print(f"浏览 {data.get('views') or 0}  创建 {data.get('created') or ''}  编辑 {data.get('edit_count') or 0}")
    if data.get("bio_text"):
        console.print(Panel(_short(data["bio_text"], 800), title="简介"))
    if data.get("members"):
        console.print("[bold]团队成员[/bold]")
        for member in data["members"]:
            console.print(f"  {member['name']}  {member.get('role') or ''}")
    if data.get("projects"):
        console.print("[bold]参与项目[/bold]")
        for project in data["projects"]:
            console.print(f"  {project.get('mod') or ''} {project['name']}  {project.get('note') or ''}")


@app.command()
def filters(
    ctx: typer.Context,
    kind: str = typer.Argument("mod", help="mod|modpack"),
    refresh: bool = typer.Option(False),
) -> None:
    """查看可用的筛选条件。"""
    try:
        payload = _state(ctx).client.get("/api/v1/meta/filters", params={"kind": kind}, refresh=refresh)
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    data = payload["data"]
    for group in data["groups"]:
        options = " | ".join(f"{o['value'] or '∅'}={o['label']}" for o in group["options"])
        console.print(f"[bold]{group['label']}[/bold] ({group['id']})\n  {_short(options, 1200)}")
    console.print(f"[dim]{_meta_caption(payload)}[/dim]")


@cache_app.command("stats")
def cache_stats(ctx: typer.Context) -> None:
    """查看缓存统计。"""
    try:
        payload = _state(ctx).client.get("/api/v1/cache/stats")
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    table = Table(title="cache", box=box.SIMPLE)
    table.add_column("field")
    table.add_column("value")
    for key, value in payload.items():
        table.add_row(key, str(value))
    console.print(table)


@cache_app.command("purge")
def cache_purge(ctx: typer.Context) -> None:
    """删除已过期的缓存条目。"""
    try:
        payload = _state(ctx).client.post("/api/v1/cache/purge")
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    console.print(f"deleted {payload.get('deleted', 0)} expired entries")


@cache_app.command("clear")
def cache_clear(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """清空所有 API 结果缓存。"""
    if not yes and not typer.confirm("确定清空全部缓存？"):
        raise typer.Exit(1)
    try:
        payload = _state(ctx).client.delete("/api/v1/cache")
    except ApiClientError as exc:
        _fail(exc)
    if _state(ctx).json_output:
        _print_json(payload)
        return
    console.print(f"deleted {payload.get('deleted', 0)} entries")


def _numeric_id(value: str, kind: str) -> int:
    from .parsers.common import extract_id

    parsed = extract_id(value, kind)
    if parsed is None:
        console.print(f"[red]无效的 {kind} ID：{value}[/red]")
        raise typer.Exit(2)
    return parsed


def main() -> None:
    try:
        app()
    except BrokenPipeError:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
