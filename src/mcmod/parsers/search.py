"""Parser for search.mcmod.cn result pages."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..errors import ParseError
from ..models import CategoryRef, PageInfo, SearchHit, SearchPage
from .common import (
    MOD_CATEGORY_NAMES,
    absolute_url,
    clean_text,
    make_soup,
    text_of,
)

FILTER_TO_COUNT_KEY = {
    "全部": "all",
    "模组": "mods",
    "整合包": "modpacks",
    "资料": "items",
    "教程": "tutorials",
    "作者": "authors",
    "用户": "users",
    "社群": "community",
    "服务器": "servers",
}

FILTER_VALUES = {
    "all": "0",
    "mods": "1",
    "modpacks": "2",
    "items": "3",
    "tutorials": "4",
    "authors": "5",
    "users": "6",
    "community": "7",
}


def _result_type(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if "bbs.mcmod.cn" in host:
        return "community"
    if "center.mcmod.cn" in host:
        return "user"
    if "/class/" in path:
        return "mod"
    if "/modpack/" in path:
        return "modpack"
    if "/item/" in path:
        return "item"
    if "/post/" in path:
        return "tutorial"
    if "/author/" in path:
        return "author"
    return "unknown"


def _parse_counts(soup: BeautifulSoup) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in soup.select(".search-menu-mcmod li a"):
        text = text_of(item)
        if not text:
            continue
        match = re.match(r"(.+?)\s*\(([\d,]+)\)", text)
        if not match:
            continue
        label = clean_text(match.group(1)) or ""
        key = FILTER_TO_COUNT_KEY.get(label)
        if key:
            counts[key] = int(match.group(2).replace(",", ""))
    return counts


def _parse_categories(item) -> list[CategoryRef]:
    categories: list[CategoryRef] = []
    for anchor in item.select(".class-category a[href*='/class/category/']"):
        match = re.search(r"/class/category/(\d+)-", anchor.get("href", ""))
        if not match:
            continue
        category_id = int(match.group(1))
        categories.append(
            CategoryRef(
                id=category_id,
                name=MOD_CATEGORY_NAMES.get(category_id, f"category-{category_id}"),
                url=absolute_url(anchor.get("href")),
            )
        )
    return categories


def _parse_page_info(soup: BeautifulSoup, results: list[SearchHit], requested_page: int) -> PageInfo:
    total = 0
    total_pages = 1
    page = requested_page
    container_text = text_of(soup.select_one(".search-result"))
    if container_text:
        match = re.search(r"找到约\s*([\d,]+)\s*条结果.*?共约\s*(\d+)\s*页", container_text)
        if match:
            total = int(match.group(1).replace(",", ""))
            total_pages = int(match.group(2))
    if not total:
        total = len(results)
    per_page = len(results) if results else 15
    if total_pages == 1 and total > per_page:
        total_pages = max(1, (total + per_page - 1) // per_page)
    return PageInfo(page=page, per_page=per_page, total_pages=total_pages, total=total)


def _plain_text(node) -> str | None:
    if node is None:
        return None
    value = node.get_text("", strip=True)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def parse_search(
    html: str,
    *,
    query: str,
    filter_name: str = "all",
    mold: str = "simple",
    page: int = 1,
) -> SearchPage:
    soup = make_soup(html)
    title = text_of(soup.select_one("title")) or ""
    if "出现错误" in title:
        raise ParseError("mcmod search returned an error page")
    results: list[SearchHit] = []
    for item in soup.select(".search-result-list .result-item"):
        head = item.select_one(".head > a[href]")
        if head is None:
            continue
        url = absolute_url(head.get("href")) or ""
        title_text = _plain_text(head) or ""
        snippet = _plain_text(item.select_one(".body"))
        source = snapshot = None
        for info in item.select(".foot .info"):
            text = text_of(info) or ""
            if text.startswith("快照时间"):
                snapshot = text.split(":", 1)[-1].split("：", 1)[-1].strip() or None
            elif text.startswith("来自"):
                source = text.split(":", 1)[-1].split("：", 1)[-1].strip() or None
        results.append(
            SearchHit(
                title=title_text,
                url=url,
                type=_result_type(url),  # type: ignore[arg-type]
                snippet=snippet,
                source=source,
                snapshot_date=snapshot,
                categories=_parse_categories(item),
            )
        )
    return SearchPage(
        query=query,
        filter=filter_name,
        mold=mold,
        counts=_parse_counts(soup),
        results=results,
        page_info=_parse_page_info(soup, results, page),
    )
