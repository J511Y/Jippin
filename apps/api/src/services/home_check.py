"""우리집 체크(home-check) 서비스 — CODEF 전유부+표제부 조회 오케스트레이션 (ADR-0008).

라우터(``routers/home_check``)가 잡 행을 만들고 즉시 202 를 돌려준 뒤, 본 모듈의
백그라운드 처리(``run_home_check`` / ``resume_home_check``)가 **요청과 분리된 새 DB
연결**로 행을 갱신한다(요청 세션 재사용 금지 — 요청 종료 후 실행되기 때문).

판정/직렬화 매핑(행 → ``HomeCheckJob``)도 여기에 둔다.

PII 정책(ADR-0008 §2.3): 소유자/설계자 성명·주민번호·세움터 password 는 DB/로그/Redis
어디에도 저장하지 않는다. CODEF 클라이언트가 이미 이를 미노출하며(types.py), 본 모듈도
``resOwnedList`` 등에서 PII 필드를 읽지 않는다. 발급 PDF 만 Storage 에 원본 보관한다.
"""

from __future__ import annotations

import base64
import uuid
from datetime import date, datetime, timezone
from typing import Any

import httpx
import sqlalchemy as sa

from ..config import Settings, get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..logging import get_logger, log_http_call
from ..models import HomeCheck, HomeCheckDocument
from ..schemas.home_check import (
    AddressInfo,
    BuildingHeading,
    ChangeEntry,
    DocumentRef,
    ErrorInfo,
    ExclusivePart,
    HomeCheckJob,
    HomeCheckReport,
    MyHomeChecksResponse,
    NeedsInput,
    PriceEntry,
    ReportMeta,
    Violation,
)
from ..services.codef import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefBuildingRegisterClient,
    CodefError,
    CodefNeedsUserInput,
    ExclusivePartResult,
)

logger = get_logger("zippin.home_check")

DISCLAIMER = (
    "본 결과는 건축물대장 기재사항을 조회 시점 기준으로 제공하는 참고용 정보이며, "
    "위법 여부의 최종 판단은 관할 행정청·전문가 확인이 필요합니다."
)

_VIOLATION_VALUE = "위반건축물"
_SCHEMA_VERSION = "1.0.0"

# re-export 로 라우터가 services 경유로 응답 모델을 쓰게 한다(기존 컨벤션 유지).
__all__ = ["MyHomeChecksResponse"]

# 사용자 안전 메시지 — CodefError 종류별 안내. 원자료/자격증명은 절대 노출하지 않는다.
_ERROR_MESSAGES: dict[str, str] = {
    "CodefAuthError": "조회 서비스 인증에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "CodefCircuitOpen": "조회 서비스가 일시적으로 혼잡합니다. 잠시 후 다시 시도해 주세요.",
    "CodefUpstreamError": "건축물대장 시스템(세움터) 점검 또는 지연으로 조회에 실패했습니다.",
    "CodefNotFound": "입력하신 주소·동·호에 해당하는 건축물대장을 찾지 못했습니다.",
    "CodefInvalidInput": "입력하신 주소 형식이 올바르지 않습니다. 다시 확인해 주세요.",
}
_ERROR_CODES: dict[str, str] = {
    "CodefAuthError": "UPSTREAM_AUTH",
    "CodefCircuitOpen": "UPSTREAM_BUSY",
    "CodefUpstreamError": "UPSTREAM_UNAVAILABLE",
    "CodefNotFound": "NOT_FOUND",
    "CodefInvalidInput": "INVALID_ADDRESS",
}


