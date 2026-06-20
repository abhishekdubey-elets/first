# =============================================================================
# stop-all.ps1 — stop the app processes started by start-all.ps1
# =============================================================================
# Stops the FastAPI API, Celery worker/beat, Next.js frontend, and the portable
# Redis. Does NOT stop PostgreSQL (a shared Windows service) or the Ollama app.
# Your data in PostgreSQL is untouched.
#
#   Run:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
# =============================================================================
Write-Host '== Stopping IAS Transfer Intelligence app processes ==' -ForegroundColor Cyan

# Celery worker + beat, uvicorn API: python processes whose command line
# references this project's backend or celery/uvicorn.
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn app.main|app.workers.celery_app' } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId) (backend)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# Next.js dev server (node) on this project.
Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
    Where-Object { $_.CommandLine -match 'next' -and $_.CommandLine -match 'abhi' } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId) (frontend)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# Portable Redis.
Get-Process -Name 'redis-server' -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "Stopping PID $($_.Id) (redis)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

Write-Host 'Done. PostgreSQL and your data are left running/intact.' -ForegroundColor Green
