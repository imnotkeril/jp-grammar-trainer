# One-command local dev bootstrap: Postgres (Docker) + migrations + seed data.
# Does NOT start the backend/frontend dev servers themselves (run those by hand afterwards —
# see the printed commands at the end).
#
# Usage:  .\setup.ps1
# Safe to re-run any time (idempotent: seed import upserts by source_note_id).

$ErrorActionPreference = "Stop"

Write-Host "==> Starting Postgres via docker compose..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "==> Waiting for Postgres to be ready..." -ForegroundColor Cyan
$maxAttempts = 30
$attempt = 0
$ready = $false
while ($attempt -lt $maxAttempts) {
    $status = docker inspect --format='{{.State.Health.Status}}' jp_grammar_db 2>$null
    if ($status -eq "healthy") { $ready = $true; break }
    Start-Sleep -Seconds 1
    $attempt++
}
if (-not $ready) { throw "Postgres did not become healthy in time (check: docker logs jp_grammar_db)" }
Write-Host "    Postgres is up on localhost:5545 (db: jp_grammar_dev)" -ForegroundColor Green

Push-Location backend
try {
    Write-Host "==> Running migrations (alembic upgrade head)..." -ForegroundColor Cyan
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed" }

    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Write-Host "==> Seeding N3 grammar (idempotent, safe to re-run)..." -ForegroundColor Cyan
    uv run python -m app.scripts.seed_import
    if ($LASTEXITCODE -ne 0) { throw "seed_import failed" }

    Write-Host "==> Seeding N4 + N2 grammar..." -ForegroundColor Cyan
    uv run python -m app.scripts.seed_import_authored
    if ($LASTEXITCODE -ne 0) { throw "seed_import_authored failed" }

    Write-Host "==> Seeding vocabulary (adaptive furigana)..." -ForegroundColor Cyan
    uv run python -m app.scripts.seed_vocabulary
    if ($LASTEXITCODE -ne 0) { throw "seed_vocabulary failed" }

    Write-Host "==> Importing curated relations (graph + confusion practice)..." -ForegroundColor Cyan
    uv run python -m app.scripts.import_curated_relations --purge-remaining-heuristic | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "import_curated_relations failed" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "==> Setup complete. Start the dev servers yourself, in two separate terminals:" -ForegroundColor Green
Write-Host ""
Write-Host "    cd backend; uv run uvicorn app.main:app --reload"
Write-Host "    cd frontend; npm run dev"
Write-Host ""
Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:3000"
Write-Host ""
Write-Host "To stop Postgres (data persists in the named volume): docker compose down"
Write-Host "To wipe the DB entirely: docker compose down -v"
