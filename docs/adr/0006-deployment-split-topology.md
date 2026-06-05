# ADR 0006 — 배포 아키텍처 재편: 분리형 토폴로지 (Vercel + Fly.io + Upstash)

- 상태: **Proposed (2026-06-05)** — 오너(CEO) 최종 "Fly 채택" 결정 시 Accepted.
- 제안자: 프로젝트 오너 (rpdla1456) — 본 대화에서 직접 토폴로지 전환을 주도.
- 승인 권자: 오너(CEO) — 단일 GitHub 계정 + base branch 보호 정책상 사람만 머지 (project_jippin_pr_merge_human_only).
- 슈퍼시드: **[`ADR-0002`](0002-deployment-cloud.md) (AWS Lightsail Seoul) 를 supersede.** [`ADR-0001`](0001-stack-reevaluation.md) §8 "단일 인스턴스 + docker-compose" 가정을 **production 토폴로지 한정으로 개정**(로컬 개발 compose 는 불변).
- 인계 출처: 본 ADR 의 직전 토론(웹/리서치 기반 비용·리전 비교), [`docs/runbooks/cloud-comparison.md`](../runbooks/cloud-comparison.md) (CMP-532 D6 비교 메모), 실행 런북 [`docs/runbooks/fly-api-deploy.md`](../runbooks/fly-api-deploy.md).
- 강한 제약 (불변):
  - 외부 의존(Supabase Postgres / Cloudflare R2 / OpenAI / Hugging Face) 그대로.
  - DB / Auth 정본은 Supabase ([`ADR-0004`](0004-supabase-transition.md)).
  - 결과 화면 법적 고지 문구.

---

## 0. 결정 요약 (TL;DR)

ADR-0002 는 "**단일 VM 1대에 web+api+redis 를 docker-compose 로 올린다**"는 ADR-0001 §8 봉인을 전제로 AWS Lightsail Seoul($84/mo)을 골랐고, 그 전제 때문에 Fly.io 와 분리형 PaaS 를 명시적으로 **컷**했다. 본 ADR 은 **그 전제 자체를 바꾼다.**

| 티어 | ADR-0002 (이전) | **ADR-0006 (본 결정)** |
|---|---|---|
| **web** | 단일 VM 내 컨테이너 | **Vercel Pro** (`apps/web`, `jippin.ai` + `www`) |
| **api** | 단일 VM 내 컨테이너 | **Fly.io 도쿄(`nrt`)** 단일 Machine, 1 vCPU / 1 GB (`apps/api`, `api.jippin.ai`) |
| **redis** | 단일 VM 내 컨테이너 (SPOF) | **Upstash Redis 도쿄(`ap-northeast-1`)** — managed, SPOF 제거 |
| **postgres** | 외부 Supabase | 외부 Supabase (불변, ADR-0004) |
| **object storage** | 외부 R2 | 외부 R2 (불변) |
| **도면 추론** | (MVP) 컴퓨트 CPU fallback / (P1) AWS g5 GPU | **Hugging Face Inference Endpoint** 로 offload |
| **클라우드 리전** | 서울 1대 | api·redis 도쿄 코로케이션 + web Vercel edge |
| **월 비용(저트래픽 MVP)** | $84 고정 | **~$26 – $32** |

> ⚠ **Proposed 상태**: 오너가 "Fly 채택"을 확정하면 Accepted. 확정 전 §7 Open Questions(특히 HF 엔드포인트 비용/지연, Upstash free tier 충분성) 은 측정 권고. Accepted 시 ADR-0002 는 Superseded, AGENTS.md §2 클라우드 줄은 본 ADR 을 가리키도록 갱신한다.

---

## 1. 왜 지금 전환이 정합적인가 — 린치핀은 "추론 offload"

ADR-0002 의 단일 VM / 서울 / 4 vCPU·16 GB 선택은 **두 가지 가정**에 매여 있었다:

1. **컴퓨트가 무거운 ML 추론을 직접 돌린다** (Mask2Former / SAM2 CPU fallback, P1 에서 GPU). → 그래서 16 GB·서울·AWS 계정 내 g5 마이그레이션 라인이 필요했다 (ADR-0002 §4).
2. **단일 인스턴스 + docker-compose** (ADR-0001 §8 봉인). → 그래서 컨테이너 1개씩 분리되는 PaaS·Fly 는 "정합 ❌"로 컷됐다 (ADR-0002 §2.3).

본 ADR 은 이 두 가정을 모두 해소한다:

- **추론을 Hugging Face Inference Endpoint 로 offload** → 컴퓨트에 GPU/대용량 RAM 이 필요 없다. AWS 계정 내 g5 마이그레이션 라인(ADR-0002 §4.2 Step 2)이라는 Lightsail 선택의 핵심 명분이 사라진다.
- **이미지 바이트는 presigned R2 URL 로 직행** ([`apps/api/src/schemas/floorplans.py`](../../apps/api/src/schemas/floorplans.py) 의 `floorplan_assets` = R2/S3 object metadata, 업로드 라우터는 메타데이터 row 만 생성). HF 호출도 이미지 **URL 만 전달**하고 바이트를 forward 하지 않는다. → api 는 순수 I/O 게이트웨이(JSON in/out + DB + Redis + HF URL 전달)이며 **1 vCPU / 1 GB 로 충분**(워커 2개 ≈ 400–500 MB RSS, 500 MB 헤드룸).
- **단일 인스턴스 가정 폐기**는 의도된 것이다. 본 결정의 목적이 곧 그 폐기다. 단, **production 토폴로지에 한정**한다 — 로컬 개발은 [`infra/compose/docker-compose.yml`](../../infra/compose/docker-compose.yml) 의 web+api+redis 3-컨테이너 그대로 유지한다.

## 2. 결정 — 분리형 토폴로지

```
┌──────────────────────────┐
│  jippin.ai / www          │  Vercel Pro · jippin-web (apps/web)
│  Next.js 16 (edge CDN/SSR)│  SSL 자동, monorepo Root Directory = apps/web
└────────────┬─────────────┘
             │ next.config rewrites: /api/:path* → https://api.jippin.ai/:path*
             │ (same-origin 유지 — 코드 변경 0, env API_INTERNAL_BASE_URL 만 세팅)
             ▼
┌──────────────────────────┐
│  api.jippin.ai            │  Fly.io 도쿄(nrt) · 단일 Machine 1c/1GB
│  FastAPI (gunicorn+uvicorn)│  apps/api/Dockerfile 그대로, rolling deploy 기본
└──────┬───────────┬───────┘
       │           │ <5ms (동일 도쿄 리전 코로케이션)
       ▼           ▼
┌──────────┐  ┌──────────────────┐
│ Supabase │  │ Upstash Redis     │  도쿄(ap-northeast-1)
│ Postgres │  │ (OAuth state +    │  Vercel Marketplace 또는 직접 계정
│ (ap-ne-2)│  │  세션/캐시)        │
└──────────┘  └──────────────────┘
       ▲
       │ presigned URL (이미지 바이트 — api 미경유)
┌──────┴───────┐        ┌─────────────────────────┐
│ Cloudflare R2 │ ─URL→ │ Hugging Face Inference   │
│ (도면 원본)    │        │ Endpoint (도면 추론)      │
└───────────────┘        └─────────────────────────┘
```

### 2.1 리전 결정 — 왜 도쿄인가 (서울이 아니라)

검증 결과(2026-06-05):

