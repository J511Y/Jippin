# 집핀(Zippin) — CEO 프로젝트 브리프

- 작성자: CEO (1a9c8580)
- 작성일: 2026-05-28
- 대상 이슈: CMP-523 "프로젝트 기본 세팅"
- 기준 문서: `docs/명세서/` v0.2 / v1.0 / v1.6 / v1.9 (2026-05-21~27)
- 본 문서는 **요구사항 합의 기준선**이다. 기술 선정·구현 분해는 CTO 산출물(아키텍처 결정 기록·구현 계획)이 정본이다.

> **⚠ 부분 supersede 표기 (2026-06-02 / CMP-602)**
>
> 본 브리프의 §2 D2/D3 “Postgres 는 Neon 원격 연결” 및 §6 T3 “Neon” 표기는 [`docs/adr/0004-supabase-transition.md`](../adr/0004-supabase-transition.md) (Proposed, 2026-05-29~) 가 **Neon → Supabase 부분 supersede 진행 중**이다. CEO 봉인 (단일 인스턴스, docker-compose, 법적 고지, 자체 비밀번호 금지, 한국 사용자 PII 보호) 은 유지된다. ADR-0004 Accepted 시점에 본 브리프 §2/§6 의 Neon 표기를 supersede 표시로 갱신할 수 있도록 CEO 가 별도 brief revision 이슈 (DevOps Lead 후속) 를 받는다. 본 PR (CMP-602) 은 브리프 본문을 직접 rewrite 하지 않는다.

---

## 1. 서비스 한 줄 정의

> **집핀**은 공동주택 비내력벽 철거(발코니 확장 등) 행위허가의 **사전검토를 AI로 자동화**하여, 비전문 사용자가 주소·도면만으로 철거 가능 여부·필요 방화시설·법령 근거를 1회 채팅 세션 안에서 확인하고, 상담·행위허가 의뢰 채널로 자연스럽게 전환되도록 만드는 **B2C 무료 웹앱**이다. (수익은 리포트 후 상담·행위허가 의뢰에서 발생)

법적 효력 없음 — 모든 결과 화면에 "본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다." 고지 의무. (FR-REPORT-009, NFR-LEGAL-001)

---

## 2. 본 이슈(CMP-523)의 확정 범위

본 이슈는 "서비스 구현"이 아니라 **모노레포 기본 세팅**을 인도한다. 인도물은 아래 6가지로 한정한다.

| # | 인도물 | 수용 기준 |
|---|---|---|
| D1 | 모노레포 디렉터리/패키지 구조 | `apps/web`·`apps/api`·`packages/*` 등 모듈 경계가 §6 모듈 분해와 1:1 추적 가능 |
| D2 | docker-compose 기반 단일 인스턴스 오케스트레이션 | `docker compose up`만으로 web·api·redis 부팅. Postgres는 Neon 원격 연결 (로컬 DB 컨테이너 X) |
| D3 | DB 연결 부트스트랩 (Neon Postgres) | `DATABASE_URL` 기반 비동기 connect/health check 성공, pooler/non-pooler 두 호스트 모두 환경변수로 토글 가능 |
| D4 | 하위 서비스 기본 골격 | (a) 웹 프레임워크 설치 (b) 공통 인터페이스 (인증 컨텍스트, 표준 에러·응답 포맷, request_id 미들웨어) (c) 전역 에러 핸들러 (d) 구조화 로깅 (e) 환경변수 로더 |
| D5 | 루트 메타 파일 | `README.md`, `AGENTS.md`, `.gitignore`, `.env.example`, `.editorconfig`, 커밋·브랜치 정책 문서 |
| D6 | 클라우드 후보·견적 비교 메모 | AWS·GCP·Azure·Vercel+Fly+Render 등 후보별 월 예상 비용·리전·운영 부담 비교표 (의사결정 X, 자료 제공만) |

**범위 외**(=후속 이슈로 분기):
- AI 파이프라인 실제 구현 (Mask2Former·VLM 호출)
- 룰 엔진의 법령 규칙 구현
- OAuth 프로바이더 실제 연동
- 도면 DB 마이그레이션
- 본 격 CI/CD 파이프라인 구축 (기본 워크플로 스켈레톤만 D5에 포함)

---

## 3. 제품 요구 요약 (전체 서비스 — 후속 이슈 입력용)

### 3.1 핵심 사용자 플로우 (9단계, 기능명세서 §1.3)

로그인 → 주소 입력 → 도면 확인(DB 후보/업로드) → 수치 마스킹 → AI 분석(Mask2Former + VLM) → 오버레이 확인·벽체 선택 → 대화형 부족 정보 수집 → 룰 엔진 판단 → 리포트 + CTA(상담/행위허가 의뢰/공유)

### 3.2 8개 논리 모듈 + 1개 감시 에이전트 (SDD §3·§4)

