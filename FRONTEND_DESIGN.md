# Frontend Design — Lib

Technical articles library ranked by depth. Built with Next.js 16 (App Router) + React 19 + Tailwind CSS v4.

## Stack

| Tool | Version | Notes |
|------|---------|-------|
| Next.js | 16.2.11 | App Router, Turbopack dev |
| React | 19.2.4 | Server Components by default |
| Tailwind CSS | v4 | CSS-based config via `@theme` directive |
| PostCSS | — | Plugin: `@tailwindcss/postcss` |
| TypeScript | ^5 | Strict mode |
| Package manager | Bun | Lockfile: `bun.lock` |
| ESLint | ^9 | `eslint-config-next` + core-web-vitals + TS |

## Project Structure

```
frontend/
├── app/                          # App Router pages
│   ├── articles/[id]/page.tsx    # Article detail (client)
│   ├── search/
│   │   ├── page.tsx              # Search page (server wrapper)
│   │   └── SearchContent.tsx     # Search page (client logic)
│   ├── globals.css               # Tailwind import + custom theme + animations
│   ├── layout.tsx                # Root layout (Navbar + Footer shell)
│   └── page.tsx                  # Homepage (server)
├── components/                   # Shared UI components (flat, no subfolders)
│   ├── ArticleCard.tsx
│   ├── FilterSidebar.tsx
│   ├── Footer.tsx
│   ├── Navbar.tsx
│   ├── SearchBar.tsx
│   ├── SectionFrame.tsx
│   ├── SectionHeader.tsx
│   ├── TagPill.tsx
│   └── TierBadge.tsx
├── data/
│   └── mock.ts                   # Article type + mock data + constants
├── lib/
│   └── utils.ts                  # cn() utility
├── public/                       # Static assets
└── package.json
```

## Scripts

```json
"scripts": {
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "eslint"
}
```

## Routes

| Route | Source File | Type |
|-------|-----------|------|
| `/` | `app/page.tsx` | Server |
| `/search` | `app/search/page.tsx` | Server wrapper |
| `/search?q=...` | → `SearchContent.tsx` | Client |
| `/articles/[id]` | `app/articles/[id]/page.tsx` | Client |
| `/submit` | Referenced in Navbar, no page yet | — |

## Key Patterns

### 1. Server/Client Boundary

Interactive components use `"use client"`. Page entry points remain server components and wrap client dependencies in `<Suspense>`:

```tsx
// app/search/page.tsx — server component
export default function SearchPage() {
  return (
    <Suspense fallback={<LoadingDots />}>
      <SearchContent />
    </Suspense>
  );
}
```

Only components that use `useState`, `useRouter`, `useSearchParams`, or `useParams` are marked `"use client"`.

### 2. State Management

Minimal — `useState` + `useMemo` only. No Context API, Redux, Zustand, or React Query.

```tsx
// SearchContent.tsx
const [selectedTiers, setSelectedTiers] = useState<Set<Article["technicalTier"]>>(new Set());
const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());

const filtered = useMemo(() => {
  let results = [...articles];
  // filter by text query, tiers, tags, then sort by tier rank then upvotes
  return results;
}, [initialQuery, selectedTiers, selectedTags]);
```

### 3. URL-Derived Initial State

Search query is read from URL params via `useSearchParams()`:

```tsx
const searchParams = useSearchParams();
const initialQuery = searchParams?.get("q") ?? "";
```

Navigation uses `router.push()`:

```tsx
router.push(`/search?q=${encodeURIComponent(trimmed)}`);
```

### 4. Component Composition

Small primitives are composed into larger ones:

```tsx
// ArticleCard.tsx
export function ArticleCard({ article }: { article: Article }) {
  return (
    <div>
      <TierBadge tier={article.technicalTier} large />
      <h3>{article.title}</h3>
      <div>{article.tags.map(tag => <TagPill key={tag} tag={tag} />)}</div>
    </div>
  );
}
```

### 5. Corner Marker Motif

A signature visual element — small squares at each corner of bordered containers:

```tsx
<span className="absolute -top-[1px] -left-[1px] w-2 h-2 border-l border-t border-black/60" />
<span className="absolute -top-[1px] -right-[1px] w-2 h-2 border-r border-t border-black/60" />
<span className="absolute -bottom-[1px] -left-[1px] w-2 h-2 border-l border-b border-black/60" />
<span className="absolute -bottom-[1px] -right-[1px] w-2 h-2 border-r border-b border-black/60" />
```

Used in: `SectionFrame`, `SearchBar` (large), `ArticleCard`, homepage cards.

