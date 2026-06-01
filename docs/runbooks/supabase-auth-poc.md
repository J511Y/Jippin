# Supabase Auth PoC runbook (CMP-576)

## 목적

Supabase Auth가 집핀의 ADR-0003 인증 정책을 대체할 수 있는지 검증한다. 이 문서는 사용자가 Supabase 콘솔에서 project URL, publishable key, OAuth provider 설정을 발급한 직후 실행할 수 있는 체크리스트다. 실제 URL, key, OAuth secret, service-role key는 이 문서와 이슈/PR 본문에 기록하지 않는다.

## 기준 정책

- 집핀 정본: `docs/adr/0003-anon-user-and-sso.md`.
- 비회원 사전검토는 허용하되 전환 시점에 OAuth로 전환한다.
- 자체 비밀번호 가입은 금지한다.
- 동일 이메일 + 다른 provider 자동 병합은 금지한다. 사용자가 명시적으로 계정 통합을 시작한 경우만 provider를 같은 사용자에 붙인다.
- Kakao Sync 약관 동의 source는 앱 테이블 `terms_consents.source='kakao_sync'`로 보존한다.

## Supabase 공식 문서에서 확인한 전제

- Anonymous sign-in은 PII 없이 `auth.users` 사용자를 만들고 JWT에 `is_anonymous` claim을 담는다. 익명 사용자도 Supabase Data API에서는 `authenticated` role을 사용하므로 RLS에서 `is_anonymous`를 별도로 확인해야 한다. 참고: <https://supabase.com/docs/guides/auth/auth-anonymous>
- 익명 사용자를 permanent user로 바꾸려면 로그인된 익명 세션에서 OAuth identity를 link한다. 이 기능은 Supabase project의 manual linking 설정이 필요하다. 참고: <https://supabase.com/docs/guides/auth/auth-anonymous>, <https://supabase.com/docs/guides/auth/auth-identity-linking>
- Supabase는 같은 verified email을 가진 OAuth identity를 자동으로 같은 user에 연결하는 전략을 제공한다. 이 동작은 집핀 ADR-0003의 "동일 이메일 자동 병합 금지"와 충돌하므로 PoC의 핵심 게이트다. 참고: <https://supabase.com/docs/guides/auth/auth-identity-linking>
- Kakao는 built-in social provider 목록에 있다. Naver는 built-in 목록에 없으므로 Custom OAuth/OIDC provider로 검증한다. Custom provider 식별자는 `custom:` prefix를 쓴다. 참고: <https://supabase.com/docs/guides/auth/>, <https://supabase.com/docs/guides/auth/custom-oauth-providers>
- FastAPI가 Supabase JWT를 직접 검증하려면 project JWKS URL `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`을 사용한다. HS256 shared-secret project는 Auth server `/auth/v1/user` 검증 fallback을 별도로 설계해야 한다. 참고: <https://supabase.com/docs/guides/auth/jwts>, <https://supabase.com/docs/guides/auth/jwt-fields>

## 환경변수 초안

`apps/api/.env.example`에 CMP-576 PoC 전용 변수명을 추가했다. 실제 값은 로컬 `.env` 또는 배포 secret manager에만 둔다.

```env
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_AUTH_REDIRECT_URL=http://localhost:3000/auth/callback
SUPABASE_AUTH_MANUAL_LINKING_REQUIRED=true
SUPABASE_AUTH_GOOGLE_PROVIDER=google
SUPABASE_AUTH_KAKAO_PROVIDER=kakao
SUPABASE_AUTH_NAVER_PROVIDER=custom:naver
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_ALGORITHMS=RS256,ES256
```

금지:

- `SUPABASE_SERVICE_ROLE_KEY`는 이 PoC의 기본 실행에 요구하지 않는다. Admin API 자동 설정이 필요해지는 별도 이슈가 생기면 그 이슈에서만 secret manager 저장 위치를 정한다.
- OAuth client secret은 Supabase 콘솔에만 입력하고 레포에는 변수명도 최소화한다.

## 콘솔 설정 체크리스트

1. Supabase Dashboard > Auth > Providers에서 Anonymous sign-ins를 enable한다.
2. Auth configuration에서 manual identity linking을 enable한다.
3. Google provider를 enable하고 redirect URL을 Supabase가 제시한 callback URL로 Google Console에 등록한다.
4. Kakao provider를 enable하고 Kakao developers callback URL을 Supabase가 제시한 callback URL로 등록한다.
5. Naver는 Custom OAuth/OIDC provider `custom:naver`로 만든다.
6. Naver가 OIDC discovery를 제공하지 않는 경우 OAuth2 provider로 만들고 Authorization URL, Token URL, UserInfo URL을 수동 입력한다.
7. Site URL과 additional redirect URLs에 `SUPABASE_AUTH_REDIRECT_URL`의 origin/path를 등록한다.
8. JWT signing key가 asymmetric인지 확인한다. JWKS endpoint가 빈 `keys` 배열을 반환하면 FastAPI adapter는 `/auth/v1/user` remote validation fallback이 필요하다.

