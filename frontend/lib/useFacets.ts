"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** Facets that accept several values at once. */
export const MULTI_FACETS = ["sector", "status", "language", "provider", "source", "keyword"] as const;
/** Facets that hold a single value. */
export const SINGLE_FACETS = ["since", "q"] as const;

export type FacetState = Record<string, string[]>;

/**
 * Facet selection stored in the URL.
 *
 * Keeping state in the query string makes a filtered edition shareable and
 * makes browser back/forward behave, which component state would not.
 */
export function useFacets() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const selected = useMemo<FacetState>(() => {
    const state: FacetState = {};
    for (const key of MULTI_FACETS) {
      const values = searchParams.getAll(key);
      if (values.length) state[key] = values;
    }
    for (const key of SINGLE_FACETS) {
      const value = searchParams.get(key);
      if (value) state[key] = [value];
    }
    return state;
  }, [searchParams]);

  const push = useCallback(
    (next: FacetState) => {
      const params = new URLSearchParams();
      for (const [key, values] of Object.entries(next)) {
        values.filter(Boolean).forEach((v) => params.append(key, v));
      }
      const qs = params.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const toggle = useCallback(
    (group: string, value: string) => {
      const next: FacetState = { ...selected };
      const isSingle = (SINGLE_FACETS as readonly string[]).includes(group);
      const current = next[group] ?? [];

      if (isSingle) {
        // Re-selecting the active value clears it.
        if (current[0] === value) delete next[group];
        else next[group] = [value];
      } else if (current.includes(value)) {
        const remaining = current.filter((v) => v !== value);
        if (remaining.length) next[group] = remaining;
        else delete next[group];
      } else {
        next[group] = [...current, value];
      }

      push(next);
    },
    [push, selected],
  );

  const clear = useCallback(() => push({}), [push]);

  const clearGroup = useCallback(
    (group: string) => {
      const next = { ...selected };
      delete next[group];
      push(next);
    },
    [push, selected],
  );

  const isActive = useCallback(
    (group: string, value: string) => (selected[group] ?? []).includes(value),
    [selected],
  );

  const activeCount = useMemo(
    () => Object.values(selected).reduce((sum, values) => sum + values.length, 0),
    [selected],
  );

  return { selected, toggle, clear, clearGroup, isActive, activeCount };
}
