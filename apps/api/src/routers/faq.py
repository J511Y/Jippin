"""자주묻는질문(FAQ) 라우터 (CMP-DIRECT).

``GET /faqs`` 는 공개 콘텐츠라 인증을 요구하지 않는다. 공개 노출(is_published=true)
FAQ 를 카테고리/정렬 순 평면 목록으로 반환하며, 그룹핑·라벨링은 프론트가 처리한다.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas.faq import FaqListResponse
from ..services import faq as faq_service

router = APIRouter(prefix="/faqs", tags=["faqs"])


@router.get("", response_model=FaqListResponse)
async def list_faqs() -> FaqListResponse:
    rows = await faq_service.list_published_faqs()
    return FaqListResponse.model_validate({"items": rows})
