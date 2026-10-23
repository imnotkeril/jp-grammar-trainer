# STATE — JP Grammar app

Append-only progress log. One line per completed step. Next work = first item below "Next".
On a rate-limit cut or new session: read this file, then `docs/plan.md`, continue with "Next".

Classification: webapp/tool (personal single-user, FastAPI + Next.js + Postgres in Docker). Adopted on branch `feature/finish-roadmap`; apply-router skipped (no skills/MCP linking needed for this finish pass).

## How to run checks (Windows, no Docker needed)
- Backend tests need a throwaway Postgres on :5544 (db `jp_grammar_test`, user postgres, pw test) — NEVER the owner's `jp_grammar_pgdata` volume. `tests/conftest.py` forces `DATABASE_URL` to it.
  Start one: `initdb`/`pg_ctl` from `C:\Program Files\PostgreSQL\18\bin` in a temp dir with `-o "-p 5544"`.
- `cd backend && uv run python -m pytest -q` · `uv run mypy app` · `cd frontend && npx tsc --noEmit && npm run build`
- `npm run lint` is broken pre-existing (no eslint config for ESLint 9) — not touched.

## Log
- [x] adopt — baseline: pytest 159 passed (before changes), tsc clean, mypy clean
- [x] T1 family-scoped confusion practice — `family_of` on POST /review/session, 8 new tests (167 passed), mypy clean, tsc clean

## Next
- [ ] T2 offline sentence-production practice (see docs/plan.md)
