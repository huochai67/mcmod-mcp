"""Shared HTML parsing helpers for mcmod.cn pages."""

from __future__ import annotations

import base64
import html as html_module
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://www.mcmod.cn"
SEARCH_URL = "https://search.mcmod.cn"

MOD_CATEGORY_NAMES = {
    1: "科技",
    2: "魔法",
    3: "冒险",
    4: "农业",
    5: "装饰",
    6: "安全",
    7: "LIB",
    8: "资源",
    9: "世界",
    10: "群系",
    11: "生物",
    12: "能源",
    13: "存储",
    14: "物流",
    15: "道具",
    16: "红石",
    17: "食物",
    18: "模型",
    19: "指南",
    20: "破坏",
    21: "魔改",
    22: "Meme",
    23: "实用",
    24: "辅助",
    25: "中式",
    26: "日式",
    27: "西式",
    28: "恐怖",
    29: "建材",
    30: "生存",
    31: "指令",
    32: "优化",
    33: "国创",
    34: "关卡",
    35: "结构",
}

MODPACK_CATEGORY_NAMES = {
    1: "科技",
    2: "魔法",
    3: "冒险",
    4: "建筑",
    5: "地图",
    6: "任务",
    7: "硬核",
    8: "休闲",
    9: "大型",
    10: "轻量",
    11: "剧情",
    12: "水槽",
    13: "空岛",
    14: "PvP",
    15: "国创",
}

LOADER_NAMES = {
    1: "Forge",
    2: "Fabric",
    3: "Rift",
    4: "LiteLoader",
    5: "数据包",
    6: "命令方块",
    7: "文件覆盖",
    8: "行为包",
    11: "Quilt",
    13: "NeoForge",
    14: "NilLoader",
    15: "Cleanroom",
    16: "内容包",
    17: "JavaAgent",
}

_PERCENT_RE = re.compile(r"([\d.]+)\s*%")
_INT_RE = re.compile(r"(\d[\d,]*)")
_ID_RE = re.compile(r"/(\d+)(?:\.html)?(?:/|$)")


def make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", html_module.unescape(value)).strip()
    return text or None


def text_of(node, separator: str = " ") -> str | None:
    if node is None:
        return None
    return clean_text(node.get_text(separator, strip=True))


def attr_of(node, name: str) -> str | None:
    if node is None:
        return None
    value = node.get(name)
    if isinstance(value, list):
        value = " ".join(value)
    return clean_text(value)


def absolute_url(href: str | None, *, base: str = BASE_URL) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("javascript:") or href.startswith("#"):
        return None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base + "/", href)


def decode_mcmod_link(href: str | None) -> str | None:
    """Resolve ``link.mcmod.cn/target/<base64>`` redirects to the real URL."""

    if not href:
        return None
    absolute = absolute_url(href)
    if not absolute:
        return None
    marker = "link.mcmod.cn/target/"
    if marker not in absolute:
        return absolute
    encoded = absolute.split(marker, 1)[1].split("?", 1)[0]
    encoded += "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(encoded, altchars=b"-_").decode("utf-8")
        if decoded.startswith("http://") or decoded.startswith("https://"):
            return decoded
    except Exception:
        pass
    return absolute


