# Runbook — 집핀 보안 정책 (Stub)

- 정본 책임자: **Security Lead**
- 관련: AGENTS.md §4.4 / §5, ADR-0001, CEO 브리프 §3.4·§5, 요구사항 명세서 NFR-SEC-001~003, CMP-533
- 상태: **Stub (CMP-533 시점)** — 실제 인증 / PII 암호화 구현은 후속 이슈에서 본 정책을 정본으로 따른다.

본 문서는 집핀의 **현 시점 적용 가능한 보안 가드**와 **후속 이슈 대상 정책**을 한 곳에 모은다. 운영자·개발자·자동화 에이전트 모두가 본 문서를 출발점으로 삼는다.

---

## 1. 정책 카탈로그 — Authoritative summary

| ID | 정책 | 적용 시점 | 정본 위치 |
|---|---|---|---|
| **POL-AUTH-001** | 자체 비밀번호 인증 금지. 소셜 OAuth (카카오/구글/네이버) 만 허용. | 시작부터 (Stub 단계: 미구현) | NFR-SEC-002, 본 §2 |
| **POL-AUTH-002** | JWT 발급 + 만료 1 시간, refresh 토큰 7 일. RBAC `user` / `admin`. Admin 2FA 필수. | M1 인증 셸에서 | NFR-SEC-003, AGENTS.md §3 (AUTH) |
| **POL-SECRET-001** | 모든 자격증명은 `.env` / 시크릿 매니저. 커밋 금지. 회전 가능 패턴은 검출. | 시작부터 | AGENTS.md §4.4, 본 §4, `tools/secret-scan/` |
| **POL-PII-001** | `contact_info` 컬럼 (`leads.contact_info`, `users.contact_*`) 은 애플리케이션 레벨에서 **AES-256-GCM** 으로 암호화 후 저장. | M1 INPUT/LEAD 단계 | CEO 브리프 §5, 본 §3 |
| **POL-PII-002** | 채팅 로그(`chat_messages.content`) 의 전화·이메일·주소 패턴은 저장 전 마스킹. | M1 CHAT 단계 | NFR-SEC-003 |
| **POL-TLS-001** | 모든 외부 트래픽은 TLS 1.2+ 강제. HTTP→HTTPS 리다이렉트. | 배포 시점 (D6 후속) | NFR-SEC-001 |
| **POL-LEGAL-001** | 모든 결과 화면·다운로드 산출물에 AI 한계 고지 문구 포함. | 시작부터 (REPORT 모듈에서 강제) | AGENTS.md §4.6, FR-REPORT-009 |
| **POL-LOG-001** | 로그·에러 메시지에 평문 비밀번호·이메일·전화·API 키 노출 금지. structlog mask processor. | M1 부터 | AGENTS.md §4.5 |

> 본 카탈로그가 모순되면 (이슈 본문) > (CEO 브리프) > (NFR-SEC 요구사항) > (본 문서) 순으로 정본 우선순위 적용 (AGENTS.md §1).

---

## 2. 인증 — POL-AUTH-001 / 002 (Stub 상세)

### 2.1 결정 — 자체 비밀번호 없음 (NFR-SEC-002)

**왜 OAuth-only 인가**:
- 비전문 사용자 B2C 무료 모델 → 비밀번호 분실·재설정 흐름 부담 회피.
- 사용자 비밀번호 저장 = 추가 PII. 보관·암호화·BCP 비용 발생.
- 한국 시장의 카카오/구글/네이버 보급률 ≥95% → UX 손실 없음.

**프로바이더 (M1 구현 대상)**:
| 프로바이더 | scope | 우선순위 |
|---|---|---|
| Kakao | `account_email`, `profile_nickname` | P0 — 한국 사용자 1순위 |
| Google | `email`, `profile` | P0 |
| Naver | `email`, `nickname` | P0 |

**금지**:
- 자체 ID/비밀번호 입력 폼 — UI 차원에서 노출 금지.
- "임시 비밀번호 메일링" 같은 우회 흐름.
- Magic-link 이메일 인증 (PII 가 메일함에 머무름 — 향후 재평가).

### 2.2 JWT — POL-AUTH-002

- Access token: HS256, payload `{ sub: user_id, role, exp, iat, request_id }`, TTL 1 시간 (`apps/api/app/core/config.py:jwt_access_ttl_seconds`).
- Refresh token: 7 일 TTL, DB `users.refresh_token_hash` 에 hash 만 저장 (bcrypt cost ≥12).
- Admin 2 차 인증: TOTP (RFC 6238). Admin 로그인 시 `/admin/2fa/verify` 강제.

### 2.3 후속 이슈 트리거

