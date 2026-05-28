<!--
집핀(Jippin) PR 템플릿
AGENTS.md §4.3 / docs/CONTRIBUTING.md §3 봉인.
모든 항목을 체크하지 않은 PR은 머지하지 않는다.
-->

## 관련 이슈

- Paperclip 이슈: `CMP-###`
- (해당 시) 관련 ADR: `ADR-####`

## 변경 요약

<!-- 무엇을 왜 바꿨는지 2~5줄. WHY 우선. WHAT 은 diff 가 말한다. -->

## 영향 모듈

<!-- 해당하는 모든 모듈에 [x]. 없으면 META(메타·도구·문서). -->

- [ ] `AUTH` (소셜 OAuth · JWT)
- [ ] `INPUT` (주소 · 도면 수신 · 검증 · OCR)
- [ ] `MASK` (도면 수치 마스킹)
- [ ] `AI` (Mask2Former · SAM2 · VLM · 스키마 정규화)
- [ ] `OVERLAY` (도면 위 인터랙티브 선택)
- [ ] `CHAT` (A2UI 세션 오케스트레이션)
- [ ] `FLOW_GUARD` (충분성 · 충돌 · 고위험 판단)
- [ ] `RULE` (국토부 고시 룰 엔진)
- [ ] `REPORT` (리포트 · 견적 · 리드)
- [ ] `CONTRACTS` (`packages/contracts/` 공통 스키마)
- [ ] `INFRA` (docker-compose · 운영)
- [ ] `DEVOPS` (CI / 시크릿 가드 / gitmoji)
- [ ] `SECURITY` (PII · 암호화 · 시크릿 회전)
- [ ] `QA` (테스트 · 결정성 회귀)
- [ ] `META` (문서 · ADR · 루트 메타 파일)

## 체크리스트 (AGENTS.md §4.3)

- [ ] 관련 Paperclip 이슈 식별자(`CMP-###`)를 본 PR 본문 첫 줄에 명시
- [ ] 영향 모듈을 위 목록에서 모두 체크
- [ ] 공통 컨트랙트(`packages/contracts/schemas/*.schema.json`) 변경 시 `schema_version` bump 및 TS/Python 바인딩 재생성
- [ ] 비밀번호 · API 키 · 도면 원본 등 민감 자료 미포함 (시크릿 스캔 CI 통과)
- [ ] 모듈별 dev 명령 또는 `docker compose -f infra/compose/docker-compose.yml up` 으로 동작 확인
- [ ] (해당 시) `README.md` / `AGENTS.md` / 모듈 README 갱신
- [ ] 모든 커밋이 gitmoji prefix 정규식 통과 (`gitmoji-validate` CI job)
- [ ] 머지 방식 = **Squash and merge** (기본 옵션)

## 테스트 / 검증

<!-- 어떤 자동·수동 테스트로 변경을 검증했는지. -->

- [ ] 자동 테스트 추가/갱신
- [ ] 로컬 수동 검증 (스크린샷 · 로그 · curl 결과)

## 보안 · 법적 고지 (해당 시)

- [ ] PII 처리 변경: contact_info 등 컬럼 AES-256 암호화 정책 준수 (AGENTS.md §4.4)
- [ ] 결과 화면 · 다운로드 산출물에 AI 한계 고지 문구 포함 (AGENTS.md §4.6 / NFR-LEGAL-001)

## 후속 작업

<!-- 본 PR 머지 후 분기할 자식 이슈 (있으면). -->

- 없음 또는 `CMP-###`

---

<!-- 본 문서가 어떻게 채워져야 하는지에 대한 가이드는 docs/CONTRIBUTING.md §3 을 참조. -->
