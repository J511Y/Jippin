# 클라우드 후보 비교 메모 (D6)

- 작성자: Cloud Engineer (Infrastructure Lead 가드, agent `575b4fb8`)
- 작성일: 2026-05-28
- 관련 이슈: **CMP-532** (`[Infra] 클라우드 후보 비용·리전 비교 메모 (D6) — 비교 전용`)
- 부모 결정 문서: `docs/brief/CEO_PROJECT_BRIEF.md` §2 D6 · `docs/adr/0001-stack-reevaluation.md` §8
- 본 문서 위치: ADR-0001 §9.2 디렉터리 봉인의 `docs/runbooks/` 에 둔다.
- **본 메모는 의사결정 문서가 아니다. 비교 자료만 제공한다.**
  - 1~3순위 후보는 CTO에게 인계.
  - 최종 클라우드 선정은 별도 **ADR-0002** 가 봉인한다.

---

## 0. 한 줄 요약

> 단일 인스턴스(MVP 30세션) · 한국 리전 1순위 · GPU는 후속(MASK CPU 가능 가정) · 사용자 egress는 R2(Cloudflare)가 흡수 → **컴퓨트 비용·한국 운영성·결제 단순성**이 결정의 3대 축. 가격만 보면 Hetzner Singapore(€51~97/mo)가 최저이나 리전 거리 75~95ms로 ADR-0001 §1.3 평가 기준 #1(한국 운영 가능성)에서 감점. **GCP Compute Engine `asia-northeast3` · AWS Lightsail Seoul · NHN Cloud** 3개를 균형 후보로 제시한다.

---

## 1. 비교 전제

### 1.1 워크로드 가정 (ADR-0001 §1.3 운영 가정 그대로)

- 단일 인스턴스, `docker-compose` 부팅 (web · api · redis 3개 컨테이너).
- 동시 세션: **MVP 30세션 / P1 200세션**.
- DB는 **Neon Postgres** (외부, `ap-southeast-1` Singapore 호스트 — `DATABASE_URL` 명세 §5.1) — 모든 후보에서 인터넷 경유 동일.
- 객체 스토리지는 **Cloudflare R2** (외부, zero-egress) — 사용자 도면 재다운로드 트래픽은 클라우드 컴퓨트 egress를 거치지 않는다.
- AI 모델 풋프린트 (ADR-0001 §7.4 미확정):
  - **Mask2Former-Swin-Large**: 약 4.5 GB VRAM / CPU fallback 시 4 vCPU · 12~16 GB RAM에서 추론 가능하나 1회 1~3분.
  - **SAM2 (Hiera-Large)**: 약 3 GB VRAM / CPU fallback 가능, prompt 1회 5~20s.
  - **MVP 정책**: CPU 기준선. GPU는 P1에서 재평가.

### 1.2 평가 차원 (ADR-0001 §1.3 가중치 그대로 적용)

| # | 차원 | 가중치 시그널 |
|---|---|---|
| 1 | **한국 리전 / latency** | 1순위. 한국어 PII 거주·법적 고지 서비스. |
| 2 | **단일 인스턴스 컴퓨트 가격 (4c/16, 8c/32)** | 무료 B2C 모델 → 매월 비용이 그대로 손익. |
| 3 | **인터넷 egress 가격 / 무료 한도** | 1차로는 R2 흡수, 그러나 API JSON / OG 미리보기 / 헬스체크 / 로그 송출 트래픽은 컴퓨트 측에서 나감. |
| 4 | **GPU 옵션** | MVP 미사용. P1 GPU 도입 시 동일 사업자 내 전환이 가능한가? |
| 5 | **요금제 모델 / 청구 단위** | 시간당 vs 월정액, 정지(stopped) 시 과금, 1년 commit 할인. |
| 6 | **한국어 지원 / 데이터 거주 / SLA** | 비전문 사용자 B2C·정부 고시 서비스 → 한국 사업자성 + CSAP / ISMS-P 우대. |
| 7 | **SSD 블록 스토리지 단가** | 도면 캐시·로그 디스크. 후보 간 차이 작음. |
| 8 | **운영 부담 / 마이그레이션 회피성** | docker-compose 이식성 보장 + lock-in 회피. |

### 1.3 단일 인스턴스 + R2 + Neon 토폴로지에서의 트래픽 모델

