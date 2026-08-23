"use client";

import type { FacetValue } from "@/lib/types";
import { FACET_GROUPS, facetLabel } from "@/lib/types";
import { useFacets } from "@/lib/useFacets";
import { cn } from "@/lib/utils";

function FacetRow({
  group,
  value,
  count,
  active,
  onClick,
}: {
  group: string;
  value: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  // Options that would return nothing are disabled rather than hidden, so the
  // set of available filters stays stable as selections change.
  const empty = count === 0 && !active;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={empty}
      className={cn(
        "flex w-full items-center justify-between gap-2 border px-2 py-1 text-left text-[10px] uppercase tracking-[0.12em] transition-colors",
        active
          ? "border-black bg-black text-[#f5f4ef]"
          : empty
            ? "cursor-not-allowed border-black/10 text-black/25"
            : "border-black/15 text-black/65 hover:border-black/40",
      )}
    >
      <span className="truncate">{facetLabel(group, value)}</span>
      <span className={cn("tabular-nums", active ? "text-[#f5f4ef]/70" : "text-black/35")}>
        {count}
      </span>
    </button>
  );
}

export function FacetSidebar({
  facets,
  total,
  loading,
}: {
  facets: Record<string, FacetValue[]>;
  total: number;
  loading?: boolean;
}) {
  const { toggle, clear, clearGroup, isActive, activeCount, selected } = useFacets();

  return (
    <aside className="space-y-5 md:sticky md:top-20 md:max-h-[calc(100vh-6rem)] md:overflow-y-auto md:pr-1">
      <div className="flex items-baseline justify-between border-b border-black/10 pb-2">
        <p className="text-[10px] uppercase tracking-[0.25em] text-black/45">Filters</p>
        {activeCount > 0 ? (
          <button
            type="button"
            onClick={clear}
            className="text-[10px] uppercase tracking-[0.15em] text-black/45 underline hover:text-black"
          >
            Clear ({activeCount})
          </button>
        ) : null}
      </div>

      <p className="text-[11px] text-black/50">
        {loading ? "Loading…" : `${total} ${total === 1 ? "story" : "stories"}`}
      </p>

      {/* Active keyword chips get their own row: they are set by clicking a
          card, not by picking from a list. */}
      {selected.keyword?.length ? (
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-[0.2em] text-black/45">Keywords</p>
            <button
              type="button"
              onClick={() => clearGroup("keyword")}
              className="text-[10px] uppercase tracking-[0.15em] text-black/40 underline hover:text-black"
            >
              clear
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {selected.keyword.map((kw) => (
              <button
                key={kw}
                type="button"
                onClick={() => toggle("keyword", kw)}
                className="inline-flex items-center gap-1 border border-black bg-black px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-[#f5f4ef]"
                title="Remove keyword filter"
              >
                {kw}
                <span aria-hidden>×</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {FACET_GROUPS.map(({ key, label }) => {
        const values = facets[key] ?? [];
        if (!values.length) return null;

        return (
          <div key={key}>
            <p className="mb-1.5 text-[10px] uppercase tracking-[0.2em] text-black/45">{label}</p>
            <div className="space-y-1">
              {values.slice(0, key === "source" ? 8 : 12).map((facet) => (
                <FacetRow
                  key={facet.value}
                  group={key}
                  value={facet.value}
                  count={facet.count}
                  active={isActive(key, facet.value)}
                  onClick={() => toggle(key, facet.value)}
                />
              ))}
            </div>
          </div>
        );
      })}

      {/* Trending keywords double as a discovery surface. */}
      {facets.keyword?.length ? (
        <div>
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.2em] text-black/45">Trending</p>
          <div className="flex flex-wrap gap-1.5">
            {facets.keyword.slice(0, 14).map((facet) => (
              <button
                key={facet.value}
                type="button"
                onClick={() => toggle("keyword", facet.value)}
                className={cn(
                  "border px-2 py-0.5 text-[10px] tracking-[0.1em] transition-colors",
                  isActive("keyword", facet.value)
                    ? "border-black bg-black text-[#f5f4ef]"
                    : "border-black/15 text-black/60 hover:border-black/40",
                )}
              >
                {facet.value}
                <span className="ml-1 text-black/30">{facet.count}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}