`AUTH` / `INPUT` / `MASK` / `AI` / `OVERLAY` / `CHAT` / `FLOW_GUARD` / `RULE` / `REPORT`

- 모듈 분해는 **물리 배포가 아닌 책임 경계** 기준 — 하나의 논리 모듈이 Presentation·Application·Data에 걸쳐 분산될 수 있다.
- 핵심 컨트랙트는 **공통 판단 스키마(CommonJudgmentSchema)**, 핵심 분기는 **CompletionDecision** `(ASK_MORE | REQUEST_OVERLAY_REVIEW | PROCEED_RULE | HOLD_OR_HANDOFF)`.

### 3.3 우선순위 (요구사항 명세서)

- **P0 MVP**: AUTH(소셜 OAuth) / INPUT(주소·도면) / MASK / AI(Mask2Former+VLM+스키마 정규화) / OVERLAY(벽체 선택) / CHAT(A2UI·세션) / RULE(국토부 고시 룰화) / REPORT(결과·법적 고지·리드 CTA) / FLOW_GUARD(보완 루프)
- **P1 확장**: HITL 매핑 이미지 표시, 룰셋 핫스왑, 견적 카드, 학습 데이터 환류
- **P2/P3**: 세움터 연동, 견적 자동화, 전국 도면 DB 확장

### 3.4 비기능 요구 핵심 (요구사항 §2, 기능 §3, 기술 §8)

| 분류 | 목표 |
|---|---|
| AI 분석 응답 | 평균 5초 / p95 8초 |
| 일반 API 응답 | 200ms 이내 |
| 동시 세션 | MVP 30 / 확장 200 |
| 가용성 | 월간 99.0% |
| 보안 | TLS 1.2+, AES-256 저장, OAuth만 허용(자체 비번 X), RBAC(user/admin) + Admin 2FA |
| 정확도 | 객체 인식 mAP ≥80%, 룰 결정성 100%, 부족 케이스 ≥95% 보류 분류 |
| 법규 | 모든 결과 화면 AI 고지 문구 필수 / 분기 1회 이상 법령 검증 |

### 3.5 데이터 모델 (기술명세서 §5)

`users` ─ `sessions(HUB)` ─ `floorplans` / `reports(1:1)` / `chat_messages(1:N)` / `leads(1:N)` / `flow_guard_decisions` / `estimate_items`.

---

## 4. 사용자 스토리 (상위 9개 — 후속 백로그 입력용)

| ID | 스토리 | 수용 기준 (요약) |
|---|---|---|
| US-01 | 사용자로서, 소셜(카카오/구글/네이버) 로그인으로 서비스를 시작하고 싶다 | OAuth 콜백 후 3초 이내 채팅 진입. JWT 발급/갱신 자동 |
| US-02 | 사용자로서, 주소·동·호·층을 한 번에 입력해 검토를 시작하고 싶다 | 필수 누락 시 다음 단계 차단. 정규화된 BuildingIdentity 생성 |
| US-03 | 사용자로서, 내 단지 도면이 후보로 자동 제시되거나, 없으면 내 도면을 업로드하고 싶다 | DB 후보 N건 썸네일 카드 / 업로드 시 20MB·형식·악성코드 검증 |
| US-04 | 사용자로서, 업로드 도면의 치수가 자동 마스킹되어 자산 보호가 되었으면 한다 | 업로드 후 10초 내 마스킹본 미리보기 |
| US-05 | 사용자로서, AI가 도면을 자동 해석해 발코니·대피공간·비내력벽 후보를 색상으로 보여주길 원한다 | 분석 완료 후 3초 내 오버레이 렌더. 신뢰도 미만은 "추가 확인 필요" 표기 |
| US-06 | 사용자로서, 어떤 비내력벽을 철거하고 싶은지 도면 위에서 클릭해 지정하고 싶다 | 단일/복수 선택·해제. selected_walls가 공통 판단 스키마에 반영 |
| US-07 | 사용자로서, 모르는 정보(스프링클러·대피공간 등)는 전문용어 없이 생활어 질문으로 안내받고 싶다 | 부족 케이스 ≥95%가 보류·추가 확인. 동일 질문 한 세션 2회 초과 X |
| US-08 | 사용자로서, 철거 가능 여부·필요 방화시설·법령 근거를 한 화면에서 확인하고 싶다 | 결과 라벨(가능/불가/보류)·시설 카드·법령 근거·법적 고지 포함 |
| US-09 | 사용자로서, 결과 화면에서 바로 상담 신청 또는 행위허가 의뢰를 보낼 수 있어야 한다 | 클릭 시 관리자 이메일/SMS 알림, lead 생성, 공유 링크 발급 |

관리자 스토리(US-A1~A5)는 별도 백로그(관리자 검토 로그·학습 데이터·룰셋 버전·리드 보드·KPI 대시보드).

