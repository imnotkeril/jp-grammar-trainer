# Running this locally

Personal-use app: one Postgres container (persistent data) + backend + frontend dev servers.

## First time / any time you want a clean start

```powershell
.\setup.ps1
```

(Git Bash: `./setup.sh`)

This starts Postgres via Docker Compose, waits for it to be healthy, runs Alembic migrations,
and re-imports all seed data — N3/N4/N2 grammar, vocabulary, curated relations (idempotent — safe to run every time, won't duplicate
rows or wipe progress). It does **not** start the backend or frontend dev servers; it prints
the two commands to do that yourself.

## Day to day

Postgres data lives in the named Docker volume `jp_grammar_pgdata`, so once it's up you don't
need to run `setup.ps1` again unless you tore the container down. Just:

```powershell
docker compose up -d      # if Postgres isn't already running
cd backend; uv run python -m uvicorn app.main:app --reload
```

```powershell
cd frontend; npm run dev
```

Backend: http://localhost:8000 — Frontend: http://localhost:3000

## Stopping

```powershell
docker compose down        # stops Postgres, keeps the data volume
docker compose down -v     # stops Postgres AND deletes all data (progress, seed data) — rarely what you want
```

## Env files

`backend/.env` and `frontend/.env` are gitignored and already point at the compose Postgres
(`postgresql+psycopg://postgres:devpass@localhost:5545/jp_grammar_dev`). Copy from
`backend/.env.example` / `frontend/.env.example` if either is missing, and fill in an
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `backend/.env` for AI question generation.

See `backend/README.md` for the throwaway-Postgres-for-tests convention (different port/db —
`TEST_DATABASE_URL`, port 5544) which is unrelated to the dev Postgres above.
