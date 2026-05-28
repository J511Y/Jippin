# AGENTS.md — Jippin(집핀) 에이전트 작업 가이드

이 문서는 본 모노레포에서 일하는 **Paperclip 에이전트(자율형)** 와 **사람 개발자** 모두를 대상으로 한다. 한 줄 요약: *집핀은 비내력벽 철거 사전검토 AI 서비스이며, 이 레포는 단일 인스턴스 docker-compose 모노레포다. 모든 결정은 `docs/명세서/`(요구·기능·기술·SDD)와 `docs/brief/CEO_PROJECT_BRIEF.md` 에 우선 따른다.*

---

## 1. 우선순위 — 무엇을 먼저 읽어야 하는가

자동화 에이전트가 어떤 이슈를 받든, 작업 시작 전에 아래 순서로 정합성을 맞춘다.

1. **이슈 본문** (`PAPERCLIP_WAKE_PAYLOAD_JSON.issue.description`)
2. **`docs/brief/CEO_PROJECT_BRIEF.md`** — 범위·인도물·금지사항
3. **`docs/명세서/` 4종 정본** — 요구사항(v0.2) / 기능명세(v1.0) / 기술명세(v1.6) / SDD(v1.9)
4. **`docs/_extracted/`** — 위 정본에서 추출한 텍스트 캐시 (Word/Excel 미설치 환경용)
5. 해당 모듈의 `README.md` 와 코드 정본

기능명세서·SDD·기술명세서 간 모순이 있으면 **(이슈 본문) > (CEO 브리프) > (SDD) > (기술명세서) > (기능명세서) > (요구사항)** 순으로 정본을 따르되, 모순 자체를 PR 또는 후속 이슈로 보고한다.

---

## 2. 모노레포 구조 (목표 상태 — CTO 분해로 확정)

```
jippin/
├── apps/
│   ├── web/           # Presentation (Next.js or 대안 — CTO ADR 결과)
│   └── api/           # Application (FastAPI or 대안 — CTO ADR 결과)
├── packages/
│   ├── contracts/     # CommonJudgmentSchema, CompletionDecision, RuleEvalResult, EstimateResult (언어 중립 JSON 스키마 + 생성된 TS/Python 타입)
│   └── eslint-config/ # (선택)
├── infra/
│   ├── docker/        # Dockerfile.web / Dockerfile.api / nginx.conf
│   └── compose/       # docker-compose.yml + override 파일
├── docs/
│   ├── 명세서/        # 정본 4종 + 참고 이미지
│   ├── _extracted/    # 위 정본의 텍스트 캐시 (read-only)
│   ├── brief/         # CEO 브리프
│   ├── adr/           # CTO 아키텍처 결정 기록
│   └── runbooks/      # 운영 런북 (후속)
└── tooling/           # extract_specs.py 등 1회성 스크립트
```

> 본 이슈(CMP-523) 종료 시점에는 위 트리의 골격만 존재한다. 모듈별 실제 코드는 후속 이슈에서 채워진다.
>
> **봉인 ADR**: 본 트리·패키지 매니저·런타임은 [`docs/adr/0001-stack-reevaluation.md`](docs/adr/0001-stack-reevaluation.md) 가 봉인한다. 변경은 새 ADR을 발행해 supersede 해야 한다. 핵심 결정:
> - `apps/web` = **Next.js 16.2 LTS** · React 19 · Node 22 LTS · **pnpm 9.x**
> - `apps/api` = **FastAPI 0.115** · Python 3.12 · **uv 0.5+**
> - DB = **Neon Postgres** (외부, 로컬 DB 컨테이너 없음). 캐시 = **Redis 7.4-alpine** 컨테이너.
> - 객체 스토리지 = **Cloudflare R2** (S3 호환, zero-egress).
> - LLM 오케스트레이션 = **LangChain v0.3+**. VLM 기본 = OpenAI `gpt-4.1-mini` / 정밀 = `gpt-4o`.
> - 클라우드 MVP = **AWS Lightsail Seoul (`ap-northeast-2`)** — ADR-0002 Accepted 후 확정.

---

