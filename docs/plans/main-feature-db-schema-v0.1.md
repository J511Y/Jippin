# 메인 기능 DB 스키마 초안 v0.1

작성일: 2026-06-04
상태: 초안
범위: Supabase Postgres 기반 P0/P1 애플리케이션 도메인 스키마 설계
관련 이슈: CMP-607

이 문서는 집핀 메인 사전검토 흐름을 위한 DB 설계를 시작하기 위한 초안이다. 아직
migration 계획이 아니며, 모듈 담당자들이 테이블 경계와 payload 계약을 합의한 뒤
`supabase/migrations/*.sql` 로 전환한다.

## 정본 정합

- 사용자 인증 정본은 Supabase Auth 다. `auth.users` 또는 `auth.identities` 를 대체하는 앱 테이블을 만들지 않는다.
- `public.users` 는 `auth.users.id` 를 PK/FK 로 받는 집핀 앱 프로필/RBAC 테이블로만 유지한다.
- forward schema 정본은 `supabase/migrations/*.sql` 이다.
- 도면 원본, 썸네일, 마스킹본, 오버레이, PDF, 이미지 산출물 같은 대형 바이너리는 Cloudflare R2/S3 호환 객체 스토리지에 둔다. Postgres 에는 소유권, 상태, object key, hash, 처리 결과 metadata 만 저장한다.
- queue/cron/webhook 연계는 Supabase 호환 기능을 전제로 한다.
  - Queue: Supabase Queues / `pgmq`
  - Cron: Supabase Cron / `pg_cron`
  - Webhook/비동기 HTTP: Database Webhooks / `pg_net`

## 설계 원칙

- `sessions` 를 사전검토 워크플로우의 허브로 둔다.
- 조회, 감사, 수명주기 제어가 필요한 결정값은 별도 row 로 저장한다.
- `packages/contracts` 에서 버전 관리되는 모델/룰 payload 는 JSONB 로 저장하되, 검색·집계가 필요한 값은 컬럼으로 분리한다.
- 사용자 소유 테이블은 직접 `user_id uuid references auth.users(id)` 를 갖거나, `sessions.user_id` 를 통해 소유권을 추적한다.
- 여기서 `user_id` 는 "회원 가입 완료 사용자"만 뜻하지 않는다. Supabase Anonymous Sign-In 이 만든 익명 `auth.users.id` 도 포함한다.
- 사용자 데이터 테이블은 RLS 를 켠다. 정책에는 `(select auth.uid())` 패턴을 쓰고, 소유권 컬럼에는 인덱스를 둔다.
- 모든 FK 컬럼은 인덱싱한다.
- status/enum 은 우선 `text + check constraint` 로 둔다. 정말 전역적이고 안정적인 값만 enum type 으로 승격한다.
- 모든 timestamp 는 `timestamptz` 를 쓴다.
- 처리 시도, webhook 발송, cron 실행 이력은 로그만 남기지 말고 테이블로 관측 가능하게 둔다.
- JSONB 는 계약 payload snapshot 보관용으로 우선 사용한다. `where` / `join` / `order by` 에 반복적으로 쓰는 값은 컬럼으로 승격하고, GIN index 는 실제 조회 패턴이 확인된 키에만 붙인다.
- FK cycle 이 생기는 `sessions.address_id` / `session_addresses.session_id` 같은 관계는 마이그레이션에서 테이블 생성 후 `alter table add constraint` 로 분리하거나 DEFERRABLE 제약으로 만든다.
- `floorplan_assets` 처럼 catalog/upload/session 중 하나 이상에 연결되어야 하는 테이블은 nullable FK 만 나열하지 말고 check constraint 로 parent scope 를 강제한다. catalog scope 와 private upload/session/generated scope 는 서로 섞지 않는다.
- publish/전환 같은 상태 변경은 앱 로직만 믿지 않는다. `reports.legal_notice_included`, `leads` non-anonymous gate, 공유 token hash unique 등은 DB 제약/RLS/서버 guard 를 함께 둔다.

## 기존 Auth/Profile 테이블

| 테이블 | 현재 역할 | 본 설계에서의 처리 |
|---|---|---|
| `auth.users` | Supabase managed identity. 익명/영구 user row 포함 | 변경 없음. 직접 alter 금지 |
| `auth.identities` | Supabase managed OAuth identity | 변경 없음. 직접 insert/update 금지 |
| `public.users` | 집핀 앱 프로필/RBAC. `id = auth.users.id` | 유지. 인증 정보 저장 금지 |
| `public.terms_consents` | 약관 동의 audit. `auth.users.id` 기준 | 유지 |
| `public.request_logs` | API request log | 유지. 추후 retention/partition 재검토 |

## Auth 전환 보조 테이블

아래 테이블은 메인 기능 테이블은 아니지만, `leads` / 리포트 저장·공유 / 상담 전환 같은 conversion-only 동작의 DB 가드를 제대로 걸려면 같은 설계에서 참조해야 한다. 실제 마이그레이션은 Auth 트랙과 충돌하지 않도록 별도 phase 로 분리할 수 있다.

### `terms_consent_intents`

Google / Naver 내부 약관 동의 후 `linkIdentity()` 전에 기록하는 짧은 TTL 의도 테이블. ADR-0004 의 정합 경로를 따른다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `user_id uuid not null references auth.users(id) on delete cascade`
- `term_id text not null`
- `version text not null`
- `source text not null default 'internal_signup'`
- `target_provider text not null`
  - `google`
  - `custom:naver`
- `agreed_at timestamptz not null default now()`
- `expires_at timestamptz not null`
- `status text not null default 'pending'`
  - `pending`
  - `promoted`
  - `expired`
- `promoted_at timestamptz`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- unique `(user_id, term_id, version, source, target_provider) where status = 'pending'`
- `(user_id, expires_at)`
- partial index: `(expires_at) where status = 'pending'`

비고:

- Kakao Sync 는 이 테이블을 쓰지 않는다. Kakao 약관 검증은 Database Webhook + Kakao API reconciliation 경로가 정본이다.
- `expires_at > now()` 는 partial unique index 조건에 직접 쓸 수 없으므로 `status` 로 live intent 를 표현한다. scheduled task 는 `status='pending' and expires_at < now()` row 를 `expired` 로 전환해 재시도 발급을 열어야 한다.
- promotion trigger 는 성공 시 `status='promoted'`, `promoted_at=now()` 로 갱신한다. 만료 row 는 같은 `(user_id, term_id, version, source, target_provider)` 의 새 pending intent 를 막지 않는다.

### `policy_current_required_terms`

conversion-only gate 가 "현재 필수 약관 전체 동의" 를 검사할 수 있게 하는 정책 테이블. 단순 `exists terms_consents` 는 약관 개정 후 과거 동의만 있는 사용자를 통과시킬 수 있으므로 금지한다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `term_id text not null`
- `version text not null`
- `required_for text not null`
  - `signup`
  - `lead`
  - `report_share`
  - `payment`
- `is_active boolean not null default true`
- `effective_from timestamptz not null default now()`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- unique `(term_id, version, required_for)`
- partial unique index: `(term_id, required_for) where is_active`
- partial index: `(required_for, term_id, version) where is_active`

비고:

- API 의 `require_permanent_user` 와 RLS restrictive policy 는 이 테이블의 active row 전체가 `terms_consents` 에 존재하는지 확인한다.
- 약관 문구 원본은 별도 문서/정책 저장소가 정본이어도 되지만, DB gate 에 필요한 `(term_id, version, required_for)` 는 Postgres 에 있어야 한다.

## 비회원 사전검토 소유권 정책

집핀의 P0 정책은 비회원 사전검토 허용이다. Supabase 전환 후에는 별도 `anonymous_users` 테이블이나 브라우저 로컬 UUID 를 쓰지 않고, Supabase Anonymous Sign-In 이 만든 `auth.users.id` 를 소유권 키로 쓴다.

따라서 `sessions.user_id not null references auth.users(id)` 는 비회원 사전검토와 충돌하지 않는다. 비회원도 사전검토 시작 전에 Supabase anonymous session 을 받아 `auth.users` row 와 access token 을 갖기 때문이다.

권장 정책:

- `sessions.user_id` 는 `not null` 로 둔다.
- FK 는 `public.users(id)` 가 아니라 `auth.users(id)` 를 참조한다.
- 익명 사용자의 `public.users` profile row 는 필수로 만들지 않는다.
- 상담/리드/리포트 저장/공유 같은 conversion-only 동작은 `auth.users.is_anonymous = false` 와 약관 동의 여부로 차단한다.
- 익명 사용자가 OAuth `linkIdentity()` 로 전환하면 같은 `auth.users.id` 가 유지되므로, 세션/도면/분석/리포트 preview ownership 을 이관할 필요가 없다.

대안으로 익명도 `public.users` 에 `status='anonymous'` 같은 profile row 를 만들 수는 있다. 하지만 이 방식은 public profile row 가 대량 생성되고, profile 상태와 Supabase `auth.users.is_anonymous` 상태가 어긋날 수 있어 정본이 둘로 갈라진다. 현재 정본에서는 `auth.users.is_anonymous` 가 익명/영구 구분의 기준이고, `public.users` 는 영구 사용자 앱 프로필/RBAC 용도로 두는 편이 더 단순하다.

## P0 핵심 테이블

도면 관련 테이블은 다음처럼 역할을 나눈다.

| 테이블 | 의미 | 예시 |
|---|---|---|
| `floorplans` | 재사용 가능한 내부/외부 후보 도면 catalog | 84A 표준 평면도, 관리자가 검수한 후보 도면 |
| `floorplan_uploads` | 사용자가 특정 세션에서 직접 올린 도면 | 사용자가 PDF/JPG 를 업로드한 사전검토 입력 도면 |
| `floorplan_assets` | R2/S3 에 저장된 실제 파일 metadata | 원본 파일, 썸네일, 마스킹본, 오버레이, PDF |
| `floorplan_candidates` | 특정 세션에서 사용자에게 실제 제시한 catalog 후보 snapshot | 101동 84A 후보 3개와 confidence |

즉, `floorplans` 는 "사용자가 업로드한 파일" 자체가 아니라 후보 DB/catalog 이다. 사용자 업로드는 `floorplan_uploads` 로 받고, 해당 파일은 `floorplan_assets` 에 저장한다. 나중에 검수 후 내부 후보 DB 에 편입할 때만 `floorplans.source='promoted_upload'` 로 승격한다.

`floorplan_candidates` 는 모든 검색 호출 결과를 무조건 저장하는 검색 로그가 아니다. 한 세션에서 주소/타입 정보를 기준으로 후보를 계산했고, 그 결과를 실제 사용자에게 보여줬거나 사용자가 그중 하나를 선택할 수 있게 된 시점의 "후보 snapshot" 이다. 같은 세션에서 주소를 수정해 후보를 다시 계산하면 새 후보 snapshot 을 만들거나, `lookup_revision` 으로 구분한다.

### 1. `sessions`

사전검토 1건의 허브 테이블.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `user_id uuid not null references auth.users(id) on delete cascade`
- `status text not null`
  - `draft`
  - `address_ready`
  - `floorplan_selected`
  - `analyzing`
  - `awaiting_overlay`
  - `collecting_info`
  - `ready_for_rule`
  - `report_ready`
  - `handoff`
  - `expired`
  - `deleted`
- `address_id uuid references session_addresses(id)`
- `selected_floorplan_id uuid references floorplans(id)`
- `selected_floorplan_upload_id uuid references floorplan_uploads(id)`
- `selected_floorplan_asset_id uuid references floorplan_assets(id)`
- `judgment_schema jsonb not null default '{}'::jsonb`
- `judgment_schema_version text`
- `completion_decision text`
- `last_activity_at timestamptz not null default now()`
- `expires_at timestamptz`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

