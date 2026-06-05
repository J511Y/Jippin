# Fly.io API 배포 런북 + 오너 체크리스트

- 작성일: 2026-06-05
- 결정 문서: [`docs/adr/0006-deployment-split-topology.md`](../adr/0006-deployment-split-topology.md) (Proposed)
- 대상 토폴로지: web=Vercel · **api=Fly.io 도쿄(`nrt`)** · redis=Upstash 도쿄 · postgres=Supabase · object=R2 · 추론=HF Endpoint
- 본 런북은 "**Fly 채택을 확정했을 때 오너(사람)가 직접 해야 하는 일**"의 순서 있는 체크리스트다. 자동화 가능한 부분은 §6 에 GitHub Action 스텁으로 분리.

> ⚠ 전제: 본 전환은 ADR-0006 이 Accepted 되어야 정본이 된다. 아래 작업은 그 확정 이후에 실행한다. 시크릿(connection string, API key, JWT secret)은 **터미널 출력·커밋·이슈/PR 본문에 남기지 않는다** (AGENTS.md §4.4).

---

## 0. 사전 준비물 (계정·도구)

- [ ] Fly.io 계정 생성 + 결제 카드 등록 (무료 티어 종료됨, 사용량 청구)
- [ ] `flyctl` 설치 — Windows: `iwr https://fly.io/install.ps1 -useb | iex`  / 확인: `fly version`
- [ ] `fly auth login`
- [ ] Vercel 계정 + Pro 플랜 (web 배포용 — 별도 런북에서 다루나 도메인 단계가 맞물림)
- [ ] Upstash 계정 (또는 Vercel Marketplace 경유)
- [ ] 도메인 `jippin.ai` DNS 관리 콘솔 접근 (Cloudflare DNS 권장)
- [ ] Hugging Face 계정 + Inference Endpoint 발급 권한 (도면 추론용, ADR-0006 §7 Q1)

---

## 1. Upstash Redis (도쿄) 생성

- [ ] Upstash 콘솔에서 Redis DB 생성 — **Region = `ap-northeast-1` (Tokyo)** 선택 (서울 없음. ADR-0006 §2.1)
- [ ] TLS 연결 URL 발급 확인: `rediss://default:****@xxx.upstash.io:6379`
- [ ] (선택) Vercel Marketplace 경유로 만들면 web project env 에 자동 주입됨. 단 api(Fly) 쪽은 수동 입력 필요 → 직접 계정이 더 단순할 수 있음 (ADR-0006 §2)
- [ ] **db 인덱스 분리 처리**: Upstash 는 인스턴스당 db 1개만 제공. 현재 코드가 `REDIS_URL`(db 0)·`OAUTH_STATE_REDIS_URL`(db 1)로 분리([`infra/compose/docker-compose.yml`](../../infra/compose/docker-compose.yml) L84/L106). 둘 중 하나:
  - (A) 단일 인스턴스 + **키 접두사**(`cache:`, `oauth_state:`) — 코드 소폭 수정. **권장.**
  - (B) Upstash 인스턴스 2개(free 2개 = $0) — 환경변수 두 URL 분리.
  - ☞ 채택안에 따라 `apps/api/src/auth/state_store.py` 의 redis 키/클라이언트 초기화 확인.

---

## 2. Fly.io api 앱 생성

작업 디렉터리: `apps/api` (Dockerfile 이 여기 있음)

- [ ] `fly launch --no-deploy` — 기존 [`apps/api/Dockerfile`](../../apps/api/Dockerfile) 자동 인식. 생성되는 `fly.toml` 을 커밋.
- [ ] `fly.toml` 핵심 값 확인/수정:
  - [ ] `primary_region = "nrt"` (도쿄)
  - [ ] `[http_service]` `internal_port = 8000`, `force_https = true`
  - [ ] `[[vm]]` `cpu_kind = "shared"`, `cpus = 1`, `memory = "1gb"` (ADR-0006 §1 근거: HF offload + presigned URL → 1GB 충분)
  - [ ] `[http_service.concurrency]` 적정값 (gunicorn workers=2 기준 hard limit 보수적으로)
  - [ ] (선택) `min_machines_running = 1` — scale-to-zero 콜드스타트로 OAuth UX 깨지지 않게 always-on 유지