## 3. 모듈 ↔ 담당 에이전트 매핑

SDD §3·§4의 8개 논리 모듈 + FLOW_GUARD를 다음 라인에 배정한다. (라인 = Paperclip 디렉터/엔지니어)

| 모듈 | 책임 1줄 | 주 담당 라인 | 부 담당 |
|---|---|---|---|
| AUTH | 소셜 OAuth + JWT | Backend Lead → Python Backend Engineer | Security Engineer |
| INPUT | 주소·도면 수신·검증·OCR | Backend Lead → Python Backend Engineer | Frontend Lead (업로드 UI) |
| MASK | 도면 수치 마스킹 | Backend Lead → Python Backend Engineer | Data Lead (OCR 모델) |
| AI | Mask2Former + VLM + 스키마 정규화 | **Data Lead → AI/ML Engineer** | Backend Lead |
| OVERLAY | 도면 위 인터랙티브 선택 | **Frontend Lead → React Engineer** | — |
| CHAT | A2UI 세션 오케스트레이션 | Frontend Lead + Backend Lead (양측 책임) | — |
| FLOW_GUARD | 충분성/충돌/고위험 판단 | **AI Engineer** (별도 LLM 에이전트 옵션) | Architecture Lead (계약 가드) |
| RULE | 국토부 고시 룰 엔진 | Python Backend Engineer | Architecture Lead |
| REPORT | 리포트 + 견적 + 리드 | Python Backend Engineer + React Engineer | — |

라인 외 횡단 책임:
- **Architecture Lead** — 모듈 간 공통 컨트랙트 (공통 판단 스키마, CompletionDecision, RuleEvalResult, EstimateResult) 일관성 가드
- **Infrastructure Lead / Cloud Engineer** — 단일 인스턴스 운영 모델, 클라우드 비용 비교
- **DevOps Engineer** — CI, gitmoji 검증, GitHub Flow 정책 자동화
- **Security Lead / Security Engineer** — 시크릿 헌팅, OAuth/PII/암호화 정책 가드
- **QA Lead / Test Engineer** — 테스트 피라미드, 룰 결정성 회귀 테스트
- **Database Engineer** — Neon 스키마/마이그레이션/인덱스 (후속 이슈)

---

## 4. 글로벌 규칙

### 4.1 커밋 메시지 — gitmoji

다음 prefix만 허용한다.

| 이모지 | prefix | 용도 |
|---|---|---|
| ✨ | `feat:` | 새 기능 |
| 🐛 | `fix:` | 버그 수정 |
| 📝 | `docs:` | 문서 |
| ♻️ | `refactor:` | 동작 변화 없는 리팩터 |
| ✅ | `test:` | 테스트 추가/수정 |
| 🔧 | `chore:` | 빌드·설정·도구 |
| 🚀 | `perf:` | 성능 개선 |
| 🔒 | `security:` | 보안 패치 |
| 🚧 | `wip:` | 임시 (PR 머지 전 squash) |

예: `✨ feat(auth): kakao oauth callback`

### 4.2 브랜치 전략 — GitHub Flow

- `main` 보호. 직접 푸시 금지.
- 브랜치 명: `<type>/<scope>-<short>` (예: `feat/auth-kakao-callback`, `chore/cmp-523-bootstrap`).
- PR 본문에는 관련 Paperclip 이슈 식별자(`CMP-###`)와 영향 모듈 표기.
- 머지 방식: Squash and merge (gitmoji prefix 유지).

### 4.3 PR 체크리스트

- [ ] 관련 이슈 식별자 명시
- [ ] 영향 모듈 명시 (`AUTH` / `INPUT` / …)
- [ ] 공통 컨트랙트(`packages/contracts/`) 변경 시 schema_version bump
- [ ] 비밀번호·키·도면 등 민감 자료 미포함
- [ ] `docker compose up` 또는 모듈별 dev 명령 정상 동작
- [ ] (해당 시) README 갱신

### 4.4 시크릿 & 환경변수

