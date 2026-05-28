# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder (uv → resolve & install deps) ----------
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir "uv>=0.5,<1.0"

WORKDIR /build

# Lockfile-first for cache reuse; falls back to fresh resolution if absent.
COPY pyproject.toml ./
COPY uv.lock* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-dev; \
    else \
        uv sync --no-install-project --no-dev; \
    fi

COPY src ./src

# ---------- Stage 2: runtime (non-root, gunicorn + uvicorn worker) ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    API_PORT=8000

RUN groupadd --system --gid 1001 app && \
    useradd  --system --uid 1001 --gid app --home /home/app --shell /usr/sbin/nologin app && \
    mkdir -p /app /home/app && chown -R app:app /app /home/app

WORKDIR /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /build/src ./src

USER app
EXPOSE 8000

CMD ["gunicorn", "src.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--access-logfile", "-", \
     "--error-logfile",  "-"]
