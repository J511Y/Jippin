# CMP-543 — 개발환경 구축 (계획서)

- 정본 책임자: **CTO**
- 관련 이슈: CMP-543 (본 계획서), CMP-538 (APP_ENV 봉인), CMP-537 (Alembic), CMP-528 (API 부트스트랩)
- 작성: 2026-05-28
- 상태: **계획안 — 보드 승인 대기 (request_confirmation)**

---

## 0. 요구사항 (이슈 본문 인용)

> 현재 DB는 Neon을 바라보고 있는데 `local` 이라는 브랜치를 따놓고, 로컬 개발 환경일 땐 해당 환경을 바로볼 수 있도록 해야한다.
>
> 또한 백엔드에서 모든 요청에 대해 DB에 로그형 데이터를 쌓을 수 있도록 엔티티 및 DB 마이그레이션 파일을 작성한다.

요청된 로그 필드 (이슈 본문):

`is_anonymous_user`, `device_id`, `user_id`, `version`, `device`(`pc|mobile|notebook|tablet|other`), `country`, `region`, `ip_addrs`(배열), `last_ip`, `url`, `parameter`, `method`, `body`(jsonb), `response_code`, `response_message`, `duration`

> *"엔지니어가 추가로 판단한 필드가 있다면 추가해도 된다"* — 본 계획서 §3.1 에 추가 필드 후보를 둔다.

---

## 1. 트랙 A — `local` Neon 브랜치 + 로컬 개발 환경 결선

### 1.1 결정 (CTO 아키텍처 콜)

- **`local` Neon 브랜치를 신규 생성한다.** Parent: `dev` (Neon 브랜치 트리 `main → dev → local`).
- **`APP_ENV` enum 은 확장하지 않는다.** CMP-538 봉인 유지. 로컬 개발자는 계속 `APP_ENV=development` 로 부팅하되, `.env` 의 `DATABASE_URL` / `DATABASE_POOL_URL` 만 `local` 브랜치 host 로 가리킨다 (12-factor — 환경별 동일 바이너리, 다른 URL).
- **`dev` 브랜치의 역할 재정의**:
  - 기존: 로컬 개발자 공용 직접 연결.
  - 변경 후: **CI / `test` APP_ENV / `development` GitHub Environment 배포** 용. 로컬 개발자는 기본적으로 `local` 을 본다.
- 기존 per-handle `dev-<handle>` 패턴은 *선택 사항* 으로 유지 (격리가 필요한 작업자만 사용).

#### 1.1.1 왜 enum 을 안 건드리나

CMP-538 의 봉인은 "**코드 분기 금지**" 가 본질이다 (`if APP_ENV == 'local': ...` 같은 분기를 막는 것). Neon 브랜치를 추가하는 것은 봉인의 범위가 아니다. enum 을 늘리면 ADR 재발행 + tests 갱신 + CI 갱신이 같이 따라오는데, 본 이슈의 의도(로컬용 DB 격리)는 URL 한 줄 교체로 달성 가능하므로 그 비용이 정당하지 않다.

### 1.2 인도물

1. **Neon 브랜치 `local` 생성** — parent `dev`, scale-to-zero ON, history retention 최소.
2. **`apps/api/.env.example` 갱신** — `development` 섹션의 URL placeholder 를 `ep-local-EXAMPLE-…` 로 교체. 코멘트 보강: "로컬 개발 = `APP_ENV=development` + `local` Neon 브랜치 URL".
3. **`docs/runbooks/neon-branches.md` 갱신**:
   - §1 트리에 `local` 추가 (`main → dev → local → (선택) local-<handle>`).
   - §2.4 자기 fork 가이드를 `local` 기준으로 재작성 (parent: `local`).
   - §0 봉인 매핑 표에 **각주** 추가: "APP_ENV=development 의 표준 Neon 브랜치는 `local` (로컬) / `dev` (CI·development environment 배포)". 표 자체 (봉인) 는 손대지 않는다.
4. **(선택) `infra/compose/.env.example` 동기화** — 이미 placeholder 인 경우 코멘트만 추가.

### 1.3 비범위

- `APP_ENV` enum 변경 / `ALLOWED_APP_ENVS` 코드 수정 — 본 트랙에서 하지 않는다.
- `dev` Neon 브랜치 폐기 — 유지 (CI / development environment 배포 경로가 의존).
- `staging` Neon 브랜치 생성 — 별도 이슈 (현재 staging 미생성 상태).

### 1.4 담당

