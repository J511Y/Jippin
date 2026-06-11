"""자주묻는질문(FAQ) 라우터 (CMP-DIRECT).

``GET /faqs``·``GET /faqs/{faq_id}`` 는 공개 콘텐츠라 인증을 요구하지 않는다.
목록은 공개 노출(is_published=true) FAQ 를 전역 정렬 순 평면 목록으로 반환하며,
카테고리 필터·검색·페이징·라벨링은 프론트가 처리한다. 상세는 비공개/부재 행을
동일하게 404 로 처리한다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.faq import FaqItem, FaqListResponse
from ..services import faq as faq_service

router = APIRouter(prefix="/faqs", tags=["faqs"])


@router.get("", response_model=FaqListResponse)
async def list_faqs() -> FaqListResponse:
    rows = await faq_service.list_published_faqs()
    return FaqListResponse.model_validate({"items": rows})


@router.get("/{faq_id}", response_model=FaqItem)
async def get_faq(faq_id: int) -> FaqItem:
    row = await faq_service.get_published_faq(faq_id)
    if row is None:
        # 전역 핸들러(errors.py)가 이 detail 을 `{ error: { message } }` 봉투의
        # message 로 옮긴다. 웹(`apps/web/lib/faq.ts`)이 그 메시지로 "부재 404" 와
        # "라우트가 없는 구버전 API 404(Not Found)" 를 구분한다 — 변경 시 동기화.
        raise HTTPException(status_code=404, detail="FAQ not found")
    return FaqItem.model_validate(row)
