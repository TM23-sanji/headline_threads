import Link from "next/link";

import type { TrackedEvent } from "@/lib/types";
import { sectorLabels } from "@/lib/types";
import { ProgressBadge } from "./ProgressBadge";
import { TagPill } from "./TagPill";

export function EventCard({ event }: { event: TrackedEvent }) {
  return (
    <Link
      href={`/events/${event.id}`}
      className="corner-markers block border border-black/10 bg-white/30 p-4 transition hover:border-black/30"
    >
      <span className="corner-bl" aria-hidden />
      <span className="corner-br" aria-hidden />
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <TagPill tag={sectorLabels[event.sector]} />
        <ProgressBadge status={event.progress_status} />
        <span className="text-[10px] uppercase tracking-[0.15em] text-black/40">
          {event.timeline.length} updates
        </span>
      </div>
      <h3 className="text-lg font-semibold leading-snug">{event.title}</h3>
      <div className="mt-3 flex flex-wrap gap-1">
        {event.keywords.slice(0, 5).map((keyword) => (
          <TagPill key={keyword} tag={keyword} />
        ))}
      </div>
    </Link>
  );
}

export function EventTimeline({ event }: { event: TrackedEvent }) {
  if (!event.timeline.length) {
    return (
      <p className="text-sm text-black/50">
        No timeline entries yet. Refresh to pull matching headlines using tracked keywords.
      </p>
    );
  }

  return (
    <ol className="space-y-4 border-l border-black/15 pl-4">
      {event.timeline.map((entry, index) => (
        <li key={entry.id} className="relative animate-fade-in">
          <span className="absolute -left-[1.35rem] top-1 h-2.5 w-2.5 rounded-full border border-black bg-[#f5f4ef]" />
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.15em] text-black/40">
              {entry.published_at ? new Date(entry.published_at).toLocaleDateString() : "Recent"}
            </span>
            <ProgressBadge status={entry.inferred_status} />
            <span className="text-[10px] text-black/35">match {(entry.match_score * 100).toFixed(0)}%</span>
          </div>
          <h4 className="font-medium leading-snug">
            <a href={entry.url} target="_blank" rel="noreferrer" className="hover:underline">
              {entry.title}
            </a>
          </h4>
          {entry.snippet ? <p className="mt-1 text-sm text-black/60 line-clamp-2">{entry.snippet}</p> : null}
          {entry.matched_keywords.length ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {entry.matched_keywords.map((keyword) => (
                <TagPill key={`${entry.id}-${keyword}`} tag={keyword} />
              ))}
            </div>
          ) : null}
          {index === 0 ? (
            <p className="mt-2 text-[10px] uppercase tracking-[0.15em] text-black/40">Latest signal</p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
