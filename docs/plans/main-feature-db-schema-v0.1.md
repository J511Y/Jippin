# 메인 기능 DB 스키마 v0.1

작성일: 2026-06-04
상태: Phase A 반영안
범위: Supabase Postgres 기반 P0/P1 애플리케이션 도메인 스키마 설계

## 정본 정합

- 사용자 인증 정본은 Supabase Auth 다. `auth.users` 또는 `auth.identities` 를 대체하는 앱 인증 테이블을 만들지 않는다.
- `public.users` 는 `auth.users.id` 를 PK/FK 로 받는 집핀 앱 프로필/RBAC 테이블로만 유지한다.
- 비회원 사전검토도 Supabase Anonymous Sign-In 이 만든 `auth.users.id` 로 소유권을 갖는다.
- forward schema 정본은 `supabase/migrations/*.sql` 이다. Alembic 은 historical reference 로만 둔다.
- 원본 도면, 썸네일, 마스킹본, 오버레이, PDF 같은 대형 바이너리는 Cloudflare R2/S3 호환 객체 스토리지에 저장한다. Postgres 에는 소유권, 상태, object key, hash, 처리 metadata 만 저장한다.

## 설계 원칙

- `sessions` 를 사전검토 워크플로우의 허브로 둔다.
- 사용자 소유 테이블은 직접 `user_id uuid references auth.users(id)` 를 갖고, RLS 정책은 `(select auth.uid())` 패턴을 쓴다.
- 모든 FK 컬럼은 인덱싱한다.
- status 값은 Phase A 에서 `text + check constraint` 로 둔다. 전역적으로 안정된 값만 추후 enum type 으로 승격한다.
- 검색·집계가 필요한 값은 컬럼으로 분리하고, 계약 버전이 있는 판단/툴 payload 는 JSONB 로 보관한다.
- 처리 시도, webhook 발송, cron 실행 이력은 로그에만 남기지 않고 테이블로 관측 가능하게 둔다.

## Phase A 테이블

| 테이블 | 역할 |
|---|---|
| `sessions` | 사전검토 1건의 허브. 익명/영구 Supabase user 가 모두 소유 가능 |
| `session_addresses` | 세션 시작 시 입력·정규화한 주소/세대 식별 정보 |
| `floorplans` | 재사용 가능한 내부/외부 후보 도면 catalog |
| `floorplan_uploads` | 사용자가 특정 세션에서 직접 업로드한 도면 record |
| `floorplan_assets` | R2/S3 객체 metadata. 원본/썸네일/마스킹본/오버레이/PDF 공통 저장 |
| `floorplan_candidates` | 특정 세션에서 사용자에게 실제 제시한 후보 snapshot |
| `chat_messages` | 세션 transcript |
| `chat_tool_calls` | tool 실행 input/output/error/duration audit |
| `processing_jobs` | AI/OCR/마스킹/리포트 등 비동기 처리 작업 상태 |
| `webhook_deliveries` | 외부 webhook 발송 시도와 응답 관측 |
| `scheduled_task_runs` | Supabase Cron 또는 운영 scheduled task 실행 이력 |
| `external_sync_records` | 세움터/건축물대장/파트너 등 외부 동기화 상태 |

## 핵심 결정

### 비회원 소유권

`sessions.user_id` 는 `not null references auth.users(id)` 이다. 여기서 user 는 회원 가입 완료 사용자만 뜻하지 않고 Supabase anonymous user 도 포함한다. 익명 사용자가 OAuth `linkIdentity()` 로 전환하면 같은 `auth.users.id` 가 유지되므로 세션, 도면, 분석 결과를 이관하지 않는다.

### 도면 catalog 와 업로드 분리

`floorplans` 는 후보 도면 catalog 다. 사용자가 직접 올린 파일은 `floorplan_uploads` 와 `floorplan_assets` 에 저장하고, 검수 후 재사용 가능한 후보로 편입될 때만 `floorplans.source='promoted_upload'` row 를 만든다.

`floorplan_candidates` 는 검색 호출 로그가 아니다. 주소/타입 기준으로 계산된 후보 중 사용자에게 실제 제시한 snapshot 만 저장한다. 같은 세션에서 주소를 수정해 후보를 다시 보여주면 `lookup_revision` 을 증가시켜 새 snapshot 을 남긴다.

### 채팅과 tool audit 분리

`chat_messages` 는 사용자/assistant/system transcript 이고, tool input/output/error/duration 은 `chat_tool_calls` 로 분리한다. 사용자가 보는 대화와 내부 실행 audit 의 보존·redaction 정책이 다르기 때문이다.

### Supabase 연계

Supabase Queues/Cron/Webhooks 또는 외부 worker 를 쓰더라도 관측 가능한 상태는 애플리케이션 테이블에 남긴다.

- `processing_jobs`: 작업 타입, 상태, 시도 횟수, 오류, 결과 payload.
- `webhook_deliveries`: endpoint, payload, HTTP status, 응답 일부, next retry.
- `scheduled_task_runs`: task key, lock key, started/finished, summary.
- `external_sync_records`: provider/resource key 별 sync 상태와 cursor.

## 성능과 보안

- 사용자 목록 조회는 `(user_id, created_at desc)` 인덱스를 기본으로 한다.
- queue polling 은 partial index 로 `status in ('queued', 'running')` 또는 retry 대상만 좁힌다.
- RLS 는 사용자 소유 테이블에 켜고, user-facing 정책은 자기 row 만 허용한다.
- catalog 인 `floorplans` 는 `public_catalog + verified` row 만 authenticated 사용자가 읽을 수 있고, 비공개 row 는 생성자만 접근한다.
- JSONB GIN index 는 Phase A 에서는 만들지 않는다. 실제 조회 패턴이 확정된 뒤 필요한 path 에만 추가한다.