주요 인덱스:

- unique `(id, user_id)` for child-table same-owner composite FKs
- foreign key `(id, address_id)` references `session_addresses(session_id, id)` with DEFERRABLE timing when `address_id` is present, or an equivalent same-session trigger/check function
- `(user_id, created_at desc)`
- `(status, last_activity_at)`
- `(selected_floorplan_id)`
- `(selected_floorplan_upload_id)`
- `(selected_floorplan_asset_id)`
- partial index: `(expires_at) where status not in ('expired', 'deleted')`

비고:

- Supabase 익명 user 도 사전검토 session 을 소유할 수 있다. 이때 `user_id` 는 null 이 아니라 anonymous `auth.users.id` 다.
- 상담/리드/저장/공유 같은 conversion-only 동작은 non-anonymous token + 약관 동의 gate 로 막는다. session owner 를 따로 옮기는 방식으로 처리하지 않는다.
- `selected_floorplan_id` 와 `selected_floorplan_upload_id` 는 둘 중 하나만 최종 선택으로 활성화되는 one-of 관계다. SQL check constraint 또는 상태 전이 함수로 중복 선택을 막는다.
- `selected_floorplan_id` 는 이 세션에서 실제 제시된 `floorplan_candidates.floorplan_id` 중 rejected 되지 않은 후보이거나, transition function 이 `floorplans.visibility='public_catalog'`, `quality_status='verified'`, 주소/타입 policy 를 통과한다고 확인한 row 여야 한다. stale/guessed/admin_only/rejected catalog UUID 로 분석 단계에 들어가지 못하게 한다.
- `selected_floorplan_upload_id` 는 같은 `session_id` 의 `floorplan_uploads` 만 참조한다. 권장 DDL 은 `floorplan_uploads(session_id, id)` unique 보강 후 복합 FK 또는 상태 전이 함수다.
- `selected_floorplan_asset_id` 는 분석 입력으로 확정한 실제 파일이다. private upload asset 은 같은 `session_id` 와 owner 의 `floorplan_assets` 만 허용하고, catalog asset 은 `selected_floorplan_id` 에 연결된 public/admin catalog asset 인지 상태 전이 함수에서 확인한다.
- `address_id` 는 `session_addresses.session_id` 와 FK cycle 이므로 초기 migration 에서는 nullable 로 만들고, 주소 row 생성 이후 update 하거나 DEFERRABLE FK 로 처리한다. 단순 FK cycle 처리로 끝내지 말고 `sessions.id = session_addresses.session_id` 를 복합 FK 또는 same-session trigger/check function 으로 반드시 보장한다.

### 2. `session_addresses`

세션 시작 시 입력·정규화한 주소/세대 식별 정보.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null unique references sessions(id) on delete cascade`
- `user_id uuid not null references auth.users(id) on delete cascade`
- `road_address text`
- `jibun_address text`
- `apartment_name text`
- `building_dong text`
- `unit_ho text`
- `floor_no integer`
- `exclusive_area_m2 numeric(8,2)`
- `size_type text`
- `building_identity jsonb not null default '{}'::jsonb`
- `address_provider text`
- `normalized_at timestamptz`
- `created_at timestamptz not null default now()`

주요 인덱스:

- unique `(session_id, id)`
- foreign key `(session_id, user_id)` references `sessions(id, user_id)` on delete cascade, or an equivalent same-owner trigger/check function
- `(user_id, created_at desc)`
- `(apartment_name, building_dong, size_type)`
- `building_identity` GIN index 는 실제 조회 패턴 확정 후 추가

비고:

- `unit_ho`, 상세 주소, 연락처 등은 PII 로 취급한다.
- request log, chat log, webhook payload 에 원문이 새지 않도록 redaction 정책이 필요하다.
- RLS 가 `session_addresses.user_id` 로 owner 를 직접 판단하므로 `user_id` 는 항상 `sessions.user_id` 와 같아야 한다. insert path 가 `auth.uid() = user_id` 만 검증하고 `session_id` 를 별도로 받는 구조는 금지한다.

### 3. `floorplans`

내부 도면 DB 또는 외부 연동에서 확보한 "재사용 가능한 후보 도면 catalog" metadata.

사용자가 사전검토 중 직접 올린 도면은 이 테이블에 바로 넣지 않는다. 사용자 업로드는 `floorplan_uploads` 와 `floorplan_assets` 로 관리하고, 관리자 검수 후 catalog 로 승격할 때만 `floorplans` row 를 만든다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `created_by uuid references auth.users(id) on delete set null`
- `source text not null`
  - `internal`
  - `external_candidate`
  - `promoted_upload`
- `visibility text not null default 'admin_only'`
  - `public_catalog`
  - `admin_only`
- `apartment_name text`
- `building_dong text`
- `size_type text`
- `exclusive_area_m2 numeric(8,2)`
- `layout_family text`
- `address_fingerprint text`
- `promoted_from_upload_id uuid references floorplan_uploads(id) on delete set null`
- `metadata jsonb not null default '{}'::jsonb`
- `quality_status text not null default 'unverified'`
  - `unverified`
  - `verified`
  - `rejected`
  - `needs_review`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

주요 인덱스:

- `(apartment_name, building_dong, size_type)`
- `(source, quality_status)`
- `(created_by, created_at desc)`
- partial index: `(address_fingerprint) where address_fingerprint is not null`
- partial unique index: `(promoted_from_upload_id) where promoted_from_upload_id is not null`

비고:

- original/masked/thumbnail/overlay/PDF 같은 파일 경로는 `floorplans` 에 컬럼으로 여러 개 두지 않는다.
- 파일별 metadata 는 `floorplan_assets` 로 분리한다.

### 4. `floorplan_uploads`

사용자가 사전검토 세션 안에서 직접 업로드한 도면 record.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `user_id uuid not null references auth.users(id) on delete cascade`
- `original_asset_id uuid references floorplan_assets(id) on delete set null`
- `status text not null default 'uploaded'`
  - `uploaded`
  - `scan_pending`
  - `scan_failed`
  - `ready_for_processing`
  - `processing`
  - `processed`
  - `rejected`
  - `promoted_to_catalog`
- `file_name text`
- `source_note text`
- `upload_metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

주요 인덱스:

- unique `(session_id, id)`
- foreign key `(session_id, user_id)` references `sessions(id, user_id)` on delete cascade, or an equivalent same-owner trigger/check function
- `(session_id, created_at desc)`
- `(user_id, created_at desc)`
- `(status, created_at desc)`
- `(original_asset_id)`

비고:

- 사용자 업로드는 기본적으로 private/session-scoped 데이터다.
- 관리자 검수 후 내부 후보 DB 에 편입할 경우 `floorplans.source='promoted_upload'` 로 별도 catalog row 를 만든다.
- `user_id` 는 반드시 `sessions.user_id` 와 같아야 한다. private upload insert 가 다른 사용자의 `session_id` 에 붙는 것을 DB constraint 또는 trigger/check function 으로 막는다.
- `original_asset_id` 는 같은 `session_id` 의 `floorplan_assets` 만 참조한다. FK cycle 이 부담되면 upload 생성 transaction 의 transition function 에서 same-session/same-owner 를 검증한다.

### 5. `floorplan_assets`

R2/S3 객체 metadata. 원본, 썸네일, 미리보기, 마스킹본, OCR debug, segmentation mask, overlay, report PDF 등을 모두 여기에 기록한다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `floorplan_id uuid references floorplans(id) on delete restrict`
- `floorplan_upload_id uuid references floorplan_uploads(id) on delete cascade`
- `session_id uuid references sessions(id) on delete cascade`
- `owner_user_id uuid references auth.users(id) on delete cascade`
- `kind text not null`
  - `original`
  - `thumbnail`
  - `preview`
  - `masked`
  - `ocr_debug`
  - `segmentation_mask`
  - `overlay`
  - `report_pdf`
  - `report_image`
- `storage_provider text not null default 'r2'`
- `bucket text not null`
- `object_key text not null`
- `content_type text not null`
- `byte_size bigint not null`
- `sha256_hex text`
- `width_px integer`
- `height_px integer`
- `page_count integer`
- `scan_status text not null default 'pending'`
  - `pending`
  - `clean`
  - `infected`
  - `failed`
  - `not_required`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- unique `(bucket, object_key)`
- unique `(session_id, id)` for private/session asset composite FKs
- check constraint: exactly one source scope:
  - catalog asset: `floorplan_id is not null and floorplan_upload_id is null and session_id is null and owner_user_id is null`
  - private upload/session/generated asset: `floorplan_id is null and (floorplan_upload_id is not null or session_id is not null or owner_user_id is not null)`
- `(floorplan_id, kind)`
- `(floorplan_upload_id, kind)`
- `(session_id, kind)`
- `(owner_user_id, created_at desc)`
- partial index: `(scan_status, created_at) where scan_status in ('pending', 'failed')`

비고:

- 업로드 API 는 먼저 `floorplan_uploads` row 와 `kind='original'` asset 을 만들고, virus scan / masking / OCR / AI job 을 enqueue 한다.
- `floorplan_id`, `floorplan_upload_id`, `session_id`, `owner_user_id` 가 모두 null 인 asset 은 고아 객체가 되므로 금지한다.
- private upload asset 은 `owner_user_id` 를 반드시 채운다. public catalog asset 은 `floorplan_id` 와 `floorplans.visibility` 로 접근 범위를 판단한다.
- report PDF/image asset 은 `session_id` 와 `owner_user_id` 를 함께 저장해 공유 링크 폐기/사용자 삭제 시 cleanup 대상이 명확해야 한다.
- private/session asset 에서 `session_id` 가 있으면 `owner_user_id = sessions.user_id` 를 강제한다. `floorplan_upload_id` 가 있으면 같은 `session_id` 의 upload 만 허용한다.
- catalog asset 과 private upload/session/generated asset 은 같은 row 에서 섞지 않는다. 사용자 업로드를 catalog 로 승격할 때는 private row 에 `floorplan_id` 를 덧붙이지 말고, 검수된 별도 immutable catalog asset row 를 만든다.
- catalog asset 은 후보 제시, 분석, 리포트, 학습 샘플에서 snapshot 으로 참조된 뒤에도 replay 가능해야 한다. 따라서 `floorplans` hard delete 가 asset metadata 를 cascade 삭제하지 않게 `on delete restrict` 또는 soft-delete 를 기본으로 하고, catalog 교체/반려 시에도 이미 참조된 `floorplan_assets` 는 immutable snapshot 으로 보존한다.

### 6. `floorplan_candidates`

특정 세션에서 사용자에게 제시한 주소 기반 후보 snapshot 과 ranking.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `lookup_revision integer not null default 1`
- `floorplan_id uuid references floorplans(id) on delete set null`
- `floorplan_snapshot jsonb not null default '{}'::jsonb`
- `rank integer not null`
- `confidence numeric(5,4) not null`
- `match_reasons jsonb not null default '[]'::jsonb`
- `lookup_input jsonb not null default '{}'::jsonb`
- `selected_at timestamptz`
- `rejected_at timestamptz`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- unique `(session_id, lookup_revision, floorplan_id) where floorplan_id is not null`
- unique `(session_id, lookup_revision, rank)`
- `(session_id, lookup_revision, confidence desc)`

비고:

- 검색 API 를 칠 때마다 모든 결과를 저장하는 용도가 아니다.
- 사용자가 실제로 본 후보 목록, 선택/거절한 후보, 리포트/관리자 검토에서 재현해야 하는 후보 목록을 보존하기 위한 테이블이다.
- RLS 는 `session_id -> sessions.user_id` 로 owner read 를 허용한다. write 는 후보 산정 service path 로 제한하거나, owner write 를 허용하더라도 transition function 이 lookup input/session ownership 을 검증한다.
- catalog row 가 삭제되어도 사용자에게 제시된 후보 이력은 보존한다. `floorplan_snapshot` 에 표시명, 타입, 면적, thumbnail asset pointer 등 재현 최소값을 저장하고, `floorplan_id` 는 `on delete set null` 로 둔다.
- 단순 검색 성능 로그가 필요하면 별도 `floorplan_lookup_logs` 또는 request log 집계로 분리한다.

