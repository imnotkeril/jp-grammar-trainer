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

Most tests are pure unit tests (SRS, seed-import parsers, generation validation) and run with
no setup. The router/service integration tests (`tests/test_review_session.py`,
`tests/test_review_answer.py`, `tests/test_stats.py`, `tests/test_generation_trigger.py`) need
a real Postgres — the schema uses Postgres-only types (JSONB, ARRAY, native ENUM) SQLite can't
represent. Point `TEST_DATABASE_URL` at a disposable Postgres to run them; they're
auto-skipped (not failed) when no DB is reachable, so plain `uv run pytest` always passes
without one. Quick throwaway DB via Docker:

```bash
docker run -d --name jp_grammar_test_db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=jp_grammar_test -p 5544:5432 postgres:16-alpine
export TEST_DATABASE_URL="postgresql+psycopg://postgres:test@localhost:5544/jp_grammar_test"
uv run pytest
```

## Status

Scaffolded by the architect agent: DB schema + migration, models, SRS algorithm, furigana
rendering, distractor selection, AI generation pipeline (provider abstraction + both
adapters + validation), and seed import were implemented and tested first.

Phase 2 (ARCHITECTURE.md §9, tasks 2.4-2.6) is now implemented:
- `POST /review/session` — due-item selection (overdue-first, then new; `app/services/review.py::select_due_progress`),
  serves one valid question per due item, schedules shortage-triggered background generation.
- `POST /review/answer` — persists `QuestionAttempt` (with a best-effort `error_type`
  heuristic per the idea doc's §29 taxonomy), runs `srs.schedule_next` to update
  `grammar_progress`, returns a templated contrastive explanation (SPEC.md §14).
- `GET /stats` — due count, status counts, rolling recall %, and application/discrimination
  averages (SPEC.md §27/§8).
- `app/services/generation/trigger.py` now wires `distractors.pick_distractors()` into
  freshly generated questions (previously left as a TODO / empty `options`).
- Fixed a pre-existing bug in `alembic/versions/0001_initial_schema.py`: the three
  Postgres ENUM types were created once explicitly and then re-created implicitly by
  `op.create_table()`, which failed with `DuplicateObject` against a real Postgres —
  `alembic upgrade head` had never actually been run against real Postgres before this task.
  Fixed with `create_type=False` on the inline column enum references; `upgrade`/`downgrade`
  are now both verified round-trip clean.
