# ADR 0011 — LLM/VLM 운영 모델 gpt-5.6-luna 전환 (ADR-0001 §7.2 부분 supersede)

- **상태**: **Accepted (2026-08-19, 2026-08-24 rev2)** — 운영자(사용자) 지시.
- **supersede 대상**: [`ADR-0001`](0001-stack-reevaluation.md) **§7.2 (VLM / LLM 모델 선정)**.
  §7.2 의 LangChain v0.3+ 추상화·프로바이더 교체 가능 구조, §7.1(세그멘테이션) 등 나머지
  결정은 영향 없음.
- **관련**: `apps/api/src/config.py::agent_model` / `::vlm_model`,
  `apps/api/src/agent/tools/vlm.py`, `apps/api/src/services/home_check_extension.py`,
  ADR-0010(세그멘테이션 v4 — VLM 은 그 파이프라인의 2단계).

## 배경 / 문제

ADR-0001(2026-05)은 LLM 을 기본 `gpt-4.1-mini` / 정밀 `gpt-4o` 로 선정했고, 명세서의
gpt-5 계열 표기를 가공 모델명으로 판정했다(CEO 브리프 R4). 그러나 실제 운영 코드는 이후
`openai:gpt-5.4-mini` 단일 모델로 운용되어 왔고, AGENTS.md 에 "코드와 ADR-0001 표기
불일치(⚠ supersede ADR 미발행)" 경고가 잔존해 왔다 — 봉인 결정과 운영 현실이 어긋난 상태.

2026-08-19 세그멘테이션 v4 후속 인계와 함께 운영자가 도면 VLM(AI-002)과 대화형 에이전트
모델을 **`gpt-5.6-luna`** 로 상향할 것을 지시했다. 본 ADR 은 그 지시를 아키텍처 정본으로
영속화하고, 위 불일치를 해소한다.

2026-08-24 운영 에이전트에서 `gpt-5.6-luna`와 function tools를 Chat Completions API로
함께 호출하자 400 응답이 발생했다. 이 모델의 reasoning과 function tools 조합은 Responses
API를 사용해야 하므로, 단순 모델명 교체만으로는 운영 전환이 완결되지 않았다.

## 결정

| 항목 | 결정 |
|---|---|
| 대화형 에이전트 모델 | `config.py::agent_model` 기본값 **`openai:gpt-5.6-luna`** (구 `gpt-5.4-mini`). deepagents/LangGraph 런타임은 불변. |
| 도면 VLM(AI-002) 모델 | **`config.py::vlm_model` 신설·분리**, 기본값 **`openai:gpt-5.6-luna`**. 값은 현재 에이전트와 같지만 설정을 분리해 **독립 조정·롤백**이 가능하다(도면 판독 품질과 대화 품질은 별개 축). `vlm_model` 부재(구 설정/롤백) 시 `agent_model` 폴백. |
| 확장 대조 판정(home_check_extension) | 별도 설정 없이 `agent_model` 공유 유지 — 본 전환을 따라 luna 로 이동. |
| OpenAI API | 모든 `ChatOpenAI` 호출(대화형 에이전트·VLM·확장 대조)은 `use_responses_api=True`로 **Responses API를 명시**한다. OpenAI 요청 `metadata`는 현행 LangChain 버전에서 `extra_body`로 전달한다. |
| 대화 이력 | LangGraph Postgres 체크포인터를 정본으로 유지한다. OpenAI `previous_response_id` 체인은 사용하지 않아 이력을 이중 관리하지 않는다. |
| 프로바이더 추상화 | ADR-0001 의 LangChain `ChatOpenAI` 추상화·`openai:<model>` 형식을 유지한다. |
| 운영 반영 | Fly 시크릿 `AGENT_MODEL`/`VLM_MODEL`=`openai:gpt-5.6-luna` 를 `jippin`(운영)·`jippin-dev`(개발) 양쪽에 설정 완료(2026-08-19, 시크릿이 코드 기본값에 우선). |

## 결과 / 트레이드오프

- **비용·지연은 운영 관찰 대상**이다. gpt-5.6-luna 는 5.4-mini 대비 단가가 높다 — 세션당
  토큰 사용량 추적(LangSmith)으로 확인하고, 문제 시 `AGENT_MODEL`/`VLM_MODEL` 시크릿만
  되돌리면 즉시 롤백된다(코드 배포 불필요).
- 두 설정이 분리되어 있으므로 "대화만 저비용 모델로 내리고 VLM 은 유지" 같은 부분 조정이
  가능하다.
- ADR-0001 의 "gpt-5 계열 = 가공 모델명" 판정은 2026-05 시점 기준이었다 — 현 시점 실제
  가용 모델로 확인되어 본 ADR 로 대체한다.
- Responses API 응답은 텍스트 외 reasoning 블록을 포함할 수 있다. SSE 번역기는 `text`
  블록만 사용자 메시지로 투영하며 reasoning 블록은 노출하지 않는다.
