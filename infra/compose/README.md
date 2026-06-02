# Jippin — 단일 인스턴스 오케스트레이션 (CMP-530)

`docker compose up` 한 번으로 **web + api + redis** 가 부팅되고 `/healthz` 200 이 반환되는 단일 인스턴스 구성. CEO 브리프 §2 D2 의 산출물이며, CMP-524 의 자식 이슈이다.

봉인 (반드시 준수):

- 단일 호스트 1대 가정. k8s / ECS 매니페스트 금지.
- Postgres 컨테이너 금지 — 외부 managed Postgres (`DATABASE_URL` / `DATABASE_POOL_URL`) 직결. SSOT 는 **Supabase project** (CMP-603 CI/CD cutover 완료; ADR-0004 Proposed).
- 모델 가중치 / 대용량 바이너리는 이미지에 포함하지 않는다 (런타임 볼륨 마운트).
- 시크릿은 `infra/compose/.env` 로컬에서만 읽고 커밋 금지 (AGENTS.md §4.4).

> 신규 개발자는 **§2 → §3 → §4** 순서로 30분 내 부팅을 목표로 한다 (CEO §10 #3).

---

## §1. 구성

| 서비스 | 이미지 / 빌드 컨텍스트 | 호스트 포트 | 헬스체크 | 의존성 |
|---|---|---|---|---|
| `web` | `apps/web/Dockerfile` (Next.js 16.2 LTS standalone + Supabase Auth SSR) | 3000 → 3000 | `wget /healthz` 30s | `api` healthy |
| `api` | `apps/api/Dockerfile` (FastAPI + Supabase Postgres) | 8000 → 8000 | `urlopen /healthz` 30s | `redis` healthy |
| `redis` | `redis:7-alpine` | 6379 → 6379 | `redis-cli ping` 10s | — |
| `nginx` (옵션) | `nginx:1.27-alpine` + `infra/docker/nginx.conf` | 80 → 80 | — | `web`+`api` healthy |

네트워크: 단일 브리지 `jippin`. 컨테이너 간 통신은 서비스명(`web`/`api`/`redis`)으로.
볼륨: `jippin-redis-data` (redis AOF 영속).

`nginx` 는 `profiles: ["edge"]` 로 묶여 있어 기본 `up` 에서는 기동되지 않는다. CEO §1.2 단일 진입점이 필요한 환경에서만 `--profile edge` 또는 `make up-edge` 로 활성화한다.

---

## §2. 사전 요구사항

1. Docker Engine 24+ / Docker Compose v2 (`docker compose version` 확인).
2. 외부 managed Postgres 두 URL — `DATABASE_URL` (non-pooler, DDL/마이그레이션) / `DATABASE_POOL_URL` (pooler, 요청 경로). SSOT 는 **Supabase project** (CMP-603 cutover 완료).
3. Supabase Auth 환경변수 — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_FLOW_COOKIE_SECRET`, `SUPABASE_JWT_ISSUER`, `SUPABASE_JWKS_URL`, `SUPABASE_JWT_SECRET` (`SUPABASE_JWT_AUDIENCE` 는 기본값 `authenticated`). `docker-compose.yml` 의 `${...:?}` 가드가 부재 시 부팅을 차단한다.
4. (선택) GNU make. Windows 사용자는 §3 의 원시 명령을 직접 사용해도 동일하다.

```bash
cp infra/compose/.env.example infra/compose/.env
$EDITOR infra/compose/.env       # DATABASE_URL, DATABASE_POOL_URL, NEXT_PUBLIC_SUPABASE_*, SUPABASE_JWT_ISSUER/JWKS_URL/SECRET 등 채워넣기
```

`.env` 는 `.gitignore` 차단되어 커밋되지 않는다. `.env.example` 만 트래킹된다.

---

## §3. 단축 ↔ 원시 명령 대조표

루트 `Makefile` 이 모든 단축 명령을 제공한다. `make` 가 없는 환경(특히 Windows)에서는 우측의 원시 `docker compose` 명령을 그대로 사용한다.

| 의도 | 단축 (Makefile) | 원시 (docker compose) |
|---|---|---|
| 포그라운드 부팅 | `make up` | `docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.yml [-f infra/compose/docker-compose.override.yml] up --build` |
| 백그라운드 부팅 | `make up-detach` | `... up --build -d` |
| prod 부팅 (override 무시) | `make up-prod` | `docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.yml up --build -d` |
| nginx 동반 | `make up-edge` | `... --profile edge up --build -d` |
| 정지 | `make down` | `... down` |
| 정지 + 볼륨 폐기 | `make down-clean` | `... down -v` |
| 단일 서비스 로그 | `make logs SVC=api` | `... logs -f --tail=200 api` |
| 컨테이너 상태 | `make ps` | `... ps` |
| 단일 서비스 재기동 | `make restart SVC=web` | `... restart web` |
| 컨테이너 내부 명령 | `make exec SVC=api CMD="alembic upgrade head"` | `... exec api sh -lc "alembic upgrade head"` |
| 파싱 검증 | `make config` | `... config --quiet` |
| 사전 점검 | `make doctor` | (없음 — Makefile 전용) |

원시 명령에서 `[-f ... override.yml]` 은 그 파일이 존재할 때만 붙인다 (§4 참조).

---

## §4. 개발자 hot-reload 오버레이 (override) 활성화

`docker compose` 는 cwd 의 `docker-compose.override.yml` 을 **자동으로 머지**한다. 본 레포는 prod 부팅에서 봉인된 standalone 이미지가 호스트 소스로 덮어쓰이는 사고를 피하기 위해 오버레이를 `*.example.yml` 로 트래킹하고, 활성화는 명시적 1회 cp 로만 허용한다.

```bash
# 활성화 (개발자 본인의 머신에서만)
cp infra/compose/docker-compose.override.example.yml \
   infra/compose/docker-compose.override.yml

make up         # 자동으로 override 가 머지된다

# 비활성화 (= prod 부팅으로 복귀)
rm infra/compose/docker-compose.override.yml
```

오버레이가 활성화되면:

- `web` — `apps/web` 이 컨테이너 `/app` 으로 마운트되고 `next dev` 가 변경을 감지한다 (`CHOKIDAR_USEPOLLING=1`).
- `api` — `apps/api/src` 가 컨테이너 `/app/src` 로 마운트되고 `uvicorn --reload` 가 감지한다 (`WATCHFILES_FORCE_POLLING=1`).
- 두 서비스의 헬스체크는 dev 모드에서 비활성화되어 watcher 콜드스타트와 경합하지 않는다.

활성화된 override 는 `.gitignore` 차단되어 절대 커밋되지 않는다.

---

## §5. 헬스체크 & 완료 정의

부팅 후 60초 이내에 모든 서비스가 healthy 상태여야 한다.

```bash
make ps           # STATUS 컬럼에 (healthy) 가 표시되는지 확인
curl -sf http://localhost:8000/healthz | jq .     # 200 + DB SELECT 1 응답 (Supabase)
curl -sf http://localhost:3000/healthz | jq .     # 200 + Next.js BFF 응답
curl -s  http://localhost:3000 | head -20         # Next.js 랜딩
```

완료 정의 (이슈 본문):

- `docker compose up --build` 후 60초 이내 web/api/redis 가 healthy.
- `curl http://localhost:8000/healthz` 200 + 외부 Supabase Postgres SELECT 1 성공.
- `curl http://localhost:3000` 가 Next.js 랜딩 반환.
- 본 README 만 보고 신규 개발자가 30분 이내 로컬 부팅 가능.

---

## §6. 시크릿 봉인

| 자산 | 위치 | 트래킹 | 가드 |
|---|---|---|---|
| 자리표시자 | `infra/compose/.env.example` | ✅ | 자리표시자만 |
| 실제 값 | `infra/compose/.env` | ❌ (`.gitignore`) | 로컬 전용 |
| dev 오버레이 (활성) | `infra/compose/docker-compose.override.yml` | ❌ (`.gitignore`) | 활성화 시 호스트만 |
| dev 오버레이 (예시) | `infra/compose/docker-compose.override.example.yml` | ✅ | — |

`docker-compose.yml` 의 `${DATABASE_URL:?...}` / `${DATABASE_POOL_URL:?...}` 가드가 시크릿 부재 시 부팅을 차단한다.

```bash
# .env 가 없거나 키가 비어 있을 때
docker compose -f infra/compose/docker-compose.yml config
# → error: required variable DATABASE_URL is missing a value:
#   DATABASE_URL must be set (Neon non-pooler)
```

---

## §7. 형제 이슈 의존 (E2E `up --build` 가능 시점)

본 산출물은 compose **파싱** (`docker compose config --quiet`) 까지는 자체적으로 검증되지만, 실제 `up --build` E2E 는 형제 이슈의 빌드 산출물이 머지되어야 가능하다.

| 이슈 | 산출물 | 본 이슈 대비 상태 |
|---|---|---|
| CMP-527 | `packages/contracts` (web/api 공유 타입) | API 빌드 의존 |
| CMP-528 | `apps/api/Dockerfile` + FastAPI `/healthz` | **`api` 서비스 빌드** |
| CMP-529 | `apps/web/Dockerfile` + Next.js `output: standalone` + `/healthz` | ✅ 본 브랜치에 머지됨 |

CMP-528 미머지 단계에서는 `make up` 의 `api` 빌드가 컨텍스트 부재로 실패한다. 임시로 `web` 만 단독 부팅하려면:

```bash
docker compose --env-file infra/compose/.env \
  -f infra/compose/docker-compose.yml up --build web redis
# web 의 depends_on(api) 이 만족되지 않으므로 web 도 기동되지 않는다 — 의도된 봉인.
```

CMP-528 머지 직후 본 이슈의 부팅 검증이 가능해진다.

---

## §8. nginx 단일 진입점 (옵션 / 스텁)

CEO §1.2 의 단일 진입점은 `nginx` 서비스로 스텁되어 있다. 기본 부팅에서는 비활성, `make up-edge` 또는 `--profile edge` 로만 기동된다.

- 설정 파일: `infra/docker/nginx.conf` (`/api/*` → api, `/*` → web).
- TLS / 도메인 / rate-limit 등 prod-grade 설정은 후속 이슈에서 보강.
- 외부 80 노출과 충돌하는 호스트(예: 다른 nginx 가 이미 80 점유)에서는 활성화하지 않는다.

---

## §9. 빠른 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `required variable DATABASE_URL is missing` | `infra/compose/.env` 생성 / 값 채워넣기. `make doctor` 로 사전 점검. |
| `required variable SUPABASE_JWT_ISSUER / SUPABASE_JWKS_URL / SUPABASE_JWT_SECRET ...` | `.env` 의 Supabase Auth 절을 채운다 (CMP-595 세션 브리지 가드). |
| `api` 가 `unhealthy` 로 떨어짐 | `make logs SVC=api` 로 DB 연결/SSL 메시지 확인. `DATABASE_URL` 에 `sslmode=require` 포함 필수 (Supabase). |
| `web` 가 `api` 를 못 부름 | Browser 경로는 `NEXT_PUBLIC_API_BASE_URL=/api`, server/rewrite 경로는 `API_INTERNAL_BASE_URL=http://api:8000` 확인. |
| Windows 에서 dev hot-reload 미동작 | override 의 `WATCHFILES_FORCE_POLLING=1` / `CHOKIDAR_USEPOLLING=1` 확인. |
| `make up` 직후 web 만 떨어짐 | `depends_on: api.healthy` — api 가 healthy 가 될 때까지 web 은 대기. `make ps` 로 진행 확인. |
| 포트 충돌 (3000/8000/6379/80) | 호스트의 기존 프로세스 종료 또는 compose 의 ports 매핑 조정 (커밋 금지 — 로컬 fork). |

---

## §10. 참조

- CEO 브리프 §2 D2 (오케스트레이션 산출물), §10 #3 (30분 부팅).
- AGENTS.md §2 (모노레포 구조), §4.4 (환경변수 / 시크릿), §5.9 (CI/CD 워크플로우 — cutover 후).
- ADR-0001 §5 (컨테이너 런타임 결정), §9 (이미지 봉인).
- ADR-0004 (Neon → Supabase 전환, Proposed) · `docs/runbooks/supabase-branching.md` · `docs/runbooks/supabase-migration-plan.md`.
- 본 이슈: CMP-530. 부모: CMP-524. 문서 정합: CMP-602 / CMP-603.
