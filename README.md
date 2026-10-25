# Papeles

**Know exactly what to bring before you line up.**

Papeles answers questions about Philippine government paperwork (passport, NBI clearance,
PhilSys ID, PSA certificates, SSS, PhilHealth, Pag-IBIG, LTO) in English, Tagalog or Bisaya.
Every answer comes from official agency pages and links back to them.

> Live demo: _coming soon_  ·  Screenshots: _coming soon_

## Why I built this

Almost everyone in the Philippines has gone home from a government office because one document
was missing. The information exists, but it's spread across many agency sites, often only in
English, and hard to search. Papeles puts it in one place and answers in your language.

## How it works

```
question ──► embed (multilingual, local) ──► pgvector similarity search
                                                     │
                                       top 5 official-page chunks
                                                     ▼
                     Claude answers ONLY from those chunks, citing [1], [2] ...
                                                     ▼
                                    answer + source links ──► web
```

1. `python -m app.ingest` fetches each page in [`apps/api/data/sources.yaml`](apps/api/data/sources.yaml),
   splits it into overlapping chunks, embeds them, and stores them in Postgres.
2. A question is embedded with the same multilingual model, so a Tagalog or Bisaya question
   still matches English source text.
3. The closest chunks go to Claude with instructions to answer only from them, cite them,
   and say so when the sources don't cover the question.

## Stack

| Layer      | Tech                                                        |
| ---------- | ----------------------------------------------------------- |
| Web        | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS |
| API        | FastAPI, Pydantic, SQLAlchemy 2                             |
| Search     | PostgreSQL + pgvector, fastembed (multilingual MiniLM)      |
| AI         | Claude API (Anthropic Python SDK)                           |
| Tooling    | Docker Compose, GitHub Actions, pytest, Ruff, ESLint        |

## Run it locally

You need Docker and an [Anthropic API key](https://console.anthropic.com).

```bash
cp .env.example .env          # then paste your ANTHROPIC_API_KEY
docker compose up --build -d
docker compose exec api python -m app.ingest   # load the official pages
```

Open http://localhost:3000. API docs are at http://localhost:8000/docs.

### Without Docker (for development)

```bash
docker compose up -d db

cd apps/api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload

cd apps/web
npm install
npm run dev
```

## Tests

```bash
cd apps/api && pytest        # API, no database or API key needed
cd apps/web && npm run lint && npm run typecheck
```

CI runs all of these on every push and pull request.

## Project layout

```
apps/
  api/            FastAPI service
    app/
      main.py       app + CORS + /health
      routers/      /ask endpoint
      rag.py        retrieval + Claude answer
      ingest.py     fetch → chunk → embed → store
      chunking.py
      embeddings.py
      models.py     sources, chunks (pgvector)
    data/sources.yaml   official pages to answer from
    tests/
  web/            Next.js frontend
    src/app/        page + layout
    src/components/ask-box.tsx
    src/lib/api.ts
docker-compose.yml
.github/workflows/ci.yml
```

## Roadmap

- [ ] Replace agency homepages in `sources.yaml` with exact requirements pages
- [ ] Personal checklist: tick off documents you already have, saved per user
- [ ] Office finder with hours and appointment links
- [ ] Stream answers token by token
- [ ] Scheduled re-ingest so answers track requirement changes
- [ ] Alembic migrations
- [ ] Deploy (Vercel for web, Render/Fly for API, Neon or Supabase for Postgres)

## Disclaimer

Papeles is a community project and is not affiliated with any government agency.
Requirements and fees change, so always confirm with the agency.