# ---------------------------------------------------------------------------
# 잡 행 생성 / 조회 (요청 경로 — pooler engine).
# ---------------------------------------------------------------------------
async def create_home_check(
    *,
    user_id: uuid.UUID,
    is_anonymous: bool,
    road_addr: str,
    jibun_addr: str | None,
    dong: str,
    ho: str,
) -> dict[str, Any]:
    """우리집 체크 잡 한 건을 status='querying' 으로 생성한다."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(HomeCheck)
                .values(
                    user_id=user_id,
                    is_anonymous=is_anonymous,
                    status="querying",
                    road_addr=road_addr,
                    jibun_addr=jibun_addr,
                    addr_dong=dong or None,
                    addr_ho=ho,
                )
                .returning(
                    HomeCheck.id,
                    HomeCheck.status,
                    HomeCheck.created_at,
                    HomeCheck.updated_at,
                )
            )
        ).one()
    return dict(row._mapping)


async def get_home_check_row(
    *, home_check_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, Any] | None:
    """소유자(user_id) 본인의 잡 한 건을 조회한다. 타인/없음 → None."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(HomeCheck).where(
                    HomeCheck.id == home_check_id,
                    HomeCheck.user_id == user_id,
                )
            )
        ).first()
    return dict(row._mapping) if row else None


async def list_home_checks_for_user(*, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """본인(user_id)의 우리집 체크 이력을 최신순으로 조회한다(마이페이지)."""

    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(HomeCheck)
                .where(HomeCheck.user_id == user_id)
                .order_by(HomeCheck.created_at.desc())
                .limit(100)
            )
        ).all()
    return [dict(row._mapping) for row in rows]


async def _load_documents(conn: Any, home_check_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await conn.execute(
            sa.select(
                HomeCheckDocument.kind,
                HomeCheckDocument.bucket,
                HomeCheckDocument.object_path,
            ).where(HomeCheckDocument.home_check_id == home_check_id)
        )
    ).all()
    return [dict(row._mapping) for row in rows]


async def get_home_check_documents(*, home_check_id: uuid.UUID) -> list[dict[str, Any]]:
    async with get_engine().begin() as conn:
        return await _load_documents(conn, home_check_id)


# ---------------------------------------------------------------------------
# 백그라운드 처리 — 새 DB 연결로 행을 갱신한다(요청 세션 재사용 금지).
#
# TODO(워커 타임아웃): 1차 조회가 최대 300s 까지 걸려 gunicorn/uvicorn 워커 타임아웃에
# 걸릴 수 있다. v1 은 BackgroundTasks(같은 워커 프로세스)로 수용하되, 출시 후 부하/타임아웃
# 지표를 보고 전용 큐(예: Redis 큐 + 별도 워커)로 분리한다.
# ---------------------------------------------------------------------------
def _new_client() -> CodefBuildingRegisterClient:
    """백그라운드 처리용 CODEF 클라이언트 — 자체 httpx/Redis 자원을 쓴다.

    테스트는 ``src.services.home_check._new_client`` 를 monkeypatch 해 외부 호출을 막는다.
    """

    return CodefBuildingRegisterClient(get_settings())


async def run_home_check(
    home_check_id: uuid.UUID,
    *,
    road_addr: str,
    jibun_addr: str | None,
    dong: str,
    ho: str,
) -> None:
    """1차 조회(전유부+표제부) 백그라운드 처리."""

    client = _new_client()
    query = BuildingRegisterQuery(
        road_addr=road_addr, dong=dong, ho=ho, jibun_addr=jibun_addr
    )
    await _process(
        home_check_id,
        exclusive_factory=lambda: client.fetch_exclusive_part(query),
        heading_factory=lambda: client.fetch_building_heading(query),
    )


