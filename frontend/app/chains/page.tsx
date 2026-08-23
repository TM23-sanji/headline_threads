"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";

import { SectionFrame } from "@/components/SectionFrame";
import { fetchThreads } from "@/lib/api";
import type { Thread } from "@/lib/types";
import {
  languageLabels,
  progressColors,
  progressLabels,
  sectorLabels,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function ThreadRow({ thread }: { thread: Thread }) {
  const first = new Date(thread.first_seen);
  const last = new Date(thread.last_seen);
  const days = Math.max(
    0,
    Math.round((last.getTime() - first.getTime()) / 86_400_000),
  );

  return (
    <Link
      href={`/chains/${thread.id}`}
      className="block border-b border-black/10 py-4 transition-colors hover:bg-black/[0.02]"
    >
      <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-black/40">
        <span>{sectorLabels[thread.sector] ?? thread.sector}</span>
        <span aria-hidden>·</span>
        <span>
          {thread.beat_count} {thread.beat_count === 1 ? "update" : "updates"}
        </span>
        <span aria-hidden>·</span>
        <span>{thread.article_count} articles</span>
        {days > 0 ? (
          <>
            <span aria-hidden>·</span>
            <span>over {days}d</span>
          </>
        ) : null}
        {thread.language === "hi" ? (
          <span className="border border-black/15 px-1 normal-case text-black/50">
            {languageLabels.hi}
          </span>
        ) : null}
      </div>

      <h3 className="text-base font-semibold leading-snug tracking-tight">{thread.title}</h3>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span
          className={cn(
            "inline-flex items-center border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
            progressColors[thread.current_status],
          )}
        >
          {progressLabels[thread.current_status]}
        </span>
        {thread.keywords.slice(0, 4).map((kw) => (
          <span
            key={kw}
            className="border border-black/12 px-1.5 py-0.5 text-[10px] tracking-[0.08em] text-black/45"
          >
            {kw}
          </span>
        ))}
      </div>
    </Link>
  );
}

function ChainsContent() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [chainsOnly, setChainsOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchThreads({ chains_only: chainsOnly })
      .then((d) => active && setThreads(d.threads))
      .catch((e) => active && setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [chainsOnly]);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 md:px-6">
      <SectionFrame className="animate-fade-in">
        <div className="border-b border-black/10 pb-4">
          <p className="text-[10px] uppercase tracking-[0.35em] text-black/45">
            Event tracking
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
            STORY CHAINS
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-black/55">
            Articles are grouped into chains by shared keywords. Reports of the same
            development from different outlets are merged into a single update, so the
            timeline shows real progress rather than repetition.
          </p>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <button
            type="button"
            onClick={() => setChainsOnly(true)}
            className={cn(
              "border px-3 py-1 text-[10px] uppercase tracking-[0.15em]",
              chainsOnly
                ? "border-black bg-black text-[#f5f4ef]"
                : "border-black/15 text-black/60 hover:border-black/40",
            )}
          >
            Developing only
          </button>
          <button
            type="button"
            onClick={() => setChainsOnly(false)}
            className={cn(
              "border px-3 py-1 text-[10px] uppercase tracking-[0.15em]",
              !chainsOnly
                ? "border-black bg-black text-[#f5f4ef]"
                : "border-black/15 text-black/60 hover:border-black/40",
            )}
          >
            All stories
          </button>
        </div>

        {loading ? <p className="py-10 text-sm text-black/50">Loading…</p> : null}
        {error ? <p className="py-10 text-sm text-red-700">{error}</p> : null}

        {!loading && !error && threads.length === 0 ? (
          <div className="py-14 text-center">
            <p className="text-sm text-black/60">No story chains yet.</p>
            <p className="mt-2 text-xs text-black/45">
              Chains form as the same story is reported again over time. Run the ingest
              script daily to build history.
            </p>
          </div>
        ) : null}

        <div className="mt-2">
          {threads.map((t) => (
            <ThreadRow key={t.id} thread={t} />
          ))}
        </div>
      </SectionFrame>
    </div>
  );
}

export default function ChainsPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-black/50">Loading…</p>}>
      <ChainsContent />
    </Suspense>
  );
}