## Styling

### Theme (`globals.css`)

```css
@import "tailwindcss";

@theme inline {
  --color-background: #f5f4ef;
  --color-foreground: #0a0a0a;
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

body {
  background: #f5f4ef;
  color: #0a0a0a;
  font-family: var(--font-mono), ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
}
```

### Typography

- **Font**: JetBrains Mono (loaded via `next/font/google`)
- **Weights**: 400, 500, 600, 700, 800
- Monospace throughout the entire application — no sans-serif in use.

### Color System

- Background: `#f5f4ef` (warm off-white/cream)
- Foreground: `#0a0a0a` (near-black)
- Selection: black background, cream text
- Heavy use of opacity (`text-black/50`, `border-black/10`) for muted/minimalist feel

### Tier Colors

```ts
export const tierColors: Record<Article["technicalTier"], string> = {
  S: "text-amber-400 border-amber-500/50 bg-amber-500/10",
  A: "text-emerald-400 border-emerald-500/50 bg-emerald-500/10",
  B: "text-blue-400 border-blue-500/50 bg-blue-500/10",
  C: "text-yellow-400 border-yellow-500/50 bg-yellow-500/10",
  D: "text-zinc-400 border-zinc-500/50 bg-zinc-500/10",
};
```

### Animations (globals.css)

```css
@keyframes marquee { ... }       /* horizontal ticker */
@keyframes blink { ... }         /* cursor blink */
@keyframes fadeIn { ... }        /* fade + translateY(6px) */
@keyframes pulse-dot { ... }     /* loading dots */
```

Utility classes: `animate-marquee`, `animate-blink`, `animate-fade-in`, `animate-fade-in-{1,2,3}`, `animate-pulse-dot`, `animate-pulse-dot-delay-{1,2}`

Line clamp utilities: `.line-clamp-1`, `.line-clamp-2`, `.line-clamp-3`

Custom scrollbar for WebKit.

## Data Layer

Currently all data is static mock data. No backend API integration.

### Type Definition (`data/mock.ts`)

```ts
export interface Article {
  id: string;
  title: string;
  url: string;
  content: string;
  snippet: string;
  source: string;
  author: string;
  tags: string[];
  technicalTier: "S" | "A" | "B" | "C" | "D";
  upvotes: number;
  downvotes: number;
  publishedAt: string;
  readTime: number;
}
```

### Constants

```ts
export const allTags = [...new Set(articles.flatMap(a => a.tags))].sort();

export const tierDescriptions: Record<Article["technicalTier"], string> = {
  S: "Deep research, advanced math, novel architectures, code-heavy deep dives",
  A: "In-depth tutorials, detailed architecture analysis, advanced patterns",
  B: "Solid how-to guides, intermediate concepts, practical deep dives",
  C: "Introductory tutorials, surface-level overviews, listicles",
  D: "News, announcements, very basic content, thin articles",
};
```

## Utility

```ts
// lib/utils.ts
export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}
```

Used by `TierBadge` to conditionally apply classes (lightweight alternative to `clsx`).

## UI Components Reference

| Component | File | Client? | Purpose |
|-----------|------|---------|---------|
| `Navbar` | `components/Navbar.tsx` | — | Sticky top bar with logo, Browse, Submit |
| `Footer` | `components/Footer.tsx` | — | Footer with link groups, newsletter, social |
| `SearchBar` | `components/SearchBar.tsx` | `"use client"` | Search input with ⌘K, two sizes |
| `SectionFrame` | `components/SectionFrame.tsx` | — | Decorated container with corner markers |
| `SectionHeader` | `components/SectionHeader.tsx` | — | Section heading with number/tag/title/description |
| `TierBadge` | `components/TierBadge.tsx` | — | Colored S/A/B/C/D indicator with tooltip |
| `TagPill` | `components/TagPill.tsx` | — | Toggleable tag button |
| `ArticleCard` | `components/ArticleCard.tsx` | — | Article preview with tier, tags, metadata |
| `FilterSidebar` | `components/FilterSidebar.tsx` | `"use client"` | Sidebar with tier + tag filters |

## Design Philosophy

1. **Dependency-light** — no external UI library, icon library, or state management library.
2. **Hand-crafted Tailwind** — every component styled with utility classes (no CSS modules, no styled-components).
3. **Technical/blueprint aesthetic** — monospace font, corner markers, muted cream + black palette.
4. **Explicit boundaries** — clear `"use client"` demarcation, Suspense boundaries for interactive islands.
5. **Flat structure** — small app, so all components live in a single flat directory.
