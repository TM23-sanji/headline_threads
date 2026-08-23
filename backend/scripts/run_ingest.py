"""Run an ingest cycle into Neon.

    uv run python scripts/run_ingest.py                 # live: hits all 3 APIs
    uv run python scripts/run_ingest.py --fixtures      # replay captured data
    uv run python scripts/run_ingest.py --threads       # replay thread fixtures
    uv run python scripts/run_ingest.py --show          # print DB state only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import dispose_engine, get_sessionmaker  # noqa: E402
from app.db.models import Article, BeatArticle, StoryThread, ThreadBeat  # noqa: E402
from app.models import NewsArticle  # noqa: E402
from app.services.ingest import ingest  # noqa: E402
from app.services.news_fetchers import _article_id  # noqa: E402

DEMO = BACKEND_DIR / "data" / "demo"


def load_fixture_articles(path: Path) -> list[NewsArticle]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[NewsArticle] = []
    for item in raw:
        item = {k: v for k, v in item.items() if not k.startswith("_")}
        item.setdefault("id", _article_id(item["title"], item["url"]))
        item.setdefault("snippet", "")
        out.append(NewsArticle(**item))
    return out


async def show(session) -> None:
    n_art = await session.scalar(select(func.count()).select_from(Article))
    n_thr = await session.scalar(select(func.count()).select_from(StoryThread))
    n_beat = await session.scalar(select(func.count()).select_from(ThreadBeat))
    n_ba = await session.scalar(select(func.count()).select_from(BeatArticle))
    print(f"\nDB: articles={n_art} threads={n_thr} beats={n_beat} beat_articles={n_ba}")

    threads = (
        await session.execute(
            select(StoryThread).order_by(StoryThread.last_seen.desc()).limit(12)
        )
    ).scalars().all()

    print("\nTHREADS (most recent first)")
    for t in threads:
        flag = " [CHAIN]" if t.beat_count > 1 else ""
        print(f"\n  [{t.id[:8]}] {t.title[:66]}{flag}")
        print(
            f"      sector={t.sector} lang={t.language} status={t.current_status} "
            f"beats={t.beat_count} articles={t.article_count}"
        )
        beats = (
            await session.execute(
                select(ThreadBeat)
                .where(ThreadBeat.thread_id == t.id)
                .order_by(ThreadBeat.occurred_at)
            )
        ).scalars().all()
        for b in beats:
            change = f"  {b.previous_status} -> {b.status}" if b.is_status_change else ""
            src = f" ({b.source_count} sources)" if b.source_count > 1 else ""
            print(f"        {b.occurred_at.date()}  [{b.status:9s}]{src} {b.headline[:52]}{change}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="replay demo_articles.json")
    ap.add_argument("--threads", action="store_true", help="replay thread_fixtures.json")
    ap.add_argument("--show", action="store_true", help="print DB state and exit")
    args = ap.parse_args()

    Session = get_sessionmaker()

    async with Session() as session:
        if args.show:
            await show(session)
            await dispose_engine()
            return 0

        articles = None
        if args.threads:
            articles = load_fixture_articles(DEMO / "thread_fixtures.json")
            print(f"replaying {len(articles)} thread fixtures")
        elif args.fixtures:
            articles = load_fixture_articles(DEMO / "demo_articles.json")
            print(f"replaying {len(articles)} captured articles")
        else:
            print("live ingest: querying all three providers")

        result = await ingest(session, articles=articles)

        print("\nINGEST RESULT")
        for k, v in result.as_dict().items():
            print(f"  {k:18s} {v}")

        await show(session)

    await dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
