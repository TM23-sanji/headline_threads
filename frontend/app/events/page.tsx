import { Suspense } from "react";

import { EventCard } from "@/components/EventTimeline";
import { SectionFrame } from "@/components/SectionFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { fetchEvents } from "@/lib/api";

async function EventsList() {
  const data = await fetchEvents();

  return (
    <div className="mx-auto max-w-5xl space-y-4 px-4 py-8 md:px-6">
      <SectionFrame>
        <SectionHeader
          number="02"
          tag="Event Desk"
          title="Tracked Events"
          description="Each event stores auto-generated keywords. Refresh on detail pages to pull new headlines and infer progress."
        />
        <div className="grid gap-4 md:grid-cols-2">
          {data.events.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
        {!data.events.length ? (
          <p className="text-sm text-black/50">No tracked events yet. Open the edition and click “Track this event” on any story.</p>
        ) : null}
      </SectionFrame>
    </div>
  );
}

export default function EventsPage() {
  return (
    <Suspense fallback={<p className="px-4 py-8 text-sm text-black/50">Loading tracked events...</p>}>
      <EventsList />
    </Suspense>
  );
}
