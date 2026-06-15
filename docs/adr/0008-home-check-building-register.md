# ADR 0008 — 우리집 체크 (집합건축물대장 전유부 + 표제부 조회)

- **상태**: **Accepted (2026-06-15)** — 운영자(사용자) 결정으로 확정.
- **제안자**: Full-stack (agent, CMP-DIRECT)
- **승인 권자**: 운영자(사용자) — 본 작업 지시에서 5개 결정항목을 명시적으로 승인.
- **관련**: ADR-0007 (Supabase Storage 도입·익명 리드), `supabase/migrations/..._0009_consultation_leads.sql`, `supabase/migrations/..._0014_home_checks.sql`, CODEF 세움터 집합건축물대장 전유부 API(`/v1/kr/public/lt/eais/aggregate-buildings`)·표제부 API(`/v1/kr/public/lt/eais/building-ledger-heading`).

---

## 0. 결정 요약 (TL;DR)

| 항목 | 본 ADR 결정 |
|---|---|
| 기능 | **우리집 체크** — 집합건물(아파트·빌라·오피스텔 등) 세대의 **위반건축물(노란딱지) 여부**와 **확장·변경 등재 여부**를 셀프 진단하고, 이상 시 사용검사 상담으로 인입. 단독·다가구(일반건축물대장)는 범위 외. |
| 데이터 출처 | **CODEF**(세움터 스크래핑). **전유부 + 표제부 병행 조회.** loginType=1(서비스 소유 단일 세움터 계정). |
| 표제부 병행 | **채택.** 위반표시(노란딱지)는 표제부(건물 전체)에 찍히는 경우가 많아 전유부 단독은 **위양성/위음성** 위험 → 표제부도 함께 조회해 건물 단위 위반을 1차 신호로 본다. |
| 클라이언트 라이브러리 | **옵션 B (인하우스).** 공식 SDK(`easycodefpy`/`aio-easycodefpy`, 2020 방치, aiohttp) 미채택. **RSA는 기존 의존성 `cryptography`로 처리**(신규 패키지 불필요), 전송은 기존 `httpx.AsyncClient` 컨벤션. |
| 실행 모델 | **비동기 잡.** `POST /home-check` → 즉시 202 + jobId → 백엔드가 전유부 1차→자동매칭→2차 + 표제부 조회 → 프론트 폴링. 동기 300s 대기 금지. |
| 영속화 | **DB `home_checks`** = SoT(잡 + 요약 + 판정). Redis는 OAuth 토큰 캐시 + 2-way `twoWayInfo` transient 한정. |
| 원본 보관 | **발급 PDF(`resOriGinalData`)를 Supabase Storage `home-check-docs` 비공개 버킷에 보관**(전유부·표제부 각 1부). PDF가 상세 원본 기록이므로 구조화 저장은 판정·표시용 최소 필드만. |
| 소유자 정보 | **저장하지 않음.** `resOwnerList`(소유자명·주민번호)·`resLicenseClassList`(설계자/시공자 성명·면허) 등 PII는 DB 미저장(원본 PDF에만 존재). 위반/변동 판정에 소유자 PII 불필요. |
| 세움터 password / 주민번호 | **어디에도 영속 저장 금지.** password는 RSA 암호화 후 전송 즉시 폐기. |
| 약관 | 운영자가 CODEF·세움터 약관 확인 완료 — 단일계정 대행조회 진행에 문제 없음. |
| 이용 제한 | **현재는 무제한** (레이트리밋·쿼터 미적용). 운영 중 남용/비용 지표를 보고 후속 결정. |
| 재사용 | 도로명주소 팝업, `ConsultationLeadForm` prefill(`source_form='property_check'`), 마이페이지 이력 탭. |

## 1. 배경 / 문제

집합건물 세대의 소유주·매수예정자·관련직군이 "내 집이 정상적인 집인지"(위반건축물 여부, 확장·변경이 대장에 제대로 등재됐는지)를 셀프로 확인할 수단이 없었다. 건축물대장은 누구나 주소로 열람 가능한 공적 장부지만, 세움터 UI 직접 조회는 비전문가에게 불친절하고 위반표시·변동이력의 의미 해석이 어렵다.

CODEF가 세움터 집합건축물대장을 API로 제공한다. 다만 (a) 스크래핑 기반이라 응답이 느리고(최대 300s) **2-way 추가인증**(주소·동·호 선택 + 보안문자)이 끼며, (b) **위반표시는 표제부(건물 전체)에 찍히는 경우가 많아** 전유부(호 단위)만 보면 건물 위반을 놓칠 수 있고, (c) 응답에 소유자 주민번호·설계자 성명 등 **타인 PII**가 포함된다.

## 2. 결정

### 2.1 데이터 — 전유부 + 표제부 병행 (CODEF, loginType=1)

- **두 API를 모두 호출**한다.
  - 전유부 `…/eais/aggregate-buildings`: 세대(호) 단위. `resViolationStatus`(호 위반), `resOwnedList`(전유면적·구조·용도·층, `resType="0"`=전유부분), `resChangeList`(변동), `resPriceList`(공동주택가격), `resOriGinalData`(PDF).
  - 표제부 `…/eais/building-ledger-heading`: 건물 단위. `resViolationStatus`(**건물 위반=노란딱지**), `resDetailList`(연면적·건폐율·용적률·사용승인일 등 key-value), `resBuildingStatusList`(층별 현황), `resChangeList`(변동), `resOriGinalData`(PDF).
