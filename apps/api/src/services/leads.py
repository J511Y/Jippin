"""상담 리드(consultation leads) 서비스 (CMP-DIRECT).

DB-backed 다 — Phase A skeleton 의 in-memory store(``main_flow``)와 달리 실
``consultation_leads`` / ``consultation_lead_attachments`` row 에 INSERT 한다. DB write
는 기존 ``middleware/request_log`` 와 동일하게 ``get_engine().begin()`` 경로를 쓴다.

비고:

- 비회원(익명 Supabase 세션)도 리드를 만들 수 있다. ``user_id`` 는 nullable 이며 익명
  여부는 ``is_anonymous`` 로 보존한다.
- 첨부 object_path 는 ``<auth.uid()>/<file>`` 규약이다(Storage RLS owner-folder).
  서비스단에서 첫 폴더가 호출자 ``user_id`` 와 일치하는지 검증해 타인 오브젝트가
  리드에 기록되는 것을 막는다.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import sqlalchemy as sa

from . import main_flow
from ..config import get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..logging import log_http_call
from ..models import ConsultationLead, ConsultationLeadAttachment, HomeCheck

# consultation_leads 로 그대로 들어가는 컬럼 화이트리스트(서비스/인증 제어 컬럼 제외).
_LEAD_FIELDS: tuple[str, ...] = (
    "source_form",
    "applicant_kind",
    "applicant_name",
    "applicant_phone",
    "road_addr_part1",
    "road_addr_part2",
    "road_addr_detail",
    "expansion_location",
    "ownership_status",
    "construction_start_date",
    "construction_end_date",
    "inflow_source",
    "message",
)


def _bad_request(message: str, code: str) -> ZippinException:
    return ZippinException(message, code=code, http_status=422)


def session_address_display(addr: dict[str, Any] | None) -> str | None:
    """세션 주소 row 를 표시용 한 줄 주소로 환산한다(상담 리드 road_addr_part1·카드 prefill).

    도로명/지번이 있으면 그대로, 없으면 아파트명+동+호로 폴백한다 — 사전검토는
    아파트명만으로도 주소를 확정할 수 있어(``confirm_address_impl``), 도로명이 없는
    세션에서 만든 상담 리드의 주소가 공란이 되던 문제를 막는다(0019).
    """

    if not isinstance(addr, dict):
        return None
    for key in ("road_address", "jibun_address"):
        value = (addr.get(key) or "").strip()
        if value:
            return value
    parts = [
        str(addr[key]).strip()
        for key in ("apartment_name", "building_dong", "unit_ho")
        if addr.get(key)
    ]
    joined = " ".join(part for part in parts if part)
    return joined or None


async def _resolve_precheck_session(
    *, session_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[uuid.UUID | None, str | None]:
    """사전검토 세션 귀속을 해석한다(본인 세션일 때만).

    ``(linked_session_id, address_fallback)`` 를 돌린다 — 타인/부재 세션 id 는 무시해
    (IDOR/오귀속 방지) ``(None, None)`` 이다. address_fallback 은 세션 확정 주소(도로명/
    지번, 없으면 아파트명+동+호)로, 호출자가 road_addr_part1 이 비어 있을 때만 채운다.
    조회 실패는 연결만 생략하고 상담 접수 자체를 막지 않는다(best-effort).
    """

    try:
        session = await main_flow._db_select_session(session_id)
    except Exception:  # noqa: BLE001 - 세션 조회 실패는 연결을 생략(상담 접수는 진행)
        return None, None
    if session is None or session.get("user_id") != user_id:
        return None, None
    try:
        display = session_address_display(
            await main_flow.get_session_address(session_id)
        )
    except Exception:  # noqa: BLE001 - 주소 폴백 실패는 연결만 남기고 진행
        display = None
    return session_id, (display[:255] if display else None)


def _validate_attachments(
    attachments: list[dict[str, Any]],
    *,
    user_id: uuid.UUID,
    default_bucket: str,
) -> list[dict[str, Any]]:
    """첨부를 검증·정규화한다. owner-folder 규약 위반은 422."""

    normalized: list[dict[str, Any]] = []
    for item in attachments:
        object_path = str(item.get("object_path") or "").strip()
        if not object_path:
            raise _bad_request(
                "첨부 object_path 가 비어 있습니다.",
                code="LEAD_ATTACHMENT_INVALID",
            )
        # Storage owner-folder 규약: 경로 첫 세그먼트가 업로더 uid 여야 한다.
        first_segment = object_path.split("/", 1)[0]
        if first_segment != str(user_id):
            raise _bad_request(
                "첨부 경로가 신청자 소유 폴더가 아닙니다.",
                code="LEAD_ATTACHMENT_OWNER_MISMATCH",
            )
        normalized.append(
            {
                "bucket": (item.get("bucket") or default_bucket),
                "object_path": object_path,
                "file_name": item.get("file_name"),
                "content_type": item.get("content_type"),
                "byte_size": item.get("byte_size"),
            }
        )
    return normalized


async def _insert_lead(
    lead_values: dict[str, Any],
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    """단일 트랜잭션으로 lead + attachments INSERT. 테스트 monkeypatch seam.

    반환은 ``LeadResponse`` 가 ``from_attributes`` 로 읽을 수 있는 dict 다.
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(ConsultationLead)
                .values(**lead_values)
                .returning(
                    ConsultationLead.id,
                    ConsultationLead.source_form,
                    ConsultationLead.status,
                    ConsultationLead.created_at,
                )
            )
        ).one()
        lead_id = row.id
        if attachments:
            await conn.execute(
                sa.insert(ConsultationLeadAttachment),
                [{"lead_id": lead_id, **att} for att in attachments],
            )
    return {
        "id": row.id,
        "source_form": row.source_form,
        "status": row.status,
        "created_at": row.created_at,
    }


