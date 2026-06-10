"""자주묻는질문(FAQ) Pydantic 계약 (CMP-DIRECT).

DB 정본은 ``supabase/migrations/..._0010_faqs.sql`` 의 ``faqs`` 테이블이다.

``GET /faqs`` 는 공개 노출(is_published=true) FAQ 를 카테고리/정렬 순으로 평면 목록으로
반환한다. 카테고리 그룹핑·한국어 라벨·카테고리 순서는 프론트(`lib/faq.ts`)가 소유한다.
``answer`` 는 마크다운 텍스트다(렌더링은 프론트 책임).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class FaqItem(BaseModel):
    """공개 FAQ 한 건."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    question: str
    answer: str
    sort_order: int


class FaqListResponse(BaseModel):
    items: list[FaqItem]
