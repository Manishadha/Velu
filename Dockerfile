# syntax=docker/dockerfile:1.7

########################
# Builder stage
########################
FROM python:3.12-slim AS builder
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# hadolint ignore=DL3013,DL3042
RUN python -m pip install --upgrade pip \
 && pip wheel --wheel-dir /wheels -r requirements.txt

########################
# Runtime stage
########################
FROM python:3.12-slim AS runtime

# Minimal OS deps for healthcheck + proper init
# hadolint ignore=DL3008
RUN apt-get update -y \
 && apt-get install -y --no-install-recommends curl ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -u 10001 -m app

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    TASK_DB=/data/jobs.db \
    RULES_DIR=/app/data/rules

# Install wheels, then clean
COPY --from=builder /wheels /wheels
# hadolint ignore=DL3013,DL3042
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels

# Copy source and give ownership to app user
COPY --chown=app:app . .

# Writable volume for sqlite db
RUN mkdir -p /data && chown -R app:app /data
VOLUME ["/data"]

EXPOSE 8000

# finally run as non-root
USER app

# Healthcheck hits FastAPI /health
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsSL "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["uvicorn","services.app_server.main:app","--host","0.0.0.0","--port","8000"]