### 7. `processing_jobs`

마스킹, OCR, AI 분석, 리포트 렌더링, 알림, cleanup, 외부 연동 작업의 도메인 job ledger.

Supabase Queues/`pgmq` 를 쓰더라도 이 테이블은 유지하는 편이 좋다. `pgmq` 는 delivery, 이 테이블은 도메인 상태와 audit 을 담당한다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `queue_name text not null`
- `job_type text not null`
  - `virus_scan`
  - `mask_floorplan`
  - `ocr_floorplan`
  - `ai_analyze_floorplan`
  - `flow_guard_evaluate`
  - `rule_evaluate`
  - `render_report`
  - `send_lead_notice`
  - `expire_sessions`
  - `sync_external_building_data`
  - `reconcile_kakao_sync`
- `session_id uuid references sessions(id) on delete cascade`
- `floorplan_id uuid references floorplans(id) on delete cascade`
- `floorplan_upload_id uuid references floorplan_uploads(id) on delete cascade`
- `asset_id uuid references floorplan_assets(id) on delete cascade`
- `pgmq_msg_id bigint`
- `status text not null default 'queued'`
  - `queued`
  - `running`
  - `succeeded`
  - `failed`
  - `cancelled`
  - `dead_lettered`
- `priority integer not null default 100`
- `attempt_count integer not null default 0`
- `max_attempts integer not null default 3`
- `run_after timestamptz not null default now()`
- `locked_by text`
- `locked_at timestamptz`
- `payload jsonb not null default '{}'::jsonb`
- `result jsonb`
- `error_code text`
- `error_message text`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

주요 인덱스:

- `(status, priority, run_after, created_at)`
- `(job_type, status, created_at desc)`
- `(session_id, created_at desc)`
- foreign key `(session_id, floorplan_upload_id)` references `floorplan_uploads(session_id, id)` when `floorplan_upload_id` is present, or an equivalent same-session trigger/check function
- foreign key `(session_id, asset_id)` references `floorplan_assets(session_id, id)` when `asset_id` is a private/session asset, or an equivalent same-session trigger/check function
- partial index: `(run_after, priority) where status = 'queued'`

비고:

- `pgmq` 미사용 fallback 으로 직접 claim loop 를 만들 경우 `for update skip locked` 패턴을 쓴다.
- worker 는 job row 를 신뢰하고 파일을 처리하므로, `session_id` 가 있는 job 은 private upload/asset reference 가 같은 세션 source 에 속한다는 DB 제약을 먼저 만족해야 한다. public catalog 작업은 `floorplan_id` 경로로 분리하고 private session asset 과 느슨하게 섞지 않는다.

### 8. `analysis_runs`

세션/도면 단위 AI/OCR/마스킹 분석 실행 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `floorplan_id uuid references floorplans(id) on delete set null`
- `floorplan_upload_id uuid references floorplan_uploads(id) on delete set null`
- `input_asset_id uuid references floorplan_assets(id) on delete set null`
- `masked_asset_id uuid references floorplan_assets(id) on delete set null`
- `overlay_asset_id uuid references floorplan_assets(id) on delete set null`
- `status text not null default 'queued'`
  - `queued`
  - `running`
  - `succeeded`
  - `failed`
  - `needs_user_review`
- `pipeline_version text not null`
- `ocr_engine text`
- `segmentation_model text`
- `vlm_model text`
- `started_at timestamptz`
- `completed_at timestamptz`
- `confidence_summary jsonb not null default '{}'::jsonb`
- `raw_outputs jsonb not null default '{}'::jsonb`
- `normalized_schema jsonb not null default '{}'::jsonb`
- `error_code text`
- `error_message text`
- `created_at timestamptz not null default now()`

주요 인덱스:

- unique `(session_id, id)`
- `(session_id, created_at desc)`
- `(status, created_at)`
- `(pipeline_version, created_at desc)`

비고:

- raw model output 이 커지면 상세 artifact 는 R2 asset 으로 빼고, 여기에는 요약과 pointer 만 둔다.
- `floorplan_upload_id` 는 같은 `session_id` 의 upload 만 참조한다. `input_asset_id`, `masked_asset_id`, `overlay_asset_id` 가 private/session asset 이면 모두 같은 `session_id` 의 `floorplan_assets` 만 허용한다.
- public catalog 도면은 `floorplan_id` 로 추적하고, catalog asset 을 직접 참조해야 할 때는 `floorplan_assets.floorplan_id = analysis_runs.floorplan_id` 및 catalog visibility 를 transition function 에서 확인한다. private artifact 와 public catalog 경로를 같은 느슨한 FK 로 섞지 않는다.

### 9. `overlay_selections`

사용자가 도면 위에서 확인/선택/정정한 벽체·공간 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `analysis_run_id uuid references analysis_runs(id) on delete set null`
- `selected_walls jsonb not null default '[]'::jsonb`
- `selected_spaces jsonb not null default '[]'::jsonb`
- `corrections jsonb not null default '[]'::jsonb`
- `schema_patch jsonb not null default '{}'::jsonb`
- `confirmed_by uuid not null references auth.users(id) on delete cascade`
- `created_at timestamptz not null default now()`

주요 인덱스:

- foreign key `(session_id, analysis_run_id)` references `analysis_runs(session_id, id)` with delete behavior that clears only `analysis_run_id`, or an equivalent same-session trigger/check function
- `(session_id, created_at desc)`
- `(confirmed_by, created_at desc)`

비고:

- overwrite 하지 말고 이력을 남긴다. 최신 row 를 현재 선택값으로 본다.
- `confirmed_by` 는 `sessions.user_id` 와 같아야 한다. 관리자 보정 flow 는 별도 admin audit/override path 로 분리하고 owner overlay row 처럼 저장하지 않는다.

### 10. `chat_messages`

세션 대화와 A2UI component 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `user_id uuid references auth.users(id) on delete set null`
- `role text not null`
  - `user`
  - `assistant`
  - `system`
  - `tool`
- `content text not null`
- `content_redacted boolean not null default false`
- `ui_components jsonb not null default '[]'::jsonb`
- `judgment_snapshot jsonb`
- `metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`

주요 인덱스:

- unique `(session_id, id)`
- `(session_id, created_at)`
- `(user_id, created_at desc)`

비고:

- 가능한 한 insert 전에 PII masking 을 끝낸다.
- `content_redacted` 로 masking 누락 여부를 관측 가능하게 둔다.
- `role='user'` 인 메시지는 `user_id = sessions.user_id` 여야 한다. assistant/system/tool 메시지는 `user_id` 를 null 로 두거나 실행 context metadata 로만 쓰고, 다른 사용자의 `user_id` 를 같은 `session_id` 에 끼워 넣을 수 없게 trigger/check function 으로 보장한다.

### 11. `chat_tool_calls`

CHAT/A2UI 에이전트 또는 backend agent 가 세션 중 실행한 tool call 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `message_id uuid references chat_messages(id) on delete set null`
- `parent_tool_call_id uuid references chat_tool_calls(id) on delete set null`
- `user_id uuid references auth.users(id) on delete set null`
- `tool_name text not null`
- `tool_kind text not null`
  - `retrieval`
  - `db_query`
  - `external_api`
  - `ai_model`
  - `rule_engine`
  - `render`
  - `notification`
  - `other`
- `status text not null default 'started'`
  - `started`
  - `succeeded`
  - `failed`
  - `cancelled`
- `input jsonb not null default '{}'::jsonb`
- `output jsonb`
- `output_summary text`
- `error_code text`
- `error_message text`
- `duration_ms integer`
- `started_at timestamptz not null default now()`
- `completed_at timestamptz`
- `metadata jsonb not null default '{}'::jsonb`

주요 인덱스:

- unique `(session_id, id)`
- foreign key `(session_id, message_id)` references `chat_messages(session_id, id)` with delete behavior that clears only `message_id`, or an equivalent same-session trigger/check function
- foreign key `(session_id, parent_tool_call_id)` references `chat_tool_calls(session_id, id)` with delete behavior that clears only `parent_tool_call_id`, or an equivalent same-session trigger/check function
- `(session_id, started_at)`
- `(message_id, started_at)`
- `(tool_name, started_at desc)`
- `(status, started_at desc)`
- `(parent_tool_call_id)`

비고:

- `ui_components` 는 사용자에게 렌더링할 UI payload 이고, tool output 은 에이전트 내부 추론/후속 메시지 생성에 쓰이는 실행 결과다. 둘을 분리한다.
- input/output 에 PII 또는 provider token 이 들어가지 않도록 tool adapter 단계에서 redaction 한다.
- output 이 너무 크면 R2 asset 또는 별도 domain table 로 빼고, `output_summary` 와 pointer 만 저장한다.
- `message_id` 와 `parent_tool_call_id` 는 반드시 같은 `session_id` 의 transcript/tool-call tree 를 가리킨다. replay/admin join 이 다른 세션의 message/tool output 을 따라가지 않도록 복합 FK 또는 same-session trigger/check function 을 둔다.

### 12. `flow_guard_decisions`

충분성/충돌/고위험 판단 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `analysis_run_id uuid references analysis_runs(id) on delete set null`
- `decision text not null`
  - `ASK_MORE`
  - `REQUEST_OVERLAY_REVIEW`
  - `PROCEED_RULE`
  - `HOLD_OR_HANDOFF`
- `missing_fields jsonb not null default '[]'::jsonb`
- `conflict_flags jsonb not null default '[]'::jsonb`
- `confidence_summary jsonb not null default '{}'::jsonb`
- `schema_snapshot jsonb not null`
- `next_actions jsonb not null default '[]'::jsonb`
- `completion_decision jsonb`
- `evaluated_by text not null`
- `created_at timestamptz not null default now()`

주요 인덱스:

- foreign key `(session_id, analysis_run_id)` references `analysis_runs(session_id, id)` with delete behavior that clears only `analysis_run_id`, or an equivalent same-session trigger/check function
- `(session_id, created_at desc)`
- `(decision, created_at desc)`

비고:

- `next_actions` 는 `packages/contracts/schemas/completion-decision.schema.json` 의 `CompletionDecision.next_actions` 배열과 같은 shape 로 저장한다.
- 전체 CompletionDecision payload 를 재현해야 하는 경우 `completion_decision` 에 schema_version, decision, reason, missing_fields, next_actions, confidence_summary, conflict_flags snapshot 을 함께 저장한다.
- `analysis_run_id` 가 있으면 같은 `session_id` 의 분석 실행만 참조한다. FLOW_GUARD decision 은 CHAT/RULE 분기를 직접 움직이므로, stale analysis UUID 가 다른 세션의 AI 결과를 현재 세션 판단에 섞지 못하게 복합 FK 또는 trigger/check function 으로 막는다.

### 13. `rule_sets`

법령/룰셋 버전 관리.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `version text not null unique`
- `status text not null`
  - `draft`
  - `active`
  - `archived`
- `effective_from date`
- `effective_to date`
- `source_refs jsonb not null default '[]'::jsonb`
- `rules jsonb not null`
- `validated_at timestamptz`
- `created_by uuid references auth.users(id) on delete set null`
- `created_at timestamptz not null default now()`

주요 인덱스:

- partial unique index: `(status) where status = 'active'`
- `(effective_from desc)`

비고:

- 룰 실행 시 current active 만 읽고 끝내지 말고, `rule_set_id` 와 `version` 을 결과에 snapshot 한다.

