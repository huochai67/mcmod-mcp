from __future__ import annotations

from mcmod.parsers import (
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
from tests.conftest import read_fixture


def test_parse_mod_list() -> None:
    page = parse_mod_list(read_fixture("modlist.html"))
    assert page.page_info.page == 1
    assert page.page_info.total_pages == 993
    assert page.page_info.total == 31747
    assert len(page.items) == 32
    first = page.items[0]
    assert first.id == 32187
    assert first.name == "森罗物语：沉浸式饮食"
    assert first.name_en == "Kaleidoscope: Immersive Eating"
    assert first.cover and first.cover.startswith("https://i.mcmod.cn/")


def test_parse_mod_detail() -> None:
    mod = parse_mod_detail(read_fixture("mod_2.html"), 2)
    assert mod.name == "工业时代2"
    assert mod.short_name == "[IC2]"
    assert mod.name_en == "Industrial Craft 2"
    assert [status.label for status in mod.statuses] == ["停更", "闭源"]
    assert mod.main_category and mod.main_category.id == 1
    assert {loader.name for loader in mod.loaders} >= {"Forge", "Fabric"}
    assert mod.environment == ["客户端需装", "服务端需装"]
    assert mod.edit_count == 194
    assert mod.tags == ["工业", "老牌模组", "EU"]
    assert any(link.name == "GitHub" and link.url.startswith("https://github.com/") for link in mod.links)
    forge = next(group for group in mod.versions if group.platform == "Forge")
    assert forge.total == 25
    assert any(version.version == "1.12.2" for version in forge.versions)
    assert mod.authors[0].name == "IC2 Dev Team"
    assert mod.stats.score == 5.0
    assert mod.stats.rank == "名扬天下"
    assert mod.stats.total_views and mod.stats.total_views > 24_000_000
    assert len(mod.rating.dimensions) == 8
    assert mod.rating.scores["趣味"] == 1517
    assert mod.item_count == 635
    assert mod.item_types[0].name == "物品/方块"
    assert mod.item_types[0].count == 615
    assert mod.tutorials_total == 105
    assert len(mod.tutorials) == 68
    assert mod.relations and mod.relations[0].mods
    assert mod.download_files_count == 226
    assert mod.download_count == 412835
    assert "简介" in mod.outline


def test_parse_mod_items() -> None:
    page = parse_mod_items(read_fixture("item_list_2_1.html"), 2, 1)
    assert page.mod_name == "[IC2]工业时代2 (Industrial Craft 2)"
    assert page.type_name == "物品/方块"
    assert page.total == 502
    assert page.declared_total == 615
    assert len(page.categories) == 13
    assert page.categories[0].name == "资源"
    assert (page.categories[0].items[0].id, page.categories[0].items[0].name) == (106, "铀锭")
    filtered = parse_mod_items(read_fixture("item_list_2_1.html"), 2, 1, query="金粉")
    assert filtered.total >= 2
    assert all("金粉" in item.name for category in filtered.categories for item in category.items)


def test_parse_downloads() -> None:
    page = parse_downloads(read_fixture("download_2.html"), 2)
    assert page.mod_name == "[IC2]工业时代2 (Industrial Craft 2)"
    assert page.total == 226
    assert len(page.files) == 226
    first = page.files[0]
    assert first.filename.endswith(".jar")
    assert first.version == "1.19.2"
    assert first.loader in {"Forge", "Fabric"}
    assert first.size_bytes and first.size_bytes > 0
    assert first.sha256 and len(first.sha256) == 64
    assert first.downloads and first.downloads > 0


def test_parse_item_detail_and_recipes() -> None:
    item = parse_item_detail(read_fixture("item_233.html"), 233)
    assert (item.name, item.name_en) == ("火力发电机", "Generator")
    assert item.mod_id == 2 and item.mod_name
    assert item.command == "/give @p ic2:te 64 3"
    assert item.properties["最大堆叠"] == "64个 / 组"
    assert item.properties["采集工具"] == "石镐"
    assert item.icon and item.icon.startswith("https://i.mcmod.cn/")
    assert item.related_items
    assert item.created_at == "2012-11-29 18:44:03"

    recipes = parse_recipes(read_fixture("item_tab_233.html"), 233)
    assert recipes.item_name == "火力发电机 (Generator)"
    assert len(recipes.recipes) == 5
    assert len(recipes.usages) == 43
    first = recipes.recipes[0]
    assert first.station and first.station.name == "工作台"
    assert first.station.mod == "我的世界原版"
    assert [(item.name, item.count) for item in first.ingredients] == [
        ("充电电池", 1),
        ("铁板", 3),
        ("铁炉", 1),
    ]
    assert [(item.name, item.count) for item in first.outputs] == [("火力发电机", 1)]
    removed = [row for row in recipes.recipes if row.version_removed]
    assert removed and "2.6.1-ex110" in removed[0].version_removed
    usage = recipes.usages[0]
    assert any(item.oredict == "plateTitanium" for item in usage.ingredients)


def test_parse_modpacks() -> None:
    page = parse_modpack_list(read_fixture("modpack_list.html"))
    assert page.page_info.total == 1509
    assert page.page_info.total_pages == 48
    assert len(page.items) == 32
    assert page.items[0].id == 829

    pack = parse_modpack_detail(read_fixture("modpack_1026.html"), 1026)
    assert pack.name == "破劫之刃"
    assert pack.name_en == "Break Disaster"
    assert pack.pack_type == "魔改整合"
    assert pack.loader == "Forge"
    assert pack.packaging == "CurseForge托管"
    assert {category.name for category in pack.categories} == {"冒险", "建筑", "任务", "大型", "国创"}
    assert pack.mods_total == 249
    assert sum(len(group.mods) for group in pack.mods) == 249
    assert pack.mods[0].category_name == "魔法"
    assert pack.team[0].role
    assert pack.versions[0].versions[0].version == "1.20.1"

    versions = parse_modpack_versions(read_fixture("modpack_version_1026.html"), 1026)
    assert versions.modpack_name == "破劫之刃 (Break Disaster)"
    assert len(versions.entries) == 31
    assert versions.entries[0].name == "V-132"
    assert "命运戒" in (versions.entries[0].content_text or "")


def test_parse_search() -> None:
    page = parse_search(read_fixture("search_industrialization.html"), query="工业化")
    assert page.counts["all"] == 635
    assert page.counts["mods"] == 17
    assert page.counts["servers"] == 938
    assert page.page_info.total == 1363
    assert page.page_info.total_pages == 46
    assert page.results[0].type == "mod"
    assert page.results[0].url == "https://www.mcmod.cn/class/3472.html"
    assert "工业化" in page.results[0].title
    assert page.results[0].snippet
    assert any(result.type == "modpack" for result in page.results)
    assert all(result.title and result.url for result in page.results)


def test_parse_post_and_author() -> None:
    post = parse_post(read_fixture("post_3339.html"), 3339)
    assert post.title.startswith("挖掘IC2")
    assert post.author and post.author.name == "cncagn"
    assert post.permission == "个人教程"
    assert post.views and post.views > 10_000
    assert post.created_at == "2023-08-03 01:22:58"
    assert post.license == "CC BY-NC-ND"
    assert post.mod and post.mod.id == 2
    assert post.related_mods and post.related_items
    assert "说明" in (post.content_text or "")

    author = parse_author(read_fixture("author_21425.html"), 21425)
    assert author.name == "IC2 Dev Team"
    assert author.views and author.views > 30_000
    assert len(author.members) == 7
    assert author.partners
    assert author.projects[0].id == 2
    assert author.projects[0].mod == "模组"


def test_parse_filters() -> None:
    filters = parse_filters(read_fixture("modlist.html"), "mod")
    groups = {group.id: group for group in filters.groups}
    assert {"category", "mcver", "platform", "api", "status", "mode", "sort"} <= set(groups)
    assert groups["category"].options[0].value == ""
    assert any(option.value == "1" and option.label == "科技" for option in groups["category"].options)
    assert any(option.value == "2" and option.label == "Fabric" for option in groups["api"].options)
    assert any(option.value == "created" for option in groups["sort"].options)

    pack_filters = parse_filters(read_fixture("modpack_list.html"), "modpack")
    pack_groups = {group.id: group for group in pack_filters.groups}
    assert {"category", "mcver", "mold", "api", "pack", "sort"} <= set(pack_groups)
    assert any(option.value == "1" and option.label == "CurseForge托管" for option in pack_groups["pack"].options)


def test_empty_mod_and_modpack_lists() -> None:
    marker = '<div class="modlist-list-frame"><p class="modlist-list-empty">没有找到符合条件的结果..</p></div>'
    mod_page = parse_mod_list(marker)
    assert mod_page.items == []
    assert mod_page.page_info.total == 0
    pack_page = parse_modpack_list(marker)
    assert pack_page.items == []
    assert pack_page.page_info.total == 0
