"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ArticleCard } from "@/components/ArticleCard";
import { FilterSidebar } from "@/components/FilterSidebar";
import { SearchBar } from "@/components/SearchBar";
import { SectionFrame } from "@/components/SectionFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { fetchNews } from "@/lib/api";
import type { NewsArticle, Sector } from "@/lib/types";

export function SearchContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams?.get("q") ?? "";
  const [selectedSector, setSelectedSector] = useState<Sector | null>(null);
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchNews(selectedSector ?? undefined, initialQuery || undefined)
      .then((data) => setArticles(data.articles))
      .catch((err) => setError(err instanceof Error ? err.message : "Search failed"))
      .finally(() => setLoading(false));
  }, [initialQuery, selectedSector]);

  const filtered = useMemo(() => {
    if (!initialQuery.trim()) return articles;
    const q = initialQuery.toLowerCase();
    return articles.filter(
      (article) =>
        article.title.toLowerCase().includes(q) ||
        article.snippet.toLowerCase().includes(q),
    );
  }, [articles, initialQuery]);

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-4 py-8 md:grid-cols-[220px_1fr] md:px-6">
      <div className="space-y-6">
        <FilterSidebar selectedSector={selectedSector} onSectorChange={setSelectedSector} />
      </div>
      <SectionFrame>
        <SectionHeader
          number="04"
          tag="Archive Search"
          title={initialQuery ? `Results for “${initialQuery}”` : "Search headlines"}
          description="Filter by sector, then track any story to monitor progress with generated keywords."
        />
        <div className="mb-6">
          <SearchBar large />
        </div>
        {loading ? <p className="text-sm text-black/50">Searching...</p> : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <div className="grid gap-4 md:grid-cols-2">
          {filtered.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
      </SectionFrame>
    </div>
  );
}
