@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo AirCrewOps ^| Nova Air Operations Simulator - Startup Launcher
echo ==============================================================================

cd /d "%~dp0"

echo [1/3] Checking environment and dependencies...
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH. Please install Python 3.12+ and try again.
    pause
    exit /b 1
)

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] npm not found in PATH. Please install Node.js 18+ and try again.
    pause
    exit /b 1
)

echo [2/3] Launching FastAPI Backend on http://localhost:8000 ...
start "AirCrewOps Backend Server" cmd /k "python -m uvicorn backend.app.main:app --reload --port 8000"

echo [3/3] Launching Vite Frontend on http://localhost:5173 ...
cd frontend
start "AirCrewOps Frontend Server" cmd /k "npm run dev"

echo ==============================================================================
echo [SUCCESS] AirCrewOps services initiated successfully!
echo   - Backend & Interactive Swagger API: http://localhost:8000/docs
echo   - Frontend Operations Control Center: http://localhost:5173
echo ==============================================================================
endlocal