```
사용자 ──▶ Cloudflare R2 (도면·오버레이·리포트 다운로드)        // egress = 0
                ▲
                │ presigned URL
                │
사용자 ──▶ [컴퓨트 1대]
            ├─ web (Next.js)        : HTML / RSC / 채팅 스트림  ← 컴퓨트 egress
            ├─ api (FastAPI)        : JSON 응답                ← 컴퓨트 egress
            └─ redis
                │
                ├──▶ Neon Postgres (Singapore)     // 외부 호출
                └──▶ OpenAI (gpt-5.4-mini / gpt-5.5) // 외부 호출
```

- **컴퓨트 측 egress 예상**: 30세션 · 1세션 ≈ 500KB JSON/HTML + 1MB OG/메타 = 약 **45MB/일/세션** → 30세션 활성 30일 ≈ **40~60 GB/월**.
- 사용자 도면·리포트(수~수십 MB)는 R2에서 직빨 → 컴퓨트 egress 무관.
- **결론**: 컴퓨트 egress 비용은 MVP 단계에서 월 $5~10 이하. 무료 한도가 큰 사업자(Lightsail 6TB, Hetzner 0.5~8TB, Fly.io 저단가)는 사실상 동등. P1(200세션) 진입 후 재계산.

---

## 2. 비교표

### 2.1 핵심 비교 (모든 가격 USD, 2026-05 기준)

