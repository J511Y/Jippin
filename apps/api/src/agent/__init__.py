"""에이전트 세션 (우리집 체크 대화형 에이전트) 런타임 패키지 — CMP-DIRECT.

deepagents(LangGraph) 기반. 무거운 의존성(langchain/deepagents/langgraph)은
모듈 import 시점이 아니라 함수 내부에서 lazy import 한다 — agent_enabled 가 꺼진
환경(테스트/CI 포함)에서도 ``src`` import 가 깨지지 않도록 하기 위함이다.

레이어:
- ``events``     : SSE 이벤트 envelope 빌더(순수).
- ``projection`` : astream 정규화 이벤트 → chat_messages/chat_tool_calls/sessions
                   투영 writer(순수, main_flow 의존). idempotent(resume-safe).
- ``tools``      : 우리집 체크 플로우 도구 + HF 세그멘테이션(실패 처리 포함).
- ``prompts``    : system/sub-agent 프롬프트.
- ``checkpointer``: LangGraph Postgres 체크포인터(전용 langgraph 스키마) + verify.
- ``graph``      : create_deep_agent 팩토리.
- ``runner``     : 런 라이프사이클 + SSE 스트리밍 + 투영 연결.
"""

from __future__ import annotations