- **종합 위반 판정** = 전유부 `resViolationStatus` **또는** 표제부 `resViolationStatus` 가 `"위반건축물"` → 🔴. 이로써 건물 단위 노란딱지 누락(위음성)을 방지한다.
- **인증**: `loginType=1` + 서비스 소유 단일 세움터 계정. `id`/`password`(전유부) · `userId`/`userPassword`(표제부)는 CODEF API별로 **필드명이 다르므로 제품별 요청 빌더로 분리**. password는 CODEF RSA 공개키로 암호화(PKCS1 v1.5 추정, 구현 시 실응답으로 확정).
- **2-way**: 전유부는 `address`(동·호 전까지) 1차 → `CF-03002` 후보(`reqDongNumList`/`reqHoNumList`) → 동·호 **서버 자동매칭** 2차. 표제부는 `address`+`dong`을 1차에 직접 전달하며 "입력 동으로 조회 가능하면 2-way 미발생". 자동매칭 실패·보안문자(`reqSecureNo`) 발생 시에만 `needs_input` 폴백.

### 2.2 클라이언트 — 옵션 B (인하우스 httpx + pycryptodome)

- 공식 SDK는 2020년 이후 방치 + async 버전이 aiohttp 의존(기존 httpx 컨벤션과 이중 스택)이라 **런타임 미채택**. RSA 암호화는 기존 의존성 `cryptography`(python-jose[cryptography] 경유 이미 설치, PKCS1 v1.5)로 처리하고, 토큰/전송/2-way/디코딩은 인하우스(`apps/api/src/services/codef/`).
- OAuth 토큰(`oauth.codef.io`)은 Redis 캐시(만료 자동 갱신). 응답은 URL-encoded → 디코드 후 `result.code`(CF-00000 성공 / CF-03002 2-way / 오류) 분류.
- **단일 세움터 계정 보호 서킷브레이커**: 자격증명/계정잠금류 오류 누적 시 회로 차단(계정 영구 잠금 방지). 자격증명 오류는 재시도 금지.

### 2.3 영속화 / 원본 보관 / PII

- 잡·판정·요약은 `home_checks` 테이블(+ `home_check_documents` PDF 포인터). 상세 마이그레이션은 `0014`.
- **발급 PDF를 SoT 원본으로 Supabase Storage `home-check-docs` 비공개 버킷에 보관**(ADR-0007의 Supabase Storage 표면 확장). 백엔드(service role) write/read, 클라이언트 직접 접근 없음 → 사용자에게는 백엔드 서명 URL로 제공.
- **소유자·설계자 등 PII는 구조화 저장하지 않는다.** 필요 시 원본 PDF로 확인. 세움터 password·주민번호 전체값은 메모리에서만 사용 후 폐기, 로그/Redis/DB 미기록.
- 익명 세션 허용(`require_supabase_request_user`), `home_checks.user_id` nullable + ON DELETE SET NULL. 이력은 전량 백엔드 경유(consultation_leads와 동일, PostgREST/anon grant 미부여).

### 2.4 제품 표면 / 면책

- 라우트 `/home-check`(랜딩) · `/home-check/new`(주소+동·호 입력) · `/home-check/[checkId]`(폴링→리포트). 주소는 기존 **도로명주소 팝업** 재사용.
- 결과 신호등(🔴 violation / 🟡 caution / 🟢 normal). **"확장 등재 여부"는 자동 단정 불가** → 사용자가 신고한 실제 확장과 대장 `resChangeList`/면적을 대조해 caution 제시(위법 단정 회피).
- 이상 발견 시 기존 `ConsultationLeadForm`으로 prefill 인입(`source_form='property_check'`).
- 면책 고정: "건축물대장 기재사항을 조회 시점 기준으로 제공하는 참고용 정보이며, 위법 여부의 최종 판단은 관할 행정청·전문가 확인이 필요합니다."

### 2.5 이용 제한

- **현재는 제한 없이 무제한 이용** 가능하도록 설정한다(레이트리밋·쿼터·로그인 게이트 미적용). 호출당 과금·세움터 단일계정 가용성 리스크는 **결과 캐시(`comm_unique_no` 기준)** + 서킷브레이커로 1차 완화하고, 남용·비용 지표를 운영 중 모니터링해 제한 도입 여부를 후속 결정한다.

## 3. 결과 / 영향

- 위반 판정이 전유부+표제부 병행으로 건물 단위까지 포괄 → 노란딱지 누락 위험 감소. 단 표제부 추가 호출만큼 과금 증가(캐시로 상쇄).
- `source_form` enum 변경이 **DB CHECK · contracts/Pydantic · web `SourceForm` 유니온** 3곳에 동시 반영되어야 한다.
- Supabase Storage 사용 표면이 `home-check-docs` 버킷만큼 확장된다(ADR-0007 결정의 연장, R2 정본은 유지).
- 무제한 이용 정책상 초기엔 남용·비용 방어가 약하다 — 모니터링 지표 기반 후속 ADR로 제한 도입 가능.

## 4. 대안 (기각)

- **공식 SDK(`aio-easycodefpy`) 런타임 채택**: 2020 방치 + aiohttp 이중 스택. RSA/토큰/디코딩 외 핵심(2-way·동호매칭)은 어차피 인하우스라 실익 적음.
- **전유부 단독 조회**: 건물 단위 위반표시 누락(위음성)으로 "정상" 오안내 위험 → 표제부 병행으로 대체.
- **소유자 정보 구조화 저장**: 위반/변동 판정에 불필요 + 타인 PII 보관 리스크. 원본 PDF 보관으로 충분 → 기각.
- **하이브리드(건축HUB 무료 API + 부분 스크래핑)**: 위반여부 오픈API 공백을 CODEF가 일괄 커버하므로, 운영 단순성 위해 CODEF 단일 소스로 통일.
