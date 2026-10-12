# Full one-shot launcher: Postgres (Docker) -> migrations -> seed (idempotent) ->
# backend + frontend dev servers (hidden windows) -> opens the browser.
# Not meant to be run directly by a person in a visible terminal - see Start App.vbs,
# which launches this with a hidden PowerShell host. Safe to double-click repeatedly:
# every step here is idempotent / skips work that's already done.

# Deliberately NOT "Stop": redirecting a native command's stderr into a file (*>>) turns
# each stderr line into a PowerShell error record, and under "Stop" that aborts the script
# even on a successful exit (e.g. docker compose's own informational status lines). Every
# native call below is checked via $LASTEXITCODE explicitly instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$launchLog = Join-Path $logDir "launch.log"
"==> Launch started $(Get-Date)" | Out-File $launchLog

function Log($msg) {
    "$(Get-Date -Format 'HH:mm:ss')  $msg" | Out-File $launchLog -Append
}

function Test-Url($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

# Runs a command through cmd.exe with output redirected to the log AT THE OS LEVEL (baked
# into the cmd.exe command line, not via PowerShell's >> / *>> operators). PowerShell's own
# redirection operators wrap a native command's stderr lines into ErrorRecords, which is
# noisy at best and, under $ErrorActionPreference "Stop", aborts the script on a successful
# exit. This sidesteps that entirely - PowerShell never sees the native process's streams.
function Invoke-Logged($commandLine) {
    & cmd.exe /c "$commandLine >> `"$launchLog`" 2>&1"
    return $LASTEXITCODE
}

try {
    if ((Test-Url "http://localhost:8000/health") -and (Test-Url "http://localhost:3000")) {
        Log "Already fully running - skipping straight to opening the browser."
        Start-Process "http://localhost:3000"
        exit 0
    }

    Log "Starting Postgres (docker compose up -d)..."
    $code = Invoke-Logged "docker compose up -d"
    if ($code -ne 0) { throw "docker compose up failed - is Docker Desktop running?" }

    Log "Waiting for Postgres to become healthy..."
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        $status = docker inspect --format='{{.State.Health.Status}}' jp_grammar_db 2>$null
        if ($status -eq "healthy") { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Postgres did not become healthy in time" }
    Log "Postgres is up."

    Push-Location (Join-Path $root "backend")
    try {
        Log "Running migrations (alembic upgrade head)..."
        $code = Invoke-Logged "uv run alembic upgrade head"
        if ($code -ne 0) { throw "alembic upgrade head failed" }

        Log "Seeding grammar data (idempotent)..."
        $code = Invoke-Logged "uv run python -m app.scripts.seed_import"
        if ($code -ne 0) { throw "seed_import failed" }

        Log "Seeding N4 + N2 grammar (idempotent)..."
        $env:PYTHONUTF8 = "1"
        $env:PYTHONIOENCODING = "utf-8"
        $code = Invoke-Logged "uv run python -m app.scripts.seed_import_authored"
        if ($code -ne 0) { throw "seed_import_authored failed" }

        Log "Seeding vocabulary data (idempotent)..."
        $code = Invoke-Logged "uv run python -m app.scripts.seed_vocabulary"
        if ($code -ne 0) { throw "seed_vocabulary failed" }

        Log "Importing curated relations (idempotent)..."
        $code = Invoke-Logged "uv run python -m app.scripts.import_curated_relations --purge-remaining-heuristic"
        if ($code -ne 0) { throw "import_curated_relations failed" }
    } finally {
        Pop-Location
    }

    if (Test-Url "http://localhost:8000/health") {
        Log "Backend already running, leaving it be."
    } else {
        Log "Starting backend (hidden)..."
        # cmd.exe /c wrapper: reliable arg/PATH resolution for 'uv' regardless of how
        # PowerShell's own Start-Process would otherwise need to resolve a shell script/exe.
        Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c uv run python -m uvicorn app.main:app --port 8000" `
            -WorkingDirectory (Join-Path $root "backend") `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir "backend.out.log") `
            -RedirectStandardError (Join-Path $logDir "backend.err.log")
    }

    if (Test-Url "http://localhost:3000") {
        Log "Frontend already running, leaving it be."
    } else {
        # Next.js dev mode on this machine has repeatedly corrupted .next across restarts
        # (stale/missing webpack chunk -> "Cannot find module './NN.js'" or similar at runtime).
        # A fresh start is the fix every time; costs a few extra seconds of cold compile, cheap
        # insurance against the app being visibly broken on open.
        $nextCache = Join-Path $root "frontend\.next"
        if (Test-Path $nextCache) {
            Log "Clearing frontend build cache (.next) before starting..."
            Remove-Item -Recurse -Force $nextCache
        }
        Log "Starting frontend (hidden)..."
        Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c npm run dev" `
            -WorkingDirectory (Join-Path $root "frontend") `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") `
            -RedirectStandardError (Join-Path $logDir "frontend.err.log")
    }

    Log "Waiting for both servers to respond (npm's first cold start can take a while)..."
    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        if ((Test-Url "http://localhost:8000/health") -and (Test-Url "http://localhost:3000")) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Backend/frontend did not become ready in time - check logs\backend.err.log / frontend.err.log" }

    Log "Ready. Opening browser."
    Start-Process "http://localhost:3000"
}
catch {
    Log "ERROR: $($_.Exception.Message)"
    # No terminal exists to show this error in - surface it visibly instead.
    Start-Process "notepad.exe" $launchLog
    exit 1
}
