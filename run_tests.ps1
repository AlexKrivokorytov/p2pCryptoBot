# Stop and remove existing containers and volumes to start fresh (just like GitHub Actions)
docker compose down -v

# Start the database and redis
docker compose up db redis -d

# Wait for database to be ready
echo "Waiting for database to start..."
Start-Sleep -Seconds 5

# Start the api container in the background
docker compose up api -d

echo "Running migrations (Alembic)..."
docker compose exec api alembic upgrade head

if ($LASTEXITCODE -ne 0) {
    echo "❌ Migrations failed! This would have crashed GitHub Actions."
    exit $LASTEXITCODE
}

echo "✅ Migrations passed!"
echo "Running Pytest..."
docker compose exec api python -m pytest

if ($LASTEXITCODE -ne 0) {
    echo "❌ Tests failed!"
    exit $LASTEXITCODE
}

echo "✅ All tests passed!"
