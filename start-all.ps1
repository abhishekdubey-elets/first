# =============================================================================
# start-all.ps1 — one-command launcher for the IAS Transfer Intelligence stack
# =============================================================================
# Brings up: PostgreSQL (check only) + FastAPI API (port 8000, with the
# discovery pipeline running in-process on its hourly scheduler) + Next.js
# frontend (port 3001). Each app runs in its OWN window so it keeps running
# independently of this terminal and you can watch its logs.
#
#   Run:    powershell -ExecutionPolicy Bypass -File .\start-all.ps1
#   Stop:   powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
#
# Prerequisites: backend\.venv created with `pip install -r requirements.txt`,
# `npm install` done in frontend\, and a .env (repo root or backend\) pointing
# DATABASE_URL / DATABASE_URL_SYNC at your Postgres with OPENAI_API_KEY set.
#
# Safe to re-run: the API (8000) and frontend (3001) are skipped if their port
# is already in use.
# =============================================================================
$ErrorActionPreference = 'Stop'

$Root     = $PSScriptRoot
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Py       = Join-Path $Backend '.venv\Scripts\python.exe'

function Test-Port([int]$Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(600)
        if ($ok) { $c.EndConnect($iar) }
        $c.Close()
        return $ok
    } catch { return $false }
}

function Start-InWindow([string]$Title, [string]$WorkDir, [string]$Command) {
    $inner = "`$host.UI.RawUI.WindowTitle='$Title'; Set-Location '$WorkDir'; " +
             "`$env:PYTHONUTF8='1'; `$env:PYTHONIOENCODING='utf-8'; $Command"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $inner
}

Write-Host '== IAS Transfer Intelligence — launcher ==' -ForegroundColor Cyan

# 1. PostgreSQL — warning only. The Windows service name varies by installer
#    (postgresql-x64-16, postgresql-x64-18, ...); you may also be using
#    Docker or Supabase, in which case no local service is expected.
$pg = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pg) {
    if (Test-Port 5432) {
        Write-Host 'Postgres: something is listening on 5432 (no Windows service found)' -ForegroundColor Green
    } else {
        Write-Host 'Postgres: no local service found and nothing on 5432 — make sure DATABASE_URL points at a reachable database.' -ForegroundColor Yellow
    }
} elseif ($pg.Status -ne 'Running') {
    Write-Host "Postgres: service $($pg.Name) is NOT running — start it from Services (needs admin)." -ForegroundColor Yellow
} else {
    Write-Host "Postgres: running ($($pg.Name))" -ForegroundColor Green
}

# 2. FastAPI backend (runs the discovery scheduler in-process)
if (-not (Test-Path $Py)) {
    Write-Host "Backend venv not found at $Py — create it: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
} elseif (Test-Port 8000) {
    Write-Host 'API: already running (8000)' -ForegroundColor Green
} else {
    Start-InWindow 'IAS API' $Backend "& '$Py' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    Write-Host 'API: starting (8000)' -ForegroundColor Green
}

# 3. Next.js frontend
if (Test-Port 3001) {
    Write-Host 'Frontend: already running (3001)' -ForegroundColor Green
} else {
    Start-InWindow 'IAS Frontend' $Frontend "`$env:NEXT_PUBLIC_API_BASE_URL='http://localhost:8000'; npm run dev -- -p 3001"
    Write-Host 'Frontend: starting (3001)' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Dashboard:  http://localhost:3001' -ForegroundColor Cyan
Write-Host 'API docs:   http://localhost:8000/docs' -ForegroundColor Cyan
Write-Host 'Health:     http://localhost:8000/health' -ForegroundColor Cyan
Write-Host 'Login:      FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD from .env (default admin@digitallearning.in / ChangeMe123!)' -ForegroundColor Cyan
Write-Host '(Give the API/frontend ~10s to finish booting; the first discovery cycle starts right after.)' -ForegroundColor DarkGray
