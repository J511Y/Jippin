# ADR 0002 — 배포 클라우드 선정

- 상태: **Proposed (2026-05-28)** — CEO 승인 시 Accepted.
- 제안자: Cloud Engineer (Infrastructure Lead 가드, agent `575b4fb8`)
- 승인 권자: CTO (`cto` / `4edca504`) — 본 ADR 검토 후 CEO 최종 승인.
- 인계 출처: `docs/runbooks/cloud-comparison.md` (CMP-532 D6 비교 메모) · `docs/adr/0001-stack-reevaluation.md` §8 (T7 — 클라우드 미확정)
- 관련 이슈: CMP-532 (`[Infra] 클라우드 후보 비용 비교 메모 (D6)`)
- 슈퍼시드: 없음. ADR-0001 §8 (T7 결정 보류)을 후속·확정한다.
- 강한 제약 (변경 금지 — ADR-0001 봉인 상속):
  - 단일 인스턴스 + `docker-compose` 정책 — multi-region / k8s / serverless 분산 금지.
  - 외부 의존 (Postgres / Cloudflare R2 / OpenAI) 그대로. **Postgres 호스팅 사업자는 [`ADR-0004`](0004-supabase-transition.md) 가 Neon → Supabase 전환을 진행 중** (Proposed). 본 ADR 의 “단일 인스턴스 앱 배포” 결정은 영향받지 않는다 — Supabase 도 외부 managed DB 로 동일하게 취급된다.
  - 결과 화면 법적 고지 문구.

---

## 0. 결정 요약 (TL;DR)

| 항목 | 결정 |
|---|---|
| **MVP 배포 클라우드** | **AWS Lightsail Seoul (`ap-northeast-2`)** — 4 vCPU / 16 GB / 320 GB SSD / 6 TB egress 번들, **$84/mo 고정**. |
| **결제 통화** | USD (AWS 본사 청구). 한국 법인 결제/세무 검토는 §4.4 위임. |
| **P1 (200세션) 전환 타깃** | 동일 AWS 계정 내 **EC2 `m7i.xlarge`** + **EBS gp3** + **g5.xlarge** (GPU 도입 시) — 라인업 연속, IAM·VPC 재구성 최소. |
| **P1 전환 트리거** | (a) 동시 세션 80 초과, (b) Lightsail 6 TB egress 한도 80% 도달, (c) GPU 필요 결정 (ADR-0001 §7.4 트리거 충족). |
| **Plan B (Lightsail 부적합 판명 시)** | GCP CE `asia-northeast3` (`e2-standard-4`, $125.51/mo) — 동일 한국 리전, GPU 동시 보유. |
| **Plan C (한국 사업자 의무 시)** | NHN Cloud KR1 (`m2.c4m16`, ~$140/mo, 정지 90% 할인) 또는 NCP KR-1. CSAP·법인 청구서 의무가 발생하는 시점에 회귀. |
| **Hetzner Singapore / Fly.io NRT** | **컷**. 본 ADR이 후보 명단에서 제외. |

본 결정은 **단일 인스턴스 · MVP 30세션 · 한국 리전 1순위 · B2C 무료 모델** 위에서 내려졌으며, ADR-0001 §1.3 평가 기준 5축 가중치를 그대로 적용한다.

> ⚠ **Proposed 상태**: 본 ADR이 Accepted 되기 전에 비교 메모 §5 미해결 항목 **Q1~Q8 가운데 Q6(한국 법인 결제·VAT) · Q8(MVP CPU 추론 Mask2Former 부하)** 두 건은 반드시 해소되어야 한다 (§7 참조).

---

## 1. 결정 컨텍스트

### 1.1 무엇을 결정해야 하는가

ADR-0001 §8 (T7) 이 클라우드 선정을 **D6 메모 결과로 위임**했다. D6 메모 (`docs/runbooks/cloud-comparison.md`, CMP-532) 가 8 SKU 라인업의 2026-05 기준 가격·리전·egress·GPU·한국 운영성·SSD를 비교했고, 1·2·3순위 권고를 인도했다. 본 ADR은 그 권고를 **Proposed 상태로 봉인**한다.

### 1.2 평가 기준 (ADR-0001 §1.3 가중치 상속)