async def resume_home_check(
    home_check_id: uuid.UUID,
    *,
    resume_token: str,
    product: str,
    dong: str | None,
    ho: str | None,
    secure_no: str | None,
    other_road_addr: str,
    other_jibun_addr: str | None,
    other_dong: str,
    other_ho: str,
) -> None:
    """needs_input 재개 — 폴백이 났던 제품은 resume_*, 다른 제품은 정상 fetch 로 다시 호출한다."""

    client = _new_client()
    query = BuildingRegisterQuery(
        road_addr=other_road_addr,
        dong=other_dong,
        ho=other_ho,
        jibun_addr=other_jibun_addr,
    )
    if product == "heading":
        heading_factory = lambda: client.resume_building_heading(  # noqa: E731
            resume_token, dong=dong, secure_no=secure_no
        )
        exclusive_factory = lambda: client.fetch_exclusive_part(query)  # noqa: E731
    else:
        exclusive_factory = lambda: client.resume_exclusive_part(  # noqa: E731
            resume_token, dong=dong, ho=ho, secure_no=secure_no
        )
        heading_factory = lambda: client.fetch_building_heading(query)  # noqa: E731
    await _process(
        home_check_id,
        exclusive_factory=exclusive_factory,
        heading_factory=heading_factory,
    )


async def _process(
    home_check_id: uuid.UUID,
    *,
    exclusive_factory: Any,
    heading_factory: Any,
) -> None:
    """전유부+표제부 조회를 수행하고 결과/예외를 행에 반영한다.

    전유부는 핵심 신호이므로 먼저 await 한다. 전유부가 일찍 종료(needs_input/오류)하면
    표제부 조회는 시작조차 하지 않는다(coroutine 은 factory 로 지연 생성). 표제부 조회
    실패는 치명이 아니라 caution 사유로만 반영한다(ADR-0008 §2.4 신호등).
    """

    # 전유부 — needs_input/오류면 즉시 행 반영 후 종료.
    try:
        exclusive = await exclusive_factory()
    except CodefNeedsUserInput as exc:
        await _mark_needs_input(home_check_id, exc, product="exclusive")
        return
    except CodefError as exc:
        await _mark_failed(home_check_id, exc)
        return
    except Exception:  # noqa: BLE001 — 예기치 못한 오류도 안전 메시지로 마감.
        await _mark_unexpected(home_check_id)
        return

    # 표제부 — needs_input 은 사용자 입력 필요라 전체 잡을 needs_input 으로, 그 외 오류는
    # caution 사유로 흡수(표제부 실패 시 heading=None 으로 진행).
    heading: BuildingHeadingResult | None = None
    heading_error = False
    try:
        heading = await heading_factory()
    except CodefNeedsUserInput as exc:
        await _mark_needs_input(home_check_id, exc, product="heading")
        return
    except CodefError:
        heading_error = True
    except Exception:  # noqa: BLE001
        heading_error = True

    await _mark_completed(
        home_check_id, exclusive, heading, heading_error=heading_error
    )


# ---------------------------------------------------------------------------
# 판정 (정본 — ADR-0008 §2 / 작업지시 판정 규칙).
# ---------------------------------------------------------------------------
def _judge(
    exclusive: ExclusivePartResult, heading: BuildingHeadingResult | None
) -> tuple[bool, bool, bool, str, list[str]]:
    """(exclusive_violation, heading_violation, violation, signal, caution_reasons)."""

    exclusive_violation = exclusive.violation_status == _VIOLATION_VALUE
    heading_violation = (
        heading is not None and heading.violation_status == _VIOLATION_VALUE
    )
    violation = exclusive_violation or heading_violation

    caution_reasons: list[str] = []
    if violation:
        signal = "violation"
    else:
        if heading is None:
            caution_reasons.append(
                "건물 전체(표제부) 위반표시를 확인하지 못했습니다. 별도 확인이 필요합니다."
            )
        if _exclusive_core_missing(exclusive):
            caution_reasons.append(
                "전유부 핵심 정보(전유면적/구조 등)를 확인하지 못했습니다."
            )
        signal = "caution" if caution_reasons else "normal"
    return exclusive_violation, heading_violation, violation, signal, caution_reasons


def _exclusive_core_missing(exclusive: ExclusivePartResult) -> bool:
    summary = _summarize_exclusive(exclusive)
    return summary.area_m2 is None and summary.use_type is None


