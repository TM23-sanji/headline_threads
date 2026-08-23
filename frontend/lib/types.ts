export type Sector =
  | "construction"
  | "roads"
  | "transport"
  | "water_lakes"
  | "bmc_civic"
  | "health"
  | "crime"
  | "politics"
  | "environment"
  | "other";

export type ProgressStatus =
  | "planned"
  | "ongoing"
  | "delayed"
  | "stalled"
  | "completed"
  | "unknown";

export interface NewsArticle {
  id: string;
  title: string;
  snippet: string;
  url: string;
  source: string;
  published_at?: string | null;
  image_url?: string | null;
  language?: string | null;
  provider?: string | null;
  sector?: Sector;
  subtopic?: string | null;
  status?: string | null;
  confidence?: number;
  keep?: boolean;
  summary?: string | null;
  matched_keywords?: string[];
}

export interface NewspaperSection {
  sector: Sector;
  label: string;
  articles: NewsArticle[];
}

export interface NewspaperResponse {
  city: string;
  date: string;
  sections: NewspaperSection[];
  total: number;
}

export interface TimelineEntry {
  id: string;
  captured_at: string;
  article_id: string;
  title: string;
  snippet: string;
  url: string;
  source: string;
  published_at?: string | null;
  inferred_status: ProgressStatus;
  match_score: number;
  matched_keywords: string[];
}

export interface TrackedEvent {
  id: string;
  title: string;
  keywords: string[];
  sector: Sector;
  location: string;
  progress_status: ProgressStatus;
  created_at: string;
  updated_at: string;
  source_article_url?: string | null;
  timeline: TimelineEntry[];
  keyword_query: string;
}

export interface KeywordGenerateResponse {
  keywords: string[];
  keyword_query: string;
  sector: Sector;
  inferred_status: ProgressStatus;
}

export const sectorLabels: Record<Sector, string> = {
  construction: "Construction",
  roads: "Roads",
  transport: "Transport",
  water_lakes: "Water & Lakes",
  bmc_civic: "BMC & Civic",
  health: "Health",
  crime: "Crime",
  politics: "Politics",
  environment: "Environment",
  other: "General",
};

export const progressLabels: Record<ProgressStatus, string> = {
  planned: "Planned",
  ongoing: "Ongoing",
  delayed: "Delayed",
  stalled: "Stalled",
  completed: "Completed",
  unknown: "Unknown",
};

export const progressColors: Record<ProgressStatus, string> = {
  planned: "text-blue-700 border-blue-500/40 bg-blue-500/10",
  ongoing: "text-emerald-700 border-emerald-500/40 bg-emerald-500/10",
  delayed: "text-amber-700 border-amber-500/40 bg-amber-500/10",
  stalled: "text-red-700 border-red-500/40 bg-red-500/10",
  completed: "text-zinc-700 border-zinc-500/40 bg-zinc-500/10",
  unknown: "text-black/60 border-black/20 bg-black/5",
};

// ---------------------------------------------------------------------------
// Faceted paper + story chains (Postgres-backed)
// ---------------------------------------------------------------------------

export type Language = "en" | "hi" | "unknown";

export interface FacetValue {
  value: string;
  count: number;
}

export interface PaperArticle {
  id: string;
  title: string;
  snippet: string;
  url: string;
  source: string;
  provider: string;
  language: string;
  published_at?: string | null;
  image_url?: string | null;
  sector: Sector;
  progress_status: ProgressStatus;
  confidence: number;
  keywords: string[];
  thread_id?: string | null;
  thread_beat_count: number;
}

export interface PaperSection {
  sector: Sector;
  label: string;
  articles: PaperArticle[];
}

export interface PaperResponse {
  city: string;
  date: string;
  total: number;
  sections: PaperSection[];
  facets: Record<string, FacetValue[]>;
  applied: Record<string, string[] | string>;
}

export interface BeatSource {
  id: string;
  title: string;
  url: string;
  source: string;
  provider: string;
  language: string;
  published_at?: string | null;
}

export interface Beat {
  id: string;
  headline: string;
  summary: string;
  occurred_at: string;
  status: ProgressStatus;
  is_status_change: boolean;
  previous_status?: ProgressStatus | null;
  source_count: number;
  sources: BeatSource[];
}

export interface Thread {
  id: string;
  slug: string;
  title: string;
  sector: Sector;
  language: string;
  location: string;
  current_status: ProgressStatus;
  first_seen: string;
  last_seen: string;
  beat_count: number;
  article_count: number;
  keywords: string[];
}

export interface ThreadDetail extends Thread {
  beats: Beat[];
}

export interface ThreadsResponse {
  total: number;
  threads: Thread[];
}

export const languageLabels: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  unknown: "Unknown",
};

export const providerLabels: Record<string, string> = {
  newsdata: "NewsData",
  gnews: "GNews",
  newsapi: "NewsAPI",
};

export const sinceLabels: Record<string, string> = {
  today: "Today",
  week: "This week",
  month: "This month",
  quarter: "3 months",
};

/** Facet groups rendered in the sidebar, in display order. */
export const FACET_GROUPS: { key: string; label: string }[] = [
  { key: "sector", label: "Sector" },
  { key: "status", label: "Progress" },
  { key: "language", label: "Language" },
  { key: "since", label: "Date" },
  { key: "provider", label: "Provider" },
  { key: "source", label: "Source" },
];

export function facetLabel(group: string, value: string): string {
  if (group === "sector") return sectorLabels[value as Sector] ?? value;
  if (group === "status") return progressLabels[value as ProgressStatus] ?? value;
  if (group === "language") return languageLabels[value] ?? value;
  if (group === "provider") return providerLabels[value] ?? value;
  if (group === "since") return sinceLabels[value] ?? value;
  return value;
}
