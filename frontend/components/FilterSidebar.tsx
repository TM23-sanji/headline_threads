"use client";

import type { Sector } from "@/lib/types";
import { sectorLabels } from "@/lib/types";
import { TagPill } from "./TagPill";

export function FilterSidebar({
  selectedSector,
  onSectorChange,
}: {
  selectedSector: Sector | null;
  onSectorChange: (sector: Sector | null) => void;
}) {
  const sectors = Object.keys(sectorLabels) as Sector[];

  return (
    <aside className="space-y-4">
      <div>
        <p className="mb-2 text-[10px] uppercase tracking-[0.25em] text-black/45">Sector Filter</p>
        <div className="flex flex-wrap gap-2">
          <TagPill tag="All" active={!selectedSector} onClick={() => onSectorChange(null)} />
          {sectors.map((sector) => (
            <TagPill
              key={sector}
              tag={sectorLabels[sector]}
              active={selectedSector === sector}
              onClick={() => onSectorChange(sector)}
            />
          ))}
        </div>
      </div>
      <p className="text-xs leading-relaxed text-black/50">
        Pick a sector to reshape the edition. Track any story to auto-generate keywords and follow progress over time.
      </p>
    </aside>
  );
}
