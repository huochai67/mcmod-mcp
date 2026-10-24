"""Parsers for item detail and item recipe/usage pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..errors import ParseError
from ..models import (
    ItemDetail,
    ItemRef,
    NamedLink,
    RecipeRow,
    RecipesPage,
)
from .common import (
    absolute_url,
    attr_of,
    extract_id,
    image_url,
    make_soup,
    parse_int,
    text_of,
    tooltip_parts,
)

_ITEM_PAREN_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")
_COUNT_RE = re.compile(r"(?:\*|×|x|X)\s*(\d+)|(\d+)\s*个")


def _split_item_name(raw: str) -> tuple[str, str | None]:
    match = _ITEM_PAREN_RE.match(raw)
    if match and re.search(r"[A-Za-z]", match.group(2)):
        return match.group(1).strip(), match.group(2).strip()
    return raw.strip(), None


def _parse_stats(soup: BeautifulSoup) -> dict[str, object]:
    result: dict[str, object] = {}
    for li in soup.select(".common-rowlist-2 li"):
        text = text_of(li) or ""
        if text.startswith("浏览量"):
            result["views"] = parse_int(text)
        elif text.startswith("创建日期"):
            result["created"] = text.split(":", 1)[-1].split("：", 1)[-1].strip()
            result["created_at"] = attr_of(li, "data-original-title")
        elif text.startswith("最后编辑"):
            result["last_edit"] = text.split(":", 1)[-1].split("：", 1)[-1].strip()
            result["last_edit_at"] = attr_of(li, "data-original-title")
        elif text.startswith("编辑次数"):
            result["edit_count"] = parse_int(text)
    return result


def _anchor_item(anchor, *, count: int | None = None) -> ItemRef:
    name = text_of(anchor) or ""
    tooltip_name, tooltip_mod = tooltip_parts(anchor)
    href = anchor.get("href") if anchor else None
    oredict = None
    if href and "/oredict/" in href:
        oredict = name.removeprefix("矿词:").strip()
    item_id = extract_id(href, "item") if href and "/item/" in href else None
    return ItemRef(
        id=item_id,
        name=name or tooltip_name or (oredict or ""),
        name_en=None,
        url=absolute_url(href),
        icon=image_url(anchor.select_one("img")) if anchor else None,
        mod=tooltip_mod,
        oredict=oredict,
        count=count,
    )


def _count_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = _COUNT_RE.search(text)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_properties(soup: BeautifulSoup) -> dict[str, str]:
    properties: dict[str, str] = {}
    for table in soup.select(".item-info-table table"):
        for row in table.select("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) != 2:
                continue
            label = text_of(cells[0])
            if not label:
                continue
            label = label.rstrip(":：").strip()
            if label in {"合/用途", "主要名称"} and not text_of(cells[1]):
                continue
            values = [
                name
                for hover in cells[1].select(".item-table-hover")
                if (name := tooltip_parts(hover)[0])
            ]
            value = text_of(cells[1]) or ", ".join(values)
            if not value or value == "查看合成/用途":
                continue
            properties[label] = value
    return properties


def _parse_related_items(soup: BeautifulSoup) -> list[ItemRef]:
    for block in soup.select(".common-imglist-block"):
        if (text_of(block.select_one(".title")) or "") != "相关物品":
            continue
        items: list[ItemRef] = []
        for li in block.select(".common-imglist li"):
            link = li.select_one(".text a[href]") or li.select_one("a[href]")
            if link is None:
                continue
            item_id = extract_id(link.get("href"), "item")
            if item_id is None:
                continue
            items.append(
                ItemRef(
                    id=item_id,
                    name=text_of(link) or attr_of(li, "data-original-title") or "",
                    url=absolute_url(link.get("href")),
                    icon=image_url(li.select_one("img")),
                )
            )
        return items
    return []


def parse_item_detail(html: str, item_id: int) -> ItemDetail:
    soup = make_soup(html)
    name_node = soup.select_one(".itemname h5")
    if name_node is None:
        raise ParseError(f"item page {item_id} did not contain an item name")
    raw_name = text_of(name_node) or f"item-{item_id}"
    name, name_en = _split_item_name(raw_name)
    properties = _parse_properties(soup)
    if properties.get("主要名称"):
        name = properties["主要名称"]
    if properties.get("次要名称"):
        name_en = properties["次要名称"]

    mod_id = mod_name = mod_url = item_type = None
    for anchor in soup.select(".common-nav a[href]"):
        href = anchor.get("href", "")
        if "/class/" in href and "/category/" not in href:
            mod_id = extract_id(href, "mod")
            mod_name = text_of(anchor)
            mod_url = absolute_url(href)
        elif "/item/list/" in href:
            item_type = text_of(anchor)

    command = attr_of(soup.select_one(".item-give"), "data-command")
    if not command:
        give_text = text_of(soup.select_one(".item-give"))
        if give_text and "：" in give_text:
            command = give_text.split("：", 1)[1].strip()

    ore_dict: list[NamedLink] = []
    for anchor in soup.select(".item-dict a[href]"):
        name_text = text_of(anchor)
        url = absolute_url(anchor.get("href"))
        if name_text and url:
            ore_dict.append(NamedLink(name=name_text, url=url))

    description = soup.select_one(".item-content")
    description_html = description.decode_contents().strip() if description else None
    description_text = text_of(description, separator="\n")

    icon = None
    for img in soup.select(".item-info-table img"):
        if img.get("width") == "128" or (icon is None and img.get("width") in {"64", "128"}):
            icon = image_url(img)
            if img.get("width") == "128":
                break
    if icon is None:
        icon = image_url(soup.select_one(".item-info-table img"))

    stats = _parse_stats(soup)
    return ItemDetail(
        id=item_id,
        url=f"https://www.mcmod.cn/item/{item_id}.html",
        name=name,
        name_en=name_en,
        mod_id=mod_id,
        mod_name=mod_name,
        mod_url=mod_url,
        item_type=item_type,
        icon=icon,
        command=command,
        ore_dict=ore_dict,
        properties=properties,
        description_html=description_html,
        description_text=description_text,
        related_items=_parse_related_items(soup),
        views=stats.get("views"),  # type: ignore[arg-type]
        created=stats.get("created"),  # type: ignore[arg-type]
        created_at=stats.get("created_at"),  # type: ignore[arg-type]
        last_edit=stats.get("last_edit"),  # type: ignore[arg-type]
        last_edit_at=stats.get("last_edit_at"),  # type: ignore[arg-type]
        edit_count=stats.get("edit_count"),  # type: ignore[arg-type]
        recipes_url=absolute_url(f"/item/tab/{item_id}.html"),
    )


def _parse_recipe_row(row) -> RecipeRow | None:
    stats_cell = row.select_one("td.item-table-count")
    if stats_cell is None:
        return None
    station: ItemRef | None = None
    paragraphs = stats_cell.find_all("p", recursive=False)
    after_arrow = False
    ingredients: list[ItemRef] = []
    outputs: list[ItemRef] = []
    for index, paragraph in enumerate(paragraphs):
        text = text_of(paragraph) or ""
        if not text:
            continue
        if text.strip() in {"↓", "↓ ", "▼"}:
            after_arrow = True
            continue
        if index == 0 and ("使用" in text or "使用:" in text or "使用：" in text):
            anchor = paragraph.select_one("a[href]")
            if anchor is not None:
                station = _anchor_item(anchor)
            continue
        anchor = paragraph.select_one("a[href]")
        if anchor is not None:
            item = _anchor_item(anchor, count=_count_from_text(text) or 1)
            (outputs if after_arrow else ingredients).append(item)
        else:
            cleaned = re.sub(r"^(?:矿词|矿物词典)[:：]\s*", "", text).strip()
            if cleaned and not cleaned.startswith("["):
                item = ItemRef(name=cleaned, count=_count_from_text(text) or 1, oredict=cleaned if "矿词" in text else None)
                (outputs if after_arrow else ingredients).append(item)
    if not ingredients and not outputs:
        return None

    remark = text_of(row.select_one(".item-table-remarks .remark"))
    alerts = [text_of(alert) for alert in row.select(".item-table-remarks .alert") if text_of(alert)]
    note_parts = [part for part in [remark, *alerts] if part]
    version_removed = None
    version_added = None
    for alert in row.select(".alert-table-endver"):
        version_removed = text_of(alert)
    for alert in row.select(".alert-table-startver"):
        version_added = text_of(alert)
    return RecipeRow(
        station=station,
        ingredients=ingredients,
        outputs=outputs,
        note=" ".join(note_parts) or None,
        version_added=version_added,
        version_removed=version_removed,
    )


def parse_recipes(html: str, item_id: int) -> RecipesPage:
    soup = make_soup(html)
    name_node = soup.select_one(".itemname h5")
    if name_node is None:
        raise ParseError(f"recipe page {item_id} did not contain an item name")
    recipes: list[RecipeRow] = []
    usages: list[RecipeRow] = []
    for table in soup.select("table.item-table-block"):
        classes = table.get("class") or []
        target = usages if "item-table-block-noout" in classes else recipes
        for row in table.select("tr"):
            parsed = _parse_recipe_row(row)
            if parsed is not None:
                target.append(parsed)
    return RecipesPage(
        item_id=item_id,
        item_name=text_of(name_node) or f"item-{item_id}",
        recipes=recipes,
        usages=usages,
    )
