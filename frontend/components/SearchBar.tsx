"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/utils";

export function SearchBar({ large = false }: { large?: boolean }) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <form onSubmit={handleSubmit} className={cn("relative w-full", large ? "max-w-2xl" : "max-w-md")}>
      <div className={cn("corner-markers border border-black/20 bg-white/40", large ? "p-3" : "p-2")}>
        <span className="corner-bl" aria-hidden />
        <span className="corner-br" aria-hidden />
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.2em] text-black/40">Query</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search Bhopal headlines..."
            className="w-full bg-transparent text-sm outline-none placeholder:text-black/30"
          />
          <kbd className="hidden text-[10px] text-black/35 md:inline">Enter</kbd>
        </div>
      </div>
    </form>
  );
}