# ---------------------------------------------------------------------------
# 요약 추출 (PII-free).
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _summarize_exclusive(exclusive: ExclusivePartResult) -> ExclusivePart:
    """resOwnedList 중 resType=='0'(전유부분) 첫 행에서 면적/용도/구조/층 추출."""

    for item in exclusive.owned:
        if str(item.get("resType")) == "0":
            return ExclusivePart(
                area_m2=_to_float(item.get("resArea")),
                use_type=_str_or_none(item.get("resUseType")),
                structure=_str_or_none(item.get("resStructure")),
                floor=_str_or_none(item.get("resFloor")),
            )
    return ExclusivePart()


# detail_list(resContents)에서 추출할 항목명 — 공백/※ 변형을 관용한다.
_HEADING_KEYS = {
    "main_use": ("주용도",),
    "floors": ("층수",),
    "approval_date": ("사용승인일",),
    "permit_date": ("허가일",),
}


def _normalize_label(label: Any) -> str:
    return str(label or "").replace("※", "").replace(" ", "").strip()


def _summarize_heading(heading: BuildingHeadingResult) -> BuildingHeading:
    extracted: dict[str, str | None] = {
        "main_use": None,
        "floors": None,
        "approval_date": None,
        "permit_date": None,
    }
    for item in heading.detail_list:
        label = _normalize_label(item.get("resType"))
        contents = _str_or_none(item.get("resContents"))
        if contents is None:
            continue
        for field, candidates in _HEADING_KEYS.items():
            if extracted[field] is not None:
                continue
            for cand in candidates:
                if label == _normalize_label(cand):
                    extracted[field] = contents
                    break
    return BuildingHeading(
        main_use=extracted["main_use"],
        floors=extracted["floors"],
        approval_date=extracted["approval_date"],
        permit_date=extracted["permit_date"],
        comm_unique_no=heading.comm_unique_no,
    )


def _merge_change_history(
    exclusive: ExclusivePartResult, heading: BuildingHeadingResult | None
) -> list[ChangeEntry]:
    entries: list[ChangeEntry] = []
    for item in exclusive.change_list:
        reason = _str_or_none(item.get("resChangeReason"))
        if reason is None:
            continue
        entries.append(
            ChangeEntry(
                date=_str_or_none(item.get("resChangeDate")),
                reason=reason,
                source="exclusive",
            )
        )
    if heading is not None:
        for item in heading.change_list:
            reason = _str_or_none(item.get("resChangeReason"))
            if reason is None:
                continue
            entries.append(
                ChangeEntry(
                    date=_str_or_none(item.get("resChangeDate")),
                    reason=reason,
                    source="heading",
                )
            )
    return entries


def _extract_prices(exclusive: ExclusivePartResult) -> list[PriceEntry]:
    prices: list[PriceEntry] = []
    for item in exclusive.price_list:
        prices.append(
            PriceEntry(
                reference_date=_str_or_none(item.get("resReferenceDate")),
                base_price=_to_int(item.get("resBasePrice")),
            )
        )
    return prices


