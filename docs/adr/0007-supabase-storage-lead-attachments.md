# ADR 0007 — 상담 리드 첨부용 Supabase Storage 도입 + 익명 리드 허용

- **상태**: **Accepted (2026-06-08)** — 운영자(사용자) 결정으로 확정. 본 ADR 은 ADR-0004 의 두 가지 봉인(① R2 정본 / Supabase Storage 비도입, ② 상담 신청·리드 생성의 conversion-only)을 **상담 리드 기능 한정**으로 override 한다.
- **제안자**: Backend/Full-stack (agent, CMP-DIRECT)
- **승인 권자**: 운영자(사용자) — 본 작업 지시에서 두 override 를 명시적으로 승인.
- **관련**: ADR-0004 §29·§86·§544-546 (Storage R2 정본), ADR-0004 §5.3 #11 (conversion-only 라우트), AGENTS.md §4.7 #2(b) (리드 생성 OAuth 의무), `supabase/config.toml [storage]`, `supabase/migrations/..._0009_consultation_leads.sql`.

---

## 0. 결정 요약 (TL;DR)

| 항목 | 본 ADR 결정 |
|---|---|
| 평면도 첨부 스토리지 | **Supabase Storage** (`lead-floorplans` 비공개 버킷). `[storage].enabled=true`. |
| R2 정본 | **유지** — 도면 분석 파이프라인 등 다른 대형 산출물은 그대로 R2. 본 ADR 은 "리드 첨부"라는 좁은 표면만 Supabase Storage 로 연다. |
| 익명 리드 | **허용** — 비회원(Supabase Anonymous Sign-In 토큰)도 상담 신청 가능. ADR-0004 §5.3 #11 / AGENTS §4.7 #2(b) 의 conversion-only(`is_anonymous=false`) 봉인을 리드 라우트 한정 override. |
| 리드 보존 | `consultation_leads.user_id` 는 **nullable + ON DELETE SET NULL**. 익명 user TTL cleanup 후에도 리드(영업 자산) 보존. |

## 1. 배경 / 문제

상담 리드를 영구 저장하는 백엔드가 없었다. 제품 요구는 (a) **비로그인 상태에서도 상담 신청 가능**, (b) 상담 신청 페이지에서 **단위세대 평면도 첨부** 가능이다. 그런데 ADR-0004 는 (1) 객체 스토리지를 R2 로 못박고 Supabase Storage 도입을 "별도 ADR" 로 미뤘으며, (2) "상담 신청 / 리드 생성"을 conversion-only(영구 가입 사용자 전용)로 봉인했다. 두 봉인 모두 위 요구와 충돌한다.

## 2. 결정

### 2.1 Supabase Storage (리드 첨부 한정)
- `supabase/config.toml` `[storage].enabled = true`.
- `lead-floorplans` **비공개** 버킷 + `storage.objects` owner-folder RLS(`<auth.uid()>/<file>` 경로에만 insert/select/delete). 정의는 migration 0009.
- **업로드 데이터 경로 = Next.js 서버 presigned URL (운영자 선택)**: 브라우저 → `POST /leads/upload-url`(Vercel Next Route Handler, `S3_ENDPOINT/REGION/ACCESS_KEY/SECRET_KEY` 사용) 가 **검증된 Supabase 세션에서 owner 폴더를 도출**해 presigned PUT URL 발급 → 브라우저가 Supabase Storage S3 엔드포인트로 파일 직접 PUT(서버 함수 본문 용량 제한 회피) → 백엔드 `POST /leads` 가 object 경로를 받아 기록하며 Bearer 토큰의 user_id 로 owner-folder 를 재검증. S3 자격증명은 Vercel 에 환경별(production/development) 분리 주입, 브라우저 비노출(NEXT_PUBLIC_ 아님).
- **운영 전제(CORS)**: 브라우저가 presigned URL 로 Supabase S3 엔드포인트에 PUT 하므로, Supabase Storage CORS 에 웹 오리진(jippin.ai 등)을 PUT 허용으로 등록해야 한다.
- **R2 정본은 보존**한다. 본 ADR 은 Supabase Storage 를 전면 채택하는 것이 아니라, 리드 첨부라는 단일 표면만 연다. 다른 산출물의 Supabase Storage 확장은 다시 별도 결정 대상이다.
- **운영 전제**: 각 Supabase branch 콘솔에서 Storage 서비스 활성화 + S3 access keys 발급. `SUPABASE_SERVICE_ROLE_KEY`/S3 시크릿은 브라우저 비노출 유지.

### 2.2 익명 리드 허용
- `POST /leads` 는 `require_supabase_request_user`(익명 OK)를 쓴다. `consultation_leads.is_anonymous` 로 익명 여부를 보존한다.
- 이는 AGENTS §4.7 #2(b)(리드 생성 시 OAuth 강제)와 ADR-0004 §5.3 #11(conversion-only RLS `is_anonymous='false'`)을 **리드 라우트 한정**으로 supersede 한다. 리드 테이블은 PostgREST 가 아닌 FastAPI 백엔드 전용 경로로만 쓰이며 RLS 는 client grant 를 부여하지 않는다(PII 보호).

## 3. 결과 / 영향
- 익명 사용자가 만든 리드도 영업 파이프라인에 들어온다. 스팸 방어(rate-limit / honeypot / CAPTCHA)는 후속 과제다(익명 게이트 G3/G2 와 백엔드 IP rate-limit).
- ADR-0004 의 storage/conversion-only 봉인은 "리드 기능 외" 범위에서는 그대로 유효하다.

## 4. 대안 (기각)
- **첨부 후속 분리**: 요구가 명시적이라 기각.
- **R2 사용**: 백엔드에 R2 클라이언트/ presigned URL 파이프라인이 없어 작업량 과다 + 본 기능엔 Supabase 세션 기반 직접 업로드가 더 단순.
- **conversion-only 유지(로그인 강제)**: "비로그인 신청 가능" 요구와 정면 충돌이라 기각.
