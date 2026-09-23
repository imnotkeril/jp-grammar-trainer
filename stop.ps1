# Stops the backend/frontend dev servers and the Postgres container (data persists in the
# named volume - use `docker compose down -v` by hand if you actually want to wipe it).

$ErrorActionPreference = "SilentlyContinue"

foreach ($port in 8000, 3000) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
docker compose down