def _parse_date(value: Any) -> date | None:
    text = _str_or_none(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# 행 갱신 (백그라운드 — 새 연결).
# ---------------------------------------------------------------------------
async def _mark_completed(
    home_check_id: uuid.UUID,
    exclusive: ExclusivePartResult,
    heading: BuildingHeadingResult | None,
    *,
    heading_error: bool,
) -> None:
    (
        exclusive_violation,
        heading_violation,
        violation,
        signal,
        caution_reasons,
    ) = _judge(exclusive, heading)

    exclusive_summary = _summarize_exclusive(exclusive)
    heading_summary = _summarize_heading(heading) if heading is not None else None
    change_history = _merge_change_history(exclusive, heading)
    prices = _extract_prices(exclusive)

    # PDF 보관(best-effort) — 실패해도 잡은 completed 로 둔다(문서 링크만 생략).
    await _store_pdfs(home_check_id, exclusive, heading)

    values: dict[str, Any] = {
        "status": "completed",
        "signal": signal,
        "exclusive_violation": exclusive_violation,
        "heading_violation": heading_violation,
        "violation": violation,
        "exclusive_area_m2": exclusive_summary.area_m2,
        "exclusive_use_type": exclusive_summary.use_type,
        "exclusive_structure": exclusive_summary.structure,
        "exclusive_floor": exclusive_summary.floor,
        "comm_unique_no": exclusive.comm_unique_no,
        "heading_comm_unique_no": heading.comm_unique_no if heading else None,
        "res_doc_no": exclusive.res_doc_no,
        "heading_res_doc_no": heading.res_doc_no if heading else None,
        "res_issue_date": _parse_date(exclusive.issue_date),
        "change_list": [e.model_dump(mode="json") for e in change_history],
        "price_list": [p.model_dump(mode="json") for p in prices],
        "result_fields": {"caution_reasons": caution_reasons},
        "error_code": None,
        "error_message": None,
        "queried_at": datetime.now(timezone.utc),
    }
    if heading_summary is not None:
        values["building_main_use"] = heading_summary.main_use
        values["building_floors"] = heading_summary.floors
        values["building_approval_date"] = _parse_date(heading_summary.approval_date)
        values["building_permit_date"] = _parse_date(heading_summary.permit_date)

    await _update_row(home_check_id, values)
    logger.info(
        "home_check_completed",
        home_check_id=str(home_check_id),
        signal=signal,
        violation=violation,
        heading_error=heading_error,
    )


async def _mark_needs_input(
    home_check_id: uuid.UUID, exc: CodefNeedsUserInput, *, product: str
) -> None:
    await _update_row(
        home_check_id,
        {
            "status": "needs_input",
            # resume_token 은 PII 가 아니다(1차 결과 복원용 핸들) — 보안문자 이미지 등 PII 는
            # 저장하지 않는다.
            "result_fields": {
                "resume_token": exc.resume_token,
                "product": product,
                "kind": exc.kind,
                "message": exc.message,
            },
            "queried_at": datetime.now(timezone.utc),
        },
    )
    logger.info(
        "home_check_needs_input",
        home_check_id=str(home_check_id),
        product=product,
        kind=exc.kind,
    )


async def _mark_failed(home_check_id: uuid.UUID, exc: CodefError) -> None:
    name = type(exc).__name__
    code = _ERROR_CODES.get(name, "UPSTREAM_UNAVAILABLE")
    message = _ERROR_MESSAGES.get(
        name, "조회에 실패했습니다. 잠시 후 다시 시도해 주세요."
    )
    await _update_row(
        home_check_id,
        {
            "status": "failed",
            "error_code": code,
            "error_message": message,
            "queried_at": datetime.now(timezone.utc),
        },
    )
    # 원자료/자격증명은 로깅하지 않는다 — 예외 타입과 잡 id 만 남긴다.
    logger.warning(
        "home_check_failed",
        home_check_id=str(home_check_id),
        error=name,
        error_code=code,
    )


async def _mark_unexpected(home_check_id: uuid.UUID) -> None:
    await _update_row(
        home_check_id,
        {
            "status": "failed",
            "error_code": "INTERNAL_ERROR",
            "error_message": "조회 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "queried_at": datetime.now(timezone.utc),
        },
    )
    logger.warning("home_check_unexpected_error", home_check_id=str(home_check_id))


async def reset_for_resume(home_check_id: uuid.UUID) -> None:
    """needs_input 잡을 querying 으로 되돌린다(continue 백그라운드 재개 전).

    signal_requires_completed CHECK 때문에 signal 은 항상 null 인 상태이므로 status 만
    바꾼다. resume_token 등 result_fields 는 재개 호출이 끝나며 _mark_* 가 덮어쓴다.
    """

    await _update_row(home_check_id, {"status": "querying"})


async def _update_row(home_check_id: uuid.UUID, values: dict[str, Any]) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            sa.update(HomeCheck).where(HomeCheck.id == home_check_id).values(**values)
        )


