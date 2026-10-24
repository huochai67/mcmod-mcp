"""SQLAlchemy engine/session helpers.

SQLite is the default backend. MariaDB/MySQL is supported through
``mysql+pymysql://`` URLs (``mariadb://`` is normalised by Settings).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import Integer, String, Text

from .config import Settings


class Base(DeclarativeBase):
    pass


class ApiCache(Base):
    """One cached API result, stored as canonical JSON."""

    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    payload: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    fetched_at: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ttl: Mapped[int] = mapped_column(Integer, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def create_engine_from_settings(settings: Settings) -> Engine:
    if settings.is_sqlite:
        path = settings.sqlite_path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            settings.database_url,
            echo=settings.database_echo,
            connect_args={
                "check_same_thread": False,
                "timeout": settings.sqlite_timeout,
            },
        )
        if path is not None:

            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute(f"PRAGMA busy_timeout={int(settings.sqlite_timeout * 1000)}")
                cursor.close()

        return engine

    return create_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"charset": "utf8mb4"},
    )


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def ping_database(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
        return True
    except Exception:
        return False

