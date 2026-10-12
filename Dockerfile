# Production Multi-Stage Dockerfile for Rotterdam Live
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies for C extensions (e.g. asyncpg, shapely)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Final Runtime Stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root application user for defense-in-depth security
RUN useradd -m -u 10001 appuser

# Copy application source code
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Default command (overridden in docker-compose for worker)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