# ---------------------------------------------------------------------------
# PDF 보관 (Supabase Storage, service_role) — best-effort.
# ---------------------------------------------------------------------------
def _storage_base(settings: Settings) -> str | None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return settings.supabase_url.rstrip("/") + "/storage/v1"


async def _store_pdfs(
    home_check_id: uuid.UUID,
    exclusive: ExclusivePartResult,
    heading: BuildingHeadingResult | None,
) -> None:
    settings = get_settings()
    base = _storage_base(settings)
    if base is None:
        return

    bucket = settings.home_check_doc_bucket
    targets: list[tuple[str, str, str | None]] = [
        ("exclusive_part", "exclusive_part.pdf", exclusive.original_pdf_base64),
    ]
    if heading is not None:
        targets.append(
            ("building_heading", "building_heading.pdf", heading.original_pdf_base64)
        )

    for kind, filename, pdf_b64 in targets:
        if not pdf_b64:
            continue
        try:
            raw = base64.b64decode(pdf_b64)
        except (ValueError, TypeError):
            logger.warning(
                "home_check_pdf_decode_failed",
                home_check_id=str(home_check_id),
                kind=kind,
            )
            continue
        object_path = f"{home_check_id}/{filename}"
        try:
            await _upload_pdf(
                settings,
                base=base,
                bucket=bucket,
                object_path=object_path,
                raw=raw,
            )
        except Exception:  # noqa: BLE001
            # 업로드 실패는 치명 아님 — 문서 링크만 생략하고 리포트는 완료한다.
            logger.warning(
                "home_check_pdf_upload_failed",
                home_check_id=str(home_check_id),
                kind=kind,
            )
            continue
        await _insert_document(
            home_check_id=home_check_id,
            kind=kind,
            bucket=bucket,
            object_path=object_path,
            byte_size=len(raw),
        )


async def _upload_pdf(
    settings: Settings,
    *,
    base: str,
    bucket: str,
    object_path: str,
    raw: bytes,
) -> None:
    url = f"{base}/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
        "Content-Type": "application/pdf",
        "x-upsert": "true",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(url, content=raw, headers=headers)

    response = await log_http_call("supabase_storage", "upload_home_check_pdf", _do)
    if response.status_code not in (200, 201):
        raise ZippinException(
            "PDF 업로드에 실패했습니다.",
            code="STORAGE_UPLOAD_FAILED",
            http_status=502,
        )


async def _insert_document(
    *,
    home_check_id: uuid.UUID,
    kind: str,
    bucket: str,
    object_path: str,
    byte_size: int,
) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            sa.insert(HomeCheckDocument).values(
                home_check_id=home_check_id,
                kind=kind,
                bucket=bucket,
                object_path=object_path,
                byte_size=byte_size,
            )
        )


async def _sign_document_url(
    settings: Settings, *, bucket: str, object_path: str
) -> str | None:
    """단기(1h) 서명 다운로드 URL 을 발급한다. 실패하면 None(링크만 생략)."""

    base = _storage_base(settings)
    if base is None:
        return None
    url = f"{base}/object/sign/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
        "Content-Type": "application/json",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(url, json={"expiresIn": 3600}, headers=headers)

    try:
        response = await log_http_call("supabase_storage", "sign_home_check_pdf", _do)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        signed = response.json().get("signedURL")
    except ValueError:
        return None
    if not signed:
        return None
    return settings.supabase_url.rstrip("/") + "/storage/v1" + signed


# ---------------------------------------------------------------------------
# 직렬화 — 행(dict) → HomeCheckJob / HomeCheckReport.
# ---------------------------------------------------------------------------
def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


