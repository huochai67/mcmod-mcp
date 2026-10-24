---
name: mcmod
description: 查询 MC百科（mcmod.cn）的 Minecraft 模组、整合包、物品、合成表、教程与作者。Use when the user asks about Minecraft mods/modpacks, mod compatibility, MC versions, crafting recipes, item usages, modpack changelogs, or mcmod.cn IDs/links; requires the mcmod MCP server.
license: MIT
compatibility: Requires the mcmod MCP server (mcmod-mcp) and its REST API (default http://127.0.0.1:8000). Read-only; no direct web scraping.
metadata:
  mcp-server: mcmod
  version: "1.0.0"
  api-default: "http://127.0.0.1:8000"
  data-license: "CC BY-NC-SA 3.0"
---

# MC百科数据检索

通过 `mcmod` MCP server 读取 MC百科的 SSR 页面解析结果。所有数据都是只读的；回答必须基于工具返回的 JSON，不得凭记忆补全模组、版本、配方或 ID。

## 何时使用

使用本技能：

- 查询 Minecraft 模组、整合包、物品/方块、合成表、用途、教程、作者或开发团队。
- 判断某个模组/整合包支持哪些 MC 版本、加载器、运行环境。
- 根据名称、关键词、分类、MC 版本筛选模组或整合包。
- 读取 mcmod.cn 的模组/物品/整合包/教程 URL 或数字 ID 对应的详情。
- 需要 mcmod.cn 的来源链接、抓取时间或缓存状态。

不用于：

- 下载模组 jar、整合包文件或附件。
- 账号登录、发帖、编辑资料、服务器状态等写操作。
- 与 MC百科无关的通用 Minecraft 问题；除非问题需要查询 MC百科数据。

## 前置检查

1. 在当前会话的 MCP 工具中查找 `mcmod` server。工具名通常为 `mcmod_*`，部分客户端会显示为 `mcp__mcmod__mcmod_*`；如果服务器配置名不同，前缀会变化，以实际工具列表为准。
2. 只调用实际存在的工具。不要编造工具名、参数或返回结果。
3. 如果没有任何 `mcmod_*` 工具：
   - 不要改用浏览器、`curl` 或自写爬虫直接抓取 mcmod.cn。
   - 告诉用户先启动 REST API（`mcmod serve`），再在 MCP 客户端配置 `mcmod-mcp`，并确认 `MCMOD_API_BASE` 指向该 API。
   - 如果工具存在但报连接错误，按下方“错误处理”处理。

## 工作流程

1. **判断实体类型**：模组（mod）、物品/方块（item）、整合包（modpack）、教程/讨论（post）、作者（author）。
2. **名称不明确时先搜索**，不要猜数字 ID：
   - 模组：`mcmod_search(query="名称", filter="mods")`
   - 物品：`mcmod_search(query="名称", filter="items")`
   - 整合包：`mcmod_search(query="名称", filter="modpacks")`
   - 教程：`mcmod_search(query="关键词", filter="tutorials")`
   - 作者：`mcmod_search(query="名称", filter="authors")`
3. **用搜索结果中的 ID 或 URL** 调用详情工具。始终使用命名参数（如 `mcmod_get_mod(mod=2)`），不要依赖位置参数；不要把物品 URL 传给模组工具，反之亦然。
4. **只取所需数据**：能用一个详情工具回答，就不要枚举整个列表。
5. **解析 JSON 后再回答**：工具返回的是 JSON 字符串，提取 `data` 和 `meta`；不要把完整原始 JSON（尤其是 HTML 字段）直接倾倒给用户。
6. **给出来源**：使用实体自带的 `url` 或 `meta.source`；需要说明新鲜度时再引用 `meta.fetched_at`。

## 工具选择

| 用户意图 | 工具 | 关键参数 |
|---|---|---|
| 全站搜索 | `mcmod_search` | `query`、`filter`、`mold`、`page` |
| 按条件列模组 | `mcmod_list_mods` | `category`、`mc_version`、`platform`、`loader`、`status`、`mode`、`keyword`、`sort`、`page` |
| 模组详情 | `mcmod_get_mod` | `mod`（ID/URL） |
| 模组资料/物品列表 | `mcmod_get_mod_items` | `mod`、`type_id`、`keyword` |
| 模组下载文件元数据 | `mcmod_get_mod_downloads` | `mod` |
| 物品详情 | `mcmod_get_item` | `item`（ID/URL） |
| 合成表与用途 | `mcmod_get_item_recipes` | `item`（ID/URL） |
| 按条件列整合包 | `mcmod_list_modpacks` | `category`、`mc_version`、`pack_type`、`loader`、`packaging`、`sort`、`page` |
| 整合包详情 | `mcmod_get_modpack` | `pack`（ID/URL） |
| 整合包更新日志 | `mcmod_get_modpack_versions` | `pack`（ID/URL） |
| 教程/讨论文章 | `mcmod_get_post` | `post`（ID/URL） |
| 作者/团队 | `mcmod_get_author` | `author`（ID/URL） |
| 筛选项元数据 | `mcmod_get_filters` | `kind="mod"` 或 `"modpack"` |
| 缓存统计 | `mcmod_cache_stats` | 无 |

## 参数速查

- `mcmod_search` 的 `filter`：`all`、`mods`、`modpacks`、`items`、`tutorials`、`authors`、`users`、`community`。
- `mold`（仅搜索）：`simple` 或 `full`；先用 `simple`，需要更多摘要再用 `full`。
- `sort`：`default`、`created`、`edited`。
- 模组列表的 `loader`/`status`/`mode` 可传名称（如 `forge`、`neoforge`、`active`、`stopped`、`client_primary`）或数字 ID。
- 整合包列表的 `pack_type` 用 `native`/`modded`；`loader` 用 `forge`/`fabric`/`quilt`/`neoforge` 等名称；`packaging` 用 `curseforge`/`ftb`/`modrinth`/`manual` 等名称。
- 不确定数字筛选值时，先调用 `mcmod_get_filters`；不要猜分类或加载器 ID。
- `mcmod_get_mod_items` 的 `type_id` 来自模组详情的 `data.item_types[].id`；默认 `1` 只是“物品/方块”，不要假设所有模组都用 1。
- `refresh=true` 只会在用户明确要求最新数据，或用户指出数据已过期时使用；不要连续刷新或对每个请求都刷新。
- `page` 仅在 `data.page_info.total_pages > 1` 且用户需要更多结果时递增；先总结当前页并说明总数。
- 实体参数（`mod`/`item`/`pack`/`post`/`author`）可接受数字 ID 或对应的 mcmod.cn URL；优先使用搜索结果返回的数字 ID。

## 返回结构与常用字段

大多数工具返回：

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

- `meta.cache`：`hit`、`miss`、`bypass`、`disabled`。只有用户关心数据新鲜度时才需要说明。
- `meta.source`：上游页面 URL，引用时使用它。
- `meta.fetched_at`：抓取时间（UTC）。
- 部分工具（如 `mcmod_cache_stats`）直接返回统计对象，没有 `data`/`meta` 包装。

常用 `data` 字段：

| 实体 | 关键字段 |
|---|---|
| 模组详情 | `name`、`short_name`、`name_en`、`statuses`、`loaders`、`platforms`、`environment`、`versions`、`item_types`、`relations`、`tutorials`、`stats`、`links`、`download_files_count` |
| 模组物品列表 | `categories[].items`、`total`、`declared_total`、`type_id`、`type_name` |
| 物品详情 | `name`、`name_en`、`mod_id`、`mod_name`、`item_type`、`command`、`ore_dict`、`properties`、`description_text`、`related_items` |
| 合成表 | `recipes`（如何合成该物品）、`usages`（该物品用于合成什么）；每行有 `station`、`ingredients`、`outputs`、`note`、`version_added`、`version_removed` |
| 整合包详情 | `name`、`pack_type`、`loader`、`packaging`、`versions`、`mods`（按分类）、`mods_total`、`team`、`stats` |
| 更新日志 | `entries[].name`、`date`、`content_text`、`content_html` |
| 教程/讨论 | `title`、`author`、`permission`、`license`、`content_text`、`related_mods`、`related_items`、`views` |
| 作者/团队 | `name`、`bio_text`、`members`、`partners`、`projects` |
| 列表/搜索 | `items` 或 `results`、`page_info`（`page`、`total_pages`、`total`、`per_page`） |

## 回答规范

1. **默认使用用户的语言**；用户用中文提问就用中文回答，但保留官方中文名、英文名、加载器名和版本号的原文。
2. **先给结论，再给证据**：先回答“支持/不支持/有/没有”，再列版本、配方、来源。
3. **引用来源**：每个实体回答附上 `url` 或 `meta.source`；不要把来源写成凭空的“官网”。
4. **区分版本**：明确区分 MC 版本（如 `1.20.1`）与模组版本（如 `2.8.1`）；不要把两者混写。
5. **兼容性措辞**：只陈述页面 `versions`/`loaders` 中列出的内容。使用“页面列出的支持版本包括……”；不要推断未列出的版本一定兼容。
6. **合成表**：说明工作站、材料、产出、备注和版本限制；有多条配方时保留“替代配方”的区别，不要只挑一条当唯一答案。
7. **列表**：默认展示最有用的 5–10 条，并给出总数；用户要求更多时再翻页。表格列建议：名称、ID、MC 版本/加载器、简短说明、链接。
8. **长文本**：优先使用 `*_text` 字段；不要直接输出 `content_html`、`intro_html` 或 `description_html`，除非用户明确要求 HTML。
9. **教程/文章**：保留作者和协议信息；只做摘要或短引用，并链接原文。
10. **数量不一致**：物品列表可能同时有 `total` 与 `declared_total`。例如“页面列出 502 条，站点标注 615 条”，不要自行断言缺失原因或声称抓取失败。
11. **下载**：只能提供文件名、加载器、版本、大小、哈希、下载量等元数据；实际 jar/整合包下载需要站点验证码，不能承诺下载。
12. **不要输出原始 JSON**，除非用户明确要求 JSON；即使用户要 JSON，也不要在 JSON 之外重复同一份数据。

## 错误处理

| 现象 | 处理 |
|---|---|
| `connection_error` / 连接被拒绝 | API 未启动或 `MCMOD_API_BASE` 错误。告诉用户运行 `mcmod serve` 并检查 MCP 的 `MCMOD_API_BASE`；不要改为直接抓网页。 |
| `not_found` / 404 | ID 或实体类型不对。用名称重新 `mcmod_search`，不要重复请求同一 ID。 |
| `invalid_request` / 422 | 参数值不合法。调用 `mcmod_get_filters` 获取合法值，或检查 `sort`/`filter`/`loader` 是否拼写正确。 |
| `parse_error` | 上游页面结构变化或页面为空。说明“页面解析失败/暂不可用”，不要伪造数据；可建议用户稍后重试或更新解析器。 |
| `upstream_error` / 429 / 5xx | 上游限流或故障。不要循环重试；告知用户稍后再试。 |
| `timeout` | 最多重试一次；仍失败则说明 API 或上游超时。 |
| `cache_unavailable` | 缓存后端不可用，读取可能降级。不要擅自清空缓存；告知用户检查数据库。 |
| `data` 为空列表 | 这是合法的“无结果”。建议换关键词、放宽筛选或确认拼写，不要说“系统错误”。 |

## 示例

### 1. 查兼容版本

用户：“工业时代2 支持 Forge 1.12.2 吗？”

```text
mcmod_search(query="工业时代2", filter="mods")
mcmod_get_mod(mod=2)
```

回答要点：在 `data.versions` 中找到 `platform="Forge"` 的分组，检查版本列表是否包含 `1.12.2`；说明这是页面列出的版本，并附模组 URL。

### 2. 查合成表

用户：“火力发电机怎么做？”

```text
mcmod_search(query="火力发电机", filter="items")
mcmod_get_item_recipes(item=233)
```

回答要点：分别总结 `recipes` 与 `usages`；列出工作台、材料、产出、备注；如果有 5 条合成方式，说明“共 5 条，以下为……”，不要只给第一条。

### 3. 查整合包更新

用户：“破劫之刃最近更新了什么？”

```text
mcmod_get_modpack_versions(pack=1026)
```

回答要点：按 `entries` 的时间倒序（通常已是倒序）总结最近 3–5 条，保留版本号和日期，附来源。

### 4. 按条件找模组

用户：“找一些 1.21.1 的 NeoForge 科技模组。”

```text
mcmod_get_filters(kind="mod")
mcmod_list_mods(loader="neoforge", mc_version="1.21.1", category=1, sort="edited")
```

回答要点：先用 filters 确认“科技”的 ID；展示前 5–10 个，给出总数和分页信息；不要因为第一页没有某个模组就断言不存在。

### 5. 查作者项目

用户：“IC2 Dev Team 还参与过什么？”

```text
mcmod_get_author(author=21425)
```

回答要点：总结 `projects`、`members`、`partners`；区分“开发团队”和“成员个人”。

## 禁止事项

- 不要猜测或编造模组 ID、物品 ID、配方、版本兼容性、下载链接。
- 不要在 MCP 工具可用时用浏览器/爬虫直接抓 mcmod.cn。
- 不要下载或尝试下载 jar/整合包文件，也不要绕过验证码。
- 不要调用缓存清理/删除接口，除非用户明确要求且已配置管理员令牌。
- 不要对同一失败请求连续重试，不要批量枚举全站。
- 不要泄露 `MCMOD_ADMIN_TOKEN` 或任何本地凭据。
- 不要忽略数据版权：引用时保留 mcmod.cn 链接；数据遵循 CC BY-NC-SA 3.0。
