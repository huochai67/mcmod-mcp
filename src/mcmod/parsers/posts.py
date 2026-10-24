"""Parsers for tutorial/discussion posts and author pages."""

from __future__ import annotations

from bs4 import BeautifulSoup

from ..errors import ParseError
from ..models import AuthorDetail, AuthorRef, ItemRef, PostDetail
from .common import (
    absolute_url,
    attr_of,
    extract_id,
    image_url,
    make_soup,
    parse_int,
    text_of,
)


def _parse_meta_list(soup: BeautifulSoup) -> dict[str, object]:
    values: dict[str, object] = {}
    for li in soup.select(".common-rowlist-2 li"):
        text = text_of(li) or ""
        if text.startswith("教程权限"):
            values["permission"] = text.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif text.startswith("浏览量"):
            values["views"] = parse_int(text)
        elif text.startswith("创建日期"):
            values["created"] = text.split(":", 1)[-1].split("：", 1)[-1].strip()
            values["created_at"] = attr_of(li, "data-original-title")
        elif text.startswith("最后编辑"):
            values["last_edit"] = text.split(":", 1)[-1].split("：", 1)[-1].strip()
            values["last_edit_at"] = attr_of(li, "data-original-title")
        elif text.startswith("编辑次数"):
            values["edit_count"] = parse_int(text)
        elif text.startswith("浏览量"):
            values["views"] = parse_int(text)
    return values


def parse_post(html: str, post_id: int) -> PostDetail:
    soup = make_soup(html)
    title_node = soup.select_one(".postname h5")
    if title_node is None:
        raise ParseError(f"post page {post_id} did not contain a title")
    meta = _parse_meta_list(soup)
    author = None
    author_link = soup.select_one(".post-user-name a[href]")
    if author_link is not None:
        author = AuthorRef(
            id=extract_id(author_link.get("href")),
            name=text_of(author_link) or "",
            avatar=image_url(soup.select_one(".post-user-avatar img")),
            url=absolute_url(author_link.get("href")),
        )
    license_text = text_of(soup.select_one(".post-cc a"))
    content = soup.select_one(".post-content .text")
    content_html = content.decode_contents().strip() if content else None
    content_text = text_of(content, separator="\n")

    mod = None
    for anchor in soup.select(".common-nav a[href*='/class/']"):
        if "/category/" in (anchor.get("href") or ""):
            continue
        mod_id = extract_id(anchor.get("href"), "mod")
        if mod_id is not None:
            mod = ItemRef(id=mod_id, name=text_of(anchor) or "", url=absolute_url(anchor.get("href")))
            break

    related_mods: list[ItemRef] = []
    related_items: list[ItemRef] = []
    seen_mods: set[str] = set()
    seen_items: set[str] = set()
    for anchor in (content.select("a[href]") if content else []):
        href = anchor.get("href") or ""
        name = text_of(anchor) or attr_of(anchor, "title")
        if not name:
            continue
        if "/class/" in href and "/category/" not in href:
            mod_id = extract_id(href, "mod")
            if mod_id is None or href in seen_mods:
                continue
            seen_mods.add(href)
            related_mods.append(ItemRef(id=mod_id, name=name, url=absolute_url(href)))
        elif "/item/" in href:
            item_id = extract_id(href, "item")
            if item_id is None or href in seen_items:
                continue
            seen_items.add(href)
            related_items.append(ItemRef(id=item_id, name=name, url=absolute_url(href)))

    return PostDetail(
        id=post_id,
        url=f"https://www.mcmod.cn/post/{post_id}.html",
        title=text_of(title_node) or "",
        author=author,
        permission=meta.get("permission"),  # type: ignore[arg-type]
        views=meta.get("views"),  # type: ignore[arg-type]
        created=meta.get("created"),  # type: ignore[arg-type]
        created_at=meta.get("created_at"),  # type: ignore[arg-type]
        last_edit=meta.get("last_edit"),  # type: ignore[arg-type]
        last_edit_at=meta.get("last_edit_at"),  # type: ignore[arg-type]
        edit_count=meta.get("edit_count"),  # type: ignore[arg-type]
        license=license_text,
        content_html=content_html,
        content_text=content_text,
        mod=mod,
        related_mods=related_mods[:80],
        related_items=related_items[:80],
    )


def _parse_author_blocks(soup: BeautifulSoup, selector: str) -> list[AuthorRef]:
    authors: list[AuthorRef] = []
    for item in soup.select(selector):
        link = item.select_one(".name a[href]") or item.select_one("a[href]")
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


def parse_author(html: str, author_id: int) -> AuthorDetail:
    soup = make_soup(html)
    name_node = soup.select_one(".author-name h5")
    if name_node is None:
        raise ParseError(f"author page {author_id} did not contain a name")
    meta = _parse_meta_list(soup)
    bio = soup.select_one(".author-content .text")
    projects: list[ItemRef] = []
    for item in soup.select(".author-mods .list .block"):
        link = item.select_one(".name a[href]")
        if link is None:
            continue
        project_id = extract_id(link.get("href"))
        projects.append(
            ItemRef(
                id=project_id,
                name=text_of(link) or attr_of(link, "title") or "",
                url=absolute_url(link.get("href")),
                icon=image_url(item.select_one(".cover img"), full=True),
                mod=text_of(item.select_one(".badge")),
                note=text_of(item.select_one(".position")),
            )
        )
    return AuthorDetail(
        id=author_id,
        url=f"https://www.mcmod.cn/author/{author_id}.html",
        name=text_of(name_node) or "",
        avatar=image_url(soup.select_one(".author-user-avatar img")),
        bio_html=bio.decode_contents().strip() if bio else None,
        bio_text=text_of(bio, separator="\n"),
        views=meta.get("views"),  # type: ignore[arg-type]
        created=meta.get("created"),  # type: ignore[arg-type]
        last_edit=meta.get("last_edit"),  # type: ignore[arg-type]
        edit_count=meta.get("edit_count"),  # type: ignore[arg-type]
        members=_parse_author_blocks(soup, ".author-member .list li"),
        partners=_parse_author_blocks(soup, ".author-partner .list li"),
        projects=projects,
    )
