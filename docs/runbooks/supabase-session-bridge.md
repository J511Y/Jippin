# Supabase session bridge — POST /auth/supabase/session

> CMP-595. 본 문서는 backend 의 Supabase session bridge endpoint contract 를 봉인한다.
> Phase 0 SSOT runbook 인 `docs/runbooks/supabase-web-auth.md` (CMP-577) 가 머지되는
> 시점에 §11 (또는 §4.7 callback 단락) 의 새 행으로 흡수해 본 문서를 폐기한다.

## 1. 책임

프런트 `apps/web/app/auth/callback/route.ts` 가 `supabase.auth.exchangeCodeForSession`
성공 직후 호출한다. backend 는 Supabase Auth access token 을 검증한 뒤 기존
`jippin_session` HS256 cookie 를 mint 한다. CMP-580 PR #47 review thread 4
(`3332741025`) 의 backend 봉인 책임이 본 endpoint 다.

## 2. Request contract

```
POST /auth/supabase/session
Authorization: Bearer <supabase_access_token>
```

본문 없음. `Accept: application/json` 은 생략 가능.

## 3. Response contract

| 상태 | 의미 | 응답 본문 | Set-Cookie |
| --- | --- | --- | --- |
| `204 No Content` | mapping 성공 → `jippin_session` mint | (없음) | `jippin_session=<HS256 JWT>; HttpOnly; Secure; SameSite=Lax` |
| `401 AUTH_INVALID_TOKEN` | Authorization 헤더 누락 / Bearer 스킴 오류 / 서명 검증 실패 / sub claim 누락 | 표준 error envelope | — |
| `401 AUTH_EXPIRED_TOKEN` | access token 만료 | 표준 error envelope | — |
| `401 AUTH_IDENTITY_NOT_LINKED` | token 은 유효하지만 `auth_identities` 매핑이 없고, email claim 으로 매칭되는 jippin user 가 존재 → 링크 ladder 필요 | 표준 error envelope | — |
| `401 AUTH_SIGNUP_REQUIRED` | token 유효, 매핑 없음, email 매칭 user 도 없음 → 회원가입 트랙 (Phase 1 (f)) 필요 | 표준 error envelope | — |
| `503 AUTH_SESSION_CONFIG_MISSING` | `SUPABASE_JWKS_URL` / `SUPABASE_JWT_ISSUER` / `AUTH_JWT_SECRET` 미설정 | 표준 error envelope | — |
| `503 AUTH_SUPABASE_JWKS_UNAVAILABLE` | JWKS endpoint 도달 실패 (network / 5xx) | 표준 error envelope | — |

error envelope 는 AGENTS.md §4.5 의 `{error: {code, message, request_id, timestamp}}` 포맷을 따른다.

## 4. 검증 흐름

1. `Authorization` 헤더에서 Bearer token 추출. 누락 시 `AUTH_INVALID_TOKEN`.
2. Supabase JWKS (`SUPABASE_JWKS_URL`) 캐시 후 RS256/ES256 알고리즘 화이트리스트로 서명 검증.
   `iss == SUPABASE_JWT_ISSUER`, `aud == SUPABASE_JWT_AUDIENCE` (`authenticated` 기본값).
3. `sub` (Supabase user UUID) 로 `auth_identities` (`provider='supabase'`) 조회.
4. 매핑 존재 → `set_session_cookie(response, user_id=jippin_uuid)` → 204.
5. 매핑 부재 + email claim 으로 jippin user 검색 시 일치 row 존재 → `AUTH_IDENTITY_NOT_LINKED`.
6. 매핑 부재 + email 매칭도 없음 → `AUTH_SIGNUP_REQUIRED`.

## 5. 의존성

- `auth_identities` 테이블 — Alembic revision `0007_auth_identities` (본 PR).
- `auth_identities` 쓰기 측 — CMP-579 / CMP-583 의 link ladder 봉인.
- Supabase 신규 user → jippin user row 자동 생성 — Phase 1 (f) 별도 트랙.
- 프런트 callback — CMP-580 PR #47 commit `c4b53292` 가 이미 봉인.

## 6. 환경 변수

`apps/api/.env.example` 의 다음 키를 참고:

```
SUPABASE_JWT_ISSUER=https://<project-ref>.supabase.co/auth/v1
SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_JWT_AUDIENCE=authenticated
```

실값은 절대 커밋 금지 (AGENTS.md §4.4 / §5.8).

## 7. 회귀 차단

`apps/api/tests/test_auth_supabase_session.py` 가 4 케이스 + 2 보조 케이스를 봉인:

1. Authorization 헤더 누락 → 401 `AUTH_INVALID_TOKEN`.
2. 유효 token + 매핑 존재 → 204 + Set-Cookie.
3. 만료 token → 401 `AUTH_EXPIRED_TOKEN`.
4. 위조 서명 (JWKS 가 광고하지 않는 키로 서명) → 401 `AUTH_INVALID_TOKEN`.
5. 매핑 부재 (이메일 매칭 user 도 없음) → 401 `AUTH_SIGNUP_REQUIRED`.
6. 매핑 부재 + 이메일 매칭 jippin user 존재 → 401 `AUTH_IDENTITY_NOT_LINKED`.
