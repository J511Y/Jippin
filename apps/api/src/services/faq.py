"""자주묻는질문(FAQ) 서비스 (CMP-DIRECT).

공개 노출 FAQ 를 카테고리/정렬 순으로 조회한다. FAQ 는 PII 가 아니라 공개 콘텐츠지만,
읽기 경로는 다른 도메인 테이블과 동일하게 백엔드(``get_engine``)를 통하며 권한 role 로
접속해 RLS 를 우회 SELECT 한다.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from ..db import get_engine
from ..models import Faq


async def list_published_faqs() -> list[dict[str, Any]]:
    """공개(is_published=true) FAQ 를 카테고리 → 정렬값 → 생성순으로 반환한다.

    카테고리 그룹핑과 한국어 라벨/카테고리 순서는 프론트가 소유하므로, 여기서는
    안정적인 결정적 순서(카테고리, sort_order, created_at)만 보장한다.
    """

    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(
                    Faq.id,
                    Faq.category,
                    Faq.question,
                    Faq.answer,
                    Faq.sort_order,
                )
                .where(Faq.is_published.is_(True))
                .order_by(
                    Faq.category,
                    Faq.sort_order,
                    Faq.created_at,
                )
                .limit(500)
            )
        ).all()
    return [dict(row._mapping) for row in rows]
