# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: compile C-extensions (asyncpg, psycopg2-binary, cryptography)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Build dependencies only (not in final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into a prefix dir — cache-friendly layer
# requirements.txt changes rarely; source code changes often
COPY requirements.txt .
RUN pip install --upgrade pip --quiet \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: minimal image, no build tools
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system deps:
#   libpq5          — psycopg2/asyncpg dynamic linking
#   postgresql-client — psql binary used by migrate.sh health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source (always fresh — after deps for cache efficiency)
COPY . .

# Migration helper script — must be executable
RUN chmod +x /app/migrate.sh

# Non-root user for security
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "bot.main"]
