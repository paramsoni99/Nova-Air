# AirCrewOps | Nova Air - Demo Dataset & Persistence Reset
$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "AirCrewOps | Nova Air - Demo Dataset & Persistence Reset" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "[1/2] Regenerating deterministic Nova Air demo CSV dataset (seed=42)..." -ForegroundColor Yellow
python scripts/generate_dataset.py --profile demo --seed 42

Write-Host "[2/2] Resetting SQLite persistence database..." -ForegroundColor Yellow
$DbPath = Join-Path $RepoRoot "data\aircrewops.db"
if (Test-Path $DbPath) {
    Remove-Item -Force $DbPath
    Write-Host "Removed data/aircrewops.db for clean cold-restart initialization." -ForegroundColor Green
}

Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "[SUCCESS] Demo dataset regenerated and persistence state reset!" -ForegroundColor Green
Write-Host "Next launch of AirCrewOps will automatically seed from clean demo CSVs." -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Green
