"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";

import { SectionFrame } from "@/components/SectionFrame";
import { fetchThread } from "@/lib/api";
import type { Beat, ThreadDetail } from "@/lib/types";
import {
  languageLabels,
  progressColors,
  progressLabels,
  providerLabels,
  sectorLabels,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function formatDate(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function BeatItem({ beat, index }: { beat: Beat; index: number }) {
  return (
    <li className="relative pl-7">
      {/* timeline rail */}
      <span
        className="absolute left-[7px] top-5 h-full w-px bg-black/12"
        aria-hidden
      />
      <span
        className={cn(
          "absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-[#f5f4ef]",
          beat.is_status_change ? "bg-black" : "bg-black/25",
        )}
        aria-hidden
      />

      <div className="pb-7">
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-black/40">
          <span>#{index + 1}</span>
          <span aria-hidden>·</span>
          <span>{formatDate(beat.occurred_at)}</span>
          {beat.source_count > 1 ? (
            <>
              <span aria-hidden>·</span>
              <span className="text-black/55">{beat.source_count} outlets</span>
            </>
          ) : null}
        </div>

        <h3 className="text-[15px] font-semibold leading-snug tracking-tight">
          {beat.headline}
        </h3>

        {beat.summary ? (
          <p className="mt-1 line-clamp-3 text-sm leading-relaxed text-black/60">
            {beat.summary}
          </p>
        ) : null}

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {/* A status transition is the actual signal of progress. */}
          {beat.is_status_change && beat.previous_status ? (
            <span className="inline-flex items-center gap-1 border border-black bg-black px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-[#f5f4ef]">
              {progressLabels[beat.previous_status]} → {progressLabels[beat.status]}
            </span>
          ) : beat.status !== "unknown" ? (
            <span
              className={cn(
                "inline-flex items-center border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]",
                progressColors[beat.status],
              )}
            >
              {progressLabels[beat.status]}
            </span>
          ) : (
            <span className="text-[10px] uppercase tracking-[0.12em] text-black/30">
              no status change
            </span>
          )}
        </div>

        {beat.sources.length ? (
          <ul className="mt-2 space-y-0.5">
            {beat.sources.map((s) => (
              <li key={s.id} className="text-[11px] text-black/45">
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-black hover:underline"
                >
                  {s.source}
                </a>
                <span className="ml-1 text-black/25">
                  ({providerLabels[s.provider] ?? s.provider}
                  {s.language === "hi" ? ` · ${languageLabels.hi}` : ""})
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </li>
  );
}

export default function ChainDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchThread(id)
      .then((d) => active && setThread(d))
      .catch((e) => active && setError(e instanceof Error ? e.message : "Not found"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);

  const span =
    thread &&
    Math.max(
      0,
      Math.round(
        (new Date(thread.last_seen).getTime() -
          new Date(thread.first_seen).getTime()) /
          86_400_000,
      ),
    );

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 md:px-6">
      <Link
        href="/chains"
        className="text-[10px] uppercase tracking-[0.2em] text-black/45 underline hover:text-black"
      >
        ← All chains
      </Link>

      <SectionFrame className="mt-3 animate-fade-in">
        {loading ? <p className="py-10 text-sm text-black/50">Loading…</p> : null}
        {error ? <p className="py-10 text-sm text-red-700">{error}</p> : null}

        {thread ? (
          <>
            <div className="border-b border-black/10 pb-4">
              <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-black/40">
                <span>{sectorLabels[thread.sector] ?? thread.sector}</span>
                <span aria-hidden>·</span>
                <span>{thread.location}</span>
                {span ? (
                  <>
                    <span aria-hidden>·</span>
                    <span>tracked {span} days</span>
                  </>
                ) : null}
              </div>

              <h1 className="text-2xl font-semibold leading-tight tracking-tight md:text-3xl">
                {thread.title}
              </h1>

              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span
                  className={cn(
                    "inline-flex items-center border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
                    progressColors[thread.current_status],
                  )}
                >
                  Now: {progressLabels[thread.current_status]}
                </span>
                <span className="text-[10px] uppercase tracking-[0.15em] text-black/40">
                  {thread.beat_count} updates · {thread.article_count} articles
                </span>
              </div>

              {thread.keywords.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {thread.keywords.map((kw) => (
                    <Link
                      key={kw}
                      href={`/?keyword=${encodeURIComponent(kw)}`}
                      className="border border-black/12 px-1.5 py-0.5 text-[10px] tracking-[0.08em] text-black/45 hover:border-black/40 hover:text-black"
                    >
                      {kw}
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>

            <ol className="mt-6">
              {thread.beats.map((b, i) => (
                <BeatItem key={b.id} beat={b} index={i} />
              ))}
            </ol>
          </>
        ) : null}
      </SectionFrame>
    </div>
  );
}
