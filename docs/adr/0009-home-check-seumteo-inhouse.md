# ADR 0009 — 우리집 체크: CODEF 제거하고 세움터 직결 내재화

- **상태**: **Accepted (2026-07-08)** — 운영자(사용자) 결정.
- **관련**: ADR-0008(우리집 체크 원안, CODEF), `apps/seumteo-worker/`, `apps/api/src/services/seumteo/`.
- **대체**: ADR-0008 §2.1~2.2 의 데이터 출처·클라이언트 결정(CODEF)을 본 ADR 이 대체한다.
  판정·PII·PDF 보관·제품 표면(§2.3~2.5)은 그대로 유지된다.

## 배경 / 문제

ADR-0008 은 CODEF(세움터 스크래핑 대행 API)로 집합건축물대장 전유부·표제부를 조회했다.
운영 결과 **CODEF 유료 계약이 최소 200만원/월**로, 실제 사용량 대비 과하다. 조사 결과:

- 무료 공식 API(건축HUB, data.go.kr 15134735)는 면적·표제부는 주지만 **「위반건축물」 플래그가
  없다**(제품 핵심 신호). 완전 대체 불가.
- CODEF = 세움터/정부24 스크래핑. 세움터 직접 자동화의 실질 장벽은 캡차가 아니라 AnySign·
  WebSquare·ToS 였는데, **세움터측에 문의해 RPA 수준(수동 유사·저볼륨) 자동화 허락**을 받았다.
- 브라우저 실정찰로 발급 전 과정이 **내부 JSON API**(주소=ES, 조회/담기/신청=`/bci/*`)이고
  **캡차·AnySign 없음**을 확인, 엔드포인트·payload 를 실측 확보했다(README 계약표).

## 결정

| 항목 | 결정 |
|---|---|
| 데이터 출처 | **세움터 직결**(CODEF 제거). 단일 계정 `shtech`(운영자 지정, 분리 금지) ID/비번 로그인. |
| 실행 위치 | **별도 Fly 앱** `jippin-seumteo-worker`(`apps/seumteo-worker`) — Playwright headless Chromium, 2GB+swap. api 본체(1GB)와 프로세스 격리(OOM 방지). |
| 호출 방식 | api → 워커 **Flycast 사설망**(`.flycast`) HTTP. `SEUMTEO_WORKER_TOKEN` Bearer 추가 인증. |
| 인터페이스 | **CODEF 동형 유지**. `SeumteoBuildingRegisterClient` 가 CODEF 3 메서드+생성자 시그니처와 `codef.types` 결과 dataclass·예외를 그대로 쓴다 → `home_check.py`·기존 테스트 무변경. |
| 발급 방식 | 1~8 단계 in-page fetch(JSON), 9 단계(발급 리포트)만 DOM 클릭. 담기 시 **`ownrYn:"N"`** 로 소유자 PII 미포함 대장 발급(ADR-0008 PII 정책 부합). |
| 위반 판정 | CLIP Report(HTML5 canvas) 뷰어에서 텍스트 확보(`paintReportText` 후킹 + `viewData` 디코드) → "위반건축물" 부분문자열. |
| PDF | 뷰어 "PDF 저장" 버튼 → 다운로드 → `original_pdf_base64` 반환. **기존 `home_check._store_pdfs` 가 Supabase 저장**(무변경). |
| 전환 | `seumteo_enabled` 플래그. true=세움터, false=CODEF(롤백). 기본 false. |
| 자격증명 | 세움터 password 는 api 프로세스에 없다. **워커(Fly secrets)만 보유**. |

## 결과 / 영향

- CODEF 월 구독(200만원) 제거. 건당 과금 소멸(세움터 온라인 발급 자체는 무료).
- api 스택 무변경(httpx·redis 기존 의존만; 브라우저는 워커에만). PDF→Supabase 경로 재사용.
- 단일 계정 세움터 세션·발급이력이 워커에 집중 → 서킷브레이커(재사용)로 계정 보호.
- **CODEF 수탁자 제거** → 세움터 대장 조회·PII 처리 책임이 인하우스로 이동. 개인정보처리방침의
  위탁 항목 갱신 필요(후속). 위반/발급 데이터는 여전히 조회 시점 참고용(면책 유지).

## 미결/후속 (README PoC 체크리스트)

7단계 신청 fetch 헤더, 단일 세션 장바구니 격리, 위반 검출(위반 케이스 실검증), PDF 다운로드
경로, 전유부 세부 파싱 — **실주소 PoC 로 확정 후 튜닝**. Flycast 60초 타임아웃 초과 시
`.internal` 상시가동 전환.

## 대안 (기각)

- **CODEF 유지**: 비용 과다(200만/월).
- **무료 API 하이브리드**: 위반건축물 플래그 공백으로 핵심 신호 불가(ADR-0008 §4 확인).
- **세움터 계정 분리(자동화 전용)**: 운영자가 세움터측과 단일 계정으로 합의 → 분리 금지.
- **api 본체에 브라우저 탑재**: 1GB 머신 OOM. 별도 워커로 격리.
