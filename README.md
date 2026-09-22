# JP Grammar App

Personal spaced-retrieval trainer for JLPT N3 Japanese grammar — 205 constructions from my
own Anki deck, 4-choice fill-in-the-blank questions, SRS scheduling, and AI-generated fresh
example sentences so I don't just memorize the same sentence forever. Single-user, no auth.

Full design/decisions: [`SPEC.md`](./SPEC.md), [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Stack

- **Backend**: FastAPI + SQLAlchemy + Alembic + PostgreSQL, `uv` for deps, typed + beartype.
- **Frontend**: Next.js 15 (App Router) + TypeScript + Tailwind, PWA.
- **AI**: dual-provider (Anthropic/OpenAI) for generating new example sentences — optional,
  seed content works with neither key set.

## Setup (fresh clone → running)

### One command

```powershell
.\setup.ps1        # PowerShell
```
```bash
./setup.sh         # Git Bash / WSL / macOS / Linux
```

Starts Postgres via `docker-compose.yml` (port 5545, db `jp_grammar_dev`), waits for it to be
healthy, runs Alembic migrations, and seeds the 205 N3 grammar items + ~200 seed questions.
Idempotent — safe to re-run. It does not start the dev servers; do that yourself afterwards
(step 3 below). See [`RUNNING.md`](./RUNNING.md) for day-to-day commands once it's set up
once. Or do the equivalent manually:

### 1. Postgres

```bash
docker compose up -d
```

(Postgres 16, exposed on `localhost:5545`, db `jp_grammar_dev`, named volume so your SRS
progress survives restarts. `docker compose down -v` wipes it.)

### 2. Backend

```bash
cd backend
uv sync
cp .env.example .env
```

Edit `backend/.env` (matches the `docker-compose.yml` port above):

```
DATABASE_URL=postgresql+psycopg://postgres:devpass@localhost:5545/jp_grammar_dev
LLM_PROVIDER=anthropic            # anthropic | openai
ANTHROPIC_API_KEY=                # optional — only needed for fresh AI-generated examples
OPENAI_API_KEY=                   # optional, alternative provider
GENERATION_SHORTAGE_THRESHOLD=5
GENERATION_BATCH_SIZE=15
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

Run migrations, then seed the 205 N3 grammar items + ~200 seed questions from the Anki export:

```bash
uv run alembic upgrade head
uv run python -m app.scripts.seed_import
```

Start the API:

```bash
uv run uvicorn app.main:app --reload
```

Backend is now on `http://localhost:8000`. API docs: `/docs`. Machine-readable API reference:
`/llms.txt`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
```

`frontend/.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

```bash
npm run dev
```

Frontend is now on `http://localhost:3000`.

### 4. Use it

Open `http://localhost:3000` → Dashboard shows due count → **Start Review** → answer 4-choice
questions (seed sentences, or AI-generated ones once a provider key is set and enough reviews
have happened to trigger a generation batch) → get immediate feedback + contrastive
explanation → SRS reschedules that grammar point → back to Dashboard, counters update. Stats
page shows recall %, and counts by new/learning/review/mastered.

No AI key needed to use the app — the seeded ~200 questions from my own curated deck cover
review out of the box; AI generation only kicks in to keep material fresh over time.

## Project structure

```
backend/            FastAPI app — routers, models, services (SRS, furigana, AI generation), Alembic migrations
frontend/            Next.js PWA — Dashboard / Review / Stats pages
data/seed/           Anki export (JSON) used by the seed import script
docker-compose.yml   Local Postgres for dev
setup.ps1            One-command bootstrap (Postgres + migrations + seed)
```

See `backend/README.md` and `frontend/README.md` for dev-specific commands (tests, type
checks, structure).
