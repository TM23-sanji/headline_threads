"use client";

import type { ProgressStatus } from "@/lib/types";
import { progressColors, progressLabels } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ProgressBadge({ status }: { status: ProgressStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
        progressColors[status],
      )}
    >
      {progressLabels[status]}
    </span>
  );
}
