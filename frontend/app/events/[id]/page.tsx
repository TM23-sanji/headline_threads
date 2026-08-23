"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { EventTimeline } from "@/components/EventTimeline";
import { ProgressBadge } from "@/components/ProgressBadge";
import { SectionFrame } from "@/components/SectionFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { TagPill } from "@/components/TagPill";
import { fetchEvent, refreshEvent } from "@/lib/api";
import type { TrackedEvent } from "@/lib/types";
import { sectorLabels } from "@/lib/types";

export default function EventDetailPage() {
  const params = useParams<{ id: string }>();
  const [event, setEvent] = useState<TrackedEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    setLoading(true);
    fetchEvent(params.id)
      .then(setEvent)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load event"))
      .finally(() => setLoading(false));
  }, [params?.id]);

  async function handleRefresh() {
    if (!params?.id) return;
    setRefreshing(true);
    try {
      const updated = await refreshEvent(params.id);
      setEvent(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  if (loading) return <p className="px-4 py-8 text-sm text-black/50">Loading event...</p>;
  if (error) return <p className="px-4 py-8 text-sm text-red-700">{error}</p>;
  if (!event) return <p className="px-4 py-8 text-sm text-black/50">Event not found.</p>;

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 md:px-6">
      <SectionFrame>
        <SectionHeader
          number="03"
          tag="Progress Monitor"
          title={event.title}
          description={`Tracking in ${event.location} · query: ${event.keyword_query}`}
        />

        <div className="mb-6 flex flex-wrap items-center gap-2">
          <TagPill tag={sectorLabels[event.sector]} />
          <ProgressBadge status={event.progress_status} />
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="border border-black/20 px-3 py-1 text-[10px] uppercase tracking-[0.15em] hover:border-black hover:bg-black hover:text-[#f5f4ef] disabled:opacity-50"
          >
            {refreshing ? "Refreshing..." : "Refresh timeline"}
          </button>
        </div>

        <div className="mb-6">
          <p className="mb-2 text-[10px] uppercase tracking-[0.25em] text-black/45">Generated Keywords</p>
          <div className="flex flex-wrap gap-2">
            {event.keywords.map((keyword) => (
              <TagPill key={keyword} tag={keyword} />
            ))}
          </div>
        </div>

        <EventTimeline event={event} />
      </SectionFrame>
    </div>
  );
}
