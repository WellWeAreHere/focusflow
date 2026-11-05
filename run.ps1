# One-command launcher: builds the engine if needed, starts FocusFlow, opens it in your browser.
# Usage (from the repo root):  .\run.ps1          Add -NoBrowser to skip opening the browser.
# Stop it with Ctrl+C. Your tasks are kept in backend\focusflow.db.
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# The C++ library is not stored in git, so build it the first time.
if (-not (Test-Path "$root\engine\build\focusflow.dll")) {
    Write-Host "First run: building the C++ engine..."
    & "$root\engine\build.ps1"
    if ($LASTEXITCODE -ne 0) { Write-Host "Engine build failed."; exit 1 }
}

# FastAPI imports its files by name, so the server must start inside backend\.
Set-Location "$root\backend"

if (-not $NoBrowser) {
    # Wait a moment for the server to come up, then open the page (runs in the background).
    Start-Job -ScriptBlock { Start-Sleep -Seconds 2; Start-Process "http://127.0.0.1:8000" } | Out-Null
}

# uvicorn prints its normal log lines to stderr; with "Stop" PowerShell could treat those as errors.
$ErrorActionPreference = "Continue"
Write-Host "FocusFlow running at http://127.0.0.1:8000  (Ctrl+C to stop)"
python -m uvicorn main:app --port 8000