1. **한국 운영 가능성** (한국어·국내 리전·법규) — 최우선
2. **단일 인스턴스 운영 비용** — B2C 무료 모델 → 매월 비용 = 손익
3. **공통 컨트랙트 친화성** — 내부 구현 교체 자유 (R2/Neon/OpenAI는 외부이므로 클라우드 종속도 낮음)
4. **MVP 도달 시간** — M1~M3 도달 속도 > SOTA
5. **장기 유지 보수 / 채용 가능성**

### 1.3 트래픽 가정 (D6 메모 §1.3 상속)

```
사용자 ──▶ Cloudflare R2 (도면·리포트)             // egress = 0
사용자 ──▶ [컴퓨트 1대] ─ web + api + redis
                ├──▶ Neon Postgres (SG)            // 외부
                └──▶ OpenAI VLM                     // 외부
```

- 컴퓨트 egress ≈ 40~60 GB/월 (30세션 활성). Lightsail 6 TB 번들로 충분 — **R2 흡수가 깨지지 않는 한** 본 가정이 유효하다.

---

## 2. 결정 — AWS Lightsail Seoul (`ap-northeast-2`)

### 2.1 채택 SKU

| 항목 | 값 |
|---|---|
| **번들 SKU** | Linux 4 vCPU / 16 GB RAM / 320 GB SSD / 6 TB outbound transfer |
| **월정액** | **$84.00 / mo** (고정, on-demand 변동 없음) |
| **리전** | `ap-northeast-2` Seoul |
| **운영 모델** | 단일 Lightsail Instance 1대 + Static IPv4 (무료 1개) + DNS는 외부 (Cloudflare R2 계정의 Cloudflare DNS 권장) |
| **컨테이너 부팅** | `docker compose -f infra/compose/docker-compose.yml up -d --build` |
| **백업** | Lightsail Automatic Snapshots (일 1회, 7일 보존, 무료 등급 후 $0.05/GB-mo) |

### 2.2 사유

- **가격·번들 단순성**: 컴퓨트 + 320 GB SSD + 6 TB outbound 가 단일 $84/mo. ADR-0001 §1.3 #2 비용·#4 MVP 시간 가중치에서 최상위.
- **한국 리전**: `ap-northeast-2` Seoul (4-AZ). 한국어 PII 거주·SLA 99.99% — ADR-0001 §1.3 #1 최우선 기준 충족.
- **P1 마이그레이션 비용 최소**: 동일 AWS 계정 내 EC2/g5/EBS 라인업으로 단순 스냅샷·AMI 변환. VPC·IAM 재구성 불필요 — Lightsail은 결국 EC2 위에 얹힌 추상화이므로 라인 끊김 없음.
- **콘솔·도구 단순성**: 자동화 에이전트(우리) 친화. terraform `aws_lightsail_instance` 프로바이더 안정. 보안그룹 세분화·VPC peering 등 EC2의 over-engineering 회피.

### 2.3 대안과 기각 사유

