"use client";

import Link from "next/link";
import { useState } from "react";

import { trackEvent } from "@/lib/api";
import type { NewsArticle } from "@/lib/types";
import { sectorLabels } from "@/lib/types";
import { ProgressBadge } from "./ProgressBadge";
import { TagPill } from "./TagPill";

export function TrackEventButton({ article }: { article: NewsArticle }) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleTrack() {
    setLoading(true);
    setMessage(null);
    try {
      const event = await trackEvent({
        title: article.title,
        snippet: article.snippet,
        url: article.url,
        sector: article.sector,
      });
      setMessage(`Tracking · ${event.keywords.slice(0, 3).join(", ")}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to track");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={handleTrack}
        disabled={loading}
        className="border border-black/20 px-2 py-1 text-[10px] uppercase tracking-[0.15em] hover:border-black hover:bg-black hover:text-[#f5f4ef] disabled:opacity-50"
      >
        {loading ? "Generating keywords..." : "Track this event"}
      </button>
      {message ? <p className="text-[10px] text-black/50">{message}</p> : null}
    </div>
  );
}

export function ArticleCard({ article, featured = false }: { article: NewsArticle; featured?: boolean }) {
  return (
    <article
      className={`corner-markers break-inside-avoid border border-black/10 bg-white/30 p-4 ${featured ? "md:col-span-2" : ""}`}
    >
      <span className="corner-bl" aria-hidden />
      <span className="corner-br" aria-hidden />
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {article.sector ? <TagPill tag={sectorLabels[article.sector]} /> : null}
        {article.status && ["planned", "ongoing", "delayed", "stalled", "completed", "unknown"].includes(article.status) ? (
          <ProgressBadge status={article.status as import("@/lib/types").ProgressStatus} />
        ) : null}
        <span className="text-[10px] uppercase tracking-[0.15em] text-black/40">{article.source}</span>
      </div>
      <h3 className={`font-semibold leading-snug ${featured ? "text-2xl md:text-3xl" : "text-base md:text-lg"}`}>
        <Link href={article.url} target="_blank" rel="noreferrer" className="hover:underline">
          {article.title}
        </Link>
      </h3>
      {article.snippet ? <p className="mt-2 text-sm leading-relaxed text-black/65 line-clamp-3">{article.snippet}</p> : null}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-black/10 pt-3">
        <p className="text-[10px] uppercase tracking-[0.15em] text-black/40">
          {article.published_at ? new Date(article.published_at).toLocaleString() : "Latest"}
        </p>
        <TrackEventButton article={article} />
      </div>
    </article>
  );
}
