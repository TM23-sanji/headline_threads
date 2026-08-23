"use client";

import { cn } from "@/lib/utils";

export function TagPill({
  tag,
  active = false,
  onClick,
}: {
  tag: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const Component = onClick ? "button" : "span";

  return (
    <Component
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "inline-flex items-center border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]",
        active
          ? "border-black bg-black text-[#f5f4ef]"
          : "border-black/15 bg-transparent text-black/60 hover:border-black/40",
      )}
    >
      {tag}
    </Component>
  );
}