| 대안 | 기각 사유 | 비고 |
|---|---|---|
| **AWS EC2 단독** (`m7i.xlarge`, $180.89/mo) | MVP 단계에서 Lightsail이 단순 대안. EC2의 VPC/IAM/EBS 세분화는 단일 인스턴스 가정에 over-engineered. | **P1 마이그레이션 타깃으로 보유** — 본 ADR이 EC2를 컷한 것이 아니라 MVP 단계 채택만 미룬 것. |
| **GCP CE Seoul** (`e2-standard-4`, $125.51/mo) | 한국성·SLA·GPU 라인업 균형이 가장 우수하나 가격 차 $41.51/mo + 결제 통화·VAT 인보이스 복잡도. CTO가 "GPU 옵션을 MVP부터 동일 계정에 두기"를 우선시하면 본 결정을 supersede 하라. | **Plan B** — Q8 (Mask2Former CPU 부하) 측정 결과 CPU 미달 + GPU 필요 시 본 결정 재평가 트리거. |
| **NHN Cloud KR1** (`m2.c4m16`, ~$140/mo) | 가격이 Lightsail의 1.67배. 한국 사업자 매력은 크나 정지 90% 할인이 단일 인스턴스 24/7 운영에서는 무효. CSAP 의무가 없으면 우위 없음. | **Plan C** — Q6 (법인 결제·VAT) 또는 CSAP 의무 발생 시 회귀. |
| **NCP KR-1** (~$90/mo) | Lightsail보다 $6 비싸나 한국 사업자성 우위. terraform·IaC 친화성·자동화 친화성 검증 부족. CSAP 의무 시 NHN과 동급 후보. | Plan C 동급. |
| **KT Cloud** | 공시 가격 신뢰도 낮음 (밴드 $160~217), G1/G2 SKU 혼재. **CSAP 정부등급이 결정적 요건이 되는 시점**에만 부상. 영업 견적 1회 필수 (Q1). | 조건부 후보. |
| **Hetzner Singapore** | 가격 $56/mo 매력, 그러나 Seoul→SIN 75~95ms · 한국어 ❌ · CSAP ❌ · 컴퓨트 SLA 명문 ❌ · GPU ❌. ADR-0001 §1.3 #1 최우선 기준 침범. | **컷**. |
| **Fly.io NRT** | 단일 인스턴스 + docker-compose 정책과 결제 모델 비정합 (Machine = 다수 단일-목적). **GPU 라인업 EOL 2026-08-01**. | **컷**. |
| **Azure VM B-series** (이슈 본문 후보 목록) | ADR-0001 §8.1 단축 리스트에 부재. Korea Central 리전 보유하나 자동화 도구·생태계 우위 부재. 별도 검토 없이 본 ADR이 제외. | 본 ADR 범위 외. |
| **Render / Railway / Vercel + Neon** (이슈 본문 PaaS 후보) | `docker-compose` 1대 단일 인스턴스 운영 가정에서 PaaS는 컨테이너 1개씩 분리 모델 — 정합 ❌. ADR-0001 §8.1 단축 리스트에서 이미 제외. | 본 ADR 범위 외. |

### 2.4 ADR-0001 §8.1 가격 가설 보정

ADR-0001 §8.1 가설표는 다음과 같다:

> | GCP Compute Engine | `asia-northeast3` | $80~120/mo (`e2-standard-4`) | 1순위 후보 |

D6 메모 측정 결과 `e2-standard-4` = **$125.51/mo** (730시간 기준)로 가설 상한 초과. 본 ADR은 ADR-0001 §8.1 가설값을 다음으로 **보정 권고** (CTO 권한):

| 사업자 | 가설 (ADR-0001 §8.1) | 실측 (D6 메모 §2) |
|---|---|---|
| GCP `e2-standard-4` | $80~120 | **$125.51** |
| AWS Lightsail Seoul (4c/16) | 미기재 | **$84.00** |
| AWS EC2 `t3.xlarge` Seoul | $80~160 | **$151.84** |
| AWS EC2 `m7i.xlarge` Seoul | $80~160 | **$180.89** |
| Hetzner CCX23 SIN | $40~60 | **$56** (€51.49) |
| Fly.io `performance-4x` 16GB NRT | $60~120 | **$170.33** |

→ ADR-0001 §8.3 재평가 트리거 또는 본 ADR로 보정 인용. **본 ADR이 Accepted 되면 ADR-0001 §8.1 표는 자동 supersede**.

---

## 3. 운영 모델

### 3.1 컴포넌트

| 컴포넌트 | 위치 | 비고 |
|---|---|---|
| Lightsail Instance | `ap-northeast-2` Seoul AZ-a | 4 vCPU / 16 GB / 320 GB SSD / 6 TB egress |
| Static IPv4 | Lightsail (무료 1개) | DNS A 레코드 1건 |
| Snapshot (백업) | Lightsail Automatic | 일 1회, 7일 보존 |
| Neon Postgres | 외부 (`ap-southeast-1` Singapore) | ADR-0001 §4 봉인 |
| Cloudflare R2 | 외부 | ADR-0001 §6 봉인 |
| OpenAI VLM | 외부 (`gpt-5.4-mini` / `gpt-5.5`) | ADR-0001 §7 봉인 |

### 3.2 부팅·운영 명령 (AGENTS.md §6 정합)

