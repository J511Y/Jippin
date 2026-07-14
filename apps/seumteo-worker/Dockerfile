# syntax=docker/dockerfile:1.7
# apps/seumteo-worker — Playwright headless Chromium 워커 (세움터 건축물대장 발급).
# apps/api Dockerfile 과 동일 스타일(python:3.13-slim + non-root + fonts-nanum).
#
# 빌드 컨텍스트는 이 디렉토리(apps/seumteo-worker)여야 한다:
#   fly deploy apps/seumteo-worker    (첫 위치 인자가 곧 build context)

# **bookworm 고정 필수**: `python:3.13-slim` 은 이제 Debian 13(trixie)로 옮겨갔는데,
# playwright 1.49.1 의 `install --with-deps` apt 목록엔 trixie 에서 사라진 폰트 패키지
# (`ttf-unifont`/`ttf-ubuntu-font-family`)가 들어 있어 빌드가 깨진다("has no installation
# candidate"). playwright 1.49 가 타깃하는 Debian 12(bookworm)로 고정한다. playwright 가
# trixie 를 지원하면 그때 slim(=trixie)으로 되돌린다.
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # 브라우저를 시스템 경로에 설치 → non-root(app) 유저도 접근 가능
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 의존성 먼저(레이어 캐시). playwright 버전과 브라우저 설치는 같은 레이어에서 고정.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Chromium + OS 의존성(--with-deps 가 libnss3/libatk/libgbm/libasound 등 전체 세트 자동 설치),
# 이어서 한글 폰트(건축물대장 렌더링 필수 — 미설치 시 □ tofu). 헤드리스 전용 shell 로 용량 절감.
RUN playwright install --with-deps chromium \
 && apt-get update \
 && apt-get install -y --no-install-recommends fonts-nanum fontconfig \
 && fc-cache -f \
 && rm -rf /var/lib/apt/lists/* \
 && chmod -R a+rX /ms-playwright

# non-root 실행 유저
RUN groupadd --system --gid 1001 app \
 && useradd  --system --uid 1001 --gid app --home /home/app --shell /usr/sbin/nologin app \
 && mkdir -p /home/app && chown -R app:app /home/app /app

COPY --chown=app:app src ./src

USER app
EXPOSE 8080

# Flycast/헬스체크(IPv4)와 .internal 잡 요청(IPv6)을 모두 받아야 한다. uvicorn CLI의
# 단일 --host 바인드로는 불가능(0.0.0.0 → v6 refused, :: → asyncio IPV6_V6ONLY로 v4 refused)
# 하므로 듀얼스택 소켓을 직접 만드는 런처로 기동한다. 상세는 src/serve.py docstring.
CMD ["python", "-m", "src.serve"]
