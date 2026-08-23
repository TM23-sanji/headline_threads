# Bhopal News API (FastAPI)

## Setup

```bash
cd /media/tm23/NewVolume/claude_bhopal/backend
source .venv/bin/activate
uv sync
cp .env.example .env   # add API keys when ready
```

## Run

```bash
source .venv/bin/activate
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

- `GET /health`
- `GET /api/news?q=Bhopal&sector=construction`

Without API keys, `/api/news` returns mock Bhopal headlines for local development.