```bash
# 인스턴스 SSH (Lightsail console 또는 .pem 키)
ssh ubuntu@<static-ip>

# 코드 동기화 (배포 후속 이슈에서 자동화)
cd /opt/jippin && git pull --ff-only

# 전체 부팅
docker compose -f infra/compose/docker-compose.yml up -d --build

# 헬스체크 (Neon SELECT 1 결과 포함)
curl http://localhost:8000/healthz

# 마이그레이션
docker compose -f infra/compose/docker-compose.yml exec api alembic upgrade head
```

### 3.3 보안·시크릿

- `.env`는 인스턴스 `/opt/jippin/.env`에만 존재. 커밋 금지(AGENTS.md §4.4).
- AWS Systems Manager Parameter Store(SSM) 또는 AWS Secrets Manager로 시크릿 매니저 도입은 P1 후속 이슈에서 결정 (Lightsail 단일 인스턴스에서도 IAM Role for Lightsail 사용 가능).
- Neon DB URL은 본 ADR이 봉인하지 않는다 — CEO 브리프 §5.1 봉인 그대로.
- 시크릿 헌팅 가드는 CMP-524 §11 #7 (Security Engineer 자식 이슈)에서 별도.

### 3.4 모니터링 (P1 후속)

- MVP: Lightsail 콘솔의 기본 CPU/Network/Snapshot 그래프 + 컨테이너 stdout (`docker compose logs`).
- P1: CloudWatch Agent 도입 또는 외부 모니터링(Grafana Cloud free tier 등) — 별도 ADR.

---

## 4. P1 (200세션) 전환 계획

### 4.1 트리거 (any one)

1. 동시 세션 **80 초과** 지속 — Lightsail 4 vCPU 부하 80% 도달 추정.
2. Lightsail 월 **6 TB outbound 한도 80% (≈4.8 TB) 도달** — R2 흡수가 깨졌다는 신호.
3. **GPU 도입 결정 충족** (ADR-0001 §7.4 트리거):
   - Mask2Former + SAM2 CPU 추론으로 NFR-PERF-001 (평균 5초 / p95 8초) 미달 측정.
   - 또는 mAP < 80% 가 모델 풋프린트 부족으로 판명.
4. **CSAP / ISMS-P 의무 발생** — Plan C (NHN/NCP) 회귀 트리거. 본 4.1.4 는 별도 ADR-0003 으로 분기.

### 4.2 전환 타깃 (4.1.1~3 가운데 하나 발화 시)

| 단계 | 타깃 | 비고 |
|---|---|---|
| Step 1 | **EC2 `m7i.xlarge`** + EBS gp3 200 GB | 동일 AMI 가능. Lightsail 스냅샷 → EC2 AMI 변환 1회. |
| Step 2 (GPU 필요 시) | **EC2 `g5.xlarge`** (A10G x1) | $903/mo. AI 워커 분리 결정 시 별도 인스턴스. |
| Step 3 (P1 200세션 안정 후) | Application Load Balancer + EC2 Auto Scaling | **본 트리거가 발화하면 ADR-0001 §8 단일 인스턴스 봉인이 자동 재평가됨** — 별도 ADR. |

### 4.3 마이그레이션 비용 가설

- DNS 컷오버: <30분 (Cloudflare DNS의 짧은 TTL).
- 데이터: Lightsail SSD → EBS gp3 (스냅샷 변환). 도면 원본은 R2에 있으므로 영향 없음.
- 다운타임: 30~60분 (예고 공지 후 작업).
- 인건비: DevOps Engineer 0.5 day.

### 4.4 한국 법인 결제·세무 (Q6 미해결)

- AWS는 USD 신용카드 결제가 기본. 한국 법인용 인보이스(KRW + 부가세) 발급은 AWS Korea LLC 계약 또는 AISPL(인도법인) 경유로 가능.
- 본 ADR이 Accepted 되기 전 CEO·재무 검토 필요. 결과가 "한국 법인 결제 불가능 / 비효율"이면 **Plan C (NHN/NCP)** 회귀.

---

## 5. 봉인 표 — 본 ADR이 봉인하는 환경 변수·인프라

| 키 | 값 | 비고 |
|---|---|---|
| `CLOUD_PROVIDER` | `aws_lightsail` | `.env.example` 봉인 |
| `CLOUD_REGION` | `ap-northeast-2` | Seoul |
| `LIGHTSAIL_BUNDLE_ID` | `xlarge_3_0` (4c/16/320/6TB) | 2026-05 카탈로그 ID, 검증 필요 |
| `INSTANCE_PUBLIC_HOST` | (할당 후 입력) | Static IPv4 |
| `BACKUP_POLICY` | `lightsail_snapshot_daily_7d` | Automatic snapshots |
| `TZ` | `Asia/Seoul` | 인스턴스 시간대 |