async def create_lead(
    *,
    user_id: uuid.UUID,
    is_anonymous: bool,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """리드 한 건을 생성한다. ``payload`` 는 ``LeadCreateRequest.model_dump()``."""

    settings = get_settings()
    lead_values: dict[str, Any] = {field: payload.get(field) for field in _LEAD_FIELDS}
    lead_values["user_id"] = user_id
    lead_values["is_anonymous"] = is_anonymous

    # 사전검토 세션 귀속 — 본인 세션이면 session_id 를 연결하고, 주소가 비어 있으면 세션
    # 확정 주소(아파트명 포함)로 폴백해 상담 메뉴 주소 공란을 막는다(0019).
    session_id = payload.get("session_id")
    if session_id is not None:
        linked_session_id, address_fallback = await _resolve_precheck_session(
            session_id=session_id, user_id=user_id
        )
        if linked_session_id is not None:
            lead_values["session_id"] = linked_session_id
            if address_fallback and not (lead_values.get("road_addr_part1") or "").strip():
                lead_values["road_addr_part1"] = address_fallback

    attachments = _validate_attachments(
        list(payload.get("attachments") or []),
        user_id=user_id,
        default_bucket=settings.lead_floorplan_bucket,
    )
    row = await _insert_lead(lead_values, attachments)
    # 사전검토 세션에서 온 상담이면 그 세션을 handoff(상담 전환)로 전진(best-effort).
    if lead_values.get("session_id") is not None:
        await main_flow.advance_session_status(
            session_id=lead_values["session_id"],
            target="handoff",
            reason="consultation_submitted",
        )
    # 우리집 체크 인입이면 원천 잡에 귀속 연결(소유자 본인 잡만, best-effort).
    home_check_id = payload.get("home_check_id")
    if home_check_id:
        await _link_home_check(
            home_check_id=home_check_id, lead_id=row["id"], user_id=user_id
        )
    return row


async def _link_home_check(
    *, home_check_id: uuid.UUID, lead_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """우리집 체크 잡(home_checks)에 생성된 상담 리드를 연결한다.

    소유자(user_id) 본인의 잡만 갱신한다 — 타인 잡은 조용히 무시(IDOR 방지). 연결 실패가
    상담 접수 자체를 막지 않도록 별도 트랜잭션의 best-effort 다.
    """

    async with get_engine().begin() as conn:
        await conn.execute(
            sa.update(HomeCheck)
            .where(HomeCheck.id == home_check_id, HomeCheck.user_id == user_id)
            .values(consultation_lead_id=lead_id)
        )


async def reassign_leads_owner(
    *, from_user_id: uuid.UUID, to_user_id: uuid.UUID
) -> int:
    """익명 user 의 리드를 영구 계정으로 이관한다(이메일 가입 시 anonymous claim).

    호출자(라우터)는 ``from_user_id`` 소유권을 익명 Supabase 토큰으로 검증한 뒤에만
    호출해야 한다. 이관된 행 수를 반환한다.
    """

    if from_user_id == to_user_id:
        return 0
    async with get_engine().begin() as conn:
        result = await conn.execute(
            sa.update(ConsultationLead)
            .where(ConsultationLead.user_id == from_user_id)
            .values(user_id=to_user_id, is_anonymous=False)
        )
    return result.rowcount or 0


async def list_leads_for_user(*, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """본인(user_id)이 신청한 상담 리드를 최신순으로 조회한다(마이페이지 상담 현황)."""

    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(
                    ConsultationLead.id,
                    ConsultationLead.source_form,
                    ConsultationLead.status,
                    ConsultationLead.applicant_name,
                    ConsultationLead.road_addr_part1,
                    ConsultationLead.road_addr_part2,
                    ConsultationLead.expansion_location,
                    ConsultationLead.created_at,
                )
                .where(ConsultationLead.user_id == user_id)
                .order_by(ConsultationLead.created_at.desc())
                .limit(100)
            )
        ).all()
    return [dict(row._mapping) for row in rows]


async def get_lead_contact(*, lead_id: uuid.UUID) -> dict[str, Any] | None:
    """알림톡 발송용 최소 연락 정보(이름/전화번호)만 조회한다 — 그 외 PII 는 읽지 않는다."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(
                    ConsultationLead.id,
                    ConsultationLead.applicant_name,
                    ConsultationLead.applicant_phone,
                ).where(ConsultationLead.id == lead_id)
            )
        ).first()
    return dict(row._mapping) if row else None


# ---------------------------------------------------------------------------
# 도로명주소 검색 프록시 (business.juso.go.kr addrLinkApi.do)
# ---------------------------------------------------------------------------


def _normalize_juso_item(juso: dict[str, Any]) -> dict[str, Any]:
    return {
        "road_addr": juso.get("roadAddr") or "",
        "road_addr_part1": juso.get("roadAddrPart1") or "",
        "road_addr_part2": juso.get("roadAddrPart2") or "",
        "jibun_addr": juso.get("jibunAddr") or None,
        "zip_no": juso.get("zipNo") or None,
        "bd_nm": juso.get("bdNm") or None,
        "si_nm": juso.get("siNm") or None,
        "sgg_nm": juso.get("sggNm") or None,
        "emd_nm": juso.get("emdNm") or None,
    }


async def search_addresses(
    *,
    keyword: str,
    page: int = 1,
    per_page: int = 10,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """도로명주소 API 를 프록시한다. 승인키는 서버측에만 둔다."""

    settings = get_settings()
    if not settings.juso_confm_key:
        raise ZippinException(
            "도로명주소 API 승인키가 설정되지 않았습니다.",
            code="JUSO_CONFM_KEY_MISSING",
            http_status=503,
        )

    keyword = (keyword or "").strip()
    if not keyword:
        raise _bad_request("검색어를 입력해 주세요.", code="ADDRESS_KEYWORD_REQUIRED")

    params = {
        "confmKey": settings.juso_confm_key,
        "currentPage": str(page),
        "countPerPage": str(per_page),
        "keyword": keyword,
        "resultType": "json",
    }

    async def _run(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(settings.juso_api_url, params=params)

    async def _do() -> httpx.Response:
        if http_client is not None:
            return await _run(http_client)
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await _run(client)

    try:
        # 검색어(keyword)는 PII 가 될 수 있으므로 로깅하지 않는다 — status/소요시간만 남긴다.
        response = await log_http_call("juso", "search_addresses", _do)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ZippinException(
            "도로명주소 API 호출에 실패했습니다.",
            code="JUSO_API_UNAVAILABLE",
            http_status=502,
        ) from exc

    results = body.get("results") or {}
    common = results.get("common") or {}
    error_code = common.get("errorCode")
    if error_code not in (None, "0"):
        raise ZippinException(
            common.get("errorMessage") or "도로명주소 검색에 실패했습니다.",
            code="JUSO_API_ERROR",
            http_status=502,
            details={"juso_error_code": error_code},
        )

    juso_list = results.get("juso") or []
    return {
        "total_count": int(common.get("totalCount") or 0),
        "page": page,
        "per_page": per_page,
        "items": [_normalize_juso_item(j) for j in juso_list],
    }