### 14. `rule_evaluations`

세션 단위 결정성 룰 평가 결과.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `rule_set_id uuid not null references rule_sets(id)`
- `input_schema jsonb not null`
- `result_schema_version text not null`
- `verdict text not null`
  - `ALLOW`
  - `WARN`
  - `DENY`
  - `HOLD`
- `ruleset_version text not null`
- `permit_type text`
  - `permit`
  - `notification`
  - `none`
  - `unknown`
- `permit_required boolean not null`
- `required_facilities jsonb not null default '[]'::jsonb`
- `legal_basis jsonb not null default '[]'::jsonb`
- `pending_reasons jsonb not null default '[]'::jsonb`
- `rule_trace jsonb not null default '[]'::jsonb`
- `result_snapshot jsonb`
- `evaluated_at timestamptz not null default now()`
- `created_at timestamptz not null default now()`

주요 인덱스:

- unique `(session_id, id)`
- `(session_id, created_at desc)`
- `(result_schema_version, created_at desc)`
- `(verdict, created_at desc)`
- `(rule_set_id, created_at desc)`

비고:

- `result_schema_version`, `verdict`, `required_facilities`, `permit_required`, `legal_basis`, `ruleset_version`, `evaluated_at` 은 `packages/contracts/schemas/rule-eval-result.schema.json` 의 `RuleEvalResult` 정본 필드와 1:1 로 맞춘다.
- `result_snapshot` 은 필요 시 전체 `RuleEvalResult` payload 를 저장한다. split column 만으로도 조회는 가능해야 하지만, contract shape 가 바뀐 뒤 historical replay 를 해야 하는 REPORT/admin path 는 `result_schema_version` 과 snapshot 을 함께 사용한다.
- 사용자 노출용 `result` 라벨이 필요하면 API/REPORT view model 에서 `ALLOW | WARN | DENY | HOLD` 를 번역한다. DB 저장값을 `possible | impossible | pending` 으로 재정의하지 않는다.

### 15. `reports`

사전검토 리포트. 현재 리포트는 세션당 1개지만, revision audit 을 위해 이력을 남긴다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `rule_evaluation_id uuid`
- `revision integer not null default 1`
- `status text not null default 'draft'`
  - `draft`
  - `published`
  - `superseded`
  - `revoked`
- `verdict text not null`
  - `ALLOW`
  - `WARN`
  - `DENY`
  - `HOLD`
- `estimate_result_schema_version text`
- `estimate_result_snapshot jsonb`
- `estimate_total_min numeric(14,2)`
- `estimate_total_max numeric(14,2)`
- `estimate_generated_at timestamptz`
- `estimate_policy_version text`
- `report_json jsonb not null`
- `legal_notice_included boolean not null default false`
- `pdf_asset_id uuid references floorplan_assets(id) on delete set null`
- `share_token_hash text`
- `share_expires_at timestamptz`
- `published_at timestamptz`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- unique `(session_id, revision)`
- unique `(session_id, id)`
- foreign key `(session_id, rule_evaluation_id)` references `rule_evaluations(session_id, id)` with delete behavior that clears only `rule_evaluation_id`, or an equivalent same-session trigger/check function
- foreign key `(session_id, pdf_asset_id)` references `floorplan_assets(session_id, id)` with delete behavior that clears only `pdf_asset_id`, or an equivalent same-session trigger/check function
- trigger/check function: when `rule_evaluation_id is not null`, `reports.verdict = rule_evaluations.verdict`
- check constraint: `share_token_hash is null or (status = 'published' and published_at is not null and share_expires_at is not null)`
- partial unique index: `(session_id) where status = 'published'`
- partial unique index: `(share_token_hash) where share_token_hash is not null`
- partial index: `(share_expires_at) where share_token_hash is not null`
- check constraint: `status <> 'published' or legal_notice_included`
- `(verdict, created_at desc)`

비고:

- 공유 token 원문은 저장하지 않는다. hash 만 저장한다.
- publish 이후 수정 대신 새 revision 을 발행하는 방식을 권장한다.
- `rule_evaluation_id` 는 같은 세션의 룰 평가 결과만 참조한다. 단일 FK 만 두면 다른 세션의 평가 결과를 리포트에 연결할 수 있으므로 복합 FK 또는 same-session trigger/check function 이 필요하다.
- `rule_evaluation_id` 가 있으면 report 대표 `verdict` 는 참조한 `rule_evaluations.verdict` 와 같아야 한다. P0 에서는 mismatch 를 허용하지 않는다. 수동 override 가 필요해지면 별도 `verdict_override_source`, `verdict_override_reason`, `verdict_overridden_by`, `verdict_overridden_at` 와 승인 audit path 를 추가한 뒤 trigger 에서 그 경로만 예외로 둔다.
- `pdf_asset_id` 는 같은 세션의 `kind='report_pdf'` 또는 `kind='report_image'` asset 만 참조한다. render job 이 stale asset UUID 를 전달해 다른 세션의 PDF/image 를 연결하는 경로를 DB 제약 또는 trigger/check function 으로 차단한다.
- publish 상태에서는 `legal_notice_included = true` 를 check/trigger 로 강제한다. 법적 고지 누락은 앱 검증만으로 막지 않는다.
- `legal_notice_included` 기본값은 `false` 로 둔다. report generator 가 법적 고지 문구를 `report_json` 과 PDF/image 산출물에 실제로 넣은 뒤 같은 publish transition 에서 명시적으로 `true` 로 설정해야 한다. 값이 false 이거나 renderer 검증이 없으면 publish 를 차단한다.
- 공유 링크 발급은 conversion-only 동작이다. 익명 사용자가 preview 를 볼 수는 있어도 `share_token_hash` 생성은 non-anonymous + current required terms 통과 후에만 허용한다.
- `share_token_hash` 는 active published report 에만 허용한다. DB check 는 `status='published'`, `published_at is not null`, `share_expires_at is not null` 을 강제하고, `share_expires_at > now()` 처럼 volatile 한 시간 비교는 발급/갱신 transition function 에서 검증한다. `revoked` 또는 `superseded` 전이 시에는 같은 transaction 에서 `share_token_hash = null`, `share_expires_at = null` 로 지워 공유 조회가 stale report 를 찾지 못하게 한다.
- `estimate_result_snapshot` 은 `packages/contracts` 의 canonical EstimateResult 전체 payload 를 저장한다. `estimate_result_schema_version`, total min/max, generated_at, policy_version 을 searchable column 으로 함께 두고, `estimate_items` 는 이 snapshot 의 queryable line item projection 이다.

### 16. `estimate_items`

리포트 하위 견적 항목.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `report_id uuid not null references reports(id) on delete cascade`
- `item_type text not null`
  - `fire_panel`
  - `fire_glass`
  - `fire_door`
  - `detector`
  - `permit_agency`
  - `consultation`
  - `other`
- `basis_value numeric(12,2)`
- `basis_unit text`
- `unit_price_min numeric(14,2)`
- `unit_price_max numeric(14,2)`
- `amount_min numeric(14,2)`
- `amount_max numeric(14,2)`
- `currency text not null default 'KRW'`
- `policy_version text not null`
- `assumptions jsonb not null default '[]'::jsonb`
- `created_at timestamptz not null default now()`

주요 인덱스:

- unique `(report_id, id)`
- `(report_id)`
- `(item_type, created_at desc)`

### 17. `leads`

상담 신청/행위허가 의뢰 전환 기록.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid not null references sessions(id) on delete cascade`
- `report_id uuid`
- `estimate_item_id uuid`
- `user_id uuid not null references auth.users(id) on delete cascade`
- `lead_type text not null`
  - `consultation`
  - `permit_agency`
- `status text not null default 'new'`
  - `new`
  - `contacted`
  - `in_progress`
  - `won`
  - `lost`
  - `closed`
- `contact_info_encrypted bytea not null`
- `contact_info_key_id text not null`
- `contact_summary jsonb not null default '{}'::jsonb`
- `assignee_id uuid references auth.users(id) on delete set null`
- `notification_status text not null default 'pending'`
  - `pending`
  - `sent`
  - `failed`
  - `suppressed`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

주요 인덱스:

- unique `(session_id, id)`
- foreign key `(session_id, report_id)` references `reports(session_id, id)` with delete behavior that clears only `report_id`, or an equivalent same-session trigger/check function
- foreign key `(report_id, estimate_item_id)` references `estimate_items(report_id, id)` with delete behavior that clears only `estimate_item_id`, or an equivalent same-report trigger/check function
- check constraint: `estimate_item_id is null or report_id is not null`
- `(user_id, created_at desc)`
- `(session_id, created_at desc)`
- `(report_id)`
- `(estimate_item_id)`
- `(status, created_at desc)`
- `(assignee_id, status, created_at desc)`
- partial index: `(notification_status, created_at) where notification_status in ('pending', 'failed')`

비고:

- conversion-only 테이블이다. 익명 Supabase token 으로 생성하면 안 된다.
- phone/email 원문을 JSONB 로 저장하지 않는다. 암호화 payload + 최소 요약만 둔다.
- `user_id` 는 `sessions.user_id` 와 같아야 한다. conversion insert 는 `auth.uid() = sessions.user_id = leads.user_id` 를 서버 guard 와 DB trigger/check function 으로 함께 확인한다.
- `report_id` 와 `estimate_item_id` 는 같은 `session_id` 범위만 참조한다. 권장 DDL 은 `reports(session_id, id)` 와 `estimate_items(report_id, id)` 또는 `estimate_items(session_id, id)` 를 unique 로 보강한 뒤 복합 FK 를 둔다. 문서 단계에서는 최소한 same-session trigger/check function 으로 다른 세션의 report/estimate 연결을 차단한다고 봉인한다.
- `estimate_item_id` 가 있으면 `report_id` 도 반드시 있어야 한다. nullable composite FK 의 MATCH SIMPLE 동작 때문에 `report_id` 가 null 이면 `(report_id, estimate_item_id)` 검증이 건너뛰어질 수 있으므로, `estimate_item_id is null or report_id is not null` check 를 별도로 둔다.

## 연동/운영 테이블

### 18. `webhook_deliveries`

외부 알림/webhook 발송 audit.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `event_type text not null`
- `target text not null`
- `related_table text`
- `related_id uuid`
- `payload jsonb not null`
- `status text not null default 'pending'`
  - `pending`
  - `sent`
  - `failed`
  - `dead_lettered`
- `attempt_count integer not null default 0`
- `last_attempt_at timestamptz`
- `next_attempt_at timestamptz`
- `response_status integer`
- `response_body_redacted text`
- `created_at timestamptz not null default now()`

주요 인덱스:

- `(status, next_attempt_at)`
- `(event_type, created_at desc)`
- `(related_table, related_id)`

비고:

- Database Webhooks/`pg_net` 으로 비동기 HTTP 를 보낼 수 있어도, 발송 상태의 정본은 이 테이블에 남긴다.

### 19. `scheduled_task_runs`

Supabase Cron / `pg_cron` 작업 실행 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `task_name text not null`
- `cron_job_id bigint`
- `status text not null`
  - `started`
  - `succeeded`
  - `failed`
  - `skipped`
- `started_at timestamptz not null default now()`
- `finished_at timestamptz`
- `result jsonb`
- `error_message text`

주요 인덱스:

- `(task_name, started_at desc)`
- `(status, started_at desc)`

후보 cron 작업:

- 비활성 session 만료
- 만료된 공유 링크 폐기
- 보존 기간 지난 익명 사전검토 artifact 삭제
- 실패 webhook 재시도
- Kakao Sync 약관 audit reconcile
- queue metrics 수집

### 20. `external_sync_records`

주소 API, 건축물대장, 세움터 등 외부 데이터 연동 이력.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid references sessions(id) on delete cascade`
- `user_id uuid references auth.users(id) on delete cascade`
- `provider text not null`
- `external_key text`
- `sync_type text not null`
- `status text not null`
  - `pending`
  - `succeeded`
  - `failed`
  - `stale`
