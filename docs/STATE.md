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
- [x] T2 offline sentence-production practice — POST /production/session|check (stateless, no SRS writes), /produce page; 184 backend tests passed, mypy + tsc + next build clean, smoke-tested in browser against a seeded throwaway DB

- [x] T3 LLM relation re-classification behind LLM_RELATION_RECLASSIFY — `generate_relations --reclassify`, mocked-provider tests (6), 190 passed, mypy clean; NOT verified live (no key)
- [x] T4 N5/N1 scaffold — offline `validate_authored_seed` (shipped N4/N2: 0 errors), empty n5/n1 seed slots, `data/seed/README.md`, backend accepts all 5 levels; no content invented; 207 passed, mypy clean

- [x] T5 README roadmap + llms.txt — final: pytest 207 passed, mypy clean, tsc clean, next build OK (branch feature/finish-roadmap, 5 local commits, not pushed)

## Next
- [ ] Owner items in docs/plan.md ("Needs owner"): live LLM reclassify run, N5/N1 content source, speaking practice decision, merge/push decision
