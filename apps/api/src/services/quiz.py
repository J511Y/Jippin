"""대기 화면 퀴즈 서비스 (우리집 체크).

공개 노출 퀴즈를 전역 정렬 순으로 조회한다. 퀴즈는 PII 가 아니라 공개 콘텐츠지만,
읽기 경로는 다른 도메인 테이블과 동일하게 백엔드(``get_engine``)를 통하며 권한 role 로
접속해 RLS 를 우회 SELECT 한다(faq 서비스 미러).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from ..db import get_engine
from ..models import Quiz

_QUIZ_COLUMNS = (
    Quiz.id,
    Quiz.categories,
    Quiz.question,
    Quiz.choices,
    Quiz.answer_index,
    Quiz.explanation,
    Quiz.sort_order,
)


async def list_published_quizzes() -> list[dict[str, Any]]:
    """공개(is_published=true) 퀴즈를 정렬값 → 생성순으로 반환한다.

    셔플(대기 화면 다양성)·카테고리 필터와 한국어 라벨은 프론트가 소유하므로,
    여기서는 안정적인 결정적 순서(sort_order, created_at)만 보장한다.
    """

    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(*_QUIZ_COLUMNS)
                .where(Quiz.is_published.is_(True))
                .order_by(Quiz.sort_order, Quiz.created_at)
                .limit(500)
            )
        ).all()
    return [dict(row._mapping) for row in rows]
