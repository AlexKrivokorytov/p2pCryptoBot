# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: compile C-extensions (asyncpg, psycopg2-binary, cryptography)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12.3-slim-bookworm AS builder

WORKDIR /build

# Build dependencies only (not in final image)
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into a prefix dir — cache-friendly layer
# requirements.txt changes rarely; source code changes often
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel --quiet \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: minimal image, no build tools
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12.3-slim-bookworm AS runtime

WORKDIR /app

# Runtime system deps:
#   libpq5          — psycopg2/asyncpg dynamic linking
#   postgresql-client — psql binary used by migrate.sh health check
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Upgrade core packages again in runtime to ensure no vulnerable defaults remain
RUN pip install --upgrade pip setuptools wheel --quiet --no-cache-dir

# Bake the seller's secret into the sealed image for license validation
ARG SELLER_SECRET
ENV SELLER_SECRET=${SELLER_SECRET}

# Copy application source (always fresh — after deps for cache efficiency)
COPY . .

# Migration helper script — must be executable
RUN chmod +x /app/migrate.sh

# Non-root user for security
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "bot.main"]
