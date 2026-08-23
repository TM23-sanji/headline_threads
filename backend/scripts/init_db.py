"""Create the `bhopal` schema, extensions and tables in Neon.

    uv run python scripts/init_db.py          # create if missing
    uv run python scripts/init_db.py --drop   # DESTRUCTIVE: recreate schema

Everything is confined to the `bhopal` schema because the target Neon database
is shared with another application (public holds conversations/messages/...).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import models  # noqa: F401,E402  (registers tables on Base.metadata)
from app.db.base import SCHEMA, Base, dispose_engine, get_engine  # noqa: E402

EXTENSIONS = ("pg_trgm", "unaccent", "btree_gin")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--drop",
        action="store_true",
        help=f"drop and recreate the {SCHEMA} schema (destroys all archived news)",
    )
    args = parser.parse_args()

    engine = get_engine()

    async with engine.begin() as conn:
        existing = await conn.scalar(
            text("select 1 from information_schema.schemata where schema_name = :s"),
            {"s": SCHEMA},
        )

        if args.drop:
            if existing:
                count = await conn.scalar(
                    text(
                        "select count(*) from information_schema.tables "
                        "where table_schema = :s"
                    ),
                    {"s": SCHEMA},
                )
                print(f"!! dropping schema {SCHEMA} ({count} tables) - archived news is lost")
            await conn.execute(text(f"drop schema if exists {SCHEMA} cascade"))

        await conn.execute(text(f"create schema if not exists {SCHEMA}"))

        for ext in EXTENSIONS:
            try:
                await conn.execute(text(f"create extension if not exists {ext}"))
                print(f"  extension ok: {ext}")
            except Exception as exc:  # noqa: BLE001
                print(f"  extension SKIPPED: {ext} ({exc})")

        await conn.run_sync(Base.metadata.create_all)

    # Trigram indexes for keyword/title matching (not expressible via ORM).
    async with engine.begin() as conn:
        for name, stmt in {
            "ix_articles_title_trgm": (
                f"create index if not exists ix_articles_title_trgm "
                f"on {SCHEMA}.articles using gin (title gin_trgm_ops)"
            ),
            "ix_article_keywords_trgm": (
                f"create index if not exists ix_article_keywords_trgm "
                f"on {SCHEMA}.article_keywords using gin (keyword gin_trgm_ops)"
            ),
            "ix_story_threads_keywords": (
                f"create index if not exists ix_story_threads_keywords "
                f"on {SCHEMA}.story_threads using gin (keywords)"
            ),
        }.items():
            await conn.execute(text(stmt))
            print(f"  index ok: {name}")

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = :s order by table_name"
            ),
            {"s": SCHEMA},
        )
        print(f"\ntables in {SCHEMA}:")
        for (name,) in rows:
            n = await conn.scalar(text(f"select count(*) from {SCHEMA}.{name}"))
            print(f"    {name:20s} rows={n}")

    # Confirm the other application's tables are untouched.
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' order by table_name"
            )
        )
        print("\npublic schema (other app, untouched):")
        print("   ", [r[0] for r in rows] or "(none)")

    await dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