- **본 정책은 stub 이다**: M1 자식 이슈에서 OAuth 콜백 구현·CSRF state 토큰·PKCE·`/auth/me`·세션 만료 정책을 본 문서로부터 분기한다.
- 구현 PR 본문에는 `Refs: docs/runbooks/security-policy.md#2` 표기.

---

## 3. PII — POL-PII-001 / 002

### 3.1 분류 (요구사항 §2 + 기능명세서 §2)

| 데이터 | 분류 | 저장 방식 | 위치 |
|---|---|---|---|
| `users.email` | identifier (OAuth 발급) | 평문 (인덱스 필요) | Neon `users` |
| `users.kakao_id` / `google_id` / `naver_id` | identifier | 평문 | Neon `users` |
| `leads.contact_info` (전화·이메일·메모) | **민감 PII** | **AES-256-GCM 암호화** | Neon `leads` |
| `chat_messages.content` | 일반 + 잠재 PII | 평문 + 저장 전 PII 마스킹 | Neon `chat_messages` |
| 도면 원본 | 자산 (사용자 소유물) | R2 `jippin-floorplans-raw`, 7 일 후 라이프사이클 삭제 | Cloudflare R2 |
| 도면 마스킹본 | 비밀번호와 동급 보호 불요 | R2 `jippin-floorplans-masked` | R2 |

### 3.2 contact_info 암호화 (POL-PII-001)

**알고리즘**: AES-256-GCM (authenticated encryption).

**키 관리**:
- 키 정본은 환경변수 `PII_ENCRYPTION_KEY` (32 bytes, base64 인코딩) — `.env` / 시크릿 매니저에 저장.
- DB 에 키 자체 저장 금지.
- 회전 정책: 90 일마다 새 키 발급, 이전 키는 `PII_ENCRYPTION_KEY_PREVIOUS` 로 보존해 재암호화 잡 실행 가능하게.

**구현 (M1 자식 이슈 입력)**:
- `apps/api/app/core/crypto.py` (스텁 — 본 이슈 범위 외): `encrypt_pii(plaintext: str) -> str`, `decrypt_pii(ciphertext: str) -> str`.
- ciphertext 포맷: `v1:<nonce_b64>:<ciphertext_b64>:<tag_b64>` (버전 prefix 로 향후 알고리즘 교체 가능).
- DB 컬럼: `leads.contact_info` 는 `text` 타입, 항상 ciphertext.

**감사**:
- 평문 `contact_info` 가 응답 JSON 으로 나가는 경로는 단 하나(`/admin/leads/{id}` admin 권한 + audit log 기록).
- 일반 사용자 응답은 마스킹된 형태 (`010-****-1234`).

### 3.3 채팅 로그 마스킹 (POL-PII-002)

- 모든 user-input 메시지는 `apps/api/app/modules/chat/pii_mask.py` (스텁) 를 통과한 뒤 저장.
- 패턴:
  - 한국 휴대폰: `01[016-9]-?\d{3,4}-?\d{4}` → `***-****-****`
  - 이메일: `[\w.+-]+@[\w.-]+` → `***@***`
  - 한국 주소 일부 (동 + 호수): `\d+동\s*\d+호` → `***동 ***호` (단, 검토 요청 본문은 예외)
- LLM 호출 (VLM, FLOW_GUARD) 직전에는 마스킹된 사본을 전달. 원본은 DB 에만 저장 (마스킹 후).

---

## 4. 시크릿 관리 — POL-SECRET-001

### 4.1 검출

- pre-commit: `tools/secret-scan/scan.py --staged` 가 staged 변경을 검사. fail-fast.
- CI: `.github/workflows/secret-scan.yml` 가 PR / push / 주간 cron 으로 전체 트리 스캔.
- 패턴 카탈로그 (`tools/secret-scan/patterns.yml`):
  - `neon-password` (`npg_*`) — critical
  - `openai-api-key` (`sk-*`, `sk-proj-*`, `sk-svcacct-*`) — critical
  - `aws-access-key-id` (`AKIA*`, `ASIA*`, `AIDA*` …) — critical
  - `aws-secret-access-key` (컨텍스트 + 40자) — critical
  - `slack-bot-token` (`xox[baprs]-*`) — high
  - `github-personal-token` (`ghp_*`) — critical
  - `github-oauth-token` (`gho_*`) — high
  - `github-app-token` (`ghs_/ghu_/ghr_*`) — high
  - `db-url-with-inline-password` (`postgresql://user:pw@`, `mysql://…`) — critical
  - `google-api-key` (`AIza*`) — high
  - `stripe-secret-key` (`sk_(live|test)_*`, `rk_*`) — critical
  - `private-key-block` (`-----BEGIN ... PRIVATE KEY-----`) — critical

