"""Parsers for modpack list/detail and modpack changelog pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..errors import ParseError
from ..models import (
    CategoryRef,
    ItemRef,
    ModpackDetail,
    ModpackListPage,
    ModpackModCategory,
    ModpackSummary,
    ModpackVersionEntry,
    ModpackVersionsPage,
    PageInfo,
)
from .common import (
    MODPACK_CATEGORY_NAMES,
    absolute_url,
    attr_of,
    clean_text,
    extract_id,
    image_url,
    make_soup,
    parse_int,
    parse_page_info,
    text_of,
)
from .mods import (
    _parse_authors,
    _parse_changelog,
    _parse_links,
    _parse_stats,
    _parse_version_groups,
)


def _split_short_name(name: str) -> tuple[str | None, str]:
    match = re.match(r"^(\[[^\]]+\])\s*(.+)$", name.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return None, name.strip()


def parse_modpack_list(html: str, *, page: int = 1) -> ModpackListPage:
    soup = make_soup(html)
    cards = soup.select(".modlist-block")
    if not cards:
        if soup.select_one(".modlist-list-empty") is not None:
            return ModpackListPage(
                items=[], page_info=PageInfo(page=page, per_page=32, total_pages=1, total=0)
            )
        raise ParseError("modpack list page contained no modpack cards")
    items: list[ModpackSummary] = []
    for card in cards:
        link = card.select_one(".title .name a[href]")
        if link is None:
            continue
        pack_id = extract_id(link.get("href"), "modpack")
        if pack_id is None:
            continue
        short_name, name = _split_short_name(text_of(link) or "")
        items.append(
            ModpackSummary(
                id=pack_id,
                name=name,
                short_name=short_name,
                name_en=text_of(card.select_one(".title .ename a")),
                description=text_of(card.select_one(".intro-content")),
                cover=image_url(card.select_one(".cover img"), full=True),
                url=absolute_url(link.get("href")) or "",
            )
        )
    return ModpackListPage(items=items, page_info=parse_page_info(soup, len(items), page))


def _parse_modpack_categories(soup: BeautifulSoup) -> list[CategoryRef]:
    categories: list[CategoryRef] = []
    for anchor in soup.select(".common-class-category a[href*='category='], .class-category a[href*='/modpack/category/'], .class-category a[href*='category=']"):
        match = re.search(r"category[/=](\d+)", anchor.get("href", ""))
        if not match:
            continue
        category_id = int(match.group(1))
        categories.append(
            CategoryRef(
                id=category_id,
                name=text_of(anchor) or MODPACK_CATEGORY_NAMES.get(category_id, f"category-{category_id}"),
                description=attr_of(anchor, "data-original-title"),
                url=absolute_url(anchor.get("href")),
            )
        )
    return categories


def _parse_modpack_mods(soup: BeautifulSoup) -> list[ModpackModCategory]:
    groups: list[ModpackModCategory] = []
    for item in soup.select(".class-relation-list li.relation.modlist"):
        category_link = item.select_one("span a[href*='/class/category/']")
        category_id = None
        if category_link:
            match = re.search(r"/class/category/(\d+)-", category_link.get("href", ""))
            if match:
                category_id = int(match.group(1))
        mods: list[ItemRef] = []
        for li in item.select("ul > li"):
            link = li.select_one("p a[href*='/class/']")
            if link is None:
                continue
            mod_id = extract_id(link.get("href"), "mod")
            if mod_id is None:
                continue
            mods.append(
                ItemRef(
                    id=mod_id,
                    name=text_of(link) or "",
                    url=absolute_url(link.get("href")),
                    version=text_of(li.select_one("p:nth-of-type(2)")),
                )
            )
        if mods:
            groups.append(
                ModpackModCategory(
                    category_id=category_id,
                    category_name=MODPACK_CATEGORY_NAMES.get(category_id or -1),
                    mods=mods,
                )
            )
    return groups


def parse_modpack_detail(html: str, pack_id: int) -> ModpackDetail:
    soup = make_soup(html)
    title_block = soup.select_one(".class-title")
    if title_block is None:
        raise ParseError(f"modpack page {pack_id} did not contain a class title")
    name = text_of(title_block.select_one("h3")) or f"modpack-{pack_id}"
    short_name = text_of(title_block.select_one(".short-name"))
    name_en = text_of(title_block.select_one("h4"))

    categories = _parse_modpack_categories(soup)
    pack_type = loader = packaging = None
    created = created_at = last_edit = last_edit_at = last_recommended = None
    edit_count = None
    tags: list[str] = []
    for li in soup.select(".class-info-left > ul > li"):
        text = text_of(li) or ""
        if text.startswith("整合包类型"):
            pack_type = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("运作方式"):
            loader = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("打包方式"):
            packaging = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("收录时间"):
            created = text.split(":", 1)[-1].split("：", 1)[-1].strip()
            created_at = attr_of(li, "data-original-title")
        elif text.startswith("最后编辑"):
            last_edit = text.split(":", 1)[-1].split("：", 1)[-1].strip()
            last_edit_at = attr_of(li, "data-original-title")
        elif text.startswith("最后推荐"):
            last_recommended = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("编辑次数"):
            edit_count = parse_int(text)
        elif "tag" in (li.get("class") or []):
            tags = [text_of(anchor) for anchor in li.select("a") if text_of(anchor)]

    intro_html = None
    intro_text = None
    pane = soup.select_one(".class-menu-main")
    if pane is not None:
        intro_li = pane.select_one("li.text-area[data-id='1']") or pane.select_one("li.text-area")
        if intro_li is not None:
            intro_html = intro_li.decode_contents().strip()
            intro_text = text_of(intro_li, separator="\n")

    menu_counts: dict[str, int] = {}
    for menu in soup.select(".common-menu-page .page-li a"):
        text = text_of(menu)
        if not text:
            continue
        match = re.match(r"(.+?)\s*\(([\d,]+)\)", text)
        if match:
            menu_counts[clean_text(match.group(1)) or text] = int(match.group(2).replace(",", ""))

    versions_url = None
    for link in soup.select("a[href*='/modpack/version/']"):
        versions_url = absolute_url(link.get("href"))
        break
    if versions_url is None:
        versions_url = absolute_url(f"/modpack/version/{pack_id}.html")

    return ModpackDetail(
        id=pack_id,
        url=f"https://www.mcmod.cn/modpack/{pack_id}.html",
        name=name,
        short_name=short_name,
        name_en=name_en,
        cover=image_url(soup.select_one(".class-cover-image img"), full=True),
        categories=categories,
        pack_type=pack_type,
        loader=loader,
        packaging=packaging,
        created=created,
        created_at=created_at,
        last_edit=last_edit,
        last_edit_at=last_edit_at,
        last_recommended=last_recommended,
        edit_count=edit_count,
        tags=tags,
        links=_parse_links(soup),
        versions=_parse_version_groups(soup),
        team=_parse_authors(soup),
        stats=_parse_stats(soup),
        intro_html=intro_html,
        intro_text=intro_text,
        mods=_parse_modpack_mods(soup),
        mods_total=menu_counts.get("包含模组"),
        changelog=_parse_changelog(soup),
        versions_url=versions_url,
    )


def parse_modpack_versions(html: str, pack_id: int) -> ModpackVersionsPage:
    soup = make_soup(html)
    name = None
    for anchor in soup.select(".common-nav a[href*='/modpack/']"):
        if "/version/" not in (anchor.get("href") or ""):
            name = text_of(anchor)
    if name is None:
        title = text_of(soup.select_one("title")) or ""
        name = title.split("更新日志", 1)[0].strip() or f"modpack-{pack_id}"
    entries: list[ModpackVersionEntry] = []
    for block in soup.select(".version-content-block"):
        title_node = block.select_one(".version-content-right .title .name")
        if title_node is None:
            continue
        content = block.select_one(".version-content-right .content")
        edit_link = block.select_one(".version-content-right .tools .edit a[href]")
        entries.append(
            ModpackVersionEntry(
                name=text_of(title_node) or "",
                date=text_of(block.select_one(".version-content-left .time")),
                content_html=content.decode_contents().strip() if content else None,
                content_text=text_of(content, separator="\n"),
                edit_url=absolute_url(edit_link.get("href")) if edit_link else None,
            )
        )
    return ModpackVersionsPage(modpack_id=pack_id, modpack_name=name, entries=entries)
