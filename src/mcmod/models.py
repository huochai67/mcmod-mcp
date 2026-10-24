"""Pydantic models shared by the API, MCP server, CLI and parsers."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    cache: Literal["hit", "miss", "bypass", "disabled"]
    source: str
    fetched_at: datetime
    ttl: int | None = None
    backend: str


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class PageInfo(BaseModel):
    page: int
    per_page: int
    total_pages: int
    total: int


class CategoryRef(BaseModel):
    id: int | None = None
    name: str
    description: str | None = None
    url: str | None = None
    main: bool = False


class ModStatus(BaseModel):
    kind: Literal["status", "source", "other"]
    label: str
    description: str | None = None


class NamedLink(BaseModel):
    name: str
    url: str
    description: str | None = None


class VersionRef(BaseModel):
    version: str
    url: str | None = None
    current: bool | None = None


class VersionGroup(BaseModel):
    platform: str
    total: int | None = None
    versions: list[VersionRef] = Field(default_factory=list)


class AuthorRef(BaseModel):
    id: int | None = None
    name: str
    role: str | None = None
    avatar: str | None = None
    url: str | None = None


class ItemPreview(BaseModel):
    id: int
    name: str
    icon: str | None = None
    url: str


class ModSummary(BaseModel):
    id: int
    name: str
    short_name: str | None = None
    name_en: str | None = None
    description: str | None = None
    cover: str | None = None
    url: str
    preview_items: list[ItemPreview] = Field(default_factory=list)


class ModListPage(BaseModel):
    items: list[ModSummary]
    page_info: PageInfo


class RatingDimension(BaseModel):
    name: str
    percent: float
    raw: str | None = None


class ModStats(BaseModel):
    score: float | None = None
    rank: str | None = None
    yesterday_index: int | None = None
    average_index: float | None = None
    total_views: int | None = None
    total_views_text: str | None = None
    data_fill_rate: float | None = None


class ModRating(BaseModel):
    dimensions: list[RatingDimension] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)


class ItemTypeRef(BaseModel):
    id: int
    name: str
    description: str | None = None
    count: int | None = None
    url: str


class TutorialRef(BaseModel):
    id: int
    title: str
    url: str
    views: int | None = None
    views_text: str | None = None
    age: str | None = None
    cover: str | None = None
    author: str | None = None


class RelationGroup(BaseModel):
    version: str | None = None
    relation: str
    description: str | None = None
    mods: list[ItemPreview] = Field(default_factory=list)


class ChangelogEntry(BaseModel):
    version: str
    date: str | None = None
    url: str | None = None


class ModDetail(BaseModel):
    id: int
    url: str
    name: str
    short_name: str | None = None
    name_en: str | None = None
    cover: str | None = None
    statuses: list[ModStatus] = Field(default_factory=list)
    main_category: CategoryRef | None = None
    categories: list[CategoryRef] = Field(default_factory=list)
    platforms: list[CategoryRef] = Field(default_factory=list)
    loaders: list[CategoryRef] = Field(default_factory=list)
    environment: list[str] = Field(default_factory=list)
    created: str | None = None
    created_at: str | None = None
    edit_count: int | None = None
    last_edit: str | None = None
    last_edit_at: str | None = None
    last_recommended: str | None = None
    tags: list[str] = Field(default_factory=list)
    links: list[NamedLink] = Field(default_factory=list)
    versions: list[VersionGroup] = Field(default_factory=list)
    authors: list[AuthorRef] = Field(default_factory=list)
    stats: ModStats = Field(default_factory=ModStats)
    rating: ModRating = Field(default_factory=ModRating)
    intro_html: str | None = None
    intro_text: str | None = None
    outline: list[str] = Field(default_factory=list)
    item_types: list[ItemTypeRef] = Field(default_factory=list)
    item_count: int | None = None
    menu_counts: dict[str, int] = Field(default_factory=dict)
    changelog: list[ChangelogEntry] = Field(default_factory=list)
    tutorials: list[TutorialRef] = Field(default_factory=list)
    tutorials_total: int | None = None
    discussions_total: int | None = None
    features_total: int | None = None
    relations: list[RelationGroup] = Field(default_factory=list)
    modpack_usage: int | None = None
    worldgen: int | None = None
    server_count: int | None = None
    server_install_rate: float | None = None
    download_count: int | None = None
    download_files_count: int | None = None
    downloads_url: str | None = None


class ItemRef(BaseModel):
    id: int | None = None
    name: str
    name_en: str | None = None
    url: str | None = None
    icon: str | None = None
    mod: str | None = None
    oredict: str | None = None
    count: int | None = None
    version: str | None = None
    note: str | None = None


class ItemCategory(BaseModel):
    name: str
    items: list[ItemRef] = Field(default_factory=list)


class ModItemsPage(BaseModel):
    mod_id: int
    mod_name: str
    type_id: int
    type_name: str | None = None
    categories: list[ItemCategory] = Field(default_factory=list)
    total: int
    declared_total: int | None = None
    query: str | None = None


class RecipeRow(BaseModel):
    station: ItemRef | None = None
    ingredients: list[ItemRef] = Field(default_factory=list)
    outputs: list[ItemRef] = Field(default_factory=list)
    note: str | None = None
    version_added: str | None = None
    version_removed: str | None = None


class RecipesPage(BaseModel):
    item_id: int
    item_name: str
    recipes: list[RecipeRow] = Field(default_factory=list)
    usages: list[RecipeRow] = Field(default_factory=list)


class ItemDetail(BaseModel):
    id: int
    url: str
    name: str
    name_en: str | None = None
    mod_id: int | None = None
    mod_name: str | None = None
    mod_url: str | None = None
    item_type: str | None = None
    icon: str | None = None
    command: str | None = None
    ore_dict: list[NamedLink] = Field(default_factory=list)
    properties: dict[str, str] = Field(default_factory=dict)
    description_html: str | None = None
    description_text: str | None = None
    related_items: list[ItemRef] = Field(default_factory=list)
    views: int | None = None
    created: str | None = None
    created_at: str | None = None
    last_edit: str | None = None
    last_edit_at: str | None = None
    edit_count: int | None = None
    recipes_url: str | None = None
    recipe_count: int | None = None
    usage_count: int | None = None


class DownloadFile(BaseModel):
    id: int | None = None
    filename: str
    platform: str | None = None
    loader: str | None = None
    version: str | None = None
    size: str | None = None
    size_bytes: int | None = None
    downloads: int | None = None
    likes: int | None = None
    uploaded: str | None = None
    uploaded_at: str | None = None
    md5: str | None = None
    crc32: str | None = None
    sha256: str | None = None
    suffix: str | None = None


class DownloadsPage(BaseModel):
    mod_id: int
    mod_name: str
    total: int
    files: list[DownloadFile] = Field(default_factory=list)


class ModpackSummary(BaseModel):
    id: int
    name: str
    short_name: str | None = None
    name_en: str | None = None
    description: str | None = None
    cover: str | None = None
    url: str


class ModpackListPage(BaseModel):
    items: list[ModpackSummary]
    page_info: PageInfo


class ModpackModCategory(BaseModel):
    category_id: int | None = None
    category_name: str | None = None
    mods: list[ItemRef] = Field(default_factory=list)


class ModpackDetail(BaseModel):
    id: int
    url: str
    name: str
    short_name: str | None = None
    name_en: str | None = None
    cover: str | None = None
    main_category: CategoryRef | None = None
    categories: list[CategoryRef] = Field(default_factory=list)
    pack_type: str | None = None
    loader: str | None = None
    packaging: str | None = None
    created: str | None = None
    created_at: str | None = None
    last_edit: str | None = None
    last_edit_at: str | None = None
    last_recommended: str | None = None
    edit_count: int | None = None
    tags: list[str] = Field(default_factory=list)
    links: list[NamedLink] = Field(default_factory=list)
    versions: list[VersionGroup] = Field(default_factory=list)
    team: list[AuthorRef] = Field(default_factory=list)
    stats: ModStats = Field(default_factory=ModStats)
    intro_html: str | None = None
    intro_text: str | None = None
    mods: list[ModpackModCategory] = Field(default_factory=list)
    mods_total: int | None = None
    changelog: list[ChangelogEntry] = Field(default_factory=list)
    versions_url: str | None = None


class ModpackVersionEntry(BaseModel):
    name: str
    date: str | None = None
    content_html: str | None = None
    content_text: str | None = None
    edit_url: str | None = None


class ModpackVersionsPage(BaseModel):
    modpack_id: int
    modpack_name: str
    entries: list[ModpackVersionEntry] = Field(default_factory=list)


class SearchHit(BaseModel):
    title: str
    url: str
    type: Literal["mod", "modpack", "item", "tutorial", "author", "user", "community", "unknown"]
    snippet: str | None = None
    source: str | None = None
    snapshot_date: str | None = None
    categories: list[CategoryRef] = Field(default_factory=list)


class SearchPage(BaseModel):
    query: str
    filter: str
    mold: str
    counts: dict[str, int] = Field(default_factory=dict)
    results: list[SearchHit] = Field(default_factory=list)
    page_info: PageInfo


class PostDetail(BaseModel):
    id: int
    url: str
    title: str
    author: AuthorRef | None = None
    category: str | None = None
    permission: str | None = None
    views: int | None = None
    created: str | None = None
    created_at: str | None = None
    last_edit: str | None = None
    last_edit_at: str | None = None
    edit_count: int | None = None
    license: str | None = None
    content_html: str | None = None
    content_text: str | None = None
    mod: ItemRef | None = None
    related_mods: list[ItemRef] = Field(default_factory=list)
    related_items: list[ItemRef] = Field(default_factory=list)


class AuthorDetail(BaseModel):
    id: int
    url: str
    name: str
    avatar: str | None = None
    bio_html: str | None = None
    bio_text: str | None = None
    views: int | None = None
    created: str | None = None
    last_edit: str | None = None
    edit_count: int | None = None
    members: list[AuthorRef] = Field(default_factory=list)
    partners: list[AuthorRef] = Field(default_factory=list)
    projects: list[ItemRef] = Field(default_factory=list)


class FilterOption(BaseModel):
    value: str
    label: str


class FilterGroup(BaseModel):
    id: str
    label: str
    options: list[FilterOption] = Field(default_factory=list)


class FilterOptions(BaseModel):
    kind: Literal["mod", "modpack"]
    groups: list[FilterGroup] = Field(default_factory=list)


class CacheStats(BaseModel):
    backend: str
    enabled: bool
    entries: int
    expired: int
    hits: int
    size_bytes: int | None = None
    error: str | None = None


class CacheClearResult(BaseModel):
    deleted: int


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    backend: str
    cache: CacheStats
