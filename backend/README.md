# backend

FastAPI backend for the Japanese N3 Grammar Retrieval Trainer. See `../ARCHITECTURE.md` for
the full system design, DB schema, SRS algorithm, and AI generation pipeline this implements.

## Setup

```bash
uv sync
cp .env.example .env   # fill in DATABASE_URL + at least one of OPENAI_API_KEY/ANTHROPIC_API_KEY
```

## Run migrations

```bash
uv run alembic upgrade head
```

## Seed the grammar table (205 N3 items from the owner's Anki export)

```bash
uv run python -m app.scripts.seed_import
```

## Dev server

```bash
uv run uvicorn app.main:app --reload
```

## Tests / type-checking

```bash
uv run pytest
uv run mypy app
uv run pyright
```

## Status

Scaffolded by the architect agent: DB schema + migration, models, SRS algorithm, furigana
rendering, distractor selection, AI generation pipeline (provider abstraction + both
adapters + validation), and seed import are implemented and tested. `POST /review/session`,
`POST /review/answer`, and `GET /stats` are stubbed (`NotImplementedError`) — see
`ARCHITECTURE.md` §9 Phase 2 (tasks 2.4-2.6) for the exact spec to implement next.
