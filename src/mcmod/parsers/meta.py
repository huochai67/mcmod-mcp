"""Parser for the filter blocks shown on mod/modpack list pages."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..models import FilterGroup, FilterOption, FilterOptions
from .common import (
    MOD_CATEGORY_NAMES,
    MODPACK_CATEGORY_NAMES,
    make_soup,
    text_of,
)

GROUP_HINTS = [
    ("元素", "category"),
    ("版本", "mcver"),
    ("平台", "platform"),
    ("运作方式", "api"),
    ("状态", "status"),
    ("运行环境", "mode"),
    ("整合包类型", "mold"),
    ("打包", "pack"),
    ("关键词", "key"),
    ("排序", "sort"),
]


def _group_id(title: str, classes: list[str], kind: str) -> str:
    for hint, value in GROUP_HINTS:
        if hint in title:
            return value
    for name in classes:
        if name in {"category", "mcver", "auto"}:
            return name
    if kind == "modpack" and "类型" in title:
        return "mold"
    return re.sub(r"\W+", "_", title).strip("_") or "filter"


def _extract_url(node) -> str | None:
    href = node.get("href")
    if href and not href.startswith("javascript:"):
        return href
    onclick = node.get("onclick") or ""
    match = re.search(r"['\"]([^'\"]*\.html\?[^'\"]+)['\"]", onclick)
    if match:
        return match.group(1)
    return None


def _option_value(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key, values in query.items():
        if values:
            return key, values[0]
    return None


def parse_filters(html: str, kind: str) -> FilterOptions:
    soup = make_soup(html)
    names = MODPACK_CATEGORY_NAMES if kind == "modpack" else MOD_CATEGORY_NAMES
    groups: list[FilterGroup] = []
    for block in soup.select(".modlist-filter-block"):
        title_text = text_of(block.select_one(".title")) or ""
        title = title_text.rstrip(":：").strip()
        classes = block.get("class") or []
        group_id = _group_id(title, classes, kind)
        options: list[FilterOption] = []
        seen: set[str] = set()
        has_all = False
        for li in block.select("ul > li"):
            text = text_of(li)
            if text == "全部":
                has_all = True
            anchor = li.select_one("a")
            if anchor is None:
                continue
            url = _extract_url(anchor)
            if not url:
                continue
            parsed = _option_value(url)
            if parsed is None:
                continue
            key, value = parsed
            if key not in {"category", "mcver", "platform", "api", "status", "mode", "mold", "pack", "sort", "key"}:
                continue
            label = text_of(anchor) or ""
            if not label and group_id == "category" and value.isdigit():
                label = names.get(int(value), "")
            if not label:
                label = value
            if group_id == "category" and value.isdigit():
                label = names.get(int(value), label)
            if group_id == "sort":
                value = {"createtime": "created", "lastedittime": "edited"}.get(value, value)
            if value in seen:
                continue
            seen.add(value)
            options.append(FilterOption(value=value, label=label))
        if has_all and options:
            options.insert(0, FilterOption(value="", label="全部"))
        if group_id == "sort":
            options.insert(0, FilterOption(value="", label="默认排序"))
        if options:
            groups.append(FilterGroup(id=group_id, label=title, options=options))
    return FilterOptions(kind=kind, groups=groups)  # type: ignore[arg-type]
