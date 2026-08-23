"""Async SQLAlchemy engine + session wiring for Neon Postgres.

Two Neon-specific details are handled here:

1. Neon issues connection strings containing `sslmode` and `channel_binding`
   query parameters. asyncpg does not accept either as a DSN argument and
   raises TypeError, so they are stripped and TLS is supplied via connect_args.
2. The target database is shared with another application (public already
   contains conversations/messages/eval_runs/...), so every table created here
   lives in a dedicated `bhopal` schema to guarantee no collisions.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

SCHEMA = "bhopal"

# Params Neon includes that asyncpg rejects.
_UNSUPPORTED_QUERY_KEYS = {"sslmode", "channel_binding", "options"}


def build_async_url(raw: str) -> str:
    """Normalize a Neon URL into an asyncpg-compatible SQLAlchemy URL."""
    if not raw:
        raise ValueError("DATABASE_URL is not set")

    url = raw.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    kept = [
        pair
        for pair in parts.query.split("&")
        if pair and pair.split("=", 1)[0].lower() not in _UNSUPPORTED_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment))


class Base(DeclarativeBase):
    """Declarative base; all models are confined to the `bhopal` schema."""

    __table_args__ = {"schema": SCHEMA}


def _ssl_context() -> ssl.SSLContext:
    # Neon requires TLS. Certificate verification stays on.
    return ssl.create_default_context()


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            build_async_url(settings.database_url),
            echo=False,
            pool_pre_ping=True,   # Neon scales to zero; drop dead connections
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
            connect_args={"ssl": _ssl_context(), "timeout": 30},
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
