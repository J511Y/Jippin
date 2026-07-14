"""대기 화면 퀴즈 라우터 (우리집 체크).

``GET /quizzes`` 는 공개 콘텐츠라 인증을 요구하지 않는다. 공개 노출(is_published=true)
퀴즈를 전역 정렬 순 평면 목록으로 반환하며, 셔플·카테고리 필터·라벨링은 프론트가
처리한다(faq 라우터 미러 — 상세 페이지가 없어 단건 경로는 두지 않는다).
"""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas.quiz import QuizListResponse
from ..services import quiz as quiz_service

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.get("", response_model=QuizListResponse)
async def list_quizzes() -> QuizListResponse:
    rows = await quiz_service.list_published_quizzes()
    return QuizListResponse.model_validate({"items": rows})
