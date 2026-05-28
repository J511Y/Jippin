# =============================================================================
# Jippin — 루트 단축 명령 (CMP-530 산출물 #4)
# -----------------------------------------------------------------------------
# 사용법:
#   make up                # docker compose up --build (override.yml 자동 머지)
#   make up-detach         # -d
#   make up-prod           # override.yml 무시 (정본 compose 만)
#   make up-edge           # nginx 프로파일 동반
#   make down              # docker compose down
#   make down-clean        # -v 볼륨 폐기
#   make logs SVC=api      # 단일 서비스 로그 follow
#   make ps                # 컨테이너 상태
#   make restart SVC=web   # 단일 서비스 재기동
#   make exec  SVC=api CMD="alembic upgrade head"
#   make config            # docker compose config (검증)
#   make doctor            # docker / compose / .env 사전 점검
#
# Windows 사용자 (make 부재) 는 README §3 의 원시 명령을 그대로 사용한다.
# =============================================================================

COMPOSE_DIR := infra/compose
BASE_FILE   := $(COMPOSE_DIR)/docker-compose.yml
OVERRIDE_F  := $(COMPOSE_DIR)/docker-compose.override.yml
ENV_FILE    := $(COMPOSE_DIR)/.env

# override 가 존재할 때만 머지한다 (prod 안전 — 봉인 §A 참조).
COMPOSE_FILES := -f $(BASE_FILE)
ifneq ("$(wildcard $(OVERRIDE_F))","")
  COMPOSE_FILES += -f $(OVERRIDE_F)
endif

DC := docker compose --env-file $(ENV_FILE) $(COMPOSE_FILES)
DC_PROD := docker compose --env-file $(ENV_FILE) -f $(BASE_FILE)

.PHONY: help up up-detach up-prod up-edge down down-clean logs ps restart exec config doctor

help:
	@echo "Jippin compose 단축 명령 (CMP-530):"
	@echo "  make up            — foreground 부팅 (override 자동 머지)"
	@echo "  make up-detach     — background 부팅"
	@echo "  make up-prod       — override 무시 (봉인 이미지만)"
	@echo "  make up-edge       — nginx 프로파일 동반"
	@echo "  make down          — 정지"
	@echo "  make down-clean    — 정지 + 볼륨 폐기"
	@echo "  make logs SVC=api  — 서비스 로그 follow"
	@echo "  make ps            — 컨테이너 상태"
	@echo "  make restart SVC=web"
	@echo "  make exec SVC=api CMD=\"alembic upgrade head\""
	@echo "  make config        — compose 파싱 검증"
	@echo "  make doctor        — 사전 점검"

up:
	$(DC) up --build

up-detach:
	$(DC) up --build -d

up-prod:
	$(DC_PROD) up --build -d

up-edge:
	$(DC) --profile edge up --build -d

down:
	$(DC) down

down-clean:
	$(DC) down -v

logs:
	@if [ -z "$(SVC)" ]; then $(DC) logs -f --tail=200; else $(DC) logs -f --tail=200 $(SVC); fi

ps:
	$(DC) ps

restart:
	@if [ -z "$(SVC)" ]; then echo "SVC=<web|api|redis> 가 필요합니다" >&2; exit 2; fi
	$(DC) restart $(SVC)

exec:
	@if [ -z "$(SVC)" ] || [ -z "$(CMD)" ]; then echo "SVC=<...> CMD=\"...\" 가 필요합니다" >&2; exit 2; fi
	$(DC) exec $(SVC) sh -lc "$(CMD)"

config:
	$(DC) config --quiet && echo "OK: compose 파싱 통과"

doctor:
	@command -v docker >/dev/null 2>&1 || { echo "✗ docker CLI 미설치" >&2; exit 1; }
	@docker compose version >/dev/null 2>&1 || { echo "✗ docker compose v2 미설치" >&2; exit 1; }
	@test -f $(ENV_FILE) || { echo "✗ $(ENV_FILE) 없음 — $(COMPOSE_DIR)/.env.example 복사 후 채워 넣으세요" >&2; exit 1; }
	@grep -qE '^DATABASE_URL=postgres' $(ENV_FILE) || { echo "✗ DATABASE_URL 미설정" >&2; exit 1; }
	@grep -qE '^DATABASE_POOL_URL=postgres' $(ENV_FILE) || { echo "✗ DATABASE_POOL_URL 미설정" >&2; exit 1; }
	@echo "✓ docker / compose / Neon URL 점검 통과"