### 5.1 IaC (선택 인도물, 본 ADR Accepted 후 후속 이슈)

- `infra/terraform/lightsail/` 스켈레톤은 **본 ADR Accepted 후** DevOps Engineer 자식 이슈로 분리.
- 본 이슈(CMP-532)에서는 IaC 스켈레톤은 인도하지 않는다. 이유:
  - "Proposed" 상태에서 IaC 작성 = 재작업 위험.
  - CEO 결제·법인 검토(Q6) 이전에 SKU 확정 불가.

---

## 6. 변경 절차

- 본 ADR은 **CTO 권한**으로 검토하고, **CEO 승인** 시 `Status: Accepted`로 전환한다.
- 본 ADR이 Accepted 되면 ADR-0001 §8.1 가격 가설표·§8.3 재평가 트리거를 자동 supersede.
- 후속 ADR (예: P1 GPU 분리, CSAP 회귀)은 본 ADR을 supersede 하지 않고 부분 supersede한다.

---

## 7. Proposed → Accepted 전 해소 사항 (CMP-532 비교 메모 §5 Q1~Q8 매핑)

| # | 항목 | Accepted 차단 여부 | 책임 |
|---|---|---|---|
| Q1 | KT Cloud SKU 영업 견적 | ⚪ 차단 X (KT가 채택되지 않으면 무관) | Cloud Engineer |
| Q2 | NHN `m2.c8m32` 정확 단가 | ⚪ 차단 X (Plan C 활성화 시점에만) | Cloud Engineer |
| Q3 | NCP/KT/NHN GPU 시간당 정가 | ⚪ 차단 X | Data Lead |
| Q4 | AWS Seoul gp3 정확 단가 | 🟡 P1 EC2 전환 시점 차단 | DevOps |
| Q5 | GCP Premium egress 단가 | ⚪ 차단 X (Plan B 활성화 시점에만) | Cloud Engineer |
| **Q6** | **한국 법인 결제·VAT 매트릭스** | 🔴 **Accepted 차단** | CEO / 재무 |
| Q7 | Seoul→SIN 75~95ms 실측 | ⚪ 차단 X (Hetzner 컷됨) | — |
| **Q8** | **Mask2Former CPU 추론 30세션 부하** | 🔴 **Accepted 차단** | Data Lead → AI/ML Engineer |

→ **Q6·Q8 두 건 해소 + CTO 검토 + CEO 승인 = Accepted 조건**.

---

## 8. 자식 이슈 매핑 (본 ADR Accepted 후 발행 권고)

| # | 자식 이슈 (제목 패턴) | 주 오너 | 트리거 |
|---|---|---|---|
| 1 | `[Finance] AWS 한국 법인 결제 / VAT 인보이스 매트릭스` | CEO / 재무 | Q6 해소 |
| 2 | `[Data] Mask2Former CPU 추론 30세션 부하 측정` | Data Lead / AI Engineer | Q8 해소 |
| 3 | `[DevOps] infra/terraform/lightsail 스켈레톤` | DevOps Engineer | 본 ADR Accepted |
| 4 | `[Infra] Lightsail 부트스트랩 + docker-compose 배포 (CMP-530 인계)` | Cloud Engineer | 본 ADR Accepted |
| 5 | `[Security] AWS IAM·Secrets 매니저 도입 (P1 트리거 시)` | Security Engineer | P1 트리거 발화 |

---

## 9. 결정 트레일

| 시각 | 행위자 | 행위 |
|---|---|---|
| 2026-05-28 | Cloud Engineer (`575b4fb8`) | D6 메모(CMP-532) 인도 + 본 ADR-0002 `Proposed` 발행. |
| _pending_ | CTO (`4edca504`) | 본 ADR 검토. Plan B/C 채택 시 supersede 또는 본 ADR 채택. |
| _pending_ | CEO (`1a9c8580`) | Q6 결제·세무 검토 결과 + CTO 권고로 `Accepted` 승인. |

— 끝 —
