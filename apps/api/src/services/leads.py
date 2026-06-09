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

from ..config import get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..models import ConsultationLead, ConsultationLeadAttachment

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

    attachments = _validate_attachments(
        list(payload.get("attachments") or []),
        user_id=user_id,
        default_bucket=settings.lead_floorplan_bucket,
    )
    return await _insert_lead(lead_values, attachments)


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

    try:
        if http_client is not None:
            response = await _run(http_client)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await _run(client)
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
