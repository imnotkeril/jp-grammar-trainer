#!/usr/bin/env bash
# One-command local dev bootstrap: Postgres (Docker) + migrations + seed data (496 grammar items, vocabulary, curated relations).
# Does NOT start the backend/frontend dev servers themselves (run those by hand afterwards —
# see the printed commands at the end).
#
# Usage:  ./setup.sh   (Git Bash / WSL / macOS / Linux)
# Safe to re-run any time (idempotent: seed import upserts by source_note_id).
set -euo pipefail

echo "==> Starting Postgres via docker compose..."
docker compose up -d

echo "==> Waiting for Postgres to be ready..."
attempt=0
max_attempts=30
until [ "$(docker inspect --format='{{.State.Health.Status}}' jp_grammar_db 2>/dev/null)" = "healthy" ]; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Postgres did not become healthy in time (check: docker logs jp_grammar_db)" >&2
        exit 1
    fi
    sleep 1
done
echo "    Postgres is up on localhost:5545 (db: jp_grammar_dev)"

cd backend
echo "==> Running migrations (alembic upgrade head)..."
uv run alembic upgrade head

export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
echo "==> Seeding N3 grammar (idempotent, safe to re-run)..."
uv run python -m app.scripts.seed_import
echo "==> Seeding N4 + N2 grammar..."
uv run python -m app.scripts.seed_import_authored
echo "==> Seeding vocabulary (adaptive furigana)..."
uv run python -m app.scripts.seed_vocabulary
echo "==> Importing curated relations (graph + confusion practice)..."
uv run python -m app.scripts.import_curated_relations --purge-remaining-heuristic > /dev/null
cd ..

cat <<'EOF'

==> Setup complete. Start the dev servers yourself, in two separate terminals:

    cd backend && uv run python -m uvicorn app.main:app --reload
    cd frontend && npm run dev

Backend:  http://localhost:8000
Frontend: http://localhost:3000

To stop Postgres (data persists in the named volume): docker compose down
To wipe the DB entirely: docker compose down -v
EOF