- 실제 값은 `.env` 로컬 또는 운영 시크릿 매니저. 커밋 금지.
- `.env.example` 만 커밋. 변수명·예시값 형식·설명 포함.
- Neon DB URL은 두 가지를 모두 관리한다: `DATABASE_URL`(non-pooler, 마이그레이션), `DATABASE_POOL_URL`(pooler, 일반 쿼리). `sslmode=require` 는 모든 URL 에 필수.
- **APP_ENV ↔ Neon 브랜치 매핑은 봉인** (CMP-538). 코드 분기 금지 — 매핑은 환경별 `.env` 의 URL 값으로만 한다 (12-factor). `apps/api/src/config.py::ALLOWED_APP_ENVS` 가 그 외 값을 부팅 단계에서 차단한다. 변경하려면 ADR 을 새로 발행한다.

  | APP_ENV       | Neon 브랜치             | 수명           | 비고                              |
  |---------------|-------------------------|----------------|-----------------------------------|
  | `development` | `dev`                   | 장기, 공유     | 로컬 개발자 공용                  |
  | `test`        | `dev` 또는 PR ephemeral | 단기           | CI / 단위 테스트                  |
  | `staging`     | `staging`               | 장기           | QA / 사전검증                     |
  | `production`  | `main`                  | 장기           | 운영 (Neon project default branch)|

  운영 절차: [`docs/runbooks/neon-branches.md`](docs/runbooks/neon-branches.md). 회전 절차: [`docs/runbooks/neon-credential-rotation.md`](docs/runbooks/neon-credential-rotation.md).

### 4.5 에러·응답 표준

모든 백엔드 모듈은 다음 응답 포맷을 따른다.

```json
{ "error": { "code": "INSUFFICIENT_DATA", "message": "...", "request_id": "...", "timestamp": "..." } }
```

- 비즈니스 예외는 `ZippinException` 계열 도메인 예외로 raise → 공통 예외 핸들러가 변환.
- AI 단계는 SDD §8.2에 정의된 코드(`SEGMENTATION_FAILED` / `VLM_TIMEOUT` / `ANALYSIS_LOW_CONFIDENCE` 등) 사용.
- 로그는 structlog 기반 JSON, `request_id` 컨텍스트 주입.

### 4.6 법적 고지 — 절대 누락 금지

모든 리포트 화면·다운로드 산출물(웹/PDF/DOCX/공유링크 OG)은 다음 문구를 포함한다.

> 본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.

---

## 5. 자동화 에이전트 작업 프로토콜 (Paperclip)

1. **Wake payload 우선** — `PAPERCLIP_WAKE_PAYLOAD_JSON` 이 가리키는 이슈만 처리한다. 다른 이슈로 분기하지 않는다.
2. **본 이슈 범위를 벗어나면 자식 이슈를 생성** — `POST /api/issues` 로 자식 이슈를 만들고 본 이슈에 blockedBy 또는 related로 묶는다. 직접 폭주 X.
3. **변경 후 반드시 final disposition** — `done` / `in_review` / `blocked` / `in_progress(live continuation only)` 중 하나로 본 이슈 상태를 정리.
4. **읽기 자료** — 정본 docx/xlsx는 `tooling/extract_specs.py` 로 `docs/_extracted/` 에 텍스트 캐시가 만들어져 있다. 정본이 갱신되면 캐시도 갱신할 것.
5. **시크릿 헌팅** — PR/커밋 단계에서 `npg_`, `sk-`, `AKIA` 등 시크릿 패턴이 들어가지 않도록 검사. 발견 시 즉시 회전 요청.
6. **모순 보고** — 명세 4종 간 모순을 발견하면 `docs/명세서-모순.md`(없으면 생성)에 기록하고 후속 이슈로 분리.

### 5.7 한글(UTF-8) 인코딩 — 이슈/코멘트/문서 작성 시 절대 위반 금지

> **배경.** Windows(PowerShell/cmd.exe) 호스트에서 `curl -d '{"title":"한글"}' ...` 형태로 Paperclip API 를 인라인 호출하면, 활성 코드페이지(CP949)와 curl 의 UTF-8 가정이 충돌해 본문이 `?` 로 깨진 채 서버에 저장된다. **이 손상은 비가역적**(원문 복원 불가)이며, 보드와 위임받은 에이전트 모두 작업 컨텍스트를 잃는다. 2026-05-28 CMP-524 사고(자식 이슈 7개 제목·본문 전손) 재발 방지.

