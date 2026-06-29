# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder (uv → resolve & install deps) ----------
FROM python:3.13-slim AS builder

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
# Alembic 스캐폴드 (CMP-537). migrate 사이드카가 같은 이미지를 공유한다.
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

# ---------- Stage 2: runtime (non-root, gunicorn + uvicorn worker) ----------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}" \
    API_PORT=8000

# WeasyPrint(사전검토 PDF 리포트) 런타임 의존 — Pango/Pangoft2 + gdk-pixbuf + ffi,
# 그리고 한글 폰트(fonts-nanum: NanumGothic). 폰트 미설치 시 PDF 한글이 □(tofu)로
# 깨지므로 필수. WeasyPrint 53+ 는 cairo 를 쓰지 않아 libcairo2 는 제외한다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        fontconfig \
        fonts-nanum \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1001 app && \
    useradd  --system --uid 1001 --gid app --home /home/app --shell /usr/sbin/nologin app && \
    mkdir -p /app /home/app && chown -R app:app /app /home/app

WORKDIR /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /build/src ./src
COPY --from=builder --chown=app:app /build/alembic.ini ./alembic.ini
COPY --from=builder --chown=app:app /build/migrations ./migrations

USER app
EXPOSE 8000

CMD ["gunicorn", "src.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--access-logfile", "-", \
     "--error-logfile",  "-"]
