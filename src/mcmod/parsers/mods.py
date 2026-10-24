"""Parsers for mod list/detail pages, item lists and download pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..errors import ParseError
from ..models import (
    AuthorRef,
    CategoryRef,
    ChangelogEntry,
    DownloadFile,
    DownloadsPage,
    ItemCategory,
    ItemPreview,
    ItemRef,
    ItemTypeRef,
    ModDetail,
    ModItemsPage,
    ModListPage,
    ModRating,
    ModStats,
    ModStatus,
    ModSummary,
    NamedLink,
    PageInfo,
    RatingDimension,
    RelationGroup,
    TutorialRef,
    VersionGroup,
    VersionRef,
)
from .common import (
    LOADER_NAMES,
    MOD_CATEGORY_NAMES,
    absolute_url,
    attr_of,
    clean_text,
    decode_mcmod_link,
    extract_id,
    image_url,
    make_soup,
    parse_compact_number,
    parse_float,
    parse_int,
    parse_page_info,
    parse_percent,
    text_of,
    tooltip_parts,
)

RATING_NAMES = ["好玩", "有挑战", "很稳定", "很实用", "很漂亮", "合理", "兼容好", "很耐玩"]
RATING_SCORE_NAMES = ["趣味", "难度", "稳定", "实用", "美观", "平衡", "兼容", "持久"]


def _page_info(soup: BeautifulSoup, count: int, requested_page: int) -> PageInfo:
    return parse_page_info(soup, count, requested_page)


def _split_short_name(name: str) -> tuple[str | None, str]:
    match = re.match(r"^(\[[^\]]+\])\s*(.+)$", name.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return None, name.strip()


def parse_mod_list(html: str, *, page: int = 1) -> ModListPage:
    soup = make_soup(html)
    cards = soup.select(".modlist-block")
    if not cards:
        if soup.select_one(".modlist-list-empty") is not None:
            return ModListPage(
                items=[], page_info=PageInfo(page=page, per_page=32, total_pages=1, total=0)
            )
        raise ParseError("mod list page contained no mod cards")
    items: list[ModSummary] = []
    for card in cards:
        link = card.select_one(".title .name a[href]")
        if link is None:
            continue
        mod_id = extract_id(link.get("href"), "mod")
        if mod_id is None:
            continue
        display_name = text_of(link) or ""
        short_name, name = _split_short_name(display_name)
        en_link = card.select_one(".title .ename a")
        description = text_of(card.select_one(".intro-content"))
        previews: list[ItemPreview] = []
        for hover in card.select(".items .item-table-hover")[:6]:
            item_link = hover.select_one("a[href]")
            item_name, _ = tooltip_parts(hover)
            item_id = parse_int(hover.get("item-id"))
            if item_link is None or item_id is None:
                continue
            previews.append(
                ItemPreview(
                    id=item_id,
                    name=item_name or (text_of(item_link) or str(item_id)),
                    icon=image_url(hover.select_one("img")),
                    url=absolute_url(item_link.get("href")) or "",
                )
            )
        items.append(
            ModSummary(
                id=mod_id,
                name=name,
                short_name=short_name,
                name_en=text_of(en_link),
                description=description,
                cover=image_url(card.select_one(".cover img"), full=True),
                url=absolute_url(link.get("href")) or "",
                preview_items=previews,
            )
        )
    return ModListPage(items=items, page_info=_page_info(soup, len(items), page))


def _parse_statuses(soup: BeautifulSoup) -> list[ModStatus]:
    statuses: list[ModStatus] = []
    for node in soup.select(".class-official-group > div"):
        classes = node.get("class") or []
        kind = "status" if any("status" in c for c in classes) else "source" if any("source" in c for c in classes) else "other"
        label = text_of(node)
        if label:
            statuses.append(
                ModStatus(kind=kind, label=label, description=attr_of(node, "data-original-title"))
            )
    return statuses


def _parse_categories(soup: BeautifulSoup) -> tuple[CategoryRef | None, list[CategoryRef]]:
    main: CategoryRef | None = None
    mold_link = soup.select_one("#MoldLink")
    if mold_link:
        category_id = None
        match = re.search(r"/class/category/(\d+)-", mold_link.get("href", ""))
        if match:
            category_id = int(match.group(1))
        name = text_of(mold_link)
        if category_id is not None:
            name = MOD_CATEGORY_NAMES.get(category_id, name)
        main = CategoryRef(
            id=category_id,
            name=re.sub(r"(?i)mod$", "", name or "").strip() or (name or ""),
            description=attr_of(mold_link, "data-original-title"),
            url=absolute_url(mold_link.get("href")),
            main=True,
        )
    categories: list[CategoryRef] = []
    for anchor in soup.select(".common-class-category a[href*='category=']"):
        match = re.search(r"category=(\d+)", anchor.get("href", ""))
        if not match:
            continue
        category_id = int(match.group(1))
        is_main = bool(anchor.select_one("svg")) or not (text_of(anchor) or "")
        name = text_of(anchor) or MOD_CATEGORY_NAMES.get(category_id, f"category-{category_id}")
        categories.append(
            CategoryRef(
                id=category_id,
                name=name,
                description=attr_of(anchor, "data-original-title"),
                url=absolute_url(anchor.get("href")),
                main=is_main,
            )
        )
    return main, categories


def _parse_version_groups(soup: BeautifulSoup) -> list[VersionGroup]:
    groups: list[VersionGroup] = []
    block = soup.select_one(".class-info-left .mcver .platform-block")
    if block is None:
        return groups
    current: VersionGroup | None = None
    for child in block.find_all(["div"], recursive=False):
        classes = child.get("class") or []
        if "mcver-title" in classes:
            platform_text = text_of(child)
            if not platform_text:
                continue
            platform = re.sub(r"\(共.*?\)|[:：]", "", platform_text).strip()
            total = parse_int(platform_text)
            current = VersionGroup(platform=platform, total=total, versions=[])
            groups.append(current)
        elif "mcver-row" in classes and current is not None:
            for element in child.find_all(recursive=False):
                element_classes = element.get("class") or []
                if element.name == "a":
                    version = text_of(element)
                    if version:
                        current.versions.append(
                            VersionRef(
                                version=version,
                                url=absolute_url(element.get("href")),
                                current="text-danger" in element_classes,
                            )
                        )
                elif "mcver-dropdown" in element_classes:
                    button = element.select_one("button")
                    if button is not None:
                        group_version = clean_text(
                            re.sub(r"\(\d+\)", "", button.get_text(" ", strip=True))
                        )
                        if group_version:
                            current.versions.append(
                                VersionRef(
                                    version=group_version,
                                    url=None,
                                    current="text-danger" in (button.get("class") or []),
                                )
                            )
                    for anchor in element.select(".dropdown-menu a"):
                        version = text_of(anchor)
                        if version:
                            current.versions.append(
                                VersionRef(
                                    version=version,
                                    url=absolute_url(anchor.get("href")),
                                )
                            )
    return groups


def _parse_authors(soup: BeautifulSoup) -> list[AuthorRef]:
    authors: list[AuthorRef] = []
    for item in soup.select(".class-info-left .author .frame li"):
        link = item.select_one(".name a[href]")
        if link is None:
            continue
        authors.append(
            AuthorRef(
                id=extract_id(link.get("href"), "author"),
                name=text_of(link) or "",
                role=text_of(item.select_one(".position")),
                avatar=image_url(item.select_one(".avatar img")),
                url=absolute_url(link.get("href")),
            )
        )
    return authors


def _parse_links(soup: BeautifulSoup) -> list[NamedLink]:
    links: list[NamedLink] = []
    for item in soup.select(".class-info-left .common-link-frame .list li"):
        anchor = item.select_one("a[href]")
        if anchor is None:
            continue
        name = text_of(item.select_one(".name")) or attr_of(anchor, "data-original-title") or "link"
        description = attr_of(anchor, "data-original-title")
        url = decode_mcmod_link(anchor.get("href"))
        if url:
            links.append(NamedLink(name=name, url=url, description=description))
    return links


def _parse_stats(soup: BeautifulSoup) -> ModStats:
    stats = ModStats()
    star = soup.select_one(".class-excount .star")
    if star:
        stats.score = parse_float(text_of(star.select_one(".up")))
        stats.rank = text_of(star.select_one(".down"))
        for text_node in star.select(".block-right .text"):
            text = text_of(text_node) or ""
            if "昨日指数" in text and "平均" not in text:
                stats.yesterday_index = parse_int(text)
            elif "平均" in text:
                stats.average_index = parse_float(text)
    for span in soup.select(".infos .span"):
        label = text_of(span.select_one(".t"))
        value = text_of(span.select_one(".n"))
        if label == "总浏览":
            stats.total_views_text = value
            stats.total_views = parse_int(attr_of(span, "title")) or parse_compact_number(value)
        elif label == "资料填充率":
            stats.data_fill_rate = parse_percent(value)
    return stats


def _parse_rating(soup: BeautifulSoup) -> ModRating:
    rating = ModRating()
    raw_node = soup.select_one("#class-rating")
    raw = attr_of(raw_node, "data-original-title") if raw_node else None
    if raw:
        for index, part in enumerate(re.split(r"<br\s*/?>", raw)):
            match = re.search(r"([^:：]+)[:：]\s*([\d.]+)", part)
            if match:
                key = clean_text(match.group(1)) or RATING_SCORE_NAMES[min(index, 7)]
                rating.scores[key] = float(match.group(2))
    for index, text_node in enumerate(soup.select(".class-rating-content .progress-text")):
        text = text_of(text_node)
        if not text:
            continue
        percent = parse_percent(text)
        if percent is None:
            continue
        name = RATING_NAMES[index] if index < len(RATING_NAMES) else f"dimension-{index + 1}"
        rating.dimensions.append(RatingDimension(name=name, percent=percent, raw=text))
    return rating


def _parse_item_types(soup: BeautifulSoup) -> list[ItemTypeRef]:
    types: list[ItemTypeRef] = []
    for anchor in soup.select(".class-menu-main[data-frame='1'] .class-item-type a[href*='/item/list/']"):
        match = re.search(r"/item/list/\d+-(\d+)\.html", anchor.get("href", ""))
        if not match:
            continue
        types.append(
            ItemTypeRef(
                id=int(match.group(1)),
                name=text_of(anchor.select_one(".title")) or text_of(anchor) or "items",
                description=text_of(anchor.select_one(".content")),
                count=parse_int(text_of(anchor.select_one(".count"))),
                url=absolute_url(anchor.get("href")) or "",
            )
        )
    return types


def _parse_menu_counts(soup: BeautifulSoup) -> dict[str, int]:
    counts: dict[str, int] = {}
    for menu in soup.select(".common-menu-page"):
        for link in menu.select(".page-li a"):
            text = text_of(link)
            if not text:
                continue
            match = re.match(r"(.+?)\s*\(([\d,]+)\)", text)
            if match:
                counts[clean_text(match.group(1)) or text] = int(match.group(2).replace(",", ""))
    return counts


def _parse_changelog(soup: BeautifulSoup) -> list[ChangelogEntry]:
    entries: list[ChangelogEntry] = []
    for block in soup.select(".common-rowlist-block"):
        title = text_of(block.select_one(".title"))
        if not title or not title.startswith("更新日志"):
            continue
        for item in block.select(".common-rowlist li"):
            link = item.select_one("a[href]")
            if link is None:
                continue
            entries.append(
                ChangelogEntry(
                    version=text_of(link) or "",
                    date=text_of(item.select_one(".time")),
                    url=absolute_url(link.get("href")),
                )
            )
        break
    return entries


def _parse_tutorials(soup: BeautifulSoup) -> list[TutorialRef]:
    tutorials: list[TutorialRef] = []
    for block in soup.select(".text-area-post .post-block"):
        link = block.select_one(".title a[href]")
        if link is None:
            continue
        post_id = extract_id(link.get("href"), "post")
        if post_id is None:
            continue
        views_text = attr_of(block.select_one(".click"), "data-original-title") or text_of(
            block.select_one(".click")
        )
        tutorials.append(
            TutorialRef(
                id=post_id,
                title=text_of(link) or "",
                url=absolute_url(link.get("href")) or "",
                views=parse_int(views_text),
                views_text=views_text,
                age=text_of(block.select_one(".time")),
                cover=image_url(block.select_one(".cover img"), full=True),
            )
        )
    return tutorials


def _parse_relations(soup: BeautifulSoup) -> list[RelationGroup]:
    groups: list[RelationGroup] = []
    for fieldset in soup.select(".class-relation-list fieldset"):
        legend = text_of(fieldset.select_one("legend"))
        for item in fieldset.select("li.relation"):
            span = item.find("span", recursive=False)
            relation = text_of(span)
            if not relation:
                continue
            mods: list[ItemPreview] = []
            for link in item.select("ul li a[href]"):
                mod_id = extract_id(link.get("href"), "mod")
                if mod_id is None:
                    continue
                mods.append(
                    ItemPreview(
                        id=mod_id,
                        name=text_of(link) or "",
                        url=absolute_url(link.get("href")) or "",
                    )
                )
            groups.append(
                RelationGroup(
                    version=legend,
                    relation=relation,
                    description=attr_of(span, "data-original-title"),
                    mods=mods,
                )
            )
    return groups


def _parse_infolist(soup: BeautifulSoup) -> dict[str, int | float | None]:
    result: dict[str, int | float | None] = {
        "modpack_usage": None,
        "worldgen": None,
        "server_count": None,
        "server_install_rate": None,
    }
    node = soup.select_one(".class-info-left li.infolist.modpack")
    if node:
        result["modpack_usage"] = parse_int(text_of(node))
    node = soup.select_one(".class-info-left li.infolist.worldgen")
    if node:
        result["worldgen"] = parse_int(text_of(node))
    node = soup.select_one(".class-info-left li.infolist.server-count")
    if node:
        result["server_count"] = parse_int(text_of(node))
    node = soup.select_one(".class-info-left li.infolist.server-pre")
    if node:
        result["server_install_rate"] = parse_percent(text_of(node))
    return result


def parse_mod_detail(html: str, mod_id: int) -> ModDetail:
    soup = make_soup(html)
    title_block = soup.select_one(".class-title")
    if title_block is None:
        raise ParseError(f"mod page {mod_id} did not contain a class title")
    name = text_of(title_block.select_one("h3")) or text_of(title_block) or f"mod-{mod_id}"
    short_name = text_of(title_block.select_one(".short-name"))
    name_en = text_of(title_block.select_one("h4"))
    main_category, categories = _parse_categories(soup)
    statuses = _parse_statuses(soup)

    platforms: list[CategoryRef] = []
    loaders: list[CategoryRef] = []
    environment: list[str] = []
    created = last_edit = last_recommended = None
    edit_count = None
    tags: list[str] = []
    for li in soup.select(".class-info-left > ul > li"):
        text = text_of(li) or ""
        if text.startswith("支持平台"):
            for anchor in li.select("a[href]"):
                platform_id = parse_int(re.search(r"platform=(\d+)", anchor.get("href", "")).group(1)) if re.search(r"platform=(\d+)", anchor.get("href", "")) else None
                platforms.append(
                    CategoryRef(
                        id=platform_id,
                        name=text_of(anchor) or "",
                        url=absolute_url(anchor.get("href")),
                    )
                )
        elif text.startswith("运作方式"):
            for anchor in li.select("a[href]"):
                match = re.search(r"api=(\d+)", anchor.get("href", ""))
                loader_id = int(match.group(1)) if match else None
                loaders.append(
                    CategoryRef(
                        id=loader_id,
                        name=text_of(anchor) or (LOADER_NAMES.get(loader_id or 0) or ""),
                        url=absolute_url(anchor.get("href")),
                    )
                )
        elif text.startswith("运行环境"):
            value = text.split(":", 1)[-1].split("：", 1)[-1]
            environment = [part.strip() for part in re.split(r"[,，]", value) if part.strip()]
        elif text.startswith("收录时间"):
            created = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("最后编辑"):
            last_edit = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("最后推荐"):
            last_recommended = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("编辑次数"):
            edit_count = parse_int(text)
        elif "tag" in (li.get("class") or []):
            tags = [text_of(anchor) for anchor in li.select("a") if text_of(anchor)]
    item_types = _parse_item_types(soup)
    menu_counts = _parse_menu_counts(soup)
    info = _parse_infolist(soup)

    intro_html = None
    intro_text = None
    outline: list[str] = []
    intro_pane = None
    for menu in soup.select(".common-menu-page"):
        if menu.find(string=lambda x: x and "Mod介绍" in x):
            intro_pane = menu.find_next_sibling(class_="class-menu-main")
            break
    if intro_pane is not None:
        intro_li = intro_pane.select_one("li.text-area[data-id='1']") or intro_pane.select_one("li.text-area")
        if intro_li is not None:
            intro_html = intro_li.decode_contents().strip()
            intro_text = text_of(intro_li, separator="\n")
            outline = [
                text
                for span in intro_li.select(".common-text-title")
                if (text := text_of(span))
            ]

    downloads_url = None
    download_count = None
    download_files_count = None
    for link in soup.select(".common-menu-page a[href*='/download/']"):
        downloads_url = absolute_url(link.get("href"))
        download_count = parse_int(attr_of(link, "title"))
        download_files_count = parse_int(text_of(link))

    return ModDetail(
        id=mod_id,
        url=f"https://www.mcmod.cn/class/{mod_id}.html",
        name=name,
        short_name=short_name,
        name_en=name_en,
        cover=image_url(soup.select_one(".class-cover-image img"), full=True),
        statuses=statuses,
        main_category=main_category,
        categories=categories,
        platforms=platforms,
        loaders=loaders,
        environment=environment,
        created=created,
        edit_count=edit_count,
        last_edit=last_edit,
        last_recommended=last_recommended,
        tags=tags,
        links=_parse_links(soup),
        versions=_parse_version_groups(soup),
        authors=_parse_authors(soup),
        stats=_parse_stats(soup),
        rating=_parse_rating(soup),
        intro_html=intro_html,
        intro_text=intro_text,
        outline=outline,
        item_types=item_types,
        item_count=sum(item.count or 0 for item in item_types) or None,
        menu_counts=menu_counts,
        changelog=_parse_changelog(soup),
        tutorials=_parse_tutorials(soup),
        tutorials_total=menu_counts.get("Mod教程"),
        discussions_total=menu_counts.get("Mod讨论"),
        features_total=menu_counts.get("Mod特性"),
        relations=_parse_relations(soup),
        modpack_usage=info["modpack_usage"],
        worldgen=info["worldgen"],
        server_count=info["server_count"],
        server_install_rate=info["server_install_rate"],
        download_count=download_count,
        download_files_count=download_files_count,
        downloads_url=downloads_url,
    )


def parse_mod_items(html: str, mod_id: int, type_id: int, *, query: str | None = None) -> ModItemsPage:
    soup = make_soup(html)
    table = soup.select_one("table.item-list-table")
    if table is None:
        raise ParseError(f"item list for mod {mod_id} type {type_id} was not found")
    mod_link = soup.select_one("table.item-list-table th .title a[href]")
    mod_name = text_of(mod_link) or text_of(soup.select_one(".common-nav li:nth-last-child(2)"))
    type_name = None
    header = soup.select_one("table.item-list-table th .title")
    if header:
        header_text = text_of(header) or ""
        if "的" in header_text:
            type_name = header_text.split("的", 1)[1].replace("资料", "").strip() or None
    declared_total = None
    active_mold = soup.select_one(".common-item-mold-list li.mold.active span")
    if active_mold:
        match = re.search(r"\(([\d,]+)\)", text_of(active_mold) or "")
        if match:
            declared_total = int(match.group(1).replace(",", ""))
    categories: list[ItemCategory] = []
    total = 0
    for row in table.select("tbody > tr"):
        left = row.select_one("th.item-list-type-left")
        right = row.select_one("td.item-list-type-right")
        if left is None or right is None:
            continue
        category = ItemCategory(name=text_of(left) or "other")
        for anchor in right.select("a[href*='/item/']"):
            item_id = extract_id(anchor.get("href"), "item")
            if item_id is None:
                continue
            name = text_of(anchor)
            if not name:
                continue
            if query and query.lower() not in name.lower() and query.lower() not in (
                (attr_of(anchor, "data-en") or "").lower()
            ):
                continue
            category.items.append(
                ItemRef(
                    id=item_id,
                    name=name,
                    name_en=attr_of(anchor, "data-en"),
                    url=absolute_url(anchor.get("href")),
                )
            )
        if category.items:
            categories.append(category)
            total += len(category.items)
    return ModItemsPage(
        mod_id=mod_id,
        mod_name=mod_name or f"mod-{mod_id}",
        type_id=type_id,
        type_name=type_name,
        categories=categories,
        total=total,
        declared_total=declared_total,
        query=query,
    )


def parse_downloads(html: str, mod_id: int) -> DownloadsPage:
    soup = make_soup(html)
    table = soup.select_one(".download-table")
    if table is None:
        raise ParseError(f"download table for mod {mod_id} was not found")
    mod_link = soup.select_one(".common-nav a[href*='/class/']")
    mod_name = text_of(mod_link)
    if not mod_name:
        page_title = text_of(soup.select_one("title")) or ""
        parts = page_title.split(" - ")
        mod_name = parts[1].strip() if len(parts) > 1 else f"mod-{mod_id}"
    files: list[DownloadFile] = []
    for row in table.select("tr[data-id]"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 7:
            continue
        platform = text_of(cells[0].select_one(".download-platform"))
        loader = text_of(cells[0].select_one(".download-api"))
        filename = clean_text(cells[1].get_text(" ", strip=True)) or attr_of(row, "data-filename") or ""
        downloads = parse_int(attr_of(cells[4], "data-original-title")) or parse_int(text_of(cells[4]))
        likes = parse_int(attr_of(cells[5], "data-original-title")) or parse_int(text_of(cells[5]))
        uploaded_tooltip = attr_of(cells[6], "data-original-title")
        uploaded_at = None
        if uploaded_tooltip:
            match = re.search(r"\(([^)]+)\)", uploaded_tooltip)
            uploaded_at = match.group(1) if match else None
        files.append(
            DownloadFile(
                id=parse_int(attr_of(row, "data-id")),
                filename=filename,
                platform=platform,
                loader=loader,
                version=attr_of(row, "data-version"),
                size=text_of(cells[3]),
                size_bytes=parse_int(attr_of(cells[3], "data-original-title")),
                downloads=downloads,
                likes=likes,
                uploaded=text_of(cells[6]),
                uploaded_at=uploaded_at,
                md5=attr_of(row, "data-md5"),
                crc32=attr_of(row, "data-crc32"),
                sha256=attr_of(row, "data-sha256"),
                suffix=attr_of(row, "data-suffix"),
            )
        )
    total = len(files)
    count_node = soup.find(string=lambda x: x and "个文件可下载" in x)
    if count_node:
        parsed = parse_int(str(count_node))
        if parsed:
            total = parsed
    return DownloadsPage(
        mod_id=mod_id,
        mod_name=mod_name or f"mod-{mod_id}",
        total=total,
        files=files,
    )
