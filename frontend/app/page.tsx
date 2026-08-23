"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { FacetSidebar } from "@/components/FacetSidebar";
import { PaperCard } from "@/components/PaperCard";
import { SectionFrame } from "@/components/SectionFrame";
import { fetchPaper } from "@/lib/api";
import type { PaperResponse } from "@/lib/types";
import { useFacets } from "@/lib/useFacets";

function LoadingDots() {
  return (
    <div className="flex items-center gap-1 py-12">
      <span className="h-2 w-2 rounded-full bg-black/70 animate-pulse-dot" />
      <span className="h-2 w-2 rounded-full bg-black/70 animate-pulse-dot-delay-1" />
      <span className="h-2 w-2 rounded-full bg-black/70 animate-pulse-dot-delay-2" />
    </div>
  );
}

function Masthead({ date }: { date?: string }) {
  return (
    <div className="border-b border-black/10 pb-4 text-center">
      <p className="text-[10px] uppercase tracking-[0.35em] text-black/45">
        Madhya Pradesh · Civic Intelligence Edition
      </p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight md:text-6xl">THE MP GAZETTE</h1>
      <p className="mt-2 text-sm text-black/55">{date ?? "Loading edition…"}</p>
      <div className="mt-3 overflow-hidden border-y border-black/10 py-2">
        <div className="animate-marquee whitespace-nowrap text-[10px] uppercase tracking-[0.25em] text-black/45">
          Bhopal · Infrastructure · Delays · BMC · Lakes · Transport · Stories tracked as chains ·
          Bhopal · Infrastructure · Delays · BMC · Lakes · Transport · Stories tracked as chains ·
        </div>
      </div>
    </div>
  );
}

function HomeContent() {
  const { selected, clear, activeCount } = useFacets();
  const [paper, setPaper] = useState<PaperResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // `selected` is derived from the URL, so this refetches on every filter change.
  const key = useMemo(() => JSON.stringify(selected), [selected]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    fetchPaper(selected)
      .then((data) => active && setPaper(data))
      .catch((err) =>
        active && setError(err instanceof Error ? err.message : "Failed to load edition"),
      )
      .finally(() => active && setLoading(false));

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const lead = paper?.sections[0]?.articles[0];
  const isEmpty = !loading && paper && paper.total === 0;

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 md:grid-cols-[210px_1fr] md:px-6">
      <FacetSidebar
        facets={paper?.facets ?? {}}
        total={paper?.total ?? 0}
        loading={loading}
      />

      <div className="space-y-6">
        <SectionFrame className="animate-fade-in">
          <Masthead date={paper?.date} />

          {loading ? <LoadingDots /> : null}

          {error ? (
            <div className="py-8">
              <p className="text-sm text-red-700">{error}</p>
              <p className="mt-1 text-xs text-black/50">
                Is the API running on {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}?
              </p>
            </div>
          ) : null}

          {isEmpty ? (
            <div className="py-16 text-center">
              <p className="text-sm text-black/60">No stories match these filters.</p>
              {activeCount > 0 ? (
                <button
                  type="button"
                  onClick={clear}
                  className="mt-3 border border-black px-3 py-1 text-[10px] uppercase tracking-[0.2em] hover:bg-black hover:text-[#f5f4ef]"
                >
                  Clear all filters
                </button>
              ) : (
                <p className="mt-2 text-xs text-black/45">
                  The archive is empty — run the ingest script to populate it.
                </p>
              )}
            </div>
          ) : null}

          {!loading && paper && paper.total > 0 ? (
            <>
              {lead ? (
                <div className="mt-6 border-b border-black/10 pb-6">
                  <p className="mb-2 text-[10px] uppercase tracking-[0.25em] text-black/45">
                    Lead Story
                  </p>
                  <PaperCard article={lead} featured />
                </div>
              ) : null}

              {paper.sections.map((section, sectionIndex) => {
                const articles =
                  sectionIndex === 0 ? section.articles.slice(1) : section.articles;
                if (!articles.length) return null;

                return (
                  <section key={section.sector} className="mt-8 border-t border-black/10 pt-5">
                    <div className="mb-3 flex items-baseline justify-between">
                      <h2 className="text-sm font-semibold uppercase tracking-[0.2em]">
                        {section.label}
                      </h2>
                      <span className="text-[10px] uppercase tracking-[0.15em] text-black/40">
                        {section.articles.length}{" "}
                        {section.articles.length === 1 ? "story" : "stories"}
                      </span>
                    </div>
                    <div className="newspaper-columns space-y-4">
                      {articles.map((article) => (
                        <PaperCard key={article.id} article={article} />
                      ))}
                    </div>
                  </section>
                );
              })}
            </>
          ) : null}
        </SectionFrame>

        <p className="text-center text-[10px] uppercase tracking-[0.2em] text-black/35">
          <Link href="/chains" className="underline hover:text-black">
            View story chains →
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<LoadingDots />}>
      <HomeContent />
    </Suspense>
  );
}
