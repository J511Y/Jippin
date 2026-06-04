# Supabase session bridge — POST /auth/supabase/session

> CMP-595, updated by CMP-604. 본 문서는 backend 의 Supabase session bridge endpoint contract 를 봉인한다.

## 1. 책임

프런트 `apps/web/app/auth/callback/route.ts` 가 `supabase.auth.exchangeCodeForSession`
성공 직후 호출한다. backend 는 Supabase Auth access token 을 검증한 뒤 기존
`jippin_session` HS256 cookie 를 mint 한다. Supabase JWT `sub` 는 곧
`auth.users.id` 이며, `public.users` 는 같은 id 를 PK/FK 로 쓰는 앱 프로필 테이블이다.

## 2. Request contract

```
POST /auth/supabase/session
Authorization: Bearer <supabase_access_token>
```

본문 없음. `Accept: application/json` 은 생략 가능.

## 3. Response contract

| 상태 | 의미 | 응답 본문 | Set-Cookie |
| --- | --- | --- | --- |
| `200 OK` | Supabase `sub` 로 `public.users` profile 을 안전 upsert 한 뒤 active profile 존재 → `jippin_session` mint | `{signup_complete, missing_required_terms, redirect_url}` | `jippin_session=<HS256 JWT>; HttpOnly; Secure; SameSite=Lax` |
| `401 AUTH_INVALID_TOKEN` | Authorization 헤더 누락 / Bearer 스킴 오류 / 서명 검증 실패 / sub claim 누락 | 표준 error envelope | — |
| `401 AUTH_EXPIRED_TOKEN` | access token 만료 | 표준 error envelope | — |
| `401 AUTH_SIGNUP_REQUIRED` | token 유효하나 upsert 후 active `public.users` profile 없음 | 표준 error envelope | — |
| `503 AUTH_SESSION_CONFIG_MISSING` | `SUPABASE_JWKS_URL` / `SUPABASE_JWT_ISSUER` / `AUTH_JWT_SECRET` 미설정 | 표준 error envelope | — |
| `503 AUTH_SUPABASE_JWKS_UNAVAILABLE` | JWKS endpoint 도달 실패 (network / 5xx) | 표준 error envelope | — |

error envelope 는 AGENTS.md §4.5 의 `{error: {code, message, request_id, timestamp}}` 포맷을 따른다.

## 4. 검증 흐름

1. `Authorization` 헤더에서 Bearer token 추출. 누락 시 `AUTH_INVALID_TOKEN`.
2. Supabase JWKS (`SUPABASE_JWKS_URL`) 캐시 후 RS256/ES256 알고리즘 화이트리스트로 서명 검증.
   `iss == SUPABASE_JWT_ISSUER`, `aud == SUPABASE_JWT_AUDIENCE` (`authenticated` 기본값).
3. `sub` (Supabase user UUID) 를 UUID 로 파싱.
4. `public.users(id=sub)` profile 을 `INSERT ... ON CONFLICT DO NOTHING` 으로 생성한다. email / provider subject / password 계열 값은 저장하지 않는다.
5. `public.users.id = sub AND status = 'active'` 조회.
6. profile active → `set_session_cookie(response, user_id=sub)` → 200.
7. 기존 profile 이 `suspended` / `deleted` 이거나 FK 위반 등으로 active profile 이 없으면 `AUTH_SIGNUP_REQUIRED`.

## 5. 의존성

- `public.users` profile table keyed by `auth.users(id)`.
- CMP-604 기준 신규 Supabase user profile 생성 경로는 `/auth/supabase/session` 의 backend transaction 이다. 유효한 non-anonymous Supabase JWT 검증 후 `sub` 만 저장하며 role/status 는 DB default (`user` / `active`) 를 사용한다.
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

`apps/api/tests/test_auth_supabase_session.py` 가 다음 케이스를 봉인:

1. Authorization 헤더 누락 → 401 `AUTH_INVALID_TOKEN`.
2. 유효 token + profile upsert + active profile 존재 → 200 + Set-Cookie.
3. 만료 token → 401 `AUTH_EXPIRED_TOKEN`.
4. 위조 서명 (JWKS 가 광고하지 않는 키로 서명) → 401 `AUTH_INVALID_TOKEN`.
5. active profile 부재 또는 inactive profile → 401 `AUTH_SIGNUP_REQUIRED`.
6. non-UUID `sub` → 401 `AUTH_INVALID_TOKEN`.