---

## 5. 제약·정책 (반드시 준수)

| 구분 | 정책 |
|---|---|
| 리포지토리 | 단일 모노레포 `J511Y/Jippin` 에 모든 서비스 코드 |
| 배포 | docker-compose 기반 단일 인스턴스 가정 |
| DB | **Neon Serverless Postgres** 사용. Pooler 호스트(`ep-empty-heart-aolzk9rl-pooler...`)는 서버리스/짧은 연결, non-pooler는 마이그레이션·롱 트랜잭션 |
| 브랜치 전략 | **GitHub Flow** — `main` 보호, feature 브랜치 → PR → 머지 |
| 커밋 메시지 | **gitmoji** 컨벤션 (`✨ feat:`, `🐛 fix:`, `📝 docs:`, `♻️ refactor:`, `✅ test:`, `🔧 chore:` 등) |
| 보안 | Neon 자격증명·OAuth 키 등 절대 커밋 금지. `.env.example`만 커밋, 실제 `.env`는 `.gitignore` |
| 법적 고지 | 모든 결과 화면·다운로드 산출물에 한계 고지 문구 포함 |
| 데이터 보존 | 채팅 로그 PII 마스킹, contact_info 애플리케이션 레벨 암호화 |

### 5.1 확정된 환경 변수(D3·D5)