- `request_payload jsonb`
- `response_payload jsonb`
- `fetched_at timestamptz`
- `expires_at timestamptz`
- `created_at timestamptz not null default now()`

주요 인덱스:

- foreign key `(session_id, user_id)` references `sessions(id, user_id)` on delete cascade, or an equivalent same-owner trigger/check function when both columns are present
- `(user_id, created_at desc)`
- `(provider, external_key)`
- `(session_id, created_at desc)`
- `(status, expires_at)`

비고:

- 주소/건물 조회 request/response payload 는 개인정보 또는 준식별 정보를 포함할 수 있으므로 owner RLS 범위에 포함한다.
- 세션 기반 조회는 `session_id -> sessions.user_id` 로 owner 를 확인하고, 세션 없이 사용자 계정 단위로 캐시하는 조회는 `user_id` 를 직접 채운다. 둘 다 null 인 row 는 service-only 운영 sync 로 제한한다.
- `session_id` 와 `user_id` 가 모두 있으면 `user_id = sessions.user_id` 를 강제한다. RLS 에서 session owner 와 direct owner 를 OR 로 허용하므로, 두 값이 어긋난 row 는 payload PII 를 잘못된 사용자에게 노출할 수 있다.

## P1/P2 데이터 환류 테이블

관리자/학습 데이터 작업이 시작되기 전까지 migration 은 미뤄도 된다. 다만 P0 설계가 이 확장을 막지 않도록 둔다.

### 21. `training_samples`

세션, 도면 asset, overlay selection 을 학습 데이터셋으로 연결.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid references sessions(id) on delete set null`
- `floorplan_id uuid references floorplans(id) on delete set null`
- `floorplan_upload_id uuid references floorplan_uploads(id) on delete set null`
- `asset_id uuid references floorplan_assets(id) on delete set null`
- `label_status text not null default 'unlabeled'`
- `label_payload jsonb`
- `quality_score numeric(5,4)`
- `reviewed_by uuid references auth.users(id) on delete set null`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- foreign key `(session_id, floorplan_upload_id)` references `floorplan_uploads(session_id, id)` when `floorplan_upload_id` is present, or an equivalent same-session trigger/check function
- foreign key `(session_id, asset_id)` references `floorplan_assets(session_id, id)` when `asset_id` is a private/session asset, or an equivalent same-session trigger/check function
- `(session_id, created_at desc)`
- `(label_status, created_at desc)`

비고:

- 학습 샘플은 하나의 source scope 만 대표해야 한다. `session_id`, upload, private asset 을 함께 쓰는 경우 모두 같은 세션에 속해야 하며, catalog sample 은 `floorplan_id` 와 보존된 catalog asset/snapshot 경로로 분리한다.
- 개인정보 삭제 후 학습 샘플을 남길 때는 session pointer 를 null 로 만들기 전에 `label_payload` 와 asset metadata 가 필요한 최소 비식별 snapshot 을 갖고 있는지 확인한다.

### 22. `permit_outcomes`

실제 행위허가 결과 환류.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `session_id uuid references sessions(id) on delete set null`
- `lead_id uuid references leads(id) on delete set null`
- `outcome text not null`
  - `approved`
  - `rejected`
  - `withdrawn`
  - `unknown`
- `authority_name text`
- `decision_date date`
- `reason_summary text`
- `evidence_asset_id uuid references floorplan_assets(id) on delete set null`
- `created_by uuid references auth.users(id) on delete set null`
- `created_at timestamptz not null default now()`

주요 제약/인덱스:

- foreign key `(session_id, lead_id)` references `leads(session_id, id)` when `lead_id` is present, or an equivalent same-session trigger/check function
- foreign key `(session_id, evidence_asset_id)` references `floorplan_assets(session_id, id)` when `evidence_asset_id` is a private/session asset, or an equivalent same-session trigger/check function
- `(session_id, created_at desc)`
- `(lead_id, created_at desc)`
- `(outcome, decision_date desc)`

비고:

- `lead_id` 가 있으면 해당 lead 의 `session_id` 와 outcome 의 `session_id` 가 같아야 한다. 관리자/data feedback 입력에서 stale lead UUID 로 다른 세션의 허가 결과를 붙이는 것을 DB 제약 또는 trigger/check function 으로 차단한다.

### 23. `admin_audit_logs`

관리자 변경 이력. lead, report, ruleset, training label, user status 변경을 기록한다.

주요 컬럼:

- `id uuid primary key default gen_random_uuid()`
- `actor_user_id uuid references auth.users(id) on delete set null`
- `action text not null`
- `target_table text not null`
- `target_id uuid not null`
- `before_snapshot jsonb`
- `after_snapshot jsonb`
- `created_at timestamptz not null default now()`

## RLS 정책 초안

P0 사용자 소유 테이블:

- `sessions`: owner 는 자기 row 읽기/수정 가능. admin 은 전체 조회 가능.
- `session_addresses`: `user_id` 기준 owner 접근. admin 전체 조회.
- `floorplans`: `public_catalog` 는 authenticated/anonymous 사용자에게 읽기 허용. `admin_only` 는 admin 만.
- `floorplan_uploads`: owner 만 읽기/수정 가능. admin 은 검수/승격 목적으로 조회 가능.
- `floorplan_assets`: public catalog asset 은 visible catalog floorplan 기준으로 읽기 허용한다. private upload/session/generated asset(`original`, `masked`, `overlay`, `report_pdf`, `report_image` 등)은 `session_id -> sessions.user_id` 또는 `owner_user_id` 로 owner read 를 허용한다. signed URL 발급은 서버 API 가 담당한다.
- `floorplan_candidates`: `session_id -> sessions.user_id` 로 owner read 를 허용한다. write 는 service-only 또는 owner write + transition function 검증으로 제한한다.
- `chat_messages`, `chat_tool_calls`, `analysis_runs`, `overlay_selections`, `flow_guard_decisions`, `rule_evaluations`, `reports`, `estimate_items`, `external_sync_records`: `sessions.user_id` 를 통해 owner 확인. `estimate_items` 는 `reports.session_id -> sessions.user_id` 로 owner 를 확인한다. `external_sync_records` 는 `session_id -> sessions.user_id` 또는 직접 `user_id` 로 owner 를 확인한다.
- `leads`: 사용자는 자기 lead summary 조회 가능. admin 은 관리 가능. insert 는 non-anonymous + required terms 통과 필요.
- `processing_jobs`, `webhook_deliveries`, `scheduled_task_runs`: service/admin 전용.

구현 메모:

- 브라우저에서 Supabase direct read 를 허용한다면 `auth.uid()` 기반 RLS 가 필수다.
- FastAPI/SQLAlchemy 경로는 PostgREST 가 아니므로 RLS claims 주입 또는 명시적 서버 인가 검사를 별도로 유지해야 한다.
- 상담/리드/리포트 저장·공유 같은 conversion-only 테이블은 restrictive policy 를 써서 permissive owner policy 로 우회되지 않게 한다.
- RLS helper 호출은 Supabase 권장 패턴대로 `(select auth.uid())`, `(select auth.jwt())` 형태로 감싸 policy row 마다 helper 를 반복 평가하지 않게 한다.
- `leads`, `reports.share_token_hash` 생성 경로, 결제/일정 예약 테이블은 permissive owner policy 만으로는 부족하다. ownership 은 permissive policy, non-anonymous + current terms 는 `as restrictive` policy 로 분리하거나 모든 policy 에 같은 술어를 fold 한다.
- `auth.users.is_anonymous` 는 RLS 에서 직접 join 하지 말고 JWT claim 또는 서버 guard 의 검증 결과를 사용한다. DB policy 에서 확인해야 한다면 stable helper function 을 별도 정의하고 EXPLAIN 으로 full scan 이 없는지 확인한다.
- admin 판정은 `public.users.role = 'admin' and status = 'active'` 를 기준으로 하되, 고빈도 policy 에서는 별도 `public.is_admin()` stable helper 로 캡슐화한다.

예시 ownership policy:

```sql
alter table public.sessions enable row level security;

create policy sessions_owner_select
on public.sessions
for select
to authenticated
using (user_id = (select auth.uid()));
```

예시 conversion-only restrictive policy:

```sql
create policy leads_owner_select
on public.leads
as permissive
for select
to authenticated
using (user_id = (select auth.uid()));