## PoC 실행 순서

### A. anonymous sign-in 생성

프론트 또는 임시 브라우저 콘솔에서 Supabase client를 만들고 anonymous sign-in을 호출한다.

```ts
const { data, error } = await supabase.auth.signInAnonymously()
console.log({ error, userId: data.user?.id, isAnonymous: data.user?.is_anonymous })
```

기대값:

- `data.user.id`가 UUID다.
- session access token의 `sub`가 같은 UUID다.
- access token payload에 `is_anonymous: true`가 있다.

### B. anonymous user에 Google identity link

같은 브라우저 세션에서 다음을 실행한다.

```ts
const { data, error } = await supabase.auth.linkIdentity({ provider: 'google' })
console.log({ error, data })
```

Google OAuth 완료 후 확인한다.

- `auth.users.id`가 A 단계의 anonymous `user.id`와 같다.
- `auth.identities`에 `provider='google'` row가 추가된다.
- 새 access token의 `sub`는 동일하고 `is_anonymous`가 `false`로 바뀐다.

### C. anonymous user에 Kakao identity link

B와 같은 절차를 Kakao provider로 반복한다. Kakao Sync 약관 동의 결과는 Supabase 기본 테이블만으로는 집핀 감사 요건을 만족하지 못하므로 앱 DB에 다음 중 하나가 필요하다.

- Supabase Auth hook 또는 callback 후처리에서 `terms_consents`에 `source='kakao_sync'` row를 insert한다.
- Kakao provider identity metadata에 약관 tag가 들어오지 않으면, 기존 first-party Kakao adapter를 유지하거나 별도 Kakao 약관 조회 endpoint를 추가한다.

### D. 동일 이메일 Google/Kakao 자동 linking 검증

새 브라우저 프로필 또는 시크릿 창을 사용한다.

1. Google 계정 `E`로 Supabase OAuth sign-in을 완료한다.
2. 로그아웃한다.
3. 같은 이메일 `E`를 가진 Kakao 계정으로 Supabase OAuth sign-in을 완료한다.
4. 두 login 결과의 `auth.users.id`와 `auth.identities.user_id`를 비교한다.

판정:

- 다른 `auth.users.id`면 ADR-0003과 정합한다.
- 같은 `auth.users.id`면 Supabase automatic linking이 집핀 정책과 충돌한다. 이 경우 Supabase Auth 완전 대체는 보류하고 Backend Lead/Architecture Lead가 "자동 linking 허용 ADR" 또는 "Supabase Auth 미채택/부분 채택" 중 하나를 결정해야 한다.

### E. Naver Custom OAuth/OIDC provider 검증

`custom:naver`로 로그인한다.

```ts
const { data, error } = await supabase.auth.signInWithOAuth({
  provider: 'custom:naver',
})
console.log({ error, data })
```

기대값:

- Supabase가 Naver authorize URL로 redirect한다.
- callback 후 `auth.identities.provider`가 `custom:naver`다.
- identity data에 Naver subject, email, display name을 안정적으로 매핑할 수 있다.

실패 시 기록할 항목:

- Naver userinfo 응답 shape가 Supabase Custom OAuth mapping에 맞지 않는지.
- OIDC discovery 미지원 때문에 OAuth2 수동 endpoint만 가능한지.
- email verified 신뢰도가 automatic linking 정책에 영향을 주는지.

### F. FastAPI JWT adapter 검증

`apps/api/src/auth/supabase_jwt.py`에 PoC용 adapter skeleton을 추가했다. 아직 라우터에 연결하지 않는다.

검증 책임:

- Authorization header의 Bearer token만 받는다.
- JWKS로 access token signature를 검증한다.
- `iss == f"{SUPABASE_URL}/auth/v1"`를 확인한다.
- `aud == SUPABASE_JWT_AUDIENCE`를 확인한다.
- `sub`를 UUID user id로 변환한다.
- `is_anonymous`를 필수 boolean claim으로 취급한다.

HS256/shared-secret project이면 JWKS endpoint가 검증용 public key를 제공하지 않을 수 있다. 이 경우 FastAPI adapter는 access token을 Supabase Auth server `/auth/v1/user`에 보내 검증하는 fallback 설계가 필요하다. 이 fallback은 네트워크 round-trip이 있으므로 일반 API path에 넣기 전에 캐시와 timeout 정책을 별도 이슈로 잡는다.

## 성공/실패 판정표