**모든 에이전트는 Paperclip API(POST/PATCH `/api/...`)로 한글 콘텐츠를 보낼 때 다음 절차를 따른다.**

1. **JSON 페이로드를 파일로 먼저 작성** — Claude Code `Write`/`Edit` 툴은 기본 UTF-8 (BOM 없음). PowerShell `Out-File`/`Set-Content` 사용 시 반드시 `-Encoding utf8NoBOM`.
2. **`curl` 은 `--data-binary @<파일>` + 명시적 charset 헤더** 로 전송한다.
3. **인라인 `-d '...'` 또는 here-string 으로 한글을 박지 않는다.** PowerShell here-doc 도 환경에 따라 변환된다 — 금지.

표준 호출 패턴 (Git Bash / MSYS):

```bash
# 1) JSON 본문을 UTF-8 파일로 저장 (Claude Code Write 툴 권장)
#    또는 Git Bash 한정: cat > .tmp/payload.json <<'EOF' ... EOF
#    PowerShell here-string 금지.

# 2) PATCH/POST 호출 — --data-binary @ 와 charset 헤더 반드시 포함
curl -s -X PATCH \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary @.tmp/payload.json \
  "$PAPERCLIP_API_URL/api/issues/<ID>" \
  -o .tmp/resp.json

# 3) 응답을 node 로 검증 — PowerShell Get-Content 는 인코딩 자동변환 위험
node -e "const d=JSON.parse(require('fs').readFileSync('.tmp/resp.json','utf8')); console.log(d.title)"
```

자기 점검 체크 (이슈 생성/수정 직후 즉시):

- [ ] 같은 ID 를 `GET /api/issues/<ID>` 로 재조회해 `title`/`description` 에 `?` 가 아닌 정상 한글이 들어있는지 확인.
- [ ] 깨진 흔적이 보이면 즉시 PATCH 로 복구 + 사고 코멘트.
- [ ] 자식 이슈를 7개 이상 일괄 생성할 때는 첫 1개 직후 위 검증을 통과해야 다음 6개를 만든다.

위반 시: 위임 사슬의 모든 자식 이슈가 영문/`?` 만 보여 보드와 위임받은 에이전트가 작업 식별 불가. **인수 거부 사유**다.

> 사람 작업자 주의: 시스템 PowerShell 콘솔 폰트가 `Lucida Console` 인 경우 정상 출력된 한글도 콘솔에서는 `?` 로 보일 수 있다. **보드(웹 UI) 또는 `GET /api/issues/<ID>` 응답을 진실의 원천으로 삼는다.**

---

## 6. 표준 명령 (CTO ADR-0001 봉인 후 정본)

각 앱의 정본 명령은 해당 앱 README에 두되, 모노레포 루트에서 자주 쓰는 명령은 다음과 같다.

```bash
# 전체 부팅 (web + api + redis. DB는 Neon 원격)
docker compose -f infra/compose/docker-compose.yml up --build

# 백엔드 단독 (uv)
cd apps/api && uv sync && uv run uvicorn src.main:app --reload --port 8000

# 프론트엔드 단독 (pnpm)
cd apps/web && pnpm install && pnpm dev

# 헬스체크 (Neon SELECT 1 결과 포함)
curl http://localhost:8000/healthz

# 마이그레이션 (api 컨테이너 내부 / Alembic)
docker compose exec api alembic upgrade head

# 정본 docx/xlsx 텍스트 캐시 재생성
python tooling/extract_specs.py
```

---

## 7. 본 문서의 변경 절차

- CEO 가 본 문서의 §1·§3·§4를 봉인한다. 변경은 새 CEO 브리프 리비전을 통해서만 일어난다.
- CTO·각 라인 리드는 §2·§5·§6을 PR로 갱신할 수 있다.
- 모든 갱신은 gitmoji `📝 docs:` 커밋과 PR 본문에 영향 범위를 명시한다.