- **Infrastructure Lead** 가 트랙 A 자식 이슈 소유.
- Neon 브랜치 생성 자체는 MCP / Neon 콘솔로 수행. credential 유출 없도록 자기 점검 (§5.7 시크릿 헌팅).

---

## 2. 트랙 B — 요청 로그 엔티티 + Alembic 마이그레이션

### 2.1 결정 (CTO 아키텍처 콜)

- **테이블명**: `request_logs` (snake_case, 복수형 — Jippin 컨벤션).
- **PK**: `id BIGSERIAL` (수십만~수백만 row 예상).
- **시간**: `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` — **인덱스 + 향후 파티셔닝 키**.
- **request_id 컬럼 추가** — `apps/api/src/logging.py` 의 `RequestIDMiddleware` 가 생성하는 UUID 와 1:1 매칭, 로그-DB 상관관계 분석 가능.
- **민감 데이터 처리** — `body` jsonb 에 비밀번호/토큰이 평문으로 들어가지 않도록 **redaction 화이트리스트 / 블랙리스트** 를 미들웨어에서 적용. Security Lead 가 정책 정본.
- **저장 경로**: 미들웨어가 응답 직후 비동기 INSERT (요청 latency 에 영향 0). 실패 시 로그만 남기고 응답 자체에는 영향 없음 (fire-and-forget).
- **본 트랙 산출물**: **엔티티 모델 + Alembic 마이그레이션** 까지. 미들웨어 자체 구현은 트랙 B-2 (자식) 로 분리한다 (privacy redaction 정책 합의가 선행되어야 안전).

### 2.2 필드 매핑 (이슈 요구 + 엔지니어 추가)

| 컬럼 | 타입 | NULL | 인덱스 | 설명 |
|---|---|---|---|---|
| `id` | `BIGSERIAL` | NOT NULL (PK) | PK | 행 ID |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | ix(created_at) | 요청 도착 시각 |
| `request_id` | `UUID` | NOT NULL | ix(request_id) | `X-Request-ID` 미들웨어 UUID |
| `is_anonymous_user` | `BOOLEAN` | NOT NULL | — | 비회원 여부 |
| `user_id` | `TEXT` | NULL | ix(user_id, created_at desc) | 회원 ID 또는 비회원 localStorage ID |
| `device_id` | `TEXT` | NULL | — | 기기 고유 ID (MAC 또는 fingerprint) |
| `version` | `TEXT` | NULL | — | 클라이언트가 보낸 API 버전 (`X-Api-Version` 헤더 또는 path prefix) |
| `device` | `TEXT` | NULL | — | `pc / mobile / notebook / tablet / other` — DB 제약 X (값 추가 빈번), 앱 enum 으로 검증 |
| `country` | `TEXT` | NULL | — | ISO 2자 국가코드 (또는 미상 시 NULL) |
| `region` | `TEXT` | NULL | — | 행정 지역명 / city |
| `ip_addrs` | `TEXT[]` | NOT NULL DEFAULT `'{}'` | — | 프록시 체인 전체 (X-Forwarded-For 분리, 정규화 후) |
| `last_ip` | `INET` | NULL | ix(last_ip) | `ip_addrs` 의 마지막 요소 = 실제 클라이언트 IP |
| `url` | `TEXT` | NOT NULL | — | path (scheme/host 제외, query 미포함) |
| `parameter` | `JSONB` | NOT NULL DEFAULT `'{}'::jsonb` | — | URL query parameter (k:v) |
| `method` | `TEXT` | NOT NULL | ix(method, url, created_at) | HTTP method |
| `body` | `JSONB` | NULL | — | POST/PUT/PATCH body (redaction 적용 후) |
| `response_code` | `INTEGER` | NOT NULL | ix(response_code) | HTTP status code |
| `response_message` | `TEXT` | NULL | — | 응답 envelope 의 `error.message` (성공 시 NULL) |
| `error_code` | `TEXT` | NULL | — | (엔지니어 추가) envelope `error.code` (`VALIDATION_ERROR` 등) |
| `duration_ms` | `INTEGER` | NOT NULL | ix(duration_ms) | 요청 소요 (ms, 정수) |
| `user_agent` | `TEXT` | NULL | — | (엔지니어 추가) raw UA — 포렌식·디바이스 추론 보조 |
| `referrer` | `TEXT` | NULL | — | (엔지니어 추가) `Referer` 헤더 |

엔지니어 추가 근거:

- `request_id`: 미들웨어 로그-DB 상관에 필수.
- `error_code`: AGENTS.md §4.5 envelope 분석에 message 보다 code 가 우선이다.
- `duration_ms`: 이슈는 단위 미지정 — 밀리초 정수가 운영적으로 가장 일반적.
- `user_agent`, `referrer`: device / 트래픽 출처 사후 추론 가능. PII 위험 낮음.

