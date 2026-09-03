# @jippin/contracts

집핀(Jippin) **공통 컨트랙트** 패키지.

- 정본은 `schemas/` 의 JSON Schema (Draft 2020-12) **10종**이다. **언어 중립.**
- `ts/` 의 TypeScript 타입과 `python/zippin_contracts/` 의 Pydantic v2 모델은 **자동 생성물**이다. 직접 수정 금지.
- 본 패키지는 ADR-0001 §9.2 가 봉인한 모노레포 트리의 일부다. 스키마 변경은 SDD §5.1·§5.2 와 ADR을 동시에 갱신해야 한다.
- **RULE/FLOW_GUARD/CHAT/REPORT/에이전트/우리집 체크 작업을 위임받으면 코드 작성 전에 `schemas/` 를 선독한다** — 여기가 인터페이스 정본이다.

## 1. 정본 컨트랙트 (정본 = `schemas/`)

| 파일 | 컨트랙트 | 근거 |
|---|---|---|
| `common-judgment-schema.schema.json` | `CommonJudgmentSchema` (**1.4.0** — `vlm_supplement.region_assessments` 추가 + `confidence`/`is_floorplan`/`judgment_hints` 계약 정합화; 1.3.0 `vlm_supplement` null 허용 명문화) | SDD §5.2 핵심 컨트랙트. 선택 벽 종합 판단·창호 경계 자동 반영·오버레이 재제공(#region-assessments, #overlay-reshow). 도면 재제출 VLM 신선도(PR #185) |
| `completion-decision.schema.json` | `CompletionDecision { ASK_MORE / REQUEST_OVERLAY_REVIEW / PROCEED_RULE / HOLD_OR_HANDOFF }` | SDD §4.7·§5.1 (FLOW_GUARD) |
| `rule-eval-result.schema.json` | `RuleEvalResult` | SDD §4.8 (RULE) |
| `estimate-result.schema.json` | `EstimateResult` | SDD §4.9 REPORT.estimate / §6.3 |
| `error-response.schema.json` | 표준 에러 응답 | AGENTS.md §4.5 |
| `agent-run-request.schema.json` | 에이전트 런 시작 요청 | `POST /sessions/{id}/agent/runs` |
| `agent-run-status.schema.json` | `AgentRunStatusValue` (런 상태 enum) | 에이전트 런 수명주기 |
| `agent-sse-event.schema.json` | SSE 이벤트 — `StateChangeDecision`·`StateChangeEvent`·`SessionStatus`·`RunStatus`·`ToolStepEvent`·`ToolKind` | 세션 상태 전이 머신 + 에이전트 스트림 |
| `home-check.schema.json` | 우리집 체크 — `HomeCheckJob`·`HomeCheckReport`·`Violation`·`ExtensionCheck`·`ExtensionVerdict` | ADR-0008/0009. 별도 building-register 스키마 파일은 없다 — 이 파일이 해당 도메인 정본 |
| `segmentation-result.schema.json` | `SegmentationResult`·`Instance`·`Region`·`Label` (**1.5.0** — error_code 에 `SEGMENTATION_STALE_INPUT`(분석 중 도면 교체 시 산출 미영속) 추가) | 도면 세그멘테이션 (HF Mask2Former). **ADR-0010**, 도면 재제출 동시성 가드(PR #185) |

스키마는 `schema_version`을 1.0.0으로 시작한다(현재 `home-check`=1.3.0, `segmentation-result`=1.5.0). 변경 시 PR 체크리스트(AGENTS.md §4.3)에 따라 bump하고, **본 README의 표 + ADR + SDD §5** 세 곳을 동시에 갱신한다 — 표에는 bump된 버전과 근거 ADR을 함께 남겨, 생성물만 보고는 알 수 없는 **의미 변화와 호환 경계**를 추적할 수 있게 한다. `evaluated_at` 류 타임스탬프 필드는 직렬화 시점에 주입한다 (스키마에 하드코딩 금지).

## 2. 사용법

### 2.1 TypeScript (`apps/web`)

```ts
import type {
  CommonJudgmentSchema,
  CompletionDecision,
  RuleEvalResult,
  EstimateResult,
  ErrorResponse,
  // 에이전트·우리집 체크·세그멘테이션 도메인 타입도 같은 배럴에서 —
  // 전체 목록은 ts/index.ts (약 70개 이름 재익스포트)
} from "@jippin/contracts";
```

### 2.2 Python (`apps/api`)

```python
from zippin_contracts import (
    CommonJudgmentSchema,
    CompletionDecision,
    RuleEvalResult,
    EstimateResult,
    ErrorResponse,
    # ExtensionVerdict, HomeCheckJob, SegmentationResult, StateChangeEvent 등 —
    # 전체 목록은 python/zippin_contracts/__init__.py
)
```

## 3. 코드 생성

```bash
# 모노레포 루트에서
pnpm -C packages/contracts run generate
```

`generate` 스크립트는 다음 두 단계를 순차 실행한다.

1. `pnpm run generate:ts` — `json-schema-to-typescript` 로 `schemas/*.schema.json` → `ts/*.ts` 생성, `ts/index.ts` 재익스포트.
2. `pnpm run generate:py` — `datamodel-code-generator` 로 `schemas/*.schema.json` → `python/zippin_contracts/*.py` 생성, `python/zippin_contracts/__init__.py` 재익스포트.

수용 기준(이슈 CMP-527 §"검증") — **재실행 후 `git diff`가 비어야 한다.**

```bash
pnpm -C packages/contracts run generate
pnpm -C packages/contracts run check   # git diff --exit-code -- ts python
```

## 4. 패키지 경계

- HTTP 엔드포인트/라우터 구현은 `apps/api`, React 컴포넌트/오버레이는 `apps/web` 소관 — 본 패키지에는 **스키마와 생성 타입만** 둔다.
- AI/RULE/REPORT/에이전트 모듈의 비즈니스 로직은 여기 두지 않는다. 본 패키지는 그 모듈들의 **인터페이스 의존**으로만 존재한다.
