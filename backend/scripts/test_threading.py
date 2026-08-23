"""Validate thread matching and beat collapsing against hand-built fixtures.

    uv run python scripts/test_threading.py

Fixtures in data/demo/thread_fixtures.json encode the behaviours we need:
  * a story followed over three weeks stays in one thread
  * two providers reporting the same event on the same day collapse to one beat
  * unrelated stories do not get absorbed into that thread
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.keywords import generate_keywords, infer_progress_status  # noqa: E402
from app.services.threading import (  # noqa: E402
    BeatCandidate,
    ThreadCandidate,
    find_duplicate_beat,
    keyword_set,
    make_id,
    match_thread,
    resolve_thread_status,
)

FIXTURES = BACKEND_DIR / "data" / "demo" / "thread_fixtures.json"


def main() -> int:
    items = json.loads(FIXTURES.read_text(encoding="utf-8"))

    threads: dict[str, ThreadCandidate] = {}
    beats: dict[str, list[BeatCandidate]] = {}
    beat_statuses: dict[str, list[str]] = {}
    assignments: list[tuple[str, str, str, float, bool]] = []

    for item in items:
        title = item["title"]
        snippet = item["snippet"]
        published = datetime.fromisoformat(item["published_at"])

        keywords, sector, _ = generate_keywords(title, snippet)
        status = infer_progress_status(f"{title} {snippet}")

        match = match_thread(
            title=title,
            keywords=keywords,
            sector=sector,
            published_at=published,
            candidates=list(threads.values()),
        )

        if match.is_new_thread:
            tid = make_id(title, item["url"])
            threads[tid] = ThreadCandidate(
                id=tid, title=title, sector=sector, keywords=keywords, last_seen=published
            )
            beats[tid] = []
            beat_statuses[tid] = []
        else:
            tid = match.thread_id
            cand = threads[tid]
            cand.last_seen = max(cand.last_seen, published)
            merged = list(dict.fromkeys([*cand.keywords, *keywords]))[:12]
            cand.keywords = merged
            cand.keyword_index = keyword_set(merged)

        dup = find_duplicate_beat(
            title=title, keywords=keywords, published_at=published, beats=beats[tid]
        )

        if dup is None:
            beats[tid].append(
                BeatCandidate(
                    id=make_id(tid, title),
                    headline=title,
                    occurred_at=published,
                    keywords=keywords,
                )
            )
            beat_statuses[tid].append(status)
            action = "NEW BEAT"
        else:
            action = f"MERGED into beat '{dup.headline[:34]}...'"

        assignments.append(
            (item["_case"], tid, action, match.score, match.is_new_thread)
        )

        print(f"* {item['_case']}")
        print(f"    title    : {title[:74]}")
        print(f"    keywords : {keywords[:5]}")
        print(f"    sector={sector} status={status}")
        print(f"    thread   : {tid[:8]} ({'NEW' if match.is_new_thread else f'matched score={match.score}'})")
        print(f"    beat     : {action}")
        print()

    print("=" * 78)
    print("THREADS")
    for tid, cand in threads.items():
        statuses = beat_statuses[tid]
        print(f"  [{tid[:8]}] {cand.title[:60]}")
        print(f"      beats={len(beats[tid])} status={resolve_thread_status(statuses)} ({statuses})")
        for b in beats[tid]:
            print(f"        - {b.occurred_at.date()}  {b.headline[:62]}")
    print()

    # --- assertions -------------------------------------------------------
    failures: list[str] = []

    by_case = {c: (tid, action, new) for c, tid, action, _, new in assignments}

    def tid_of(fragment: str) -> str:
        for case, (tid, _, _) in by_case.items():
            if fragment in case:
                return tid
        raise KeyError(fragment)

    chain1 = tid_of("chain-1 / day 0 - story breaks")

    if tid_of("SYNDICATION") != chain1:
        failures.append("syndicated duplicate did not join the original thread")
    if "MERGED" not in by_case["chain-1 / day 0 - SYNDICATION, must collapse into same beat"][1]:
        failures.append("syndicated duplicate created a second beat instead of merging")

    if tid_of("day 7") != chain1:
        failures.append("day-7 follow-up did not join chain-1")
    if "NEW BEAT" not in by_case["chain-1 / day 7 - NEW development, same thread"][1]:
        failures.append("day-7 development was wrongly merged into an existing beat")

    if tid_of("day 21") != chain1:
        failures.append("day-21 development did not join chain-1")

    if tid_of("unrelated crime") == chain1:
        failures.append("unrelated crime story was absorbed into chain-1")
    if tid_of("separate infra story") == chain1:
        failures.append("metro story was absorbed into chain-1")

    metro = tid_of("separate infra story")
    if tid_of("metro follow-up") != metro:
        failures.append("metro follow-up did not join the metro thread")

    chain1_beats = len(beats[chain1])
    if chain1_beats != 3:
        failures.append(f"chain-1 should have 3 beats (4 articles, 1 syndicated), got {chain1_beats}")

    if resolve_thread_status(beat_statuses[chain1]) != "stalled":
        failures.append(
            f"chain-1 should end 'stalled', got '{resolve_thread_status(beat_statuses[chain1])}'"
        )

    print("=" * 78)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL THREADING ASSERTIONS PASSED")
    print(f"  chain-1: 4 articles -> {chain1_beats} beats (syndication collapsed)")
    print(f"  threads formed: {len(threads)} (expected 3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
