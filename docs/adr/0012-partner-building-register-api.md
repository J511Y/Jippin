# ADR 0012 — 파트너 건축물대장 발급 API (워크 연동)

- **상태**: **Accepted (2026-11-11)** — 운영자(사용자) 결정.
- **관련**: ADR-0008(우리집 체크 원안), ADR-0009(세움터 직결 내재화),
  `apps/api/src/routers/partner_building_register.py`,
  `apps/api/src/services/partner_building_register.py`.
- **유지**: ADR-0008 §2.3(소유자 등 PII 비구조화)은 그대로다. 본 ADR 은 표면을 하나 더할 뿐이다.

## 배경 / 문제

사내 업무 시스템 "워크"(별도 시스템, 셀프호스트)가 의뢰를 만들 때 집합건축물대장
전유부+표제부를 백그라운드로 발급받아야 한다. 그런데:

- 세움터 워커(`jippin-seumteo-worker`)는 Fly 사설망에서 **api 만** 닿을 수 있다.
- 기존 `/home-check` 는 소비자용 Supabase JWT 를 요구하고, 결과를 `home_checks` 테이블과
  Supabase Storage 에 남긴다. 서버 간 호출·사내 업무 자료에는 맞지 않는다.

## 결정

| 항목 | 결정 |
|---|---|
| 표면 | `POST /partner/building-registers`(제출, 202) · `GET /partner/building-registers/{job_id}`(폴링) · `DELETE /partner/building-registers/{job_id}`(수령 확인, 204). |
| 인증 | `Authorization: Bearer <PARTNER_API_TOKEN>` 고정 토큰(상수 시간 비교). 토큰 미설정이면 전 라우트 503 — 기본은 꺼져 있다. |
| 멱등 | `Idempotency-Key` 헤더 필수. 같은 키의 재제출은 기존 잡을 돌려주고 발급을 다시 하지 않는다. |
| 처리 | 우리집 체크와 같은 `SeumteoBuildingRegisterClient`·BackgroundTasks. 두 종류를 함께 요청하면 통합 잡(`fetch_bundle`), 하나면 단건. |
| 결과 | 종류별 봉투. 성공은 발급일·위반 여부(전유부만 — 표제부 봉투의 `violation_status` 는 항상 `null`, ADR-0008 §5 2026-11-11)·문서번호와 **PDF base64 중계만** 한다. 실패는 `auth`/`not_found`/`invalid`/`upstream`/`needs_input`/`busy` 분류. needs_input 재개는 없다 — 호출자가 주소를 고쳐 다시 제출한다. |
| 저장 | **Redis TTL 만.** `partner:bldg:job:<job_id>`, `partner:bldg:idem:<sha256>`. 대기·처리 중 15분(프로세스가 죽은 잡은 스스로 사라져 404), 완료 결과 30분. DELETE 는 즉시 지운다. |
| 저장하지 않는 것 | `home_checks`/`home_check_documents` 테이블, Supabase Storage, request_logs 본문. 주소·동·호·PDF 는 로그에도 남기지 않는다. |
| 구조화 추출 | **하지 않는다.** 세대수·소유자 해석은 워크가 PDF 를 직접 읽어 한다. jippin 은 소유자 정보를 파싱·저장하지 않는다(ADR-0008 §2.3 불변). |
| 오류 본문 | 호출자와 고정한 `{"detail": "..."}`. AGENTS.md §4.5 봉투는 본문 검증 실패(422)에만 쓰인다. |

## 결과 / 영향

- 소비자 트래픽(우리집 체크)과 **세움터 단일 계정·워커·서킷브레이커를 공유**한다. 파트너
  호출의 인증 실패도 같은 서킷에 쌓이고, 서킷이 열리면 양쪽 모두 막힌다(`busy`).
  워크 쪽 발급량은 의뢰 생성 건수 수준의 저볼륨으로 합의했다. 늘어나면 한도·대기열을 따로 둔다.
- 잡 상태는 gunicorn 프로세스 2개가 공유해야 하므로 Redis 가 필수다. Redis 장애 시
  이 API 는 503 을 낸다. 프로세스 내 dict 폴백은 테스트·로컬 전용이다.
- PDF 가 Redis 에 최대 30분 머문다. 호출자는 받은 뒤 DELETE 로 지우는 것을 원칙으로 한다.
- DB 마이그레이션·컨트랙트(`packages/contracts`) 변경 없음. 워커(`apps/seumteo-worker`) 무변경.
- 운영 시크릿 `PARTNER_API_TOKEN` 1개 추가(`docs/runbooks/fly-api-deploy.md` §3.1).

## 대안 (기각)

- **워크가 워커를 직접 호출**: 워커는 사설망 전용이고 세움터 자격증명·서킷을 api 뒤에 둔다는
  ADR-0009 구조를 깬다.
- **`/home-check` 재사용(서비스 계정 JWT)**: 사내 업무 자료가 소비자 이력·Storage 에 섞이고
  익명/회원 정책과 얽힌다.
- **jippin 이 소유자·세대수를 구조화해 반환**: ADR-0008 §2.3 위반. 해석 책임은 워크에 둔다.
- **PDF 를 Supabase Storage 서명 URL 로 전달**: 보관 지점이 하나 더 생긴다. 중계 후 즉시 삭제가 단순하다.