| 질문 | 성공 조건 | 실패 조건 | 조치 |
|---|---|---|---|
| Anonymous sign-in | `auth.users.id` 생성, JWT `is_anonymous=true` | anonymous sign-in 비활성 또는 claim 없음 | Supabase Auth 대체 보류 |
| Anonymous + OAuth link | link 후 `sub`/`auth.users.id` 유지, `is_anonymous=false` | 새 user id 생성 | anonymous 사전검토 이관 모델 재설계 |
| 동일 이메일 Google/Kakao | provider별 별도 user 유지 또는 자동 linking 차단 가능 | 자동으로 같은 user에 병합되고 차단 방법 없음 | ADR-0003 충돌. Supabase 완전 대체 불가 |
| Naver Custom OAuth/OIDC | `custom:naver` identity 생성과 subject/email 매핑 성공 | callback/userinfo 매핑 실패 | Naver는 first-party adapter 유지 |
| Kakao Sync terms | Kakao 약관 source를 앱 DB에 보존 가능 | Supabase metadata로 약관 tag 확인 불가 | 기존 Kakao adapter 유지 또는 후처리 endpoint 설계 |
| FastAPI JWT 검증 | JWKS 또는 `/auth/v1/user` fallback으로 `sub`/`is_anonymous` 확인 | 검증 불가 또는 issuer/audience 불일치 | adapter 미채택 |

## 기존 자체 auth 엔드포인트 처리 계획

| 현재 엔드포인트/모듈 | Supabase 전환 시 처리 | 이유 |
|---|---|---|
| `POST /auth/anonymous-users` | 폐기 후보 | Supabase `signInAnonymously()`가 `auth.users.id`와 JWT를 발급한다. 단, 앱 DB shadow row가 필요하면 호환 endpoint로 축소한다. |
| `GET /auth/{provider}/start` | 폐기 또는 302 호환 shim | Supabase client `signInWithOAuth`/`linkIdentity`가 provider redirect를 소유한다. 현재 GET route는 ADR-0003의 POST start 정본과도 이미 불일치한다. |
| `GET /auth/callback/{provider}` | 폐기 후보 | Supabase Auth callback이 OAuth code exchange를 처리한다. 앱은 frontend callback에서 Supabase session을 읽는다. |
| `POST /auth/sso-accounts/{provider}/link` | Supabase `linkIdentity` wrapper로 대체 후보 | 명시 계정 통합 UX는 유지해야 한다. 자동 email merge는 허용하지 않는다. |
| `POST /auth/terms/accept` | 유지 | Google/Naver 내부 약관 동의와 Kakao Sync source 보존은 앱 DB 책임이다. |
| `GET /auth/me` | 유지/재구현 | FastAPI가 Supabase JWT를 검증한 뒤 앱 DB profile/terms state를 합쳐 반환한다. |
| `POST /auth/logout` | 프론트 Supabase `signOut()` 중심, 서버 cookie 제거 shim | Supabase session이 client-owned가 되면 서버 JWT cookie는 제거 대상이다. |
| `apps/api/src/services/auth.py` | 단계적 축소 | user/identity 생성 로직은 Supabase Auth로 이동하되 terms/app profile claim 로직은 남는다. |
| `apps/api/src/models/auth.py` | shadow profile/terms 중심으로 재설계 | `users`/`external_sso_accounts`를 직접 정본으로 쓰지 않고 `auth.users` FK 또는 shadow table로 바꿀지 ADR 필요. |

## 보안/UX 영향

- Supabase anonymous user도 `authenticated` role로 동작한다. RLS와 FastAPI dependency에서 `is_anonymous`를 확인하지 않으면 익명 사용자가 permanent-only 리소스에 접근할 수 있다.
- Supabase automatic linking이 켜진 상태로 같은 email OAuth를 병합하면 ADR-0003의 계정 탈취 방어 모델이 깨진다.
- Supabase client 중심 flow는 OAuth callback ownership을 프론트/Supabase로 이동시킨다. 현재 API-owned 302 callback과 충돌하므로 한동안 호환 shim이 필요할 수 있다.
- Kakao Sync 약관 source는 Supabase Auth가 자동 보존해주는 집핀 도메인 개념이 아니므로 앱 DB 후처리가 반드시 필요하다.

## 정적 검증

Supabase project 값 없이 실행 가능한 검증:

```bash
cd apps/api
uv run pytest tests/test_supabase_jwt.py
```

전체 auth 영향이 걱정될 때:

```bash
cd apps/api
uv run pytest tests/test_supabase_jwt.py tests/test_auth_anonymous_users.py tests/test_auth_oauth_start.py tests/test_auth_secondary_endpoints.py
```

## 다음 결정

PoC 결과가 모두 성공하면 Backend Lead에 다음 구현 이슈를 요청한다.

- Supabase JWT dependency를 FastAPI 라우터에 연결한다.
- 앱 DB auth 모델을 `auth.users` shadow profile/terms 중심으로 재설계한다.
- 기존 OAuth start/callback 라우트를 deprecation shim으로 전환한다.

동일 이메일 자동 linking을 차단할 수 없거나 Naver/Kakao Sync 감사 요건이 충족되지 않으면 Supabase Auth 완전 대체는 보류하고, Supabase Postgres만 유지하면서 현재 first-party auth stack을 계속 쓴다.
