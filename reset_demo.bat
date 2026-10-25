@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo AirCrewOps ^| Nova Air - Demo Dataset ^& Persistence Reset
echo ==============================================================================

cd /d "%~dp0"

echo [1/2] Regenerating deterministic Nova Air demo CSV dataset (seed=42)...
python scripts/generate_dataset.py --profile demo --seed 42
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to generate demo dataset.
    pause
    exit /b 1
)

echo [2/2] Resetting SQLite persistence database...
if exist "data\aircrewops.db" (
    del /f /q "data\aircrewops.db"
    echo Removed data\aircrewops.db for clean cold-restart initialization.
)

echo ==============================================================================
echo [SUCCESS] Demo dataset regenerated and persistence state reset!
echo Next launch of AirCrewOps will automatically seed from clean demo CSVs.
echo ==============================================================================
endlocal
