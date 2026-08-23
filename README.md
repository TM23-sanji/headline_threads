# headline_threads

Bhopal/MP news monitor — newspaper-style Bhopal/MP news dashboard with **story chains**. Headlines are
pulled from three news APIs, normalized, classified by sector, keyworded, and
grouped into chains so you can follow how a story develops over time.

live link : https://headline-threads-web.onrender.com/

![The MP Gazette — newspaper edition with sector sections, progress badges and keyword chips](docs/demo.png)

> Full walkthrough: [`docs/demo.mp4`](docs/demo.mp4)

### A chain in the wild

The Bhopal metro story auto-formed a chain from two articles published two
weeks apart, arriving through different providers. Same thread, two beats,
both flagged `DELAYED` — matched by shared keywords, not by hand.

![Story chain for the Bhopal metro rail project, showing two beats over 14 days with progress status](docs/metro.png)


## Stack

- **Frontend:** Next.js 16 + React 19 + Tailwind v4 + Bun
- **Backend:** FastAPI + uv + SQLAlchemy (async)
- **Storage:** Neon Postgres (all objects in a dedicated `bhopal` schema)

## Setup

Secrets live in `backend/.env` (gitignored). Copy `backend/.env.example`:

```
NEWSDATA_API_KEY=...
GNEWS_API_KEY=...
NEWS_API_KEY=...
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb
```

`DATABASE_URL` must use the `postgresql+asyncpg://` driver and the **pooled**
Neon host. Drop any `sslmode` / `channel_binding` query parameters — asyncpg
rejects them, and TLS is applied in code.

```bash
cd backend
uv run python scripts/init_db.py      # create bhopal schema + tables + indexes
uv run python scripts/run_ingest.py   # fetch from all 3 APIs into Neon
uv run uvicorn app.main:app --reload --port 8000

cd ../frontend
bun install && bun dev                # http://localhost:3000
```

Check `GET /health` for per-provider key status and archive counts.

## How story chains work

1. **Ingest** queries all three providers, normalizes the results and stores
   them in Neon. Each article gets a sector, a progress status and keywords.
2. **Threading** matches a new article against open threads using keyword
   overlap plus headline token similarity. Above threshold it joins the
   existing chain; otherwise it starts a new one.
3. **Beat collapsing** merges reports of the *same* development published
   within ~36 hours into a single beat, recording the extra outlets as
   corroborating sources. Without this, one syndicated story would look like
   three separate developments.
4. **Progress** is read beat-to-beat, and the UI highlights transitions
   (`ongoing → stalled`) rather than repeating headlines.

Example produced by the pipeline:

```
Illegal construction in Shahpura            status: stalled
  2026-08-01  [ongoing]  BMC issues notices          (2 outlets)
  2026-08-08  [ongoing]  demolition drive begins
  2026-08-22  [stalled]  drive halted, court stay    ongoing -> stalled
```

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | provider keys, last call status, archive counts |
| `GET /api/paper` | faceted edition + facet counts |
| `GET /api/threads?chains_only=true` | story chains |
| `GET /api/threads/{id}` | chain detail with beats and sources |
| `GET /api/news`, `/api/events/*` | legacy live-fetch endpoints (JSON store) |

`/api/paper` accepts repeatable `sector`, `status`, `language`, `provider`,
`source`, `keyword`, plus `since` (`today|week|month|quarter`) and `q`. All
filtering runs in Postgres, so no filter combination costs an API call.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/init_db.py [--drop]` | create schema, extensions, indexes |
| `scripts/run_ingest.py` | live ingest (hits all 3 APIs) |
| `scripts/run_ingest.py --fixtures` | replay captured articles, no quota used |
| `scripts/run_ingest.py --threads` | replay chain fixtures |
| `scripts/run_ingest.py --show` | print archive state |
| `scripts/fetch_demo_data.py` | capture raw API responses to `data/demo/` |
| `scripts/test_threading.py` | assert chain/beat behaviour on fixtures |

## Provider constraints (measured, not assumed)

These shaped the architecture and are worth knowing before changing it.

| | NewsData | GNews | NewsAPI |
|---|---|---|---|
| Full article text | paid only | ~265 char stub | ~200 char stub |
| Backfill | archive is paid | ~30 days | ~30 days |
| Geo targeting | `region` is paid | publisher-only | none |
| Freshness | real time | **12h delay** | real time |
| Free keywords | **yes** | no | no |

Two consequences:

- **History cannot be backfilled, so Neon is the archive.** Any day without an
  ingest run is permanently lost. Run ingest on a schedule.
- **Only ~300–500 characters of text exist per article**, so progress status is
  frequently `unknown`. The UI shows that honestly instead of guessing.

Relevance depends on searching *headlines*: NewsData `qInTitle` and NewsAPI
`searchIn=title` moved on-topic results from 56% to 100% on live data, and also
surfaced Hindi articles that a body-wide search had buried.

## Deploy

Both services deploy to Render as Docker web services; Neon hosts Postgres.
`render.yaml` at the repo root is a Blueprint — importing it in the Render
dashboard provisions both services in one step.

```
Render Blueprint  →  headline-threads-api   (backend/Dockerfile)
                     headline-threads-web   (frontend/Dockerfile)
Neon             →   neondb, schema `bhopal`
GitHub Actions   →   .github/workflows/ingest.yml (scheduled ingest, every 6h)
```

**One-time setup after applying the Blueprint:**

1. In the Render dashboard, fill the env vars marked `sync: false` in
   `render.yaml`:
   - `NEWSDATA_API_KEY`, `GNEWS_API_KEY`, `NEWS_API_KEY`, `DATABASE_URL`
     on the API service.
   - `CORS_ORIGINS` = the frontend service URL (Render's `fromService` only
     exposes a bare hostname, so the scheme has to be added by hand).
   - `NEXT_PUBLIC_API_URL` = the API service URL, on the frontend service.
     Next inlines `NEXT_PUBLIC_*` at build time, so this must be set before
     the first successful frontend build.
2. Run `uv run python scripts/init_db.py` once from your machine — creates
   the `bhopal` schema, extensions and indexes in Neon. Idempotent.
3. In GitHub → Settings, add:
   - Variable **`API_URL`** = `https://headline-threads-api.onrender.com`
   - Secret **`INGEST_SECRET`** = the value Render generated for the API.
   These wire the scheduled ingest to your backend.

**Free-plan caveats worth flagging:**

- Both services sleep after ~15 min idle. The first request after that
  cold-starts in ~30–50 s. The 6-hourly ingest cron doubles as a keep-warm
  ping for the API, but the frontend has no equivalent.
- Free tier has no persistent disk. The `bhopal` Postgres schema is the
  only durable storage — anything written to the container filesystem is
  lost on redeploy, which is why event tracking is DB-backed.
- Provider quotas (~100–200 req/day per provider) are shared across all
  ingest runs. The default 6-hourly schedule uses ~12 calls/day.

## Known gaps

- Chain matching is lexical, so a Hindi article will not link to its
  English counterpart. A `vector` column is reserved for embeddings.
- No CI (typecheck / lint / test on push).
- `FRONTEND_DESIGN.md` documents a different project and is stale.
