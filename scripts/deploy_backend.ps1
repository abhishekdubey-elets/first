# =============================================================================
# deploy_backend.ps1 — publish ./backend to the Hugging Face Space
# =============================================================================
# The Space (abhishek-elets/ias-transfer-intelligence) builds from its OWN git
# repository whose root is this repo's backend/ directory. This script clones
# (or refreshes) that repository, mirrors backend/ into it, commits and pushes.
# Every push triggers an image rebuild + restart; Space secrets are preserved.
#
#   Usage:  powershell -ExecutionPolicy Bypass -File .\scripts\deploy_backend.ps1 -Message "fix: ..."
#   Auth:   set $env:HF_TOKEN to a Hugging Face token with write access, or
#           rely on a git credential helper that already knows huggingface.co.
# =============================================================================
param(
    [string]$Message = "Deploy backend from $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    [string]$Space = "abhishek-elets/ias-transfer-intelligence",
    [string]$WorkDir = (Join-Path $env:TEMP "ias-space-deploy")
)
$ErrorActionPreference = 'Stop'

$Root    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Remote  = "https://huggingface.co/spaces/$Space"
if ($env:HF_TOKEN) { $Remote = "https://user:$($env:HF_TOKEN)@huggingface.co/spaces/$Space" }

if (-not (Test-Path (Join-Path $WorkDir '.git'))) {
    Write-Host "Cloning $Space into $WorkDir ..." -ForegroundColor Cyan
    git clone --quiet $Remote $WorkDir
} else {
    Write-Host "Refreshing $WorkDir ..." -ForegroundColor Cyan
    git -C $WorkDir fetch --quiet $Remote main
    git -C $WorkDir reset --quiet --hard FETCH_HEAD
}

# Mirror backend/ -> Space root. /MIR deletes files that no longer exist in
# backend/, but never touches the Space's .git directory or LFS attributes.
robocopy $Backend $WorkDir /MIR /NFL /NDL /NJH /NJS /XD .git .venv __pycache__ .pytest_cache data storage /XF .env '*.pyc' 'celerybeat-schedule.*' | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
git -C $WorkDir checkout --quiet -- .gitattributes 2>$null

git -C $WorkDir add -A
$pending = git -C $WorkDir status --porcelain
if (-not $pending) { Write-Host "Nothing to deploy — Space already matches backend/." -ForegroundColor Green; exit 0 }

git -C $WorkDir commit --quiet -m $Message
git -C $WorkDir push $Remote HEAD:main
Write-Host "Pushed. The Space is rebuilding: https://huggingface.co/spaces/$Space" -ForegroundColor Green
Write-Host "Check: https://$($Space.Replace('/', '-')).hf.space/health" -ForegroundColor Green