create policy leads_non_anonymous_current_terms_insert
on public.leads
as restrictive
for insert
to authenticated
with check (
  coalesce((select auth.jwt()) ->> 'is_anonymous', 'true') = 'false'
  and not exists (
    select 1
    from public.policy_current_required_terms as required_term
    where required_term.is_active
      and required_term.required_for in ('lead', 'signup')
      and not exists (
        select 1
        from public.terms_consents as consent
        where consent.user_id = (select auth.uid())
          and consent.term_id = required_term.term_id
          and consent.version = required_term.version
      )
  )
);
```

이 gate 는 conversion write path 에만 적용한다. `for all` restrictive policy 로 만들면 약관 버전이 갱신된 뒤 기존 lead owner/admin SELECT 에도 현재 약관 조건이 AND 되어 과거 lead 조회가 막힐 수 있다. owner/admin read policy 는 lead 생성 시점의 약관 충족 여부와 분리한다.

FastAPI 경로 주의:

- SQLAlchemy connection 은 PostgREST 가 아니므로 `auth.uid()` / `auth.jwt()` claim 이 자동 설정되지 않는다.
- RLS 를 실제로 DB 레벨에서 적용하려면 backend login role 은 `bypassrls` 권한이 없어야 하고, 트랜잭션마다 JWT claims 를 `SET LOCAL` 로 주입해야 한다.
- 그 전까지는 RLS 를 미래 direct-read 보호막으로 두되, FastAPI service layer 에서 동일 인가를 중복 강제한다.

## 권장 migration 단계

### Phase 0: Auth gate 보조 테이블

추가 테이블:

- `terms_consent_intents`
- `policy_current_required_terms`

가능해지는 기능:

- Google / Naver 내부 약관 intent 저장
- current required terms 기반 conversion-only gate
- `leads` / 리포트 저장·공유 RLS restrictive policy 의 공통 참조점

### Phase A: INPUT/CHAT 셸

추가 테이블:

- `sessions`
- `session_addresses`
- `floorplans`
- `floorplan_uploads`
- `floorplan_assets`
- `floorplan_candidates`
- `chat_messages`
- `chat_tool_calls`

가능해지는 기능:

- 주소 입력
- 도면 후보 조회 metadata
- 사용자 업로드 metadata
- 빈/mock 채팅 세션

### Phase B: MASK/AI/OVERLAY

추가 테이블:

- `processing_jobs`
- `analysis_runs`
- `overlay_selections`
- queue setup (`pgmq` 또는 SQL `skip locked` fallback)

가능해지는 기능:

- scan/mask/analyze job tracking
- 모델 출력 버전 관리
- 사용자 벽체 선택 이력

### Phase C: FLOW_GUARD/RULE/REPORT

추가 테이블:

- `flow_guard_decisions`
- `rule_sets`
- `rule_evaluations`
- `reports`
- `estimate_items`

가능해지는 기능:

- 결정성 룰 평가
- 리포트 생성
- 공유 링크 metadata
- 법적 고지 포함 여부 가드

### Phase D: 리드/운영 연계

추가 테이블:

- `leads`
- `webhook_deliveries`
- `scheduled_task_runs`
- `external_sync_records`
- session expiry / retry / reconcile cron

가능해지는 기능:

- 상담/행위허가 리드 전환
- 이메일/SMS/admin 알림 발송 추적
- cleanup/retry/reconcile 자동화

선행 조건:

- `policy_current_required_terms` 와 `terms_consents` 기반 current terms guard
- Kakao Sync reconciliation 경로 확정
- contact_info 암호화 key id / rotation 정책 확정

### Phase E: 관리자/데이터 환류

추가 테이블:

- `training_samples`
- `permit_outcomes`
- `admin_audit_logs`

가능해지는 기능:

- 학습 데이터 환류
- 실제 행위허가 결과 추적
- 관리자 audit

## 남은 결정 사항

1. Queue 정본을 Supabase Queues/`pgmq` 로 바로 갈지, 우선 `processing_jobs` claim loop 로 시작할지 결정해야 한다. 권장: `processing_jobs` 는 도메인 ledger 로 유지하고, Supabase branch 에서 extension 가능성이 확인되면 `pgmq` 를 delivery 로 붙인다.
2. 브라우저가 Supabase client 로 session/report 데이터를 직접 읽을지 결정해야 한다. 직접 읽지 않더라도 RLS 는 미래 접근 경로 보호를 위해 둔다.
3. 익명 session, 업로드 도면, chat log, 공유 링크, request log, webhook payload 의 retention window 를 정해야 한다.
4. `public.users` 를 `public.user_profiles` 로 rename 할지 결정해야 한다. 현재 코드는 `public.users` 를 쓰므로 rename 은 별도 clarity-only migration 으로 분리하는 게 맞다.
5. report 는 publish 후 immutable 로 볼지 결정해야 한다. 권장: publish 후 수정 금지, 새 revision 발행.
6. raw model output 을 JSONB 로 얼마나 보관할지 결정해야 한다. 권장: Postgres 에는 요약과 schema snapshot, 대형 debug artifact 는 R2 asset.
7. `sessions` 와 `session_addresses` 의 FK cycle 을 DEFERRABLE 로 둘지, `sessions.address_id` 를 application-level current pointer 로만 둘지 결정해야 한다.
8. `floorplan_assets` 에서 catalog asset 과 private session asset 을 같은 테이블로 유지할지, RLS 복잡도가 커지면 public catalog asset view 를 분리할지 결정해야 한다.

## Migration 작성 체크리스트

- [ ] 모든 `status` / `kind` / `role` 계열 text 컬럼에 check constraint 를 둔다.
- [ ] 모든 FK 컬럼에 index 를 둔다. 단일 FK 외에 주요 조회 순서가 있으면 `(fk, created_at desc)` 복합 index 를 우선한다.
- [ ] JSONB GIN index 는 처음부터 남발하지 않는다. `building_identity`, `metadata`, `report_json` 등은 쿼리 패턴이 생긴 뒤 targeted expression/GIN index 를 추가한다.
- [ ] `updated_at` 이 있는 테이블은 공통 trigger 또는 애플리케이션 update path 중 하나로 일관되게 관리한다.
- [ ] RLS 를 켜는 테이블은 owner policy, admin policy, conversion-only restrictive policy 를 같은 migration 에 포함한다.
- [ ] `reports.status='published'` 는 `legal_notice_included = true` 를 강제한다.
- [ ] `leads` insert 는 non-anonymous + current required terms 통과를 DB/RLS/API 에서 모두 검증한다.
- [ ] 공유 token 원문, 연락처 원문, provider token, 도면 원본 binary 는 Postgres 에 저장하지 않는다.
- [ ] 대량 삭제/retention 대상 테이블은 `created_at`, `expires_at`, `status` 기준 partial index 를 둔다.
- [ ] 신규 모델 파일을 만들면 `.github/workflows/ci.yml::migrate-check` 조건에 맞춰 `supabase/migrations/*.sql` 을 같은 PR 에 포함한다.

## 필드 설명

아래 설명은 검토용이다. 실제 migration 작성 시에는 타입, nullable, default, check constraint 를 함께 확정한다.

### `sessions`

| 필드 | 설명 |
|---|---|
| `id` | 사전검토 세션 고유 ID. 모든 메인 기능 데이터의 중심 참조값이다. |
| `user_id` | 세션 소유자. Supabase `auth.users.id` 를 참조한다. 비회원도 Supabase Anonymous Sign-In 으로 생성된 anonymous `auth.users.id` 를 가지므로 null 로 두지 않는다. |
| `status` | 세션 진행 상태. 주소 입력, 도면 선택, 분석 중, 리포트 준비 등 워크플로우 단계를 표현한다. |
| `address_id` | 이 세션에서 사용한 정규화 주소 row. 값이 있으면 같은 세션의 `session_addresses(session_id, id)` 만 참조한다. |
| `selected_floorplan_id` | 사용자가 내부/외부 후보 catalog 에서 선택한 도면. 직접 업로드를 선택한 경우 null 일 수 있다. 같은 세션에 제시된 non-rejected 후보이거나 verified/public visible row 로 transition 검증을 통과해야 한다. |
| `selected_floorplan_upload_id` | 사용자가 직접 업로드한 도면을 선택한 경우의 upload row. catalog 후보를 선택한 경우 null 일 수 있다. 같은 session 의 upload 만 허용한다. |
| `selected_floorplan_asset_id` | 실제 분석 입력으로 사용한 asset row. catalog 후보든 사용자 업로드든 최종 입력 파일은 asset 으로 추적한다. private asset 은 같은 session/owner 로 제한한다. |
| `judgment_schema` | 주소, 도면 해석, 사용자 선택, 추가 질의 응답을 병합한 공통 판단 스키마 현재값. |
| `judgment_schema_version` | `judgment_schema` 의 schema version. `packages/contracts` 버전과 맞춰야 한다. |
| `completion_decision` | 마지막 FLOW_GUARD 결정값. `ASK_MORE`, `REQUEST_OVERLAY_REVIEW`, `PROCEED_RULE`, `HOLD_OR_HANDOFF` 중 하나가 된다. |
| `last_activity_at` | 사용자의 마지막 활동 시각. 세션 만료/정리 cron 의 기준값이다. |
| `expires_at` | 세션 만료 예정 시각. 익명 세션 retention 정책과 연결된다. |
| `created_at` | 세션 생성 시각. |
| `updated_at` | 세션 마지막 갱신 시각. |

### `session_addresses`

| 필드 | 설명 |
|---|---|
| `id` | 주소 row 고유 ID. |
| `session_id` | 주소가 속한 사전검토 세션. 한 세션에 기본 1개 주소를 둔다. |
| `user_id` | 주소 입력 사용자. RLS 소유권 확인을 빠르게 하기 위해 session 을 거치지 않고도 둔다. |
| `road_address` | 도로명 주소 원문 또는 정규화값. |
| `jibun_address` | 지번 주소 원문 또는 정규화값. |
| `apartment_name` | 사용자가 입력하거나 주소 API 로 보정된 아파트/단지명. |
| `building_dong` | 아파트 동 정보. 예: `101동`. |
| `unit_ho` | 호수 정보. PII 성격이 강하므로 로그/외부 payload 에 노출하지 않는다. |
| `floor_no` | 층수. 룰/도면 후보 매칭에 쓰일 수 있다. |
| `exclusive_area_m2` | 전용면적 m2. 평형/타입 후보 매칭에 사용한다. |
| `size_type` | 84A, 59B 같은 세대 타입 문자열. |
| `building_identity` | 주소 API, 내부 DB, 외부 연동에서 얻은 building key 묶음. JSONB 로 보관한다. |
| `address_provider` | 주소 정규화 출처. 예: 공공 주소 API, 수동 입력, 외부 업체 API. |
| `normalized_at` | 주소 정규화가 완료된 시각. |
| `created_at` | 주소 row 생성 시각. |

### `floorplans`

| 필드 | 설명 |
|---|---|
| `id` | 후보 catalog 도면 metadata 고유 ID. |
| `created_by` | catalog 도면을 등록/승격한 관리자 또는 시스템 user. |
| `source` | 도면 출처. 내부 DB, 외부 후보, 사용자 업로드 승격본 등을 구분한다. |
| `visibility` | catalog 접근 범위. 사용자에게 후보로 보여줄지, 관리자 전용으로 둘지 구분한다. |
| `apartment_name` | 도면이 대응되는 아파트/단지명. |
| `building_dong` | 대응 동. 표준 평면도처럼 동 구분이 없으면 null 가능하다. |
| `size_type` | 84A, 59B 등 평면 타입. 후보 검색의 핵심 키다. |
| `exclusive_area_m2` | 전용면적. 타입명이 불명확할 때 후보 검색 보조값으로 사용한다. |
| `layout_family` | 같은 구조를 공유하는 도면 묶음명. 예: 84A 좌우반전군. |
| `address_fingerprint` | 주소/단지/타입을 정규화해 만든 검색용 fingerprint. 원문 주소 저장을 줄이는 데도 사용 가능하다. |
| `promoted_from_upload_id` | 사용자 업로드 도면을 검수 후 catalog 로 승격한 경우 원본 upload row 를 가리킨다. |
| `metadata` | 수집 출처, 원본 해상도, OCR summary, 검수 메모 등 확장 metadata. |
| `quality_status` | 도면 신뢰/검수 상태. 미검수, 검증됨, 반려, 재검토 필요 등. |
| `created_at` | 도면 metadata 생성 시각. |
| `updated_at` | 도면 metadata 마지막 수정 시각. |

### `floorplan_uploads`

| 필드 | 설명 |
|---|---|
| `id` | 사용자 업로드 도면 record 고유 ID. |
| `session_id` | 업로드가 발생한 사전검토 세션. |
| `user_id` | 업로드한 사용자. 비회원이면 anonymous `auth.users.id`. |
| `original_asset_id` | 사용자가 올린 원본 파일 asset. 업로드 직후 asset 생성 순서 때문에 일시적으로 null 가능하다. |
| `status` | 업로드 처리 상태. 스캔 대기, 처리 가능, 처리 중, 처리 완료, 반려, catalog 승격 등을 표현한다. |
| `file_name` | 사용자가 올린 원본 파일명. PII 가능성이 있으므로 외부 노출 주의. |
| `source_note` | 사용자가 입력한 출처/설명. 예: 관리사무소 제공, 직접 촬영. |
| `upload_metadata` | 브라우저 업로드 context, 이미지 크기, PDF 페이지 수 등 부가 metadata. |
| `created_at` | 업로드 row 생성 시각. |
| `updated_at` | 업로드 row 마지막 갱신 시각. |

### `floorplan_assets`

| 필드 | 설명 |
|---|---|
| `id` | 객체 스토리지 asset 고유 ID. |
| `floorplan_id` | asset 이 연결된 catalog 도면. catalog asset scope 에서만 사용하며 private upload/session/generated asset 과 같은 row 에 섞지 않는다. 이미 후보/리포트/학습 샘플에서 참조된 catalog asset 은 catalog row cleanup 으로 cascade 삭제하지 않는다. |
| `floorplan_upload_id` | asset 이 연결된 사용자 업로드 record. catalog asset 이면 null 이며, private scope 에서만 사용한다. |
| `session_id` | 특정 세션에서만 쓰이는 asset 인 경우 연결한다. masked/overlay/report_pdf/report_image 같은 generated private asset 도 이 경로로 owner RLS 를 적용한다. |
| `owner_user_id` | asset 소유 사용자. private upload/session/generated asset 접근 제어에 사용한다. |
| `kind` | asset 종류. 원본, 썸네일, 마스킹본, overlay, PDF 등을 구분한다. |
| `storage_provider` | 저장소 provider. 현재 기본값은 R2 이지만 S3 호환 provider 교체 가능성을 둔다. |
| `bucket` | 객체 스토리지 bucket 이름. |
| `object_key` | bucket 내부 object key. signed URL 발급 시 사용한다. |
| `content_type` | MIME type. 예: `image/png`, `application/pdf`. |
| `byte_size` | 파일 크기 byte. 업로드 제한/비용 추적에 사용한다. |
| `sha256_hex` | 파일 hash. 중복 탐지, 무결성 확인, 악성 파일 추적에 사용한다. |
| `width_px` | 이미지 너비. PDF 등에는 null 가능하다. |
| `height_px` | 이미지 높이. PDF 등에는 null 가능하다. |
| `page_count` | PDF 페이지 수. 이미지 단일 파일은 1 또는 null 가능하다. |
| `scan_status` | 악성코드/파일 검증 상태. 처리 전에는 `pending`, 통과 후 `clean`. |
| `created_at` | asset metadata 생성 시각. |

### `floorplan_candidates`

| 필드 | 설명 |
|---|---|
| `id` | 후보 row 고유 ID. |
| `session_id` | 후보 snapshot 이 속한 세션. |
| `lookup_revision` | 같은 세션에서 주소/평형 등을 바꿔 후보를 다시 계산했을 때 구분하는 revision. |
| `floorplan_id` | 후보로 제시된 도면. |
| `floorplan_snapshot` | catalog row 삭제 후에도 사용자가 본 후보를 재현하기 위한 표시명, 타입, 면적, thumbnail object metadata 등 최소 snapshot. 단순 asset id 만 복사하면 catalog cleanup 때 replay 가 깨질 수 있다. |
| `rank` | 사용자에게 표시할 후보 순서. |
| `confidence` | 주소/면적/타입 매칭 신뢰도. 0~1 범위 소수로 본다. |
| `match_reasons` | 후보로 선정된 이유. 예: 단지명 일치, 전용면적 근접, 타입명 일치. |
| `lookup_input` | 후보 계산에 사용한 정규화 입력 snapshot. 주소 전체 원문보다는 단지명/동/평형/fingerprint 등 재현에 필요한 최소값만 둔다. |
| `selected_at` | 사용자가 이 후보를 선택한 시각. |
| `rejected_at` | 사용자가 이 후보를 배제한 시각. |
| `created_at` | 후보 row 생성 시각. |

### `processing_jobs`

| 필드 | 설명 |
|---|---|
| `id` | job ledger 고유 ID. |
| `queue_name` | `pgmq` queue 이름 또는 내부 worker queue 이름. |
| `job_type` | 작업 종류. scan, mask, OCR, AI 분석, 리포트 렌더링, 알림 등. |
| `session_id` | 작업이 속한 세션. 세션과 무관한 운영 job 은 null 가능하다. |
| `floorplan_id` | 작업 대상 catalog 도면. |
| `floorplan_upload_id` | 작업 대상 사용자 업로드 도면. `session_id` 가 있으면 같은 세션 upload 만 허용한다. |
| `asset_id` | 작업 대상 asset. 예: 원본 이미지 scan, 마스킹본 생성. private/session asset 은 job 의 `session_id` 와 같은 세션이어야 한다. |
| `pgmq_msg_id` | Supabase Queues/`pgmq` 사용 시 해당 message id 를 저장한다. |
| `status` | job 상태. queued/running/succeeded/failed 등. |
| `priority` | 낮을수록 먼저 처리하는 우선순위값으로 쓴다. |
| `attempt_count` | 지금까지 실행 시도 횟수. |
| `max_attempts` | 실패 재시도 최대 횟수. 초과하면 dead letter 처리한다. |
| `run_after` | 이 시각 이후 처리 가능. delay/retry backoff 에 사용한다. |
| `locked_by` | 현재 job 을 잡은 worker 식별자. |
| `locked_at` | worker 가 job 을 claim 한 시각. |
| `payload` | worker 입력 payload. object key, model version, 옵션 등을 담는다. |
| `result` | 작업 성공 결과 요약. 상세 artifact 는 asset 으로 분리한다. |
| `error_code` | 실패 시 표준 error code. |
| `error_message` | 실패 설명. 민감정보를 넣지 않는다. |
| `created_at` | job 생성 시각. |
| `updated_at` | job 마지막 갱신 시각. |

### `analysis_runs`

| 필드 | 설명 |
|---|---|
| `id` | 분석 실행 고유 ID. |
| `session_id` | 분석이 속한 세션. |
| `floorplan_id` | 분석 대상 catalog 도면 metadata. 사용자 업로드 분석이면 null 가능하다. |
| `floorplan_upload_id` | 분석 대상 사용자 업로드 도면. catalog 후보 분석이면 null 가능하다. |
| `input_asset_id` | 분석 입력 asset. 보통 원본 또는 마스킹본. |
| `masked_asset_id` | 수치 마스킹 결과 asset. |
| `overlay_asset_id` | 오버레이 렌더링 결과 asset. |
| `status` | 분석 실행 상태. queued/running/succeeded/failed/needs_user_review. |
| `pipeline_version` | OCR, masking, segmentation, VLM, schema normalization 조합의 pipeline version. |
| `ocr_engine` | 사용한 OCR 엔진명/버전. |
| `segmentation_model` | 사용한 segmentation 모델명/버전. |
| `vlm_model` | 사용한 VLM 모델명/버전. |
| `started_at` | 분석 시작 시각. |
| `completed_at` | 분석 완료 시각. |
| `confidence_summary` | 객체별/영역별/전체 신뢰도 요약. |
| `raw_outputs` | 모델별 raw output 요약. 큰 payload 는 R2 asset 으로 분리한다. |
| `normalized_schema` | CommonJudgmentSchema 로 정규화한 결과. |
| `error_code` | 분석 실패 error code. |
| `error_message` | 분석 실패 설명. |
| `created_at` | 분석 row 생성 시각. |

### `overlay_selections`

| 필드 | 설명 |
|---|---|
| `id` | overlay 선택 이력 고유 ID. |
| `session_id` | 선택이 속한 세션. |
| `analysis_run_id` | 선택 기준이 된 분석 실행. |
| `selected_walls` | 사용자가 철거 희망 대상으로 선택한 벽체 목록. 좌표, polygon, 모델 object id 등을 담는다. |
| `selected_spaces` | 발코니, 대피공간 등 사용자가 선택/확인한 공간 목록. |
| `corrections` | 사용자가 AI 결과를 수정한 내용. 예: 벽체 분류 변경, 누락 object 추가. |
| `schema_patch` | 이 선택이 CommonJudgmentSchema 에 반영해야 하는 patch. |
| `confirmed_by` | 선택을 확정한 사용자. 보통 session owner. |
| `created_at` | 선택/확정 시각. |

### `chat_messages`

| 필드 | 설명 |
|---|---|
| `id` | 메시지 고유 ID. |
| `session_id` | 메시지가 속한 세션. |
| `user_id` | 메시지를 작성한 사용자. `role='user'` 이면 `sessions.user_id` 와 같아야 하고, assistant/system/tool 메시지는 null 가능하다. |
| `role` | 메시지 역할. user/assistant/system/tool. |
| `content` | 메시지 본문. 가능한 한 PII masking 후 저장한다. |
| `content_redacted` | 본문에 masking 이 적용됐는지 여부. |
| `ui_components` | A2UI 선택지, 이미지 카드, 입력 폼 같은 UI component payload. |
| `judgment_snapshot` | 이 메시지 시점의 판단 스키마 snapshot. 대화형 보완 흐름 추적용. |
| `metadata` | LLM run id, prompt version, token usage 등 부가 정보. |
| `created_at` | 메시지 생성 시각. |

비고:

- tool call input/output 은 이 테이블에 넣지 않고 `chat_tool_calls` 에 저장한다.
- `role='tool'` 메시지를 쓰더라도 사용자에게 보일 transcript 용도일 뿐, 실행 audit 의 정본은 `chat_tool_calls` 다.

### `chat_tool_calls`

| 필드 | 설명 |
|---|---|
| `id` | tool call 고유 ID. |
| `session_id` | tool call 이 발생한 세션. |
| `message_id` | 이 tool call 을 유발했거나 이 tool call 결과를 사용한 chat message. 독립 실행이면 null 가능하다. 값이 있으면 같은 `session_id` 의 message 만 허용한다. |
| `parent_tool_call_id` | tool 이 내부적으로 다른 tool 을 호출한 경우 부모 tool call. 값이 있으면 같은 `session_id` 의 parent call 만 허용한다. |
| `user_id` | 실행 당시 사용자 context. system/background 실행이면 null 가능하다. |
| `tool_name` | 실행한 tool 이름. 예: floorplan.lookup_candidates, rule.evaluate, address.normalize. |
| `tool_kind` | tool 분류. retrieval, db_query, external_api, ai_model 등. |
| `status` | started/succeeded/failed/cancelled. |
| `input` | tool 입력값. PII/token redaction 후 저장한다. |
| `output` | tool 출력값. 후속 assistant 메시지 생성에 쓰인 결과를 저장한다. |
| `output_summary` | 큰 output 을 요약한 텍스트. output 을 외부 asset/domain table 로 뺀 경우에도 남긴다. |
| `error_code` | 실패 시 표준 error code. |
| `error_message` | 실패 설명. 민감정보를 넣지 않는다. |
| `duration_ms` | tool 실행 시간. 성능/장애 분석용. |
| `started_at` | tool 실행 시작 시각. |
| `completed_at` | tool 실행 종료 시각. |
| `metadata` | provider request id, model version, cache hit 여부 등 부가 metadata. |

비고:

- tool output 은 항상 UI 로 렌더링되지 않는다. 조회/계산/외부 API 결과를 다음 assistant 메시지에서만 사용할 수도 있으므로 `ui_components` 와 분리한다.
- 장기 보존하면 위험한 민감 output 은 redaction 하거나 asset pointer 만 저장한다.

### `flow_guard_decisions`

| 필드 | 설명 |
|---|---|
| `id` | FLOW_GUARD 판단 고유 ID. |
| `session_id` | 판단 대상 세션. |
| `analysis_run_id` | 참고한 AI 분석 실행. 없으면 null 가능하다. 값이 있으면 같은 `session_id` 의 analysis run 만 허용한다. |
| `decision` | 충분성 판단 결과. 추가 질문, overlay 재확인, 룰 진행, 보류/상담 전환 중 하나. |
| `missing_fields` | 룰/리포트 진행 전에 부족한 필드 목록. |
| `conflict_flags` | AI 결과와 사용자 입력, 모델 간 결과, 도면 후보 간 충돌 flag. |
| `confidence_summary` | 판단 근거가 된 신뢰도 요약. |
| `schema_snapshot` | 판단 시점의 CommonJudgmentSchema snapshot. |
| `next_actions` | CompletionDecision 정본의 후속 행동 배열. 예: 물어볼 질문, overlay 재확인 요청. |
| `completion_decision` | 전체 CompletionDecision payload snapshot. 필요 시 schema_version, reason, confidence_summary, conflict_flags 까지 재현한다. |
| `evaluated_by` | 판단 주체. 예: rule_guard_v1, llm_guard_v1, manual_admin. |
| `created_at` | 판단 생성 시각. |

### `rule_sets`

| 필드 | 설명 |
|---|---|
| `id` | 룰셋 고유 ID. |
| `version` | 룰셋 버전. 리포트/룰 평가 결과에 반드시 snapshot 한다. |
| `status` | draft/active/archived. active 는 한 시점에 하나만 허용하는 것을 권장한다. |
| `effective_from` | 룰셋 적용 시작일. |
| `effective_to` | 룰셋 적용 종료일. 종료 전이면 null 가능하다. |
| `source_refs` | 법령, 고시, 내부 정책 문서 reference 목록. |
| `rules` | 실행 가능한 룰 정의 JSONB. |
| `validated_at` | 회귀 테스트/검증이 완료된 시각. |
| `created_by` | 룰셋을 만든 관리자 user id. |
| `created_at` | 룰셋 생성 시각. |

### `rule_evaluations`

| 필드 | 설명 |
|---|---|
| `id` | 룰 평가 고유 ID. |
| `session_id` | 평가 대상 세션. |
| `rule_set_id` | 사용한 룰셋. |
| `input_schema` | 룰 엔진에 들어간 CommonJudgmentSchema snapshot. |
| `result_schema_version` | 저장한 RuleEvalResult contract schema version. historical replay 와 contract migration 기준이다. |
| `verdict` | RuleEvalResult 정본 판정값. `ALLOW`, `WARN`, `DENY`, `HOLD` 중 하나다. |
| `ruleset_version` | RuleEvalResult 와 리포트에 남길 룰셋 버전 snapshot. |
| `permit_type` | 행위허가, 신고, 불필요, 불명확 등을 구분한다. |
| `permit_required` | RuleEvalResult 정본의 행위허가 필요 여부 boolean. |
| `required_facilities` | 필요한 방화시설/안전시설 목록. 위치, 수량, 근거를 포함한다. |
| `legal_basis` | RuleEvalResult 정본의 적용 법령/고시/조문 근거 목록. |
| `pending_reasons` | 보류 사유. 부족 정보, 신뢰도 부족, 고위험 케이스 등. |
| `rule_trace` | 어떤 룰이 어떤 입력으로 발화했는지에 대한 audit trace. |
| `result_snapshot` | 전체 RuleEvalResult payload snapshot. split column 과 함께 replay/audit 에 사용한다. |
| `evaluated_at` | RuleEvalResult 평가 시점. |
| `created_at` | 평가 생성 시각. |

### `reports`

| 필드 | 설명 |
|---|---|
| `id` | 리포트 고유 ID. |
| `session_id` | 리포트가 속한 세션. |
| `rule_evaluation_id` | 리포트 근거가 된 룰 평가 결과. 값이 있으면 같은 세션이어야 하며 report `verdict` 와 rule evaluation `verdict` 가 일치해야 한다. |
| `revision` | 같은 세션 내 리포트 개정 번호. publish 후 수정 대신 새 revision 발행을 권장한다. |
| `status` | draft/published/superseded/revoked. |
| `verdict` | 리포트 대표 판정값. `rule_evaluation_id` 가 있으면 참조한 `rule_evaluations.verdict` 와 같은 `ALLOW`, `WARN`, `DENY`, `HOLD` 값을 저장한다. |
| `estimate_result_schema_version` | 저장한 EstimateResult contract schema version. |
| `estimate_result_snapshot` | 사용자에게 제시한 canonical EstimateResult 전체 payload snapshot. |
| `estimate_total_min` | EstimateResult 총액 범위의 최소값. 검색/정렬용 projection 이다. |
| `estimate_total_max` | EstimateResult 총액 범위의 최대값. 검색/정렬용 projection 이다. |
| `estimate_generated_at` | EstimateResult 생성 시각. |
| `estimate_policy_version` | 견적 산정 정책/단가표 버전. |
| `report_json` | 화면/다운로드 산출물에 필요한 리포트 구조화 payload. |
| `legal_notice_included` | 필수 법적 고지 포함 여부. 기본값은 false 이며, renderer 가 고지를 실제 포함한 뒤 true 로 설정해야 한다. false 이면 publish 차단해야 한다. |
| `pdf_asset_id` | 생성된 PDF asset. 같은 report session 의 `report_pdf` 또는 `report_image` asset 만 허용한다. |
| `share_token_hash` | 공유 링크 token 의 hash. 원문 token 은 저장하지 않는다. active published report 에만 허용하고 revoked/superseded 전이 시 null 로 지운다. |
| `share_expires_at` | 공유 링크 만료 시각. token 이 있으면 필수이며 발급/갱신 transition function 에서 미래 시각인지 검증한다. |
| `published_at` | 리포트 publish 시각. |
| `created_at` | 리포트 row 생성 시각. |

### `estimate_items`

| 필드 | 설명 |
|---|---|
| `id` | 견적 항목 고유 ID. |
| `report_id` | 견적이 붙은 리포트. |
| `item_type` | 방화판, 방화유리, 감지기, 행위허가 대행 등 항목 종류. |
| `basis_value` | 산정 기준값. 예: 길이 m, 수량, 면적 등. |
| `basis_unit` | 산정 기준 단위. 예: `m`, `ea`, `m2`. |
| `unit_price_min` | 최소 단가. |
| `unit_price_max` | 최대 단가. |
| `amount_min` | 예상 최소 금액. |
| `amount_max` | 예상 최대 금액. |
| `currency` | 통화. 기본 `KRW`. |
| `policy_version` | 적용한 단가 정책 버전. |
| `assumptions` | 견적 산정 전제와 주의사항. |
| `created_at` | 견적 항목 생성 시각. |

### `leads`

| 필드 | 설명 |
|---|---|
| `id` | 리드 고유 ID. |
| `session_id` | 리드가 발생한 세션. |
| `report_id` | 리드 전환 근거가 된 리포트. 없으면 null 가능하다. |
| `estimate_item_id` | 리드 전환 근거가 된 견적 line item. 값이 있으면 `report_id` 도 필수이며 같은 세션/리포트 범위여야 한다. |
| `user_id` | 리드 제출 사용자. non-anonymous user 여야 한다. |
| `lead_type` | 상담 신청 또는 행위허가 의뢰. |
| `status` | 리드 처리 상태. 신규, 연락 완료, 진행 중, 성사, 실패, 종료 등. |
| `contact_info_encrypted` | 이름/전화/email 등 연락처 원문을 애플리케이션 레벨로 암호화한 payload. |
| `contact_info_key_id` | 암호화에 사용한 key 식별자. key rotation 추적용. |
| `contact_summary` | 민감정보가 아닌 최소 표시 정보. 예: 선호 연락 시간, 문의 유형. |
| `assignee_id` | 담당 관리자 user id. |
| `notification_status` | 관리자 알림 발송 상태. |
| `created_at` | 리드 생성 시각. |
| `updated_at` | 리드 마지막 수정 시각. |

### `webhook_deliveries`

| 필드 | 설명 |
|---|---|
| `id` | webhook/알림 발송 이력 고유 ID. |
| `event_type` | 이벤트 종류. 예: lead_created, report_published. |
| `target` | 발송 대상. 예: email, sms, slack, admin_webhook. |
| `related_table` | 이벤트가 연결된 도메인 테이블명. |
| `related_id` | 이벤트가 연결된 도메인 row id. |
| `payload` | 발송 payload. 민감정보는 제거하거나 암호화해야 한다. |
| `status` | pending/sent/failed/dead_lettered. |
| `attempt_count` | 발송 시도 횟수. |
| `last_attempt_at` | 마지막 발송 시도 시각. |
| `next_attempt_at` | 다음 재시도 예정 시각. |
| `response_status` | 외부 endpoint 응답 status code. |
| `response_body_redacted` | 외부 응답 본문 요약. 민감정보 제거 후 저장한다. |
| `created_at` | 발송 이력 생성 시각. |

### `scheduled_task_runs`

| 필드 | 설명 |
|---|---|
| `id` | scheduled task 실행 이력 고유 ID. |
| `task_name` | cron 작업 이름. 예: expire_sessions, retry_webhooks. |
| `cron_job_id` | Supabase Cron/`pg_cron` job id. |
| `status` | started/succeeded/failed/skipped. |
| `started_at` | 실행 시작 시각. |
| `finished_at` | 실행 종료 시각. |
| `result` | 처리 건수, 삭제 건수, 재시도 건수 등 실행 결과 요약. |
| `error_message` | 실패 시 에러 요약. |

### `external_sync_records`

| 필드 | 설명 |
|---|---|
| `id` | 외부 연동 이력 고유 ID. |
| `session_id` | 외부 조회가 연결된 세션. |
| `user_id` | 세션 없이 사용자 단위로 캐시하거나 조회한 외부 연동의 owner. |
| `provider` | 외부 데이터 provider. 예: address_api, building_register, 세움터. |
| `external_key` | provider 쪽 식별키. |
| `sync_type` | 조회/동기화 종류. 예: address_normalize, building_info_lookup. |
| `status` | pending/succeeded/failed/stale. |
| `request_payload` | 외부 요청 payload. PII 최소화 필요. |
| `response_payload` | 외부 응답 payload. 장기 보존 필요성과 PII 포함 여부를 검토해야 한다. |
| `fetched_at` | 외부 데이터 조회 완료 시각. |
| `expires_at` | 캐시/활용 만료 시각. |
| `created_at` | 연동 이력 생성 시각. |

### `training_samples`

| 필드 | 설명 |
|---|---|
| `id` | 학습 샘플 고유 ID. |
| `session_id` | 샘플의 출처 세션. 개인정보 삭제 후에도 학습 샘플을 남길 수 있도록 null 허용을 검토한다. |
| `floorplan_id` | 샘플 출처가 catalog 도면인 경우의 도면 metadata. |
| `floorplan_upload_id` | 샘플 출처가 사용자 업로드 도면인 경우의 upload row. `session_id` 가 있으면 같은 세션 upload 만 허용한다. |
| `asset_id` | 실제 학습에 쓸 도면/마스크 asset. private/session asset 은 샘플의 `session_id` 와 같은 source scope 여야 한다. |
| `label_status` | unlabeled/reviewing/approved/rejected 등 라벨링 상태. |
| `label_payload` | mask, bbox, class, region_id 등 라벨 데이터. |
| `quality_score` | 라벨 품질 점수. |
| `reviewed_by` | 라벨 검수 관리자. |
| `created_at` | 학습 샘플 생성 시각. |

### `permit_outcomes`

| 필드 | 설명 |
|---|---|
| `id` | 실제 행위허가 결과 고유 ID. |
| `session_id` | 결과가 연결된 사전검토 세션. |
| `lead_id` | 결과가 연결된 리드. 값이 있으면 `permit_outcomes.session_id = leads.session_id` 를 만족해야 한다. |
| `outcome` | approved/rejected/withdrawn/unknown. |
| `authority_name` | 판단한 관할 행정기관명. |
| `decision_date` | 실제 결정일. |
| `reason_summary` | 승인/반려/철회 사유 요약. |
| `evidence_asset_id` | 허가서, 반려 통지 등 증빙 asset. |
| `created_by` | 결과를 입력한 관리자 또는 사용자. |
| `created_at` | 결과 row 생성 시각. |

### `admin_audit_logs`

| 필드 | 설명 |
|---|---|
| `id` | 관리자 audit log 고유 ID. |
| `actor_user_id` | 변경을 수행한 관리자 user id. |
| `action` | 수행한 작업. 예: lead.assign, report.revoke, ruleset.activate. |
| `target_table` | 변경 대상 테이블명. |
| `target_id` | 변경 대상 row id. |
| `before_snapshot` | 변경 전 주요 값 snapshot. |
| `after_snapshot` | 변경 후 주요 값 snapshot. |
| `created_at` | audit log 생성 시각. |

## 참고 문서

- `docs/brief/CEO_PROJECT_BRIEF.md`
- `docs/_extracted/01_요구사항명세서_v02.txt`
- `docs/_extracted/02_집핀_기능명세서_v10.txt`
- `docs/_extracted/03_집핀_기술명세서_v16.txt`
- `docs/_extracted/04_집핀_소프트웨어설계문서_v19.txt`
- `docs/adr/0004-supabase-transition.md`
- `docs/runbooks/supabase-session-bridge.md`
- Supabase Cron: https://supabase.com/docs/guides/cron
- Supabase Queues/PGMQ: https://supabase.com/docs/guides/queues
- Supabase Database Webhooks/pg_net: https://supabase.com/docs/guides/database/webhooks
