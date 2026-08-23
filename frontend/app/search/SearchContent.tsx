"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { PaperCard } from "@/components/PaperCard";
import { SectionFrame } from "@/components/SectionFrame";
import { fetchPaper } from "@/lib/api";
import type { PaperArticle, Sector } from "@/lib/types";
import { sectorLabels } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Archive search over the Postgres-backed paper endpoint.
 *
 * Previously this called `/api/news`, which fetched from all three provider
 * APIs on every keystroke and burned ~100-200/day free quotas in minutes.
 * `/api/paper` reads from the ingested archive, so search is now free and
 * offline-tolerant.
 */
export function SearchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const q = searchParams?.get("q") ?? "";
  const activeSector = (searchParams?.get("sector") as Sector | null) ?? null;

  const [draft, setDraft] = useState(q);
  const [articles, setArticles] = useState<PaperArticle[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft(q), [q]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    fetchPaper({
      q: q || undefined,
      sector: activeSector ? [activeSector] : undefined,
      limit: "60",
    })
      .then((data) => {
        if (!active) return;
        // Flatten sections since search results are a single ranked list.
        const flat = data.sections.flatMap((section) => section.articles);
        setArticles(flat);
        setTotal(data.total);
      })
      .catch((err) => active && setError(err instanceof Error ? err.message : "Search failed"))
      .finally(() => active && setLoading(false));

    return () => {
      active = false;
    };
  }, [q, activeSector]);

  const pushQuery = (nextQ: string, nextSector: Sector | null) => {
    const params = new URLSearchParams();
    if (nextQ) params.set("q", nextQ);
    if (nextSector) params.set("sector", nextSector);
    const qs = params.toString();
    router.push(`/search${qs ? `?${qs}` : ""}`);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    pushQuery(draft.trim(), activeSector);
  };

  const sectors = Object.keys(sectorLabels) as Sector[];

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-6">
      <SectionFrame>
        <div className="border-b border-black/10 pb-4">
          <p className="text-[10px] uppercase tracking-[0.35em] text-black/45">
            Archive Search
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
            {q ? `Results for “${q}”` : "Search the archive"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-black/55">
            Reads the ingested archive, not live APIs. Follow a story?{" "}
            <Link href="/chains" className="underline hover:text-black">
              See chains →
            </Link>
          </p>
        </div>

        <form onSubmit={submit} className="mt-4 flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Try “flyover”, “illegal construction”, “metro”…"
            className="flex-1 min-w-[220px] border border-black/25 bg-transparent px-3 py-2 text-sm focus:border-black focus:outline-none"
          />
          <button
            type="submit"
            className="border border-black bg-black px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[#f5f4ef] hover:bg-black/85"
          >
            Search
          </button>
        </form>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => pushQuery(q, null)}
            className={cn(
              "border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
              activeSector === null
                ? "border-black bg-black text-[#f5f4ef]"
                : "border-black/15 text-black/60 hover:border-black/40",
            )}
          >
            All sectors
          </button>
          {sectors.map((sector) => (
            <button
              key={sector}
              type="button"
              onClick={() => pushQuery(q, sector)}
              className={cn(
                "border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
                activeSector === sector
                  ? "border-black bg-black text-[#f5f4ef]"
                  : "border-black/15 text-black/60 hover:border-black/40",
              )}
            >
              {sectorLabels[sector]}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="py-10 text-sm text-black/50">Searching archive…</p>
        ) : null}
        {error ? <p className="py-10 text-sm text-red-700">{error}</p> : null}

        {!loading && !error ? (
          <>
            <p className="mt-6 text-[10px] uppercase tracking-[0.2em] text-black/45">
              {total} {total === 1 ? "match" : "matches"}
            </p>

            {articles.length === 0 ? (
              <p className="py-14 text-center text-sm text-black/55">
                No matches. Try a broader keyword or clear the sector filter.
              </p>
            ) : (
              <div className="mt-3 grid gap-4 md:grid-cols-2">
                {articles.map((article) => (
                  <PaperCard key={article.id} article={article} />
                ))}
              </div>
            )}
          </>
        ) : null}
      </SectionFrame>
    </div>
  );
}