```env
# Neon Postgres
DATABASE_URL=postgresql://neondb_owner:****@ep-empty-heart-aolzk9rl.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
DATABASE_POOL_URL=postgresql://neondb_owner:****@ep-empty-heart-aolzk9rl-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

(자격증명은 시크릿 매니저에 등록하고, 로컬은 `.env`. 이슈 본문에 평문 노출된 비밀번호는 차후 회전 권장.)

---

## 6. 명세 → 재평가가 필요한 기술 결정 (CTO 입력)

이슈 본문이 명시했듯 **명세서의 스택은 권장값**이다. CTO는 아래 7개 항목을 **2026-05-28 기준 최신 릴리스 기준으로 재평가**하고 ADR(아키텍처 결정 기록)을 남긴 뒤 진행한다.

| # | 명세서 권장 | 재평가 포인트 |
|---|---|---|
| T1 | **Next.js 14+ (App Router)** | 2026-05 현재 릴리스 라인 확인 (16.x 후보). RSC/Server Actions·Turbopack 안정성·Node 런타임 요구 사항. |
| T2 | **FastAPI / Python 3.11+** | Python 3.13/3.14, FastAPI vs LiteStar, Pydantic v2 성능. AI 워커 분리 시 Ray/Celery vs Uvicorn 동기. |
| T3 | **PostgreSQL 15+** (Neon) | Neon 지원 메이저 버전·HNSW/pgvector 필요 시점, branching 활용 여부. |
| T4 | **Redis 7+** | Neon 환경에서 Upstash·Redis Cloud vs 자체 컨테이너 비용·관리 부담. |
| T5 | **객체 스토리지 = S3** | Cloudflare R2 / Tigris / Backblaze B2 등 비용·송신 무료 옵션. (클라우드 미정과 연동) |
| T6 | **Mask2Former + OpenAI VLM** | 2026 기준 SOTA 비교 (Florence-2, Qwen2.5-VL, SAM2 등). LangChain 추상화 유지 가능 여부. |
| T7 | **EC2 단일 인스턴스 + Docker Compose** | 클라우드 미정 — AWS EC2 / GCP CE / Hetzner / Fly.io Machines 등 비용·리전(국내) 비교. 단일 인스턴스 정책은 유지. |

**가드레일** — 재평가 결과 어떤 스택이 선정되더라도 SDD §5.1의 모듈 간 인터페이스 계약(공통 판단 스키마, CompletionDecision, RuleEvalResult, EstimateResult)은 **그대로 유지**한다. 인터페이스가 안정되면 내부 구현·언어·프레임워크는 자유롭다.

---

## 7. 팀 편성 권고 (CTO에게)

리포팅 라인을 단순화하기 위해 CTO 하위 디렉터 중 다음 6개 라인을 본 프로젝트에 활성화할 것을 권한다.

| 라인 | 담당 | 본 이슈(CMP-523) 기여 | 후속 단계 기여 |
|---|---|---|---|
| **Architecture Lead** (8c65d6c0) | 모노레포 구조·공통 컨트랙트(공통 판단 스키마·CompletionDecision) ADR | D1, D4 인터페이스 정의 | 모든 모듈 경계 가드 |
| **Backend Lead** (1e359a75) → Python Backend Engineer | FastAPI/대안 골격, Neon 연결, 표준 에러·로깅, JWT 미들웨어 | D3, D4(a~e) | AUTH/INPUT/MASK/CHAT/RULE/REPORT |
| **Frontend Lead** (60ef2b0f) → React Engineer | Next.js (또는 대안) 골격, A2UI 컴포넌트 베이스, 인증 인터셉터 | D1, D4 | OVERLAY/CHAT/REPORT UI |
| **Data Lead** (5bdb41f8) → AI Engineer + ML Engineer | AI 모델 후보 비교(T6), LangChain 추상층, Mask2Former 부트 전략 | T6 사전 조사 | AI 파이프라인 |
| **Infrastructure Lead** (1e1a5fed) → Cloud Engineer | 클라우드 비교(T7, D6), 단일 인스턴스 운영 모델 | D6, docker-compose 시안 | 운영·스케일 |
| **DevOps Lead** (e5b2ebe1) → DevOps Engineer | gitmoji·GitHub Flow 자동화(commit lint), CI 스켈레톤, `.env.example`, 시크릿 관리 | D2, D5 | CI/CD·배포 자동화 |
| **Security Lead** (76b858f5) → Security Engineer | 시크릿 헌팅, OAuth/PII/암호화 정책 가드 | 자격증명 회전 검토 | 보안 리뷰 |
| **QA Lead** (8b401f56) → Test Engineer | 테스트 피라미드 설계, 결정성 테스트(NFR-QUAL-002) 프레임 | D4 테스트 골격 | 회귀·룰셋 검증 |

> Database Engineer(6e289f8a)는 후속 이슈("도면 DB 마이그레이션·인덱스 설계")에서 합류.

---

## 8. 위험·열린 질문

| ID | 항목 | 영향 | 권고 |
|---|---|---|---|
| R1 | 명세 비밀번호(Neon, OpenAI 등)가 이슈 본문 평문 노출 | 자격증명 유출 위험 | Neon DB 비밀번호 즉시 회전 + 향후 `paperclip.local` 또는 시크릿 매니저 경유 |
| R2 | 클라우드 미정 | D6 비용 비교 결과에 따라 docker-compose 구성·CI 배포 타깃 변화 | 이번 이슈에선 **로컬 + Neon** 만 동작 보장, 배포 타깃은 후속 이슈 |
| R3 | Mask2Former 메모리(워커 부팅 1회 로드) | 단일 인스턴스 GPU/메모리 요건이 클라우드 비용을 좌우 | T6 결정 시 모델 풋프린트 측정 |
| R4 | 명세서 v1.6의 `gpt-5.4-mini` 등 가공의 모델명 | 실제 OpenAI 라인업과 매핑 필요 | CTO·AI Engineer가 "현행 가용 모델"로 치환 |
| R5 | 단일 인스턴스 + AI 동기 처리의 동시 30세션 부하 | NFR-PERF 미달 가능성 | 부하 테스트 후속 이슈로 |

---

## 9. 하이레벨 마일스톤 (CTO 확정 대상)

1. **M0 — 기본 세팅 (CMP-523, 본 이슈)**: D1~D6
2. **M1 — AUTH/INPUT/CHAT 셸**: 로그인 → 주소 입력 → 빈 채팅 세션까지 동작
3. **M2 — MASK/AI/OVERLAY 파이프라인**: 모델은 mock → 실모델 단계적 교체
4. **M3 — RULE/REPORT + FLOW_GUARD**: 결정성 100% 룰 골격
5. **M4 — 관리자·리드 백오피스 / KPI**
6. **M5 — 외부 연동(세움터·견적·학습 환류)**

---

## 10. 본 이슈의 종결 조건 (CEO 확인 포인트)

D1~D6 인도물이 모두 `main`에 머지되고 다음이 모두 참이면 본 이슈를 종결한다.
- [ ] `docker compose up` 으로 web·api·redis 부팅 + `/healthz` 200
- [ ] `/healthz` 가 Neon Postgres `SELECT 1` 결과를 포함
- [ ] `README.md` 만 보고 신규 개발자가 30분 내 로컬 부팅 가능
- [ ] `AGENTS.md` 가 본 브리프의 팀 라인과 일치하고, 각 에이전트가 자신의 트리거 조건을 알 수 있음
- [ ] `.gitignore` 가 `.env`·`__pycache__/`·`node_modules/`·`.next/`·모델 가중치 디렉터리를 모두 차단
- [ ] gitmoji + GitHub Flow 정책 문서가 루트에 존재 (`docs/CONTRIBUTING.md` 권장)
- [ ] CTO 산출물(ADR · 구현 계획)이 자식 이슈로 연결되어 있음

---

## 11. 하드 핸드오프

본 브리프는 요구사항 합의 기준선이다. 이 시점부터 **기술 결정·구현 분해·자식 이슈 생성은 CTO 권한**이다. CEO는 본 문서를 봉인하고, 본 이슈는 CTO에게 인계한다. 변경이 필요하면 CEO가 새 브리프 리비전을 발행한다.
