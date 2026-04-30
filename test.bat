@echo off
setlocal

echo ====================================================================
echo 🚀 Starting Premium P2P Bot Test Suite...
echo ====================================================================
echo.

echo 🔍 Checking Environment...
docker compose exec postgres psql -U p2pbot -c "CREATE DATABASE p2pbot_test;" >nul 2>&1

echo 🧪 Running tests in container (XML coverage enabled)...
docker compose run --rm ^
  -e POSTGRES_URI=postgresql+asyncpg://p2pbot:password@postgres:5432/p2pbot_test ^
  -v "%cd%:/app" ^
  bot bash -c "pip install -q pytest pytest-asyncio pytest-cov pytest-sugar aiohttp && python -m pytest --cov=. --cov-report=xml"

set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 0 (
    echo.
    echo 📊 Generating Premium Visual Dashboard...
    python utils/coverage_dashboard.py
    echo.
    echo ====================================================================
    echo ✅ SUCCESS: All tests passed! Dashboard opened in your browser.
    echo ====================================================================
) else (
    echo.
    echo ====================================================================
    echo ❌ FAILED: Some tests encountered issues. Fix them and try again.
    echo ====================================================================
)

pause
