# =============================================================================
# stop-all.ps1 — stop the app processes started by start-all.ps1
# =============================================================================
# Stops the FastAPI API and the Next.js frontend. Does NOT stop PostgreSQL
# (a shared Windows service). Your data in PostgreSQL is untouched.
#
#   Run:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
# =============================================================================
Write-Host '== Stopping IAS Transfer Intelligence app processes ==' -ForegroundColor Cyan

# uvicorn API (python process for this project's backend).
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn app.main' } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId) (API)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# Next.js dev server (node) on this project.
Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
    Where-Object { $_.CommandLine -match 'next' -and $_.CommandLine -match 'abhi' } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId) (frontend)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host 'Done. PostgreSQL and your data are left running/intact.' -ForegroundColor Green
