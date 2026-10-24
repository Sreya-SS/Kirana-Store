# One-command backend start for the demo (Windows PowerShell).
#   Usage:  .\run.ps1
# Seeds SYNTHETIC data, then serves on 0.0.0.0:8000 so your phone can reach it.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "No venv found. Creating one and installing requirements..." -ForegroundColor Yellow
  python -m venv .venv
  & $py -m pip install --upgrade pip
  & $py -m pip install -r requirements.txt
}

Write-Host "Seeding SYNTHETIC demo data..." -ForegroundColor Cyan
& $py seed.py
if ($LASTEXITCODE -ne 0) { throw "Seed failed" }

Write-Host "Starting API on http://0.0.0.0:8000 ..." -ForegroundColor Green
& $py -m uvicorn main:app --host 0.0.0.0 --port 8000
