# mcmod-mcp

非官方 **REST API + MCP Server + CLI**，用于读取 [MC百科 (mcmod.cn)](https://www.mcmod.cn/) 的公开页面数据。

网站是服务端渲染（SSR），没有公开 API。本项目抓取并解析 HTML，将结果规范化为 JSON，缓存到 SQLite 或 MariaDB，再通过 REST、MCP 或命令行提供给调用方。

> **非官方项目。** 与 mcmod.cn 无隶属关系。页面数据版权归 MC百科及原作者所有（CC BY-NC-SA 3.0），请保留来源链接并遵守网站的 robots.txt 与使用条款。默认请求间隔 1 秒，请勿批量抓取。

## 功能

- 搜索模组、整合包、资料、教程、作者、用户与社群。
- 模组列表、模组详情、支持版本、作者、依赖关系、教程索引。
- 模组资料/物品列表、下载文件元数据（不下载文件）。
- 物品详情、合成表与用途、矿物词典、属性。
- 整合包列表、详情、包含模组、更新日志。
- 教程/讨论文章与作者/开发团队资料。
- 筛选条件元数据（分类、MC 版本、加载器、状态、排序等）。
- SQLite（默认）或 MariaDB 持久缓存，按资源类型配置 TTL。
- CLI 的表格/JSON 双输出；MCP 的 14 个只读工具。
- 全局请求限速、429/5xx 重试、OpenAPI 文档。

## 架构

```text
mcmod.cn / search.mcmod.cn
          │  HTTPS（限速 + 重试）
          ▼
    mcmod-api（FastAPI）
       ├── parsers/       HTML → Pydantic 模型
       ├── service/       抓取、解析、缓存编排
       └── SQLite/MariaDB api_cache 表
          ▲
          │ JSON（X-Cache: hit/miss/bypass）
          ├──────── CLI（mcmod）
          └──────── MCP Server（mcmod-mcp）── Claude / Cursor / 其他 MCP 客户端
```

API 服务是唯一抓取网站的进程；CLI 与 MCP Server 只访问 REST API。这样缓存、限速和解析逻辑只有一份。

## 快速开始

要求 Python 3.11+。推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync
cp .env.example .env          # 可选，按需修改
uv run mcmod serve            # 默认 http://127.0.0.1:8000
```

或安装为可编辑包：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
mcmod serve
```

验证：

```bash
curl http://127.0.0.1:8000/health
curl 'http://127.0.0.1:8000/api/v1/search?q=工业化&filter=mods'
curl http://127.0.0.1:8000/api/v1/mods/2
```

- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>
- 首次访问某个资源会抓取网站（`X-Cache: miss`），后续命中缓存（`X-Cache: hit`）。

## Docker

镜像包含 REST API、CLI 和 MCP Server 三个入口，默认启动 API，使用非 root 用户，SQLite 数据保存在 `/data` 卷中。

```bash
docker build -t mcmod-mcp:0.1 .

docker run -d --name mcmod-api \
  -p 127.0.0.1:8000:8000 \
  -v mcmod-data:/data \
  mcmod-mcp:0.1

curl http://127.0.0.1:8000/health
docker logs -f mcmod-api
docker inspect --format '{{.State.Health.Status}}' mcmod-api
```

- `/data` 是持久化卷，SQLite 数据库默认为 `/data/mcmod.db`；删除容器不会丢缓存。
- 使用 bind mount 时确保宿主目录对容器 UID `10001` 可写（例如 `mkdir -p ./data && sudo chown 10001:10001 ./data`），或直接使用上面的命名卷。
- 修改端口时同时设置环境变量和端口映射：`-e MCMOD_API_PORT=9000 -p 9000:9000`。
- 使用 MariaDB 时覆盖数据库 URL：

```bash
docker run -d --name mcmod-api \
  -p 127.0.0.1:8000:8000 \
  -e MCMOD_DATABASE_URL='mariadb://mcmod:secret@db-host:3306/mcmod?charset=utf8mb4' \
  mcmod-mcp:0.1
```

- 如果 API 暴露到公网，务必设置 `MCMOD_ADMIN_TOKEN`，否则缓存清理接口对调用方开放。
- 国内构建可替换基础镜像或 PyPI 源：

```bash
docker build \
  --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t mcmod-mcp:0.1 .
```

镜像内也可直接运行 CLI（默认入口是 `mcmod-api`，CLI 会访问同一容器内的 API）：

```bash
docker exec mcmod-api mcmod mod 2
```

## GitHub Actions

`.github/workflows/docker.yml` 在以下时机构建镜像：

- push 到 `main`/`master`：推送 `latest`、分支名和 `sha-*` 标签。
- push `v*` 标签：额外推送版本标签（如 `v0.1.0`、`0.1`）。
- Pull Request：只构建验证，不推送。
- 手动触发：`workflow_dispatch`。

镜像推送到 GitHub Container Registry：

```bash
docker pull ghcr.io/huochai67/mcmod-mcp:latest
```

工作流使用 `GITHUB_TOKEN` 和 `packages: write` 权限，无需额外 secret。首次推送后，如需要公开拉取，请在 GitHub 仓库的 Packages 设置中将镜像可见性改为 public。PR 会先运行 `uv sync --frozen`、`pytest` 和 `ruff`，通过后才构建镜像。

## 配置

所有配置使用 `MCMOD_` 前缀，可写入 `.env` 或环境变量。完整示例见 [`.env.example`](.env.example)。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MCMOD_DATABASE_URL` | `sqlite:///./mcmod.db` | SQLAlchemy URL；支持 SQLite / MariaDB / MySQL |
| `MCMOD_DATABASE_ECHO` | `false` | 输出 SQL |
| `MCMOD_SQLITE_TIMEOUT` | `30` | SQLite 忙等待秒数 |
| `MCMOD_CACHE_ENABLED` | `true` | 关闭后所有请求都实时抓取 |
| `MCMOD_CACHE_TTL_SEARCH` | `900` | 搜索缓存 TTL（秒） |
| `MCMOD_CACHE_TTL_LIST` | `1800` | 列表/下载缓存 TTL |
| `MCMOD_CACHE_TTL_DETAIL` | `21600` | 详情/合成表/教程/作者 TTL |
| `MCMOD_CACHE_TTL_META` | `86400` | 筛选项 TTL |
| `MCMOD_MIN_INTERVAL` | `1.0` | 两次上游请求的最小间隔（秒） |
| `MCMOD_MAX_RETRIES` | `2` | 429/5xx/网络错误重试次数 |
| `MCMOD_TIMEOUT` | `20` | 上游 HTTP 超时（秒） |
| `MCMOD_BASE_URL` | `https://www.mcmod.cn` | 主站地址 |
| `MCMOD_SEARCH_URL` | `https://search.mcmod.cn` | 搜索站地址 |
| `MCMOD_USER_AGENT` | `mcmod-mcp/0.1 ...` | 上游 User-Agent |
| `MCMOD_API_HOST` | `127.0.0.1` | REST API 监听地址 |
| `MCMOD_API_PORT` | `8000` | REST API 端口 |
| `MCMOD_API_BASE` | `http://127.0.0.1:8000` | CLI/MCP 访问的 API 地址 |
| `MCMOD_ADMIN_TOKEN` | 空 | 设置后，缓存清理接口要求 `X-Admin-Token` |
| `MCMOD_CORS_ORIGINS` | 空 | 逗号分隔的 CORS 来源 |

### 数据库 URL

```bash
# SQLite（相对路径）
MCMOD_DATABASE_URL=sqlite:///./mcmod.db

# SQLite（绝对路径）
MCMOD_DATABASE_URL=sqlite:////var/lib/mcmod/mcmod.db

# MariaDB（mariadb:// 会自动规范化为 mysql+pymysql://）
MCMOD_DATABASE_URL='mariadb://mcmod:secret@127.0.0.1:3306/mcmod?charset=utf8mb4'

# MySQL 驱动写法
MCMOD_DATABASE_URL='mysql+pymysql://mcmod:secret@127.0.0.1:3306/mcmod?charset=utf8mb4'
```

启动时自动建表（`api_cache`），无需迁移工具。SQLite 默认开启 WAL、`busy_timeout` 与 `synchronous=NORMAL`。

### MariaDB 示例

```bash
docker run -d --name mcmod-mariadb \
  -e MARIADB_ROOT_PASSWORD=root-secret \
  -e MARIADB_DATABASE=mcmod \
  -e MARIADB_USER=mcmod \
  -e MARIADB_PASSWORD=mcmod-secret \
  -p 3306:3306 \
  mariadb:11

export MCMOD_DATABASE_URL='mariadb://mcmod:mcmod-secret@127.0.0.1:3306/mcmod?charset=utf8mb4'
uv run mcmod serve
```

## REST API

### 响应约定

成功响应统一为：

```json
{
  "data": {},
  "meta": {
    "cache": "hit",
    "source": "https://www.mcmod.cn/class/2.html",
    "fetched_at": "2026-10-24T14:46:35Z",
    "ttl": 21480,
    "backend": "sqlite"
  }
}
```

- `meta.cache`：`hit`（缓存命中）、`miss`（抓取后写入）、`bypass`（`refresh=true` 跳过读取）、`disabled`（缓存关闭）。
- `meta.source`：实际抓取的上游 URL。
- `meta.ttl`：剩余有效期（秒）；实时抓取时为配置的 TTL。
- 响应头 `X-Cache` 与 `meta.cache` 一致；`Cache-Control: no-store`。
- 缓存管理接口（`/api/v1/cache/stats` 等）不包 envelope。

错误响应：

```json
{
  "error": {
    "code": "not_found",
    "message": "mcmod page not found: ...",
    "detail": "HTTP 404 from ..."
  }
}
```

| HTTP | code | 含义 |
|---|---|---|
| 400 | `invalid_request` | 非法的筛选项/排序值 |
| 401 | `unauthorized` | 缓存管理令牌错误 |
| 404 | `not_found` | 上游页面不存在 |
| 422 | `invalid_request` | 参数校验失败（FastAPI） |
| 502 | `upstream_error` / `parse_error` | 上游错误或页面结构变化 |
| 503 | `cache_unavailable` | 数据库/缓存不可用 |

所有读取接口都支持 `refresh=true` 跳过缓存读取并重新抓取。

### 端点

| 方法 | 路径 | 说明 | 主要参数 |
|---|---|---|---|
| GET | `/health` | API、数据库、缓存状态 | — |
| GET | `/api/v1/search` | 全站搜索 | `q`（必填）、`filter`、`mold`、`page` |
| GET | `/api/v1/mods` | 模组列表 | `category`、`mcver`、`platform`、`loader`、`status`、`mode`、`keyword`、`sort`、`page` |
| GET | `/api/v1/mods/{mod_id}` | 模组详情 | `refresh` |
| GET | `/api/v1/mods/{mod_id}/items` | 模组资料/物品 | `type_id`、`q`、`refresh` |
| GET | `/api/v1/mods/{mod_id}/downloads` | 下载文件元数据 | `refresh` |
| GET | `/api/v1/items/{item_id}` | 物品详情 | `refresh` |
| GET | `/api/v1/items/{item_id}/recipes` | 合成表与用途 | `refresh` |
| GET | `/api/v1/modpacks` | 整合包列表 | `category`、`mcver`、`mold`、`loader`、`pack`、`sort`、`page` |
| GET | `/api/v1/modpacks/{pack_id}` | 整合包详情 | `refresh` |
| GET | `/api/v1/modpacks/{pack_id}/versions` | 整合包更新日志 | `refresh` |
| GET | `/api/v1/posts/{post_id}` | 教程/讨论文章 | `refresh` |
| GET | `/api/v1/authors/{author_id}` | 作者/团队 | `refresh` |
| GET | `/api/v1/meta/filters` | 筛选项 | `kind=mod|modpack` |
| GET | `/api/v1/cache/stats` | 缓存统计 | — |
| POST | `/api/v1/cache/purge` | 删除过期缓存 | `X-Admin-Token`（若配置） |
| DELETE | `/api/v1/cache` | 清空缓存 | `X-Admin-Token`（若配置） |

参数取值：

- `filter`：`all`、`mods`、`modpacks`、`items`、`tutorials`、`authors`、`users`、`community`
- `mold`（搜索）：`simple`、`full`
- `platform`：`java`、`bedrock` 或对应数字 ID
- `loader`：`forge`、`fabric`、`quilt`、`neoforge`、`liteloader`、`datapack`、`rift`、`cleanroom` 等，或数字 ID
- `status`：`active`、`half`、`stopped`，或数字 ID
- `mode`：`client`、`server`、`client_primary`、`server_primary`、`both_required`、`both_optional`
- `sort`：`default`、`created`、`edited`
- 整合包 `mold`：`native`、`modded`；整合包 `pack`：`curseforge`、`ftb`、`other_launcher`、`manual`、`atlauncher`、`modrinth`、`other`，或数字 ID

> 模组列表与整合包列表的 `loader` 数字 ID 空间不同；使用名称更稳妥。完整选项以 `GET /api/v1/meta/filters?kind=mod|modpack` 为准。

### 缓存行为

缓存键为 `sha256(resource + 规范化参数)`，参数顺序、空值与 `refresh` 不影响键。缓存值保存完整响应 `data` 及来源、抓取时间、TTL。

- 同一进程内，相同键的并发未命中由逐键锁合并，避免重复抓取。
- `refresh=true` 跳过读取，但成功抓取后仍会覆盖写入缓存。
- 缓存读写失败时服务降级为实时抓取（健康检查会显示 `degraded`）；缓存统计/清理失败返回 503。
- `POST /api/v1/cache/purge` 只删除已过期条目；`DELETE /api/v1/cache` 删除全部。
- 配置 `MCMOD_ADMIN_TOKEN` 后，两个写接口都要求请求头 `X-Admin-Token`；未配置时允许本机调用。
- 多 worker 部署时逐键锁只在单进程内生效；SQLite 使用 WAL，MariaDB 建议使用独立数据库/连接池。

## CLI

CLI 只是 REST API 的客户端，先启动 `mcmod serve`。

```bash
# 全局选项
mcmod --api http://127.0.0.1:8000 --json search 工业化
mcmod --admin-token "$MCMOD_ADMIN_TOKEN" cache clear --yes

# 搜索与列表
mcmod search 工业化 --filter mods
mcmod mods --loader neoforge --mcver 1.21.1 --sort edited
mcmod modpacks --loader neoforge --pack modrinth
mcmod filters modpack

# 详情（ID 或完整 URL 均可）
mcmod mod 2
mcmod mod https://www.mcmod.cn/class/2.html
mcmod mod-items 2 -q 金粉 --type-id 1
mcmod mod-downloads 2 --limit 10
mcmod item 233
mcmod item-recipes 233 --limit 10
mcmod modpack 1026
mcmod modpack-versions 1026 --limit 5
mcmod post 3339 --full
mcmod author 21425

# 健康与缓存
mcmod health
mcmod cache stats
mcmod cache purge
mcmod cache clear --yes
```

- 默认输出 Rich 表格；`--json` 输出完整 envelope（含 `meta`），适合管道处理。
- 所有请求可加 `--refresh` 绕过缓存。
- 表格模式下 `item-recipes` 每类默认显示 20 行，可用 `--limit` 调整。

## MCP Server

MCP Server 通过 REST API 读取数据，因此需要先启动 API：

```bash
mcmod serve                       # 终端 1
mcmod-mcp                         # 终端 2：stdio 传输
```

### Claude Desktop / Cursor 配置

把可执行文件换成你的实际路径（`uv run` 安装后通常是项目下的 `.venv/bin/mcmod-mcp`）：

```json
{
  "mcpServers": {
    "mcmod": {
      "command": "/absolute/path/to/mcmod-mcp/.venv/bin/mcmod-mcp",
      "args": [],
      "env": {
        "MCMOD_API_BASE": "http://127.0.0.1:8000"
      }
    }
  }
}
```

- Claude Desktop：`claude_desktop_config.json`
- Cursor：项目内 `.cursor/mcp.json` 或全局 MCP 配置
- Claude Code：`claude mcp add mcmod -- /absolute/path/to/mcmod-mcp`

### HTTP 传输

```bash
mcmod-mcp --transport streamable-http --host 127.0.0.1 --port 8001 --path /mcp
# 或旧版 SSE
mcmod-mcp --transport sse --host 127.0.0.1 --port 8001
```

远程部署时把 `MCMOD_API_BASE` 指向可访问的 API；MCP 本身不直接访问 mcmod.cn。

### 工具

所有工具返回 JSON 字符串（API envelope），参数中的 `mod`/`item`/`pack`/`post`/`author` 可传数字 ID 或完整 mcmod.cn URL。所有读取工具均支持 `refresh=true`，可绕过缓存重新抓取。

| 工具 | 作用 |
|---|---|
| `mcmod_search` | 全站搜索 |
| `mcmod_list_mods` | 模组列表/筛选 |
| `mcmod_get_mod` | 模组详情 |
| `mcmod_get_mod_items` | 模组资料/物品 |
| `mcmod_get_mod_downloads` | 下载文件元数据 |
| `mcmod_get_item` | 物品详情 |
| `mcmod_get_item_recipes` | 合成表与用途 |
| `mcmod_list_modpacks` | 整合包列表/筛选 |
| `mcmod_get_modpack` | 整合包详情 |
| `mcmod_get_modpack_versions` | 整合包更新日志 |
| `mcmod_get_post` | 教程/讨论文章 |
| `mcmod_get_author` | 作者/团队 |
| `mcmod_get_filters` | 筛选项 |
| `mcmod_cache_stats` | 缓存统计 |

## Claude Skill

仓库内置一个 Agent Skill：`.claude/skills/mcmod/SKILL.md`。它假定 MCP server 已配置，并指导模型：

- 先 `mcmod_search` 解析名称，再用 ID/URL 获取详情，不猜 ID。
- 正确选择 mod/item/modpack/post/author 工具及 `type_id`、加载器、整合包筛选参数。
- 区分 MC 版本与模组版本，只根据 `versions` 陈述兼容性。
- 总结合成表、更新日志和列表，保留来源链接。
- 遇到 `connection_error`/`not_found`/`parse_error` 时按既定策略处理，不直接抓网页。
- 不下载文件、不清缓存、不批量枚举。

Claude Code 在本仓库启动时会自动加载项目级 skill，也可直接输入 `/mcmod` 调用。个人级安装：

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/.claude/skills/mcmod" ~/.claude/skills/mcmod
```

其他支持 [Agent Skills](https://agentskills.io) 的客户端可复制整个 `.claude/skills/mcmod/` 目录；目录名与 frontmatter 的 `name: mcmod` 必须一致。校验：

```bash
uvx --from skills-ref agentskills validate .claude/skills/mcmod
```

## 开发与测试

```bash
uv sync
uv run pytest            # 离线测试，使用 tests/fixtures 中的真实页面
uv run ruff check src tests
```

测试覆盖解析器、缓存、API、CLI、MCP 与 Skill 工具清单；默认套件不会访问网络，MariaDB 测试会自动跳过。需要验证 MariaDB 时：

```bash
MCMOD_TEST_MARIADB_URL='mariadb://root:secret@127.0.0.1:3307/mcmod' \
  uv run pytest tests/test_mariadb.py -q
```

上游页面改版时，解析器测试会首先失败。

目录：

```text
Dockerfile           服务端镜像定义
.dockerignore        构建上下文排除项
.github/workflows/docker.yml  CI 镜像构建/推送
src/mcmod/
  api.py            FastAPI 路由与错误处理
  service.py        抓取/解析/缓存编排
  cache.py          持久缓存
  http.py           限速与重试
  db.py             SQLAlchemy 引擎与 api_cache 表
  models.py         Pydantic 响应模型
  parsers/          各页面 HTML 解析器
  cli.py            Typer CLI
  mcp_server.py     MCP Server
  client.py         CLI/MCP 使用的 REST 客户端
tests/
  fixtures/         真实页面快照
.claude/
  skills/mcmod/SKILL.md  Claude/Agent Skill
```

## 已知限制

- 项目依赖 SSR HTML 结构；网站改版可能导致 `parse_error`，需要更新对应 parser。
- 下载页只返回文件元数据。实际文件下载需要站点验证码（`POST /action/doDownload`），本项目不实现。
- 页面中的评分、浏览量、下载量等数字可能被网站动态格式化（万/亿），解析器会尽量保留原始文本与换算值。
- 未做账号登录、发帖、编辑等写操作。
- 上游限速是进程级；多实例部署时请自行控制总请求速率。

## 许可证

代码以 MIT 许可证发布。抓取到的数据版权归 MC百科及原作者所有，遵循其 CC BY-NC-SA 3.0 协议；使用本项目时请注明来源并遵守网站条款。
