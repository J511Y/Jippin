"""자주묻는질문(FAQ) Pydantic 계약 (CMP-DIRECT).

DB 정본은 ``supabase/migrations/..._0011_faqs_v2.sql`` 의 ``faqs`` 테이블이다.

``GET /faqs`` 는 공개 노출(is_published=true) FAQ 를 전역 정렬(sort_order) 순 평면
목록으로 반환하고, ``GET /faqs/{faq_id}`` 는 상세 한 건을 반환한다. 카테고리
필터·검색·페이징과 한국어 라벨·카테고리 순서는 프론트(`lib/faq.ts`)가 소유한다.
``answer`` 는 마크다운 텍스트다(렌더링은 프론트 책임).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FaqItem(BaseModel):
    """공개 FAQ 한 건. ``id`` 는 상세 URL(`/faq/{faqId}`)에 쓰는 identity 정수."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    categories: list[str]
    question: str
    answer: str
    sort_order: int


class FaqListResponse(BaseModel):
    items: list[FaqItem]
