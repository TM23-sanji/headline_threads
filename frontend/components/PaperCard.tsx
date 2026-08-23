"use client";

import Link from "next/link";

import type { PaperArticle } from "@/lib/types";
import { languageLabels, progressColors, progressLabels } from "@/lib/types";
import { useFacets } from "@/lib/useFacets";
import { cn } from "@/lib/utils";

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PaperCard({
  article,
  featured = false,
}: {
  article: PaperArticle;
  featured?: boolean;
}) {
  const { toggle, isActive } = useFacets();
  const published = formatDate(article.published_at);
  const isChain = Boolean(article.thread_id) && article.thread_beat_count > 1;

  return (
    <article
      className={cn(
        "group break-inside-avoid border-b border-black/10 pb-4",
        featured && "border-b-0 pb-0",
      )}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-black/40">
        <span>{article.source}</span>
        {published ? <span aria-hidden>·</span> : null}
        {published ? <span>{published}</span> : null}
        {article.language === "hi" ? (
          <span className="border border-black/15 px-1 text-black/50">
            {languageLabels.hi}
          </span>
        ) : null}
      </div>

      <a href={article.url} target="_blank" rel="noopener noreferrer">
        <h3
          className={cn(
            "font-semibold leading-snug tracking-tight hover:underline",
            featured ? "text-2xl md:text-3xl" : "text-base",
          )}
        >
          {article.title}
        </h3>
      </a>

      {article.snippet ? (
        <p
          className={cn(
            "mt-1.5 text-sm leading-relaxed text-black/60",
            featured ? "line-clamp-4" : "line-clamp-3",
          )}
        >
          {article.snippet}
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {/* Status is only shown when actually inferred. With ~400 chars of
            text per article, "unknown" is common and claiming otherwise
            would be misleading. */}
        {article.progress_status !== "unknown" ? (
          <span
            className={cn(
              "inline-flex items-center border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
              progressColors[article.progress_status],
            )}
          >
            {progressLabels[article.progress_status]}
          </span>
        ) : null}

        {isChain ? (
          <Link
            href={`/chains/${article.thread_id}`}
            className="inline-flex items-center gap-1 border border-black/70 bg-black/5 px-2 py-0.5 text-[10px] uppercase tracking-[0.15em] text-black hover:bg-black hover:text-[#f5f4ef]"
          >
            Chain · {article.thread_beat_count} updates
          </Link>
        ) : null}
      </div>

      {article.keywords.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {article.keywords.slice(0, 5).map((kw) => (
            <button
              key={kw}
              type="button"
              onClick={() => toggle("keyword", kw)}
              title={`Filter by "${kw}"`}
              className={cn(
                "border px-1.5 py-0.5 text-[10px] tracking-[0.08em] transition-colors",
                isActive("keyword", kw)
                  ? "border-black bg-black text-[#f5f4ef]"
                  : "border-black/12 text-black/45 hover:border-black/40 hover:text-black/75",
              )}
            >
              {kw}
            </button>
          ))}
        </div>
      ) : null}
    </article>
  );
}