| 사업자 | 한국 리전 | 4 vCPU/16 GB ($/mo, on-demand) | 8 vCPU/32 GB ($/mo) | egress | 무료 egress | GPU 동일 리전 | 한국어 지원·거주 | SSD $/GB-mo | 출처 |
|---|---|---|---|---|---|---|---|---|---|
| **GCP Compute Engine** | ✅ `asia-northeast3` Seoul | $125.51 (`e2-standard-4`) | $251.02 (`e2-standard-8`) | $0.08~0.12/GB | 200 GB/mo 공통 | ✅ L4 (`g2-standard-8`) $800/mo · T4(`n1` + add-on) ~$330~380 | ✅ 한국어 유료 서포트 / Seoul 3-zone 거주 / SLA 99.99% | $0.221 (pd-ssd) | [GCP Seoul aggregated](https://gcloud-compute.com/asia-northeast3.html), [GCP network pricing](https://cloud.google.com/vpc/network-pricing) |
| **AWS EC2 Seoul** | ✅ `ap-northeast-2` | $180.89 (`m7i.xlarge`) · $151.84 (`t3.xlarge` 버스트) | $361.79 (`m7i.2xlarge`) | ~$0.126/GB (1차 10TB) | 100 GB/mo 공통 | ✅ `g5.xlarge` (A10G) $903/mo | ✅ Business/Enterprise 플랜 한국어 / Seoul 4-AZ 거주 / 99.99% | ~$0.0912 (gp3, 추정) | [AWS m7i.xlarge Seoul](https://aws-pricing.com/m7i.xlarge.html), [AWS EC2 on-demand](https://aws.amazon.com/ec2/pricing/on-demand/) |
| **AWS Lightsail Seoul** | ✅ `ap-northeast-2` | **$84** (4c/16/320GB SSD/6TB egress 번들) | **$164** (8c/32/640GB SSD/7TB egress) | 번들, 초과 ~$0.09/GB | **6~7 TB/mo 번들** | ❌ Lightsail 자체 GPU 없음. 동일 계정 EC2 전환 가능. | ✅ 동일 (AWS 계정 공유) / 거주 동일 | 디스크 번들 | [AWS Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) |
| **Naver Cloud Platform** | ✅ KR-1 Pangyo · KR-2 | ~₩124~127k/mo (**~$90~92**) | ~₩250~260k/mo (**~$181~188**, 선형 추정) | ~₩100/GB (**~$0.072**) | 없음 | ✅ T4 / V100 / A100 / H100. T4 시간당 ~₩2,000~2,400 (~$1.45~1.74/hr) `~estimated` | ✅ 네이티브 한국어·법인 계약·KISA/ISMS-P · 99.95% | ~$0.072 (블록 SSD) `~estimated` | [NCP pricing](https://www.ncloud.com/charge/pricing), [4vCPU/16GB 한국 VPS 비교](https://picory.com) |
| **KT Cloud** | ✅ Seoul / 천안 / 김해 DC (CSAP gov) | ₩220k~300k/mo 밴드 (**~$160~217**) `~estimated` (G2 Standard Memory) | ₩440k~600k/mo 밴드 (**~$320~435**) `~estimated` | 초과 ~₩70~90/GB (~$0.05~0.065) | **VM당 1~2 TB/mo 무료** | ✅ T4 / A100 / H100 (가격 비공개·견적) | ✅ KT 통신사 한국어 / 한국 거주 / **CSAP 정부등급** / 99.9~99.95% | ~$0.058~0.072 `~estimated` | [KT Cloud product](https://cloud.kt.com), [KT 표준 SKU 가격 listing](https://www.ncloud24.com/index.php/ktcloud/server) |
| **NHN Cloud** | ✅ KR1 Pangyo · KR2 Pyeongchon · KR3 Gwangju | ₩192,720/mo (**~$140**, `m2.c4m16`) | ~₩385,440/mo (**~$279**, `m2.c8m32`, 선형 추정) | ~₩100/GB (**~$0.072**) | 없음 | ✅ T4 / V100 / A100 (가격 calculator 게이트) | ✅ NHN 한국어 / 한국 거주 / **CSAP** 라인 / 99.95% / **정지 시 90일간 90% 할인** | ~$0.072 `~estimated` | [NHN Cloud pricing](https://www.nhncloud.com/kr/pricing/m-content?c=Compute&s=Instance), [NHN instance 개요](https://docs.nhncloud.com/ko/Compute/Instance/ko/overview/) |
| **Hetzner Cloud** | ❌ Singapore `sin` (Seoul→SIN ~75~95ms) | **€51.49 (~$56)** `CCX23` 전용 vCPU | **€96.99 (~$105)** `CCX33` 전용 vCPU | 초과 €7.40/TB (**~$0.008/GB**) | **0.5~8 TB/mo 서버별 번들** | ❌ Hetzner Cloud는 GPU 없음 (Hetzner Robot 별도) | ❌ 독/영 only / EU 본사 / 컴퓨트 SLA 명문 없음, 네트워크 99.9% | €0.05/GB (~$0.054, 추가 볼륨) | [Hetzner 2026 price adjustment (Singapore)](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/), [Hetzner regular performance](https://www.hetzner.com/cloud/regular-performance) |
| **Fly.io Machines** | ❌ `nrt` Tokyo (Seoul→NRT ~30~40ms) | $170.33 (`performance-4x` 16GB) · $253.45 (`performance-4x` 32GB) | $506.90 (`performance-8x` 32GB) | $0.02/GB (APAC) | 없음, 단가 매우 낮음 | ❌ **GPU EOL 발표 (Aug 1)** | ❌ 영문 only / 한국 거주 ❌ / **단일 머신 공식 SLA 없음** | $0.15/GB (Fly Volumes) | [Fly.io pricing](https://fly.io/docs/about/pricing/) |

> **데이터 품질 주의**
> - 한국 사업자(NCP / KT / NHN) 가격은 공개 페이지가 calculator-gated 되어 있어 일부 SKU·GPU 가격은 한국 블로그·디스트리뷰터 listing 으로 교차 확인했다. `~estimated` 표시 셀은 ADR-0002 확정 전 영업 견적으로 재검증해야 한다.
> - Fly.io GPU는 2026-08-01 EOL — GPU 후보로 보지 않는다.
> - AWS Lightsail은 EC2 동일 계정 내 전환이 가능하므로 "Lightsail → EC2 GPU"는 운영 라인이 끊기지 않는다.

### 2.2 1년 약정·정지(stopped) 시 과금

| 사업자 | 1년 commit 할인 | 정지 시 청구 | 비고 |
|---|---|---|---|
| GCP CE | 약 37% (Committed Use Discount, 3년 ~55%) + 자동 SUD | 디스크만 청구 | 단일 인스턴스 강한 정합 |
| AWS EC2 | Savings Plans 1-yr no-upfront ~28~30%, all-upfront ~37~40% | EBS만 청구 | 약정 계좌 단위 |
| AWS Lightsail | 약정 없음 | 정지 불가(고정 월정액) | 단순함 |
| NCP | 월정액(평정) / 1년 약정 ~10~15% | 정지 시 인스턴스 base 계속 청구 | |
| KT Cloud | 연 약정 협상가 (공시 X) | 정지해도 청구 (삭제만 중단) | |
| NHN Cloud | 연 약정 협상가 (공시 X) | **정지 시 첫 90일 90% 할인**, 이후 정상 청구 | MVP에 친화적 |
| Hetzner | 약정 없음, 시간당·**월 상한 자동 적용** | 정지해도 청구(자원 점유) | |
| Fly.io | 약정 없음 | **정지하면 스토리지만 청구** ($0.15/GB-mo) | 사실상 scale-to-zero — 단, 본 ADR-0001 §8.1 "단일 인스턴스" 가정과 결제 모델이 어긋남 |

### 2.3 단순화한 월 손익 시나리오 (4 vCPU / 16 GB · 무료 사용자 1,000명 / 30세션 동시)

> ⚠ 환율 1,380 KRW/USD 가정. R2 / Neon / OpenAI 외부 비용은 별도. **컴퓨트 + 디스크 + egress + (선택) GPU 점유** 만 합산.

| 사업자 | 컴퓨트(4c/16) | + 200GB SSD | + 50GB egress | (GPU 미사용 가정) | **합계 USD/mo** |
|---|---:|---:|---:|---:|---:|
| **GCP CE** Seoul | $125.51 | $44.20 | $5 | 0 | **~$175** |
| **AWS EC2** Seoul (`t3.xlarge`) | $151.84 | ~$18.24 (gp3 200GB) | ~$6.30 | 0 | **~$176** |
| **AWS Lightsail** Seoul | $84 (320GB SSD + 6TB egress 번들) | (포함) | (포함, 한도 내) | 0 | **~$84** |
| **NCP** | ~$90 | ~$14 (200GB) | ~$3.60 | 0 | **~$108** |
| **KT Cloud** | ~$160 (밴드 중심) | ~$13 | ~$3.25 (1TB 무료 후 초과만) | 0 | **~$176** |
| **NHN Cloud** | ~$140 | ~$14 | ~$3.60 | 0 | **~$158** |
| **Hetzner Singapore** | $56 (CCX23) | $11 (200GB 추가 볼륨) | $0 (3TB 번들 한도 내) | 0 | **~$67** |
| **Fly.io NRT** | $170 (16GB) / $253 (32GB) | $30 (200GB) | $1 (50GB) | 0 | **~$201 / ~$284** |

---

## 3. 후보별 노트 — 가정·한계·리스크

### 3.1 GCP Compute Engine — `asia-northeast3` (Seoul)

- **장점**: ADR-0001 §8.1이 이미 "1순위 후보"로 명시. Seoul 3-zone, 99.99% SLA, 한국어 유료 서포트. GPU(L4 / T4) 동일 리전 보유 → P1 GPU 도입 시 인스턴스 라인업만 교체. 분당 청구 + 자동 SUD.
- **단점**: 4c/16 $125.51 / 8c/32 $251.02 — 한국 사업자보다 30~40% 비쌈. egress $0.08~0.12/GB로 R2 사용 가정에서도 P1 200세션에서 의미 있는 비용. **결제는 USD 신용카드 (한국 법인 청구서 어려움)**.
- **리스크**:
  - 결제 통화·세무: 한국 부가세 처리 별도(VAT invoice).
  - "단일 인스턴스 + docker-compose" 정책과 정합하나, 자동확장(MIG)·k8s(GKE) 유혹 → ADR-0001 §8.1 봉인 위배 가능. **사용 가이드라인을 ADR-0002에 명시할 것**.
- **MVP 적합성**: ★★★★☆ (가격 빼면 만점).
- **P1 확장성**: ★★★★★ (GPU·k8s·Cloud SQL 전환 자유).

### 3.2 AWS EC2 — `ap-northeast-2` (Seoul)

- **장점**: 생태계·도구 풍부, Seoul 4-AZ, 99.99% SLA, g5 GPU(A10G) 동일 리전. Savings Plans 약정 시 ~30% 절감.
- **단점**: on-demand 가격 GCP보다 약간 비쌈(`m7i.xlarge` $180.89). egress $0.126/GB로 본 메모 후보 중 두 번째 고가. 또한 ADR-0001 §6.3에서 S3 종속을 명시 회피했으므로 **R2 정책과 충돌하지는 않으나 "왜 AWS인가" 명분이 약해진다**.
- **리스크**:
  - "EC2가 가장 익숙"이라는 디폴트 편향 — 본 메모는 그 편향을 배척.
  - VPC·보안그룹·IAM 학습 곡선이 docker-compose 단일 인스턴스에 비해 과대.
- **MVP 적합성**: ★★★☆☆ (over-engineered, 가격 메리트 부재).
- **P1 확장성**: ★★★★★.

### 3.3 AWS Lightsail — `ap-northeast-2` (Seoul) **★ 단순성 다크호스**

- **장점**: **월 $84 고정** (4c/16/320GB SSD/6TB egress 번들). MVP 단일 인스턴스·예측 가능한 비용 모델·콘솔이 매우 단순. EC2와 동일 AWS 계정 → P1에서 EC2/g5로 매끄러운 마이그레이션. Korea 거주·한국어 지원 동일.
- **단점**: GPU 직접 옵션 없음. 정지 불가(과금 계속). 일부 EC2 기능(VPC 세분화, 보안그룹 세밀화) 미지원 — 단, 본 ADR-0001 §1.3은 단일 인스턴스 가정이므로 무관.
- **리스크**:
  - P1 도달 직전 EC2 마이그레이션이 필요해진다 — **마이그레이션 시점·트리거를 ADR-0002에 명시**.
  - 6TB egress 번들이 P1 200세션 트래픽 + 도면 미리보기에서 부족할 수 있음 → 그때는 R2-우선 정책을 재확인.
- **MVP 적합성**: ★★★★★ (단순성·가격·한국 리전 3박자).
- **P1 확장성**: ★★★★☆ (EC2 마이그레이션 1회 필요).

### 3.4 Naver Cloud Platform — KR-1 Pangyo / KR-2

- **장점**: 네이티브 한국 사업자, 한국 법인 청구서·세금계산서, KISA·ISMS-P, 약 $90/mo (4c/16). GPU(T4/V100/A100/H100) 동일 리전.
- **단점**: 영문 문서·콘솔 UX 부족 — 자동화 에이전트(우리) 친화성 낮음. 공개 가격 페이지가 calculator-gated. terraform `nks` 프로바이더 성숙도 (cloud-init·snapshot 등) 검증 필요.
- **리스크**:
  - 자동화 에이전트가 콘솔 위주 API에서 실수할 가능성 → DevOps 부담 ↑.
  - GPU 도입 시 가격이 GCP·AWS 대비 비쌀 가능성(공시 가격 미상).
- **MVP 적합성**: ★★★★☆ (가격·한국성, IaC 미지수).
- **P1 확장성**: ★★★☆☆ (한국 내 확장은 유리, 다중 리전·해외 확장은 약함).

### 3.5 KT Cloud — Seoul / 천안 / 김해

- **장점**: KT 통신사 인프라, **CSAP 정부등급** 보유 — 행위허가·고시 데이터 다루는 본 서비스 성격과 정합. VM당 1~2 TB egress 무료.
- **단점**: 공개 가격 변동성 큼(밴드 $160~217), G1/G2 세대·표준/Memory SKU 혼재. **공개 SKU listing 신뢰도가 본 비교에서 가장 낮음** → 영업 견적 필요. terraform provider·API 친화성 미검증.
- **리스크**:
  - 공시 SKU·콘솔이 한국어 일색 → 자동화 친화성 ↓.
  - 가격이 본 메모에서 가장 변동성 크다 — **ADR-0002 전에 KT 영업견적 1회 필수**.
- **MVP 적합성**: ★★★☆☆ (CSAP 매력 vs 자동화·가격 불투명).
- **P1 확장성**: ★★★☆☆ (정부·B2B 라인업 확장은 강함).

### 3.6 NHN Cloud — KR1 / KR2 / KR3 **★ 정지 90일 90% 할인 다크호스**

- **장점**: 약 $140/mo (4c/16), 한국 거주, CSAP. **정지 시 첫 90일간 90% 할인** → MVP의 비활성 기간(주말·야간) 자동 절감 가능. terraform / openstack 호환 API.
- **단점**: 8c/32 가격이 calculator-gated. 한국 사업자 중에서는 NCP보다 약간 비쌈. GPU 가격 비공개.
- **리스크**:
  - 단일 인스턴스 정책과 "정지 후 재기동" 운영이 결합하면 부팅 latency·세션 손실이 사용자 경험에 영향. 결과적으로 docker-compose 풀스택 cold start ≈ 30~60s — **시연 모드에는 부적합**.
  - 90% 할인이 자동 적용된다고는 하나 SKU별 적용 조건 확인 필요.
- **MVP 적합성**: ★★★★☆ (한국성·CSAP·할인).
- **P1 확장성**: ★★★☆☆ (NCP와 동급).

### 3.7 Hetzner Cloud — Singapore `sin`

- **장점**: 압도적 가격 (CCX23 €51.49 = ~$56, CCX33 ~$105). egress 0.5~8 TB/서버 번들 + 초과 €7.40/TB로 후보 중 최저. 월 상한 자동 적용.
- **단점**: **한국 리전 없음** — 서울 → 싱가포르 75~95ms. 본 서비스는 채팅 + 도면 오버레이 인터랙션이 핵심이라 latency가 사용자 체감에 영향. 한국어 지원 ❌, 데이터 거주 ❌, **CSAP/ISMS 부재** — 행위허가·법령 검토 서비스의 신뢰도에서 약점. 컴퓨트 SLA 명문 없음. **GPU 없음** (Hetzner Cloud 라인업 한정).
- **리스크**:
  - ADR-0001 §1.3 평가 기준 #1(한국 운영 가능성) 핵심 감점 항목.
  - PII(주소·연락처) 데이터를 SG 리전에 두는 것에 대한 법무 검토 필요 — 본 메모에서는 권장하지 않는다.
- **MVP 적합성**: ★★☆☆☆ (가격 매력 vs 한국성 결손).
- **P1 확장성**: ★☆☆☆☆ (한국 GPU·CSAP 필요해지면 이주 비용 큼).

### 3.8 Fly.io Machines — `nrt` Tokyo

- **장점**: 도쿄 30~40ms로 latency 양호. 초당 청구 + scale-to-zero. egress $0.02/GB 매우 저렴.
- **단점**: ADR-0001 §8.1이 우려한 "단일 인스턴스 가정과 결제 모델 어긋남" — Fly의 Machine 모델은 다수 단일-목적 머신 + edge 분산이 디폴트. docker-compose 3-컨테이너 그대로 운영하기에 어색. **GPU EOL (2026-08-01)** — P1 GPU 옵션 부재. 한국 거주·한국어 지원 ❌. **단일 머신 공식 SLA 없음** (앱 단위 가용성은 multi-machine 가정).
- **리스크**:
  - 단일 인스턴스 + docker-compose 정책 위배 가능 — ADR-0001 §8.1 봉인.
  - GPU 라인업 단절로 P1 확장 시 사업자 변경 강제.
- **MVP 적합성**: ★★☆☆☆.
- **P1 확장성**: ★★☆☆☆.

---

## 4. CTO 인계 — 1·2·3순위 후보 추천 (ADR-0002 입력)

> **본 메모는 의사결정 문서가 아니다.** 아래는 §2 비교표와 §3 노트의 합산 결과를 ADR-0001 §1.3 가중치(한국성·비용·계약·MVP·유지보수)로 본 작성자 의견 순위이며, CTO는 ADR-0002에서 자유롭게 조정할 수 있다.

### 🥇 1순위 — **AWS Lightsail Seoul (`ap-northeast-2`)** *(MVP 한정 추천)*

- **이유**: $84/mo 고정·6TB egress 번들·한국 리전·단순한 콘솔이 ADR-0001 §1.3 가중치(#1 한국성 + #2 비용 + #4 MVP 시간)에 모두 최상위.
- **수반 조건 (ADR-0002에 봉인 권장)**:
  1. P1(200세션) 진입 또는 GPU 도입 시점에 **EC2 마이그레이션** — 동일 AWS 계정·VPC 라인업 보존.
  2. 6TB egress 번들 한도의 80%에 도달하면 **R2 라우팅 점검** 알림.
  3. KT Cloud / NHN Cloud 영업 견적이 Lightsail 가격을 하회할 경우 즉시 후보 재평가.

### 🥈 2순위 — **GCP Compute Engine `asia-northeast3`**

- **이유**: 한국성·SLA·GPU 라인업이 가장 균형. CTO가 "MVP부터 GPU 옵션을 동일 계정에 두고 시작하고 싶다" 또는 "Lightsail의 EC2 마이그레이션 비용을 피하고 싶다"고 판단하면 1순위.
- **수반 조건**:
  1. CUD 1년 약정 시점·할인율을 ADR-0002에 봉인.
  2. **MIG·GKE 사용 금지** — 단일 VM + docker-compose 정책 명문 유지.
  3. 한국 법인 결제·VAT 인보이스 절차 사전 정리.

### 🥉 3순위 — **NHN Cloud KR1 또는 Naver Cloud KR-1** *(한국 사업자 라인)*

- **이유**: CSAP·ISMS-P·한국어 지원·법인 청구서가 필요해지면(예: 공공·지자체 협업, 또는 KISA 권고 강한 적용) 이 두 사업자로 회귀. NHN의 **정지 90% 할인**이 단일 인스턴스 야간 절감에 유리.
- **수반 조건**:
  1. 8c/32 SKU·GPU·SSD 가격을 **ADR-0002 전에 영업 견적**으로 봉인. 본 메모의 추정치는 결정 입력으로 부족.
  2. terraform 등 IaC 호환성 — DevOps Engineer 검토 필요.
  3. KT Cloud는 **CSAP 정부등급이 결정적 요건이 되는 시점**에만 4순위로 부상.

### 비추천 (본 메모에서 컷)

- **Hetzner Singapore**: 가격 매력 큼에도 한국 리전·한국어·CSAP·SLA 결손이 §1.3 평가 기준 #1을 침범.
- **Fly.io NRT**: 단일 인스턴스 + docker-compose 정책과 결제 모델 비정합 + GPU EOL.
- **AWS EC2 단독**: Lightsail이 동일 계정 내 단순 대안이므로 MVP 단계에서 EC2 직접 채택의 메리트 없음. P1 마이그레이션 타깃으로만 보유.

---

## 5. 미해결 / ADR-0002 에서 확정해야 할 점

| # | 항목 | 부족한 데이터 | 책임 |
|---|---|---|---|
| Q1 | KT Cloud 표준 SKU 4c/16, 8c/32 영업 견적 | 공시값 신뢰도 낮음 | Cloud Engineer + DevOps Engineer |
| Q2 | NHN Cloud `m2.c8m32` 8c/32 정확 단가 | calculator-gated | Cloud Engineer |
| Q3 | NCP / KT / NHN GPU(T4·A100) 시간당 정가 | 공시 누락 | Data Lead (T6 GPU 옵션 결정과 연계) |
| Q4 | AWS Seoul gp3 정확 단가 | 메모에서 추정값 사용 | DevOps Engineer (Terraform 적용 시 verify) |
| Q5 | GCP Premium Tier egress Seoul-출발 표 정확 단가 | 공식 페이지 발췌 누락 | Cloud Engineer |
| Q6 | 한국 법인 결제 / VAT inv. 가능 사업자 매트릭스 | 본 메모 범위 외 | CEO / 재무 |
| Q7 | 단일 인스턴스 모델에서 latency 측정 (Seoul→SIN 75~95ms 가정) | 측정 부재 | DevOps Engineer (선정 후 PoC) |
| Q8 | MVP CPU 추론으로 Mask2Former 30세션 동시 부하 견딤 여부 | 미측정 — 후보 사양 결정에 영향 | Data Lead → AI/ML Engineer |

> **참고**: Q8이 "견디지 못한다"로 결론나면 본 메모의 1·2·3순위는 4 vCPU/16GB → 8 vCPU/32GB 또는 GPU 보유 사업자(GCP/AWS)로 재가중되어야 한다.

---

## 6. ADR-0001 §8 정합 확인

| ADR-0001 §8 봉인 사항 | 본 메모 정합 |
|---|---|
| 단일 인스턴스 + docker-compose 정책 유지 | ✅ 모든 후보를 1대 VM 기준으로 비교 |
| 클라우드 미확정 — D6 메모로 결정 위임 | ✅ 본 메모는 비교만 제공, 결정은 ADR-0002 |
| 1순위 후보군에 한국 리전 사업자 우선 | ✅ Lightsail·GCP Seoul·NHN·NCP 모두 한국·한국 인접 |
| §8.1 가설 가격 (`e2-standard-4` $80~120) | ⚠ 본 메모 측정 결과 $125.51 — 약간 상회. ADR-0001 §8.1 가격 가설 수치를 **§8.1 표 업데이트 또는 §8.3 재평가 트리거에 반영** 필요 (CTO 권한) |
| §8.2 vendor lock-in 미루는 비용 낮음 (Neon·R2·OpenAI 외부) | ✅ 모든 후보에서 동일 |

---

## 7. 변경 로그

| 시각 | 행위자 | 행위 |
|---|---|---|
| 2026-05-28 | Cloud Engineer (`575b4fb8`) | 초안 작성, CMP-532 인계 |

— 끝 —
