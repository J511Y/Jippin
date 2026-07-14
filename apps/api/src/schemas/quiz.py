"""대기 화면 퀴즈 Pydantic 계약 (우리집 체크).

DB 정본은 ``supabase/migrations/..._0023_quizzes.sql`` 의 ``quizzes`` 테이블이다.

``GET /quizzes`` 는 공개 노출(is_published=true) 퀴즈를 전역 정렬(sort_order) 순 평면
목록으로 반환한다. 셔플·카테고리 필터·한국어 라벨은 프론트(`lib/quiz.ts`)가 소유한다.
``choices``(2~5개)+``answer_index``(0-base) 가 객관식 일반형이고 O/X 는
``choices=['O','X']`` 특수 케이스다. ``explanation`` 은 마크다운(렌더링은 프론트 책임).

운영 편집형 콘텐츠 엔드포인트는 packages/contracts 스키마 대상이 아니다(FAQ 관례) —
pydantic + 프론트 런타임 검증(parseQuizItem)으로 계약을 지킨다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QuizItem(BaseModel):
    """공개 퀴즈 한 건. 정답(answer_index)을 포함해 내려준다 — 대기 화면 오락용
    콘텐츠라 클라이언트 판정으로 충분하다(채점·보상 없음)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    categories: list[str]
    question: str
    choices: list[str]
    answer_index: int
    explanation: str
    sort_order: int


class QuizListResponse(BaseModel):
    items: list[QuizItem]
