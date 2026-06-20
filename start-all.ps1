# =============================================================================
# start-all.ps1 — one-command launcher for the IAS Transfer Intelligence stack
# =============================================================================
# Brings up: PostgreSQL (check) + Redis + Ollama + FastAPI API + Celery worker
# + Celery beat + Next.js frontend. Each app runs in its OWN window so it keeps
# running independently of any terminal/session and you can watch its logs.
#
#   Run:    powershell -ExecutionPolicy Bypass -File .\start-all.ps1
#   Stop:   close the individual windows (or run stop-all.ps1).
#
# Safe to re-run: services with a fixed port (Redis 6379, Ollama 11434, API
# 8000, frontend 3001) are skipped if already up. Worker/beat have no port, so
# only run this when they are NOT already running (else you double them up).
# =============================================================================
$ErrorActionPreference = 'Stop'

$Root     = 'C:\Users\User\Desktop\abhi\first'
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Py       = Join-Path $Backend '.venv\Scripts\python.exe'
$Redis    = 'C:\Users\User\redis\redis-server.exe'
$Ollama   = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'

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
             "`$env:PYTHONUTF8='1'; `$env:PYTHONIOENCODING='utf-8'; " +
             "`$env:TESSDATA_PREFIX='C:\Users\User\tessdata'; $Command"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $inner
}

Write-Host '== IAS Transfer Intelligence — launcher ==' -ForegroundColor Cyan

# 1. PostgreSQL (installed Windows service — should already auto-start)
$pg = Get-Service -Name 'postgresql-x64-18' -ErrorAction SilentlyContinue
if (-not $pg) {
    Write-Host 'Postgres: service postgresql-x64-18 not found!' -ForegroundColor Red
} elseif ($pg.Status -ne 'Running') {
    Write-Host 'Postgres: NOT running — start it from Services (needs admin).' -ForegroundColor Yellow
} else {
    Write-Host 'Postgres: running' -ForegroundColor Green
}

# 2. Redis
if (Test-Port 6379) {
    Write-Host 'Redis: already running (6379)' -ForegroundColor Green
} elseif (Test-Path $Redis) {
    Start-Process -FilePath $Redis -ArgumentList '--port', '6379' -WindowStyle Minimized
    Write-Host 'Redis: started (6379)' -ForegroundColor Green
} else {
    Write-Host "Redis: not found at $Redis" -ForegroundColor Yellow
}

# 3. Ollama (local LLM)
if (Test-Port 11434) {
    Write-Host 'Ollama: already running (11434)' -ForegroundColor Green
} elseif (Test-Path $Ollama) {
    Start-Process -FilePath $Ollama -ArgumentList 'serve' -WindowStyle Minimized
    Write-Host 'Ollama: started (11434)' -ForegroundColor Green
} else {
    Write-Host 'Ollama: not found — LLM extraction will be unavailable.' -ForegroundColor Yellow
}

Start-Sleep -Seconds 2

# 4. FastAPI backend
if (Test-Port 8000) {
    Write-Host 'API: already running (8000)' -ForegroundColor Green
} else {
    Start-InWindow 'IAS API' $Backend "& '$Py' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    Write-Host 'API: starting (8000)' -ForegroundColor Green
}

# 5. Celery worker (Windows requires --pool=solo)
Start-InWindow 'IAS Worker' $Backend "& '$Py' -m celery -A app.workers.celery_app.celery worker --loglevel=info --pool=solo"
Write-Host 'Celery worker: starting' -ForegroundColor Green

# 6. Celery beat (10-min discovery cadence)
Start-InWindow 'IAS Beat' $Backend "& '$Py' -m celery -A app.workers.celery_app.celery beat --loglevel=info"
Write-Host 'Celery beat: starting' -ForegroundColor Green

# 7. Next.js frontend
if (Test-Port 3001) {
    Write-Host 'Frontend: already running (3001)' -ForegroundColor Green
} else {
    Start-InWindow 'IAS Frontend' $Frontend "`$env:NEXT_PUBLIC_API_BASE_URL='http://localhost:8000'; npm run dev -- -p 3001"
    Write-Host 'Frontend: starting (3001)' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Dashboard:  http://localhost:3001' -ForegroundColor Cyan
Write-Host 'API docs:   http://localhost:8000/docs' -ForegroundColor Cyan
Write-Host 'Login:      admin@digitallearning.in / ChangeMe123!' -ForegroundColor Cyan
Write-Host '(Give the API/frontend ~10s to finish booting.)' -ForegroundColor DarkGray
