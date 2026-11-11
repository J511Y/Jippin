"""파트너(서버 간) 건축물대장 발급 라우터 (ADR-0012).

사내 업무 시스템 "워크"가 의뢰 생성 시 전유부+표제부를 백그라운드로 발급받는다. 세움터
워커는 Fly 사설망에서 api 만 닿을 수 있고 ``/home-check`` 는 소비자 Supabase JWT 를 요구하므로,
토큰으로 보호한 제출/폴링 표면을 따로 둔다.

- ``POST   /partner/building-registers``          잡 제출(202, Idempotency-Key 필수)
- ``GET    /partner/building-registers/{job_id}`` 상태·결과 폴링
- ``DELETE /partner/building-registers/{job_id}`` 결과 즉시 삭제(ack, 204)

오류 본문은 호출자와 고정한 ``{"detail": "..."}`` 이다(AGENTS.md §4.5 봉투가 아니다 —
본문 검증 실패 422 만 공통 핸들러의 봉투로 나간다).

개인정보: 주소·동·호·PDF 는 로그에 남기지 않고, 요청 본문은 request_logs 에 저장하지
않는다(``middleware.request_log.BODY_SKIP_SUBSTRINGS``).
"""

from __future__ import annotations

import hmac
import re
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import get_settings
from ..logging import get_logger
from ..services import partner_building_register as partner_service

logger = get_logger("zippin.partner_building_register")

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_IDEMPOTENCY_KEY_MAX = 200


class PartnerApiError(Exception):
    """파트너 API 전용 오류 — ``{"detail": ...}`` 본문으로 응답한다."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def partner_api_error_handler(
    request: Request, exc: PartnerApiError
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def require_partner_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = (get_settings().partner_api_token or "").strip()
    if not expected:
        raise PartnerApiError(503, "partner api disabled")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token.strip().encode("utf-8"), expected.encode("utf-8")
    ):
        raise PartnerApiError(401, "invalid partner token")


router = APIRouter(
    prefix="/partner/building-registers",
    tags=["partner"],
    dependencies=[Depends(require_partner_token)],
)


class PartnerBuildingRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    road_addr: str = Field(min_length=1, max_length=255)
    jibun_addr: str | None = None
    dong: str = ""
    ho: str = ""
    kinds: list[Literal["exclusive", "heading"]] = Field(
        default_factory=lambda: ["exclusive", "heading"], min_length=1
    )

    @field_validator("kinds")
    @classmethod
    def _dedupe_kinds(cls, value: list[str]) -> list[str]:
        # 순서를 고정하고 중복을 없앤다 — 뒤 단계는 "둘 다 / 하나만" 만 구분한다.
        return [kind for kind in ("exclusive", "heading") if kind in value]


class PartnerBuildingRegisterAccepted(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done"]


def _store_unavailable() -> PartnerApiError:
    return PartnerApiError(503, "partner job store unavailable")


def _not_found() -> PartnerApiError:
    return PartnerApiError(404, "job not found")


@router.post("", response_model=PartnerBuildingRegisterAccepted, status_code=202)
async def submit_building_register(
    payload: PartnerBuildingRegisterRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PartnerBuildingRegisterAccepted:
    key = (idempotency_key or "").strip()
    if not key or len(key) > _IDEMPOTENCY_KEY_MAX:
        raise PartnerApiError(400, "Idempotency-Key header is required (1..200 chars)")

    try:
        job, created = await partner_service.submit_job(
            idempotency_key=key, kinds=payload.kinds
        )
    except partner_service.PartnerJobStoreUnavailable as exc:
        raise _store_unavailable() from exc

    if created:
        background_tasks.add_task(
            partner_service.run_job,
            job["job_id"],
            road_addr=payload.road_addr,
            jibun_addr=payload.jibun_addr,
            dong=payload.dong,
            ho=payload.ho,
            kinds=payload.kinds,
        )
    logger.info(
        "partner_building_register_submitted",
        job_id=job["job_id"],
        kinds=payload.kinds,
        created=created,
    )
    return PartnerBuildingRegisterAccepted(job_id=job["job_id"], status=job["status"])


@router.get("/{job_id}")
async def get_building_register(job_id: str) -> dict[str, Any]:
    if not _JOB_ID_RE.match(job_id):
        raise _not_found()
    try:
        job = await partner_service.get_job(job_id)
    except partner_service.PartnerJobStoreUnavailable as exc:
        raise _store_unavailable() from exc
    if job is None:
        raise _not_found()

    body: dict[str, Any] = {"job_id": job["job_id"], "status": job["status"]}
    if job["status"] == "done":
        body["results"] = job.get("results") or {}
    return body


@router.delete("/{job_id}", status_code=204)
async def delete_building_register(job_id: str) -> Response:
    if _JOB_ID_RE.match(job_id):
        try:
            await partner_service.delete_job(job_id)
        except partner_service.PartnerJobStoreUnavailable as exc:
            raise _store_unavailable() from exc
        logger.info("partner_building_register_deleted", job_id=job_id)
    return Response(status_code=204)
