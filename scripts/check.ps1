# P2P Bot Quality Check Script (GitHub-like)
# Run this before every commit

Write-Host "Running P2P Bot Quality Checks..." -ForegroundColor Cyan

# 1. Ruff Lint
Write-Host "Checking Ruff Lint..." -ForegroundColor Yellow
ruff check . --fix
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ruff Lint failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

# 2. Ruff Format Check
Write-Host "Checking Code Formatting..." -ForegroundColor Yellow
ruff format .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ruff Format failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

# 3. Mypy Strict Type Check
Write-Host "Checking Mypy Strict..." -ForegroundColor Yellow
mypy --strict bot/ services/ providers/ utils/ tasks/ db/
if ($LASTEXITCODE -ne 0) {
    Write-Host "Mypy Strict Check failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

# 4. Pytest (Unit + Integration)
Write-Host "Running Tests..." -ForegroundColor Yellow
pytest tests/
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tests failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "ALL CHECKS PASSED!" -ForegroundColor Green