### 4.2 우회 / Allowlist

- `git commit --no-verify` 는 **코드 리뷰 단계에서 거부 사유**.
- 정당한 fixture / 문서 인용은 `tools/secret-scan/patterns.yml` 의 `allowlist:` 에 등록 (reason 필수).
- Allowlist 변경 PR 은 Security Engineer 리뷰 필수.

### 4.3 회전

- Neon 자격증명: `docs/runbooks/neon-credential-rotation.md`.
- 그 외 (OpenAI / AWS / Slack / GitHub) 키는 본 문서 §6 의 회전 절차 표를 따른다.

### 4.4 저장

- 로컬: `.env` 파일. **절대 git 추적 금지**. `.gitignore` 가 강제.
- CI: GitHub Actions Repository Secrets.
- 배포: D6 결정 후의 시크릿 매니저 (1순위: GCP Secret Manager / AWS Secrets Manager).
- 1Password team vault 의 `집핀 / Production` 폴더가 마스터 카탈로그 (사람 간 공유).

---

## 5. 로깅·관측 — POL-LOG-001

- 로그 포맷: structlog JSON, 키 화이트리스트 기반 (개발 모드만 free-form).
- 마스크 프로세서: `request_id`, `user_id` 는 평문 OK. `email`, `phone`, `password`, `api_key`, `token`, `secret`, `contact_info` 키는 자동 마스킹.
- HTTP 액세스 로그는 query string 평문 저장 금지 — 미들웨어가 known sensitive params (`token`, `code`, `state`) 를 마스킹.
- 로그 보존: 30 일 (NFR-SEC-001 미정의 — 운영 단계에서 자식 이슈로 확정).

---

## 6. 키·자격증명 카탈로그 + 회전 정책

| 종류 | 보유처 | 회전 주기 | 회전 트리거 | Owner |
|---|---|---|---|---|
| Neon `neondb_owner` password | Neon Console | 90 일 | 노출 / 이탈 / 사고 | CEO / DBA |
| OpenAI API key (`OPENAI_API_KEY`) | OpenAI Platform | 90 일 | 노출 / 사고 / quota 분리 | Backend Lead |
| Cloudflare R2 access key | Cloudflare Dashboard | 180 일 | 노출 / 이탈 | Cloud Engineer |
| GitHub Actions `GITHUB_TOKEN` | 자동 (per run) | 자동 | — | — |
| `JWT_SECRET` | `.env` / 시크릿 매니저 | 180 일 + 사고 시 즉시 | 노출 / 사고 / 임직원 이탈 | Backend Lead |
| `PII_ENCRYPTION_KEY` | `.env` / 시크릿 매니저 | 90 일 (재암호화 잡 동반) | 노출 / 알고리즘 변경 | Backend Lead + DBA |
| OAuth Client Secret (Kakao/Google/Naver) | 각 콘솔 | 180 일 | 노출 / 사고 | Backend Lead |

---

## 7. 본 문서의 다음 단계

본 문서는 **stub** 이다. 다음 자식 이슈에서 본 문서를 확정한다.

| 후속 이슈 (제안) | 본 §확정 대상 | 주 오너 |
|---|---|---|
| `[Backend] OAuth 콜백 + JWT 미들웨어 + Admin 2FA` | §2 | Python Backend Engineer |
| `[Backend] PII 암호화 모듈 + DB 마이그레이션` | §3.2 | Python Backend Engineer + DBA |
| `[Backend] 채팅 로그 PII 마스킹 미들웨어` | §3.3 | Python Backend Engineer |
| `[DevOps] TLS / HSTS / CSP 헤더` | POL-TLS-001 | DevOps Engineer |
| `[QA] 보안 회귀 테스트 (시크릿 스캔 self-test 포함)` | §4 | Test Engineer |
| `[Security] 외부 의존성 SCA / SBOM` | §추가 | Security Engineer |

---

## 8. 참고

- OWASP Top 10 (2021): 본 정책의 §2 (A07 Identification & Authentication), §3 (A02 Cryptographic Failures), §4 (A05 Security Misconfiguration / A09 Logging) 가 명시적으로 대응.
- 한국 개인정보보호법 §29 안전성 확보 조치 — §3.2 의 AES-256-GCM 적용.
- AGENTS.md §4.4 (시크릿), §4.5 (에러·로깅), §4.6 (법적 고지).
- ADR-0001 (스택 봉인) — §5 의 의존성 회전 정책은 본 ADR 의 봉인 버전과 함께 갱신.
