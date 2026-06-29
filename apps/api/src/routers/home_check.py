"""우리집 체크(home-check) 라우터 (ADR-0008).

집합건축물대장 전유부+표제부를 CODEF 로 비동기 조회한다. ``POST /home-check`` 가 잡 행을
만들고 즉시 202(``HomeCheckJob``)를 돌려준 뒤, 백그라운드 태스크가 **요청과 분리된 새 DB
연결**로 조회 결과를 반영한다(``services.home_check``).

비회원(Supabase Anonymous Sign-In)도 조회할 수 있다(``require_supabase_request_user``,
ADR-0008 §2.3). 이력 조회(``/mine``)는 로그인 회원만 가능하다(/leads/mine 와 동일).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.home_check import (
    HomeCheckContinueRequest,
    HomeCheckCreateRequest,
    HomeCheckJob,
    MyHomeChecksResponse,
)
from ..services import home_check as home_check_service

logger = get_logger("zippin.home_check")
router = APIRouter(prefix="/home-check", tags=["home-check"])


def _not_found() -> ZippinException:
    return ZippinException(
        "우리집 체크 조회를 찾을 수 없습니다.",
        code="HOME_CHECK_NOT_FOUND",
        http_status=404,
    )


@router.post("", response_model=HomeCheckJob, status_code=202)
async def create_home_check(
    payload: HomeCheckCreateRequest,
    background_tasks: BackgroundTasks,
    requester: RequestUser = Depends(require_supabase_request_user),
) -> HomeCheckJob:
    row = await home_check_service.create_home_check(
        user_id=requester.user_id,
        is_anonymous=requester.is_anonymous,
        road_addr=payload.road_addr,
        jibun_addr=payload.jibun_addr,
        dong=payload.dong,
        ho=payload.ho,
    )
    # 주소·동·호는 PII 가 될 수 있어 로깅하지 않는다 — 잡 id/익명여부만 남긴다.
    logger.info(
        "home_check_created",
        home_check_id=str(row["id"]),
        is_anonymous=requester.is_anonymous,
    )
    # 백그라운드 조회 — 응답(202) 이후 새 DB 연결로 행을 갱신한다(요청 세션 재사용 금지).
    background_tasks.add_task(
        home_check_service.run_home_check,
        row["id"],
        road_addr=payload.road_addr,
        jibun_addr=payload.jibun_addr,
        dong=payload.dong,
        ho=payload.ho,
    )
    return await home_check_service.serialize_job(row, with_documents=False)


@router.get("/mine", response_model=MyHomeChecksResponse)
async def list_my_home_checks(
    requester: RequestUser = Depends(require_supabase_request_user),
) -> MyHomeChecksResponse:
    """마이페이지 우리집 체크 이력 — 로그인한 회원 본인 잡만 반환한다."""

    if requester.is_anonymous:
        raise ZippinException(
            "우리집 체크 이력 조회는 로그인한 회원만 가능합니다.",
            code="AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED",
            http_status=403,
        )
    rows = await home_check_service.list_home_checks_for_user(user_id=requester.user_id)
    # 목록은 외부 서명 URL 발급을 생략하되(with_documents=False), report 의 address+signal 은
    # serialize_job 가 채운다.
    items = [
        await home_check_service.serialize_job(row, with_documents=False)
        for row in rows
    ]
    return MyHomeChecksResponse(items=items)


@router.get("/{home_check_id}", response_model=HomeCheckJob)
async def get_home_check(
    home_check_id: uuid.UUID,
    requester: RequestUser = Depends(require_supabase_request_user),
) -> HomeCheckJob:
    row = await home_check_service.get_home_check_row(
        home_check_id=home_check_id, user_id=requester.user_id
    )
    if row is None:
        raise _not_found()
    return await home_check_service.serialize_job(row)


@router.post("/{home_check_id}/continue", response_model=HomeCheckJob)
async def continue_home_check(
    home_check_id: uuid.UUID,
    payload: HomeCheckContinueRequest,
    background_tasks: BackgroundTasks,
    requester: RequestUser = Depends(require_supabase_request_user),
) -> HomeCheckJob:
    row = await home_check_service.get_home_check_row(
        home_check_id=home_check_id, user_id=requester.user_id
    )
    if row is None:
        raise _not_found()
    if row["status"] != "needs_input":
        raise ZippinException(
            "추가 입력이 필요한 상태가 아닙니다.",
            code="HOME_CHECK_NOT_RESUMABLE",
            http_status=409,
        )

    fields = row.get("result_fields") or {}
    resume_token = fields.get("resume_token")
    if not resume_token:
        raise ZippinException(
            "재개 정보가 없어 처음부터 다시 조회해 주세요.",
            code="HOME_CHECK_NOT_RESUMABLE",
            http_status=409,
        )

    # 잡을 다시 querying 으로 되돌리고 백그라운드 재개(재개는 항상 전유부).
    await home_check_service.reset_for_resume(home_check_id)
    background_tasks.add_task(
        home_check_service.resume_home_check,
        home_check_id,
        resume_token=resume_token,
        selection=payload.selection,
        dong=payload.dong,
        ho=payload.ho,
        secure_no=payload.secure_no,
        other_road_addr=row.get("road_addr") or "",
        other_jibun_addr=row.get("jibun_addr"),
        other_dong=row.get("addr_dong") or "",
        other_ho=row.get("addr_ho") or "",
    )
    logger.info(
        "home_check_resumed",
        home_check_id=str(home_check_id),
    )
    refreshed = await home_check_service.get_home_check_row(
        home_check_id=home_check_id, user_id=requester.user_id
    )
    return await home_check_service.serialize_job(refreshed or row)