- [ ] **헬스체크**: `fly.toml` `[[http_service.checks]]` 에 `path = "/healthz"` (기존 [`apps/api/src/routers/healthz.py`](../../apps/api/src/routers/healthz.py) — SELECT 1 포함). `grace_period` 충분히(부팅 30s+).

---

## 3. 시크릿 주입 (`fly secrets`)

> 값은 Supabase·Upstash·OAuth 콘솔에서 복사. 절대 echo/커밋 금지.

- [ ] DB (Supabase, sslmode=require):
  - `fly secrets set DATABASE_URL="postgresql://...:5432/postgres?sslmode=require"` (non-pooler/direct)
  - `fly secrets set DATABASE_POOL_URL="postgresql://...pooler...:6543/postgres?sslmode=require"`
- [ ] Redis (Upstash 도쿄):
  - `fly secrets set REDIS_URL="rediss://default:****@xxx.upstash.io:6379"`
  - `fly secrets set OAUTH_STATE_REDIS_URL="rediss://..."` (§1 의 A/B 안에 맞춰)
- [ ] Supabase Auth (정본, ADR-0004 §2.3):
  - `SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_SECRET`, `SUPABASE_JWT_AUDIENCE`
- [ ] APP_ENV:
  - `fly secrets set APP_ENV="production"` (또는 staging — `config.py::ALLOWED_APP_ENVS`)
- [ ] FRONTEND_AUTH_*_URL — **Vercel 도메인 기준으로 갱신** (localhost 아님):
  - `FRONTEND_AUTH_SUCCESS_URL=https://jippin.ai/auth/success`, `_FAILURE_URL`, `_TERMS_URL`
- [ ] OAuth provider (Naver fallback 잔존 시, ADR-0004 §2.5): KAKAO/GOOGLE/NAVER 키 + **REDIRECT_URI 를 `https://api.jippin.ai/...` 로 갱신**
- [ ] `AUTH_JWT_*` (필요 시)
- [ ] 전체 목록은 [`infra/compose/.env.example`](../../infra/compose/.env.example) 대조. `:?` 가드 변수가 빠지면 부팅 차단됨.

---

## 4. 도메인 / DNS / TLS

### 4.1 api.jippin.ai → Fly

- [ ] `fly deploy` (최초 배포)
- [ ] `fly certs add api.jippin.ai`
- [ ] 출력된 DNS 레코드를 도메인 콘솔에 추가:
  - `AAAA` + `A` (Fly 가 지정한 IP) **또는** `CNAME api → <app>.fly.dev`
  - `_acme-challenge.api` TXT (인증서 검증, Fly 안내대로)
