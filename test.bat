@echo off
setlocal

echo ====================================================================
echo Starting P2P Bot Test Suite Verification...
echo ====================================================================
echo.
echo Installing testing dependencies in the container and running pytest...
echo Please wait...
echo.

echo Creating test database if it does not exist...
docker compose exec postgres psql -U p2pbot -c "CREATE DATABASE p2pbot_test;" >nul 2>&1

docker compose run --rm -e POSTGRES_URI=postgresql+asyncpg://p2pbot:password@postgres:5432/p2pbot_test -v "%cd%:/app" bot bash -c "pip install -q pytest pytest-asyncio pytest-cov pytest-sugar aiohttp && python -m pytest"

set EXIT_CODE=%ERRORLEVEL%
echo.
echo ====================================================================
if %EXIT_CODE% EQU 0 (
    echo SUCCESS: All tests passed flawlessly! Great job!
) else (
    echo FAILED: Some tests encountered issues. See the report above for details.
)
echo ====================================================================
pause