### 2.3 인덱스 정책

- 모든 인덱스는 Alembic 마이그레이션 본문에 명시 (autogenerate diff 안정성).
- 복합 인덱스 `ix_request_logs_user_id_created_at_desc (user_id, created_at DESC)` — 회원별 최근 요청 조회 빈번.
- 복합 인덱스 `ix_request_logs_method_url_created_at (method, url, created_at)` — 엔드포인트별 분석.
- `created_at` 단일 인덱스 — 향후 월별 파티셔닝 전환 시 키 검증용.

### 2.4 보존 / 파티셔닝 (정책만, 본 트랙 구현 X)

- 1차 가설: **90일 보존, 월 단위 파티셔닝**. 운영 시점에서 트래픽 보고 결정.
- 본 트랙은 단일 테이블로 시작, 파티셔닝은 별도 후속 이슈.

### 2.5 인도물 (트랙 B-1: 엔티티 + 마이그레이션)

1. `apps/api/src/models/request_log.py` — `class RequestLog(Base)` 모델.
2. `apps/api/src/models/__init__.py` 갱신 — `from .request_log import RequestLog` import (autogenerate 인식).
3. `apps/api/migrations/versions/<UTC ts>_0004_request_logs.py` — 테이블 + 인덱스 생성, downgrade 에 drop.
4. `apps/api/tests/test_models_request_log.py` — 모델 메타데이터 / 인덱스 이름 단위 테스트.

### 2.6 인도물 (트랙 B-2: 로깅 미들웨어 — 자식 이슈 분리)

- 별도 자식 이슈로 분리. 사유:
  - Redaction 정책은 **Security Lead** 가 정본 — body 의 어떤 키를 마스킹할지 (`password`, `token`, `authorization`, `cookie`, …) 합의 필요.
  - IP 추출 (`X-Forwarded-For` 신뢰 경계, `X-Real-IP`) 도 인프라 토폴로지(역방향 프록시) 합의 필요.
  - country / region (GeoIP) 는 외부 의존성 (MaxMind / Cloudflare 헤더) — ADR 영향.

### 2.7 담당

- **트랙 B-1 (모델 + 마이그레이션)**: Backend Lead → Python Backend Engineer.
- **트랙 B-2 (미들웨어)**: 별도 자식 이슈, Backend Lead. 단, **Security Lead 가 redaction 정책에 +1 줘야 머지 가능**.

---

## 3. 자식 이슈 분해 (제안)

| 자식 ID (제안) | 트랙 | 제목 | 담당 라인 | 의존 |
|---|---|---|---|---|
| CMP-543-A | A | Neon `local` 브랜치 신설 + .env.example + runbook 갱신 | Infrastructure Lead | — |
| CMP-543-B1 | B-1 | `request_logs` 엔티티 + Alembic 마이그레이션 | Backend Lead → Python Backend Engineer | — |
| CMP-543-B2 | B-2 | 요청 로깅 미들웨어 + redaction | Backend Lead (Security Lead 리뷰) | B-1 |

A 와 B-1 은 병렬 가능. B-2 는 B-1 완료 후 시작.

본 부모 이슈(CMP-543) 는 세 자식이 모두 완료되면 `done` 으로 종결.

---

## 4. 비범위 / 후속

- `staging` Neon 브랜치 신설 — 별도 이슈.
- 요청 로그 보존·파티셔닝 자동화 — 별도 이슈.
- GeoIP 조회 의존성 채택 (MaxMind GeoLite2 vs CloudFlare 헤더) — B-2 자식 또는 별도 ADR.
- 응답 본문(`body`) 의 어떤 키를 redact 할지 정본 — Security Lead, B-2 자식 이슈에 첨부.

---

## 5. 보드 승인 필요 사항

본 계획서가 다음을 확정한다 — 보드(PM/CEO)는 다음 두 가지를 확인해 주시기 바람:

1. **`local` Neon 브랜치 신설 + `dev` 의 역할 재정의** (`dev` = CI/배포 전용, `local` = 로컬 개발자 직접 연결) — OK 인가?
2. **요청 로그 엔티티는 본 부모 이슈에서 모델 + 마이그레이션까지** 수행하고, **미들웨어는 별도 자식 이슈로 분리** — OK 인가?
3. 추가 필드(`request_id`, `error_code`, `duration_ms`, `user_agent`, `referrer`) 추가 — 반대 없으면 채택.

승인 후 위 §3 의 자식 이슈 3건을 생성한다.
