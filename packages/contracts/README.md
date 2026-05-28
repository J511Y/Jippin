# @jippin/contracts

집핀(Jippin) **공통 컨트랙트** 패키지.

- 정본은 `schemas/` 의 JSON Schema (Draft 2020-12) 5종이다. **언어 중립.**
- `ts/` 의 TypeScript 타입과 `python/zippin_contracts/` 의 Pydantic v2 모델은 **자동 생성물**이다. 직접 수정 금지.
- 본 패키지는 ADR-0001 §9.2 가 봉인한 모노레포 트리의 일부다. 스키마 변경은 SDD §5.1·§5.2 와 ADR을 동시에 갱신해야 한다.

## 1. 정본 컨트랙트 (정본 = `schemas/`)

| 파일 | 컨트랙트 | 근거 |
|---|---|---|
| `common-judgment-schema.schema.json` | `CommonJudgmentSchema` | SDD §5.2 핵심 컨트랙트 |
| `completion-decision.schema.json` | `CompletionDecision { ASK_MORE / REQUEST_OVERLAY_REVIEW / PROCEED_RULE / HOLD_OR_HANDOFF }` | SDD §4.7·§5.1 (FLOW_GUARD) |
| `rule-eval-result.schema.json` | `RuleEvalResult` | SDD §4.8 (RULE) |
| `estimate-result.schema.json` | `EstimateResult` | SDD §4.9 REPORT.estimate / §6.3 |
| `error-response.schema.json` | 표준 에러 응답 | AGENTS.md §4.5 |

모든 스키마는 `schema_version`을 1.0.0으로 고정한다. 변경 시 PR 체크리스트(AGENTS.md §4.3)에 따라 bump하고, **본 README의 표 + ADR + SDD §5** 세 곳을 동시에 갱신한다.

## 2. 사용법

### 2.1 TypeScript (`apps/web`, 향후 사용처)

```ts
import type {
  CommonJudgmentSchema,
  CompletionDecision,
  RuleEvalResult,
  EstimateResult,
  ErrorResponse,
} from "@jippin/contracts";
```

### 2.2 Python (`apps/api`, 향후 사용처)

```python
from zippin_contracts import (
    CommonJudgmentSchema,
    CompletionDecision,
    RuleEvalResult,
    EstimateResult,
    ErrorResponse,
)
```

> **주의**: 본 이슈(CMP-527) 범위는 패키지 골격까지다. 백엔드(CMP-524 #2)·프론트엔드(CMP-524 #3) 골격 이슈가 이 패키지를 import하도록 배선한다.

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

## 4. 본 이슈 범위 밖

- HTTP 엔드포인트/라우터 구현(`apps/api`)
- React 컴포넌트/오버레이(`apps/web`)
- AI/RULE/REPORT 모듈의 비즈니스 로직

위 항목은 모두 CMP-524 의 형제 자식 이슈에서 다룬다. 본 패키지는 그 형제 이슈들의 **의존**으로만 존재한다.