def extract_id(value: str | int | None, kind: str = "id") -> int | None:
    if isinstance(value, int):
        return value
    if not value:
        return None
    value = str(value)
    if value.isdigit():
        return int(value)
    if kind == "mod":
        patterns = [r"/class/(\d+)\.html", r"/class/(\d+)(?:[/?#]|$)"]
    elif kind == "item":
        patterns = [r"/item/(\d+)\.html", r"/item/(\d+)(?:[/?#]|$)"]
    elif kind == "modpack":
        patterns = [r"/modpack/(\d+)\.html", r"/modpack/(\d+)(?:[/?#]|$)"]
    elif kind == "post":
        patterns = [r"/post/(\d+)\.html", r"/post/(\d+)(?:[/?#]|$)"]
    elif kind == "author":
        patterns = [r"/author/(\d+)\.html", r"/author/(\d+)(?:[/?#]|$)"]
    else:
        patterns = [r"/(\d+)(?:\.html)?(?:[/?#]|$)"]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return int(match.group(1))
    return None


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = _INT_RE.search(value.replace(",", ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"([\d.]+)", value.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_compact_number(value: str | None) -> int | None:
    """Parse Chinese compact numbers such as ``2444.96万`` or ``1.06万``."""

    if not value:
        return None
    text = value.replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)(亿|万|千|k|K|M)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    multiplier = {"亿": 100_000_000, "万": 10_000, "千": 1_000, "k": 1_000, "K": 1_000, "M": 1_000_000}
    if unit:
        number *= multiplier[unit]
    return int(number)


def parse_percent(value: str | None) -> float | None:
    if not value:
        return None
    match = _PERCENT_RE.search(value)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return parse_float(value)


def tooltip_parts(node) -> tuple[str | None, str | None]:
    """Parse a ``data-original-title`` item tooltip into (name, mod)."""

    if node is None:
        return None, None
    raw = node.get("data-original-title") or node.get("title") or ""
    if not raw:
        return None, None
    fragment = make_soup(raw)
    first = fragment.select_one(".item-table-hover-t1")
    second = fragment.select_one(".item-table-hover-t2")
    name = clean_text(first.get_text(" ", strip=True)) if first else None
    mod = clean_text(second.get_text(" ", strip=True)) if second else None
    if name is None:
        name = clean_text(fragment.get_text(" ", strip=True))
    return name, mod


def image_url(node, *, full: bool = False) -> str | None:
    if node is None:
        return None
    src = node.get("src") or node.get("data-src") or node.get("data-original")
    if not src:
        return None
    if src.startswith("data:"):
        return None
    if full:
        src = re.sub(r"@\d+x\d+\.(?:jpg|jpeg|png|webp)$", "", src)
    return absolute_url(src)


def find_field(container, label: str) -> str | None:
    """Find ``label: value`` inside a block of label/value pairs."""

    if container is None:
        return None
    for node in container.find_all(["li", "td", "p", "span", "div"]):
        text = text_of(node, separator="")
        if not text or not text.startswith(label):
            continue
        value = text[len(label) :].lstrip(":： ").strip()
        if value:
            return value
    return None


def parse_labeled_li(li) -> tuple[str | None, list]:
    """Return label and direct anchor children for ``<li>Label: ...</li>``."""

    if li is None:
        return None, []
    text = text_of(li)
    if not text:
        return None, []
    label = re.split(r"[:：]", text, maxsplit=1)[0].strip()
    return label, li.find_all("a", href=True)


def parse_page_info(soup, count: int, requested_page: int):
    """Parse the common ``当前 x / y 页，共计 n 条`` pagination block."""

    from ..models import PageInfo

    page = requested_page
    total_pages = 1
    total = count
    active = soup.select_one(".pagination .page-item.active")
    if active:
        parsed = parse_int(text_of(active))
        if parsed:
            page = parsed
    pagination_text = text_of(soup.select_one(".pagination"))
    if pagination_text:
        match = re.search(r"当前\s*(\d+)\s*/\s*(\d+)\s*页.*?共计\s*([\d,]+)\s*条", pagination_text)
        if match:
            page = int(match.group(1))
            total_pages = int(match.group(2))
            total = int(match.group(3).replace(",", ""))
    if total_pages == 1 and total > count:
        total_pages = max(1, (total + count - 1) // count) if count else 1
    return PageInfo(page=page, per_page=count, total_pages=total_pages, total=total)



def label_value(text: str, label: str) -> str | None:
    if not text:
        return None
    match = re.search(re.escape(label) + r"\s*[:：]\s*([^:：]+)", text)
    return clean_text(match.group(1)) if match else None


def inline_anchor_groups(li) -> list[list[tuple[str, str | None]]]:
    """Split anchors in a metadata ``li`` by comma boundaries.

    The class info rows use ``支持平台: a, a`` and ``运作方式: a, a``.
    Returning groups is unnecessary for those fields; a flat list is used
    instead by the parser, so this helper is intentionally simple.
    """

    return [[(text_of(a) or "", a.get("href")) for a in li.find_all("a", href=True)]]
