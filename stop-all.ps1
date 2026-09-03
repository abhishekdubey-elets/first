# =============================================================================
# stop-all.ps1 — stop the app processes started by start-all.ps1
# =============================================================================
# Stops the FastAPI API (uvicorn) and the Next.js dev server belonging to THIS
# repository. Does NOT stop PostgreSQL (a shared service) — your data is
# untouched.
#
#   Run:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
# =============================================================================
Write-Host '== Stopping IAS Transfer Intelligence app processes ==' -ForegroundColor Cyan

$Root = $PSScriptRoot
$RootPattern = [regex]::Escape($Root)

# uvicorn API: python processes running app.main from this repo's backend.
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object {
        $_.CommandLine -match 'uvicorn app\.main' -and
        ($_.CommandLine -match $RootPattern -or $_.ExecutablePath -match $RootPattern)
    } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId) (backend)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# Next.js dev server (node) for this repo's frontend.
Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
    Where-Object { $_.CommandLine -match 'next' -and $_.CommandLine -match $RootPattern } |
    ForEach-Object {
        Write-Host "Stopping PID $($_.ProcessId) (frontend)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host 'Done. PostgreSQL and your data are left running/intact.' -ForegroundColor Green
