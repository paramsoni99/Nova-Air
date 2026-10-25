# AirCrewOps | Nova Air Operations Simulator - PowerShell Launcher
$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "AirCrewOps | Nova Air Operations Simulator - Startup Launcher" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

# 1. Check Python and Node
Write-Host "[1/3] Checking environment..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.12+ was not found in PATH. Please install Python and try again."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm (Node.js) was not found in PATH. Please install Node.js and try again."
}

# 2. Launch Backend
Write-Host "[2/3] Launching FastAPI Backend on http://localhost:8000 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$RepoRoot'; python -m uvicorn backend.app.main:app --reload --port 8000"

# 3. Launch Frontend
Write-Host "[3/3] Launching Vite Frontend on http://localhost:5173 ..." -ForegroundColor Yellow
$FrontendPath = Join-Path $RepoRoot "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$FrontendPath'; npm run dev"

Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "[SUCCESS] AirCrewOps services initiated successfully!" -ForegroundColor Green
Write-Host "  - Backend & Interactive Swagger API: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  - Frontend Operations Control Center: http://localhost:5173" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Green
