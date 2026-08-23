import type {
  KeywordGenerateResponse,
  PaperResponse,
  Sector,
  ThreadDetail,
  ThreadsResponse,
  TrackedEvent,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Paper + threads (Postgres-backed)
// ---------------------------------------------------------------------------

/** Facets are multi-select, so each selected value repeats in the query string. */
export function buildPaperQuery(
  params: Record<string, string[] | string | undefined>,
) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (!value) continue;
    if (Array.isArray(value)) {
      value.forEach((v) => v && search.append(key, v));
    } else {
      search.set(key, value);
    }
  }
  return search.toString();
}

export function fetchPaper(
  params: Record<string, string[] | string | undefined> = {},
) {
  const qs = buildPaperQuery(params);
  return request<PaperResponse>(`/api/paper${qs ? `?${qs}` : ""}`);
}

export function fetchThreads(
  params: {
    chains_only?: boolean;
    sector?: string;
    status?: string;
    language?: string;
  } = {},
) {
  const search = new URLSearchParams();
  if (params.chains_only) search.set("chains_only", "true");
  if (params.sector) search.set("sector", params.sector);
  if (params.status) search.set("status", params.status);
  if (params.language) search.set("language", params.language);
  const qs = search.toString();
  return request<ThreadsResponse>(`/api/threads${qs ? `?${qs}` : ""}`);
}

export function fetchThread(id: string) {
  return request<ThreadDetail>(`/api/threads/${id}`);
}

// ---------------------------------------------------------------------------
// Tracked events (also Postgres-backed)
// ---------------------------------------------------------------------------

export function fetchEvents() {
  return request<{ events: TrackedEvent[]; total: number }>("/api/events");
}

export function fetchEvent(id: string) {
  return request<TrackedEvent>(`/api/events/${id}`);
}

export function generateKeywords(title: string, snippet = "") {
  return request<KeywordGenerateResponse>("/api/events/keywords", {
    method: "POST",
    body: JSON.stringify({ title, snippet }),
  });
}

export function trackEvent(payload: {
  title: string;
  snippet?: string;
  url?: string;
  sector?: Sector;
  location?: string;
  keywords?: string[];
}) {
  return request<TrackedEvent>("/api/events/track", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refreshEvent(id: string) {
  return request<TrackedEvent>(`/api/events/${id}/refresh`, { method: "POST" });
}
