#!/bin/sh
# migrate.sh — safe Alembic migration runner.
#
# Problem: If the PostgreSQL volume is wiped but the alembic_version table
# survives (e.g. in a fresh volume without prior data), Alembic thinks all
# migrations are already applied and skips them — leaving the DB with no
# tables, which crashes the bot.
#
# Solution: Before running `upgrade head`, check whether the `users` table
# actually exists. If it doesn't (stale alembic_version or completely fresh DB),
# drop alembic_version and re-apply all migrations from scratch.

set -e

DB_URL="${ALEMBIC_DB_URL}"

echo "[migrate.sh] Checking database state..."

# Check if the 'users' table exists using psql.
# We use the sync psycopg2 URL (ALEMBIC_DB_URL) because psql can parse it.
# Extract connection params from the URL:
#   postgresql+psycopg2://user:pass@host:port/dbname
PSQL_HOST=$(echo "$DB_URL" | sed 's|.*@||' | cut -d: -f1)
PSQL_PORT=$(echo "$DB_URL" | sed 's|.*@||' | cut -d: -f2 | cut -d/ -f1)
PSQL_USER=$(echo "$DB_URL" | sed 's|.*://||' | cut -d: -f1)
PSQL_PASS=$(echo "$DB_URL" | sed 's|.*://[^:]*:||' | sed 's|@.*||')
PSQL_DB=$(echo "$DB_URL" | sed 's|.*/||')

export PGPASSWORD="$PSQL_PASS"

TABLE_EXISTS=$(psql -h "$PSQL_HOST" -p "$PSQL_PORT" -U "$PSQL_USER" -d "$PSQL_DB" \
  -tAc "SELECT EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema='public' AND table_name='users'
  );" 2>/dev/null || echo "f")

if [ "$TABLE_EXISTS" = "f" ]; then
    echo "[migrate.sh] 'users' table not found — resetting alembic_version..."
    psql -h "$PSQL_HOST" -p "$PSQL_PORT" -U "$PSQL_USER" -d "$PSQL_DB" \
      -c "DROP TABLE IF EXISTS alembic_version CASCADE;" 2>/dev/null || true
    echo "[migrate.sh] Running full migration from scratch..."
else
    echo "[migrate.sh] Database looks healthy. Applying pending migrations..."
fi

alembic upgrade head

echo "[migrate.sh] Migrations complete."