- [ ] `fly certs show api.jippin.ai` 로 `Issued` 확인 (Let's Encrypt 자동)
- [ ] `curl https://api.jippin.ai/healthz` → 200 + DB 응답 확인

### 4.2 jippin.ai / www → Vercel

- [ ] Vercel jippin-web 프로젝트에 도메인 `jippin.ai` + `www.jippin.ai` 추가
- [ ] DNS: apex `jippin.ai` → A `76.76.21.21`, `www`/`*` → CNAME `cname.vercel-dns.com`
- [ ] SSL 자동 발급 확인

### 4.3 same-origin 프록시 (코드 변경 0)

- [ ] Vercel jippin-web 프로젝트 env 에 **`API_INTERNAL_BASE_URL=https://api.jippin.ai`** 설정
  - ☞ [`apps/web/next.config.mjs`](../../apps/web/next.config.mjs) L40-48 의 `rewrites()` 가 `/api/:path*` → `${API_INTERNAL_BASE_URL}/:path*` 로 프록시. 즉 브라우저는 same-origin `/api/*` 만 호출하고 `jippin_session` 쿠키 scope 가 유지된다. **CORS 설정·쿠키 SameSite 변경 불필요.**
- [ ] `NEXT_PUBLIC_API_BASE_URL=/api` 유지 (브라우저는 same-origin)
- [ ] `NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_FLOW_COOKIE_SECRET` 등 web 측 env 도 Vercel 에 세팅

---

## 5. OAuth / Supabase 콜백 URL 갱신 (외부 콘솔)

도메인이 바뀌므로 각 provider·Supabase 콘솔에서 redirect 를 새 도메인으로 등록:

- [ ] **Supabase Auth** → URL Configuration → Site URL `https://jippin.ai`, Redirect allow-list 에 `https://jippin.ai/**` 추가
- [ ] **Kakao / Google / Naver** 개발자 콘솔 → Redirect URI 를 `https://api.jippin.ai/...` (또는 Supabase callback) 으로 갱신
- [ ] `NEXT_PUBLIC_SUPABASE_URL` 기반 open-redirect allow-list 가 새 origin 포함하는지 확인 ([`infra/compose/.env.example`](../../infra/compose/.env.example) Supabase OAuth handoff 절)

---

## 6. 배포 자동화 (선택, 권장)

- [ ] api: `.github/workflows/` 에 `fly deploy --remote-only` 스텝 추가 (`FLY_API_TOKEN` = repo secret, `fly tokens create deploy`)
- [ ] 기존 [`DEPLOYMENT.md`](../../DEPLOYMENT.md) §1 의 Neon/Supabase 마이그레이션 Action 과 **분리 유지** — 본 배포는 앱 런타임만, 마이그레이션은 기존 경로.
- [ ] web: Vercel 은 git integration 으로 `dev`/`main` push 시 자동 — 별도 Action 불필요.

---

## 7. 컷오버 & 검증

- [ ] HF Inference Endpoint 발급 + api 가 **이미지 URL 만 전달**하는지 확인 (바이트 forward 금지 — ADR-0006 §1, 메모리 footprint 불변식)
- [ ] 이미지 업로드가 **presigned R2 URL** 경로인지 확인 (multipart 로 api 통과 금지)
- [ ] 스모크: 로그인(OAuth) → 세션 → 도면 업로드(메타데이터) → 채팅 1턴 → `/healthz`
- [ ] `fly logs` / Upstash 콘솔 / Supabase 대시보드에서 에러 없는지
- [ ] 롤백 리허설: `fly releases` → `fly deploy --image <previous>` 동작 확인

---

## 8. 문서 갱신 (전환 확정 후)

- [ ] ADR-0006 `Status: Accepted` 로 전환, ADR-0002 `Superseded by ADR-0006` 확정
- [ ] [`AGENTS.md`](../../AGENTS.md) §2 클라우드 줄 → 본 토폴로지로 갱신 (이미 ADR-0006 포인터 배너 반영됨)
- [ ] [`DEPLOYMENT.md`](../../DEPLOYMENT.md) §1 표의 production runtime 확정
- [ ] `INSTANCE_PUBLIC_HOST` 등 ADR-0002 §5 봉인 표는 폐기(분리형이라 단일 호스트 개념 소멸)

---

## 부록 A — "오너가 직접 해야 하는 일"만 1줄 요약

1. Fly·Vercel·Upstash·HF 계정/결제 등록 (§0)
2. Upstash 도쿄 Redis 생성 + db 분리 방식 결정 (§1)
3. `fly launch` → `fly.toml` 1c/1GB·nrt·/healthz (§2)
4. `fly secrets` 로 DB/Redis/Supabase/OAuth 값 주입 (§3)
5. DNS: `api.jippin.ai`→Fly, `jippin.ai/www`→Vercel, TLS 발급 (§4)
6. Vercel env `API_INTERNAL_BASE_URL=https://api.jippin.ai` (§4.3 — 코드 변경 없이 프록시 완성)
7. OAuth/Supabase 콜백 도메인 갱신 (§5)
8. HF 엔드포인트 + presigned/URL 불변식 검증 후 스모크 (§7)