async def serialize_job(
    row: dict[str, Any], *, with_documents: bool = True
) -> HomeCheckJob:
    """행을 ``HomeCheckJob`` 으로 직렬화한다.

    completed → report, needs_input → needs_input, failed → error 를 채운다.
    ``with_documents`` 가 False 면 문서 서명 URL 발급(외부 호출)을 생략한다(목록용).
    """

    status = row["status"]
    job_kwargs: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "id": str(row["id"]),
        "status": status,
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }

    if status == "completed":
        job_kwargs["signal"] = row.get("signal")
        job_kwargs["report"] = await _build_report(row, with_documents=with_documents)
    elif status == "needs_input":
        fields = row.get("result_fields") or {}
        job_kwargs["needs_input"] = NeedsInput(
            kind=fields.get("kind") or "dong_ho",
            message=fields.get("message") or "추가 입력이 필요합니다.",
        )
    elif status == "failed":
        job_kwargs["error"] = ErrorInfo(
            code=row.get("error_code") or "UPSTREAM_UNAVAILABLE",
            message=row.get("error_message")
            or "조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return HomeCheckJob(**job_kwargs)


async def _build_report(
    row: dict[str, Any], *, with_documents: bool
) -> HomeCheckReport:
    signal = row.get("signal") or "normal"
    fields = row.get("result_fields") or {}
    caution_reasons = fields.get("caution_reasons") or None

    address = AddressInfo(
        road_addr=row.get("road_addr"),
        jibun_addr=row.get("jibun_addr"),
        dong=row.get("addr_dong"),
        ho=row.get("addr_ho"),
    )
    violation = Violation(
        is_violation=bool(row.get("violation")),
        exclusive=row.get("exclusive_violation"),
        heading=row.get("heading_violation"),
        raw=_VIOLATION_VALUE if row.get("violation") else None,
    )

    exclusive_part = None
    if any(
        row.get(k) is not None
        for k in (
            "exclusive_area_m2",
            "exclusive_use_type",
            "exclusive_structure",
            "exclusive_floor",
        )
    ):
        exclusive_part = ExclusivePart(
            area_m2=(
                float(row["exclusive_area_m2"])
                if row.get("exclusive_area_m2") is not None
                else None
            ),
            use_type=row.get("exclusive_use_type"),
            structure=row.get("exclusive_structure"),
            floor=row.get("exclusive_floor"),
        )

    building = None
    if any(
        row.get(k) is not None
        for k in (
            "building_main_use",
            "building_floors",
            "building_approval_date",
            "building_permit_date",
            "heading_comm_unique_no",
        )
    ):
        building = BuildingHeading(
            main_use=row.get("building_main_use"),
            floors=row.get("building_floors"),
            approval_date=_iso(row.get("building_approval_date")),
            permit_date=_iso(row.get("building_permit_date")),
            comm_unique_no=row.get("heading_comm_unique_no"),
        )

    change_history = [
        ChangeEntry(**entry) for entry in (row.get("change_list") or [])
    ] or None
    prices = [PriceEntry(**entry) for entry in (row.get("price_list") or [])] or None

    documents = None
    if with_documents:
        documents = await _report_documents(row)

    meta = ReportMeta(
        comm_unique_no=row.get("comm_unique_no"),
        res_doc_no=row.get("res_doc_no"),
        issue_date=_iso(row.get("res_issue_date")),
        queried_at=_iso(row.get("queried_at")),
    )

    return HomeCheckReport(
        signal=signal,
        violation=violation,
        address=address,
        exclusive_part=exclusive_part,
        building=building,
        change_history=change_history,
        prices=prices,
        documents=documents,
        caution_reasons=caution_reasons,
        meta=meta,
        disclaimer=DISCLAIMER,
    )


async def _report_documents(row: dict[str, Any]) -> list[DocumentRef] | None:
    docs = await get_home_check_documents(home_check_id=row["id"])
    if not docs:
        return None
    settings = get_settings()
    refs: list[DocumentRef] = []
    for doc in docs:
        url = await _sign_document_url(
            settings, bucket=doc["bucket"], object_path=doc["object_path"]
        )
        refs.append(DocumentRef(kind=doc["kind"], url=url))
    return refs