- **Fly.io 는 서울(ICN) 리전이 없다.** APAC 은 도쿄(`nrt`)·싱가포르(`sin`)·뭄바이(`bom`)·시드니(`syd`). 최근접 = 도쿄(한국에서 ~30–40 ms). 출처: [Fly.io Regions](https://fly.io/docs/reference/regions/).
- **Upstash Redis 도 서울이 없다.** APAC 은 도쿄(`ap-northeast-1`)·싱가포르·시드니. 최근접 = 도쿄. 출처: [Upstash regions](https://upstash.com/docs/devops/developer-api/redis/update_regions).

핵심 지연 경로는 **user↔api 가 아니라 api↔redis** 다. OAuth Authorization Code Flow 의 `state`/`nonce`/`code_verifier` 는 콜백 1회당 Redis 를 여러 번 친다 (AGENTS.md §5.9 item 10, ≤10분 TTL). 이 경로를 같은 리전에 두는 것이 우선이다.

| 배치 | api↔redis | user(KR)→api | 평가 |
|---|---|---|---|
| **Fly 도쿄 + Upstash 도쿄** | **<5 ms (코로케이션)** | ~30–40 ms | ✅ 본 결정 |
| Lightsail 서울 + Upstash 도쿄 | ~30 ms (콜백마다) | 5–15 ms | ❌ 콜백 지연 누적 |
| Cloud Run 서울 + Upstash 도쿄 | ~30 ms + 콜드스타트 | 5–15 ms | ❌ 코로케이션 깨짐 + scale-to-zero UX |

→ Upstash 가 도쿄뿐이므로 **api 도 도쿄에 두는 것이 코로케이션상 최적**이다. user→api 의 +30 ms 는 무거운 자산(도면·리포트)을 R2 와 Vercel edge 가 흡수하고 api 응답은 JSON 이라 체감이 작다.

### 2.2 사유 (ADR-0001 §1.3 가중치 적용)

- **#2 비용**: ~$26–32/mo 로 Lightsail $84 대비 저렴. redis 가 managed 로 빠져 VM 운영·snapshot 부담 0.
- **#1 한국 운영성**: 실 PII 는 Supabase 서울(`ap-northeast-2`)에 거주. Redis 는 ≤10분 만료 OAuth state 만 도쿄에 잔류 — PII 민감도 낮음. (단 §7 Q4 법무 확인 권고.)
- **#3 컨트랙트 친화성**: api Docker 이미지([`apps/api/Dockerfile`](../../apps/api/Dockerfile)) 그대로 Fly 에 배포 — 런타임 호환 검증 부담 0. web 은 Vercel 의 monorepo Root Directory 로 독립 배포.
- **#4 MVP 시간**: web 은 git push 즉시 배포(가장 빠른 dev cycle). api 는 `fly deploy` 1회. Fly 의 rolling deploy 가 기본이라 무중단 배포가 공짜로 따라옴(오너는 다운타임 수용 의사였으나 손해 볼 것 없음).
- **redis SPOF 제거**: 이전 토폴로지에서 redis 는 단일 VM 위 AOF 였다([`docker-compose.yml`](../../infra/compose/docker-compose.yml) `redis-data` 볼륨). VM 사망 시 OAuth state·세션 손실. managed 로 분리되어 이 시나리오가 소멸.

### 2.3 이전 ADR-0002 의 Fly.io 컷 사유 재검토

| ADR-0002 §2.3 의 Fly 컷 사유 | 본 ADR 의 해소 |
|---|---|
| "단일 인스턴스 + docker-compose 정책과 결제 모델 비정합" | 단일 인스턴스 정책 자체를 폐기. Fly 에는 **api 단일 서비스 1개**만 올린다(머신 sprawl 아님) → 정합. |
| "GPU 라인업 EOL 2026-08-01" | 추론을 HF 로 offload → 우리 컴퓨트에 GPU 불필요 → 무관. |
| "도쿄(nrt), 한국 거주 ❌" | 실 PII 는 Supabase 서울. redis OAuth state(≤10분)만 도쿄. 수용. |

## 3. 비용 (월 / 저트래픽 MVP: ~10K 방문, ~50K API 요청, ~100K redis ops)

| 항목 | 비용 | 비고 |
|---|---|---|
| Vercel Pro (1 seat) | $20 | $20 usage credit 포함, 1 TB 전송/10M edge req 안 |
| Fly.io 도쿄 1c/1GB (always-on) | ~$5–6 | shared-cpu-1x 1GB |
| Upstash Redis (도쿄) | $0 | free 256 MB / 500K cmd·월 (OAuth state TTL 짧아 free 안 가능성 높음) |
| **합계** | **~$26** | + HF 엔드포인트 비용(별도, §7 Q1) |

ADR-0002 Lightsail $84 대비 약 1/3. 단 HF Inference Endpoint 가 always-on dedicated 면 별도 비용이 추가되므로 §7 Q1 에서 측정 필요(scale-to-zero serverless 옵션이면 저트래픽 거의 무료).

## 4. 운영 모델

- **배포**: web = Vercel git integration(`dev`/`main` push → 자동). api = `fly deploy`(GitHub Action 자동화 권고, §실행 런북). DB 마이그레이션은 본 ADR 과 독립이며 **Supabase GitHub Integration**(`supabase/migrations/*.sql`, `dev`→development / `main`→production 자동 적용)이 forward SSOT 다. `.github/workflows/deploy.yml` 은 빌드/배포 스텁이며 **마이그레이션을 실행하지 않는다**(CMP-603 cutover). Alembic 은 historical reference.
- **시크릿**: web = Vercel Project env. api = `fly secrets`. 로컬 = `infra/compose/.env` (불변, AGENTS.md §4.4).
- **모니터링**: Vercel Analytics(web) + Fly metrics/logs(api) + Upstash 콘솔(redis) + Supabase 대시보드(db). 4면 분산은 트레이드오프(§5).
- **무중단 배포**: Fly rolling deploy 기본. Redis·VM SPOF 가 제거되어 api 재배포가 상태 손실 없이 진행.

## 5. 결과 (Consequences)

**긍정**
- redis SPOF 제거, 비용 ↓($84→$26), web dev cycle 최단, api Docker 자산 100% 재활용, 무중단 배포 기본.

**부정 / 이월 리스크**
- **인프라 컴포넌트 4면(Vercel·Fly·Upstash·Supabase) 분산** → 모니터링·과금처·장애 추적 분산.
- **서울 리전 상실** → KR user→api +30–40 ms (경감: R2/edge 흡수).
- **CSAP / ISMS-P 경로 상실** — Lightsail/NHN/NCP 의 한국 사업자성·정부등급 라인이 사라진다. 공공·지자체 협업이나 KISA 의무가 발생하면 ADR-0002 의 **Plan C (NHN/NCP)** 로 회귀하는 별도 ADR 필요.
- **Vercel/Fly 종속** — Vercel 빌드·Fly Machine 규약. lock-in 은 낮음(둘 다 표준 Next.js/Docker)이나 0은 아님.

## 6. 변경·회귀 트리거

- 오너가 "Fly 채택" 확정 → `Status: Accepted`, ADR-0002 Superseded, AGENTS.md §2 갱신.
- **회귀 트리거**: (a) CSAP/ISMS-P 의무 발생, (b) HF 엔드포인트 비용이 자체 GPU 보다 비효율로 판명(P1), (c) 도쿄 지연이 사용자 이탈로 측정됨 → 각각 별도 ADR 로 ADR-0002 계열(서울 VM) 또는 P1 GPU 라인 재평가.

## 7. Open Questions (Accepted 전 측정 권고)

| # | 항목 | 차단 여부 | 책임 |
|---|---|---|---|
| Q1 | HF Inference Endpoint 리전/지연/비용 (serverless vs dedicated) | 🟡 비용 산정 차단 | 오너 / AI |
| Q2 | Vercel Pro seat·사용량이 저트래픽서 $20 안 유지되는지 | ⚪ | 오너 |
| Q3 | Upstash free tier(500K cmd) 가 OAuth+세션 부하 견디는지 | ⚪ | 오너 |
| Q4 | redis 도쿄 잔류 OAuth state 의 PII 법무 검토 (≤10분 TTL) | 🟡 법무 | 오너 / 법무 |
| Q5 | Fly 도쿄 capacity / 단일 머신 SLA 수용 여부 | ⚪ | 오너 |

## 8. 결정 트레일

| 시각 | 행위자 | 행위 |
|---|---|---|
| 2026-06-05 | 프로젝트 오너 (rpdla1456) | 분리형 토폴로지 토론·리전 검증 후 본 ADR-0006 `Proposed` 발행. ADR-0002 supersede 예고. |
| _pending_ | 오너(CEO) | "Fly 채택" 확정 시 `Accepted`. |

— 끝 —
