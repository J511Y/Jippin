"""사전검토 PDF 리포트 발부 (CMP-DIRECT, REPORT PDF).

세션에 영속된 룰 판정(rule-eval-result) · 견적 · 도면 분석을 모아 **디자인된 A4
PDF 리포트**를 만들고 Supabase Storage 에 보관한 뒤 단기 서명 URL 을 돌려준다.

파이프라인: 컨텍스트 조립 → Jinja2(``report_pdf.html.j2``) 렌더 → WeasyPrint(HTML→
PDF) → ``session_report_bucket`` 업로드(upsert) → 서명 URL. 콘텐츠 정본은
``report_content``(고정 안내) · ``estimate``(견적) · ``report_overlay``(도면 SVG).

WeasyPrint 는 시스템 라이브러리(pango/cairo)에 의존하므로 **지연 임포트**한다 —
라이브러리가 없는 환경(로컬 Windows 등)에서도 컨텍스트 조립/검증은 가능하게 둔다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from ..errors import ZippinException
from ..logging import get_logger
from . import estimate as estimate_svc
from . import main_flow, report_content, report_overlay, storage

logger = get_logger("zippin.report_pdf")

_TEMPLATE_DIR = Path(__file__).parent / "report_templates"
_TEMPLATE_NAME = "report_pdf.html.j2"

#: 기본 공개 웹 오리진 — public_web_origin 미설정 시 절대 링크용 폴백.
_DEFAULT_WEB_ORIGIN = "https://jippin.ai"


@lru_cache(maxsize=1)
def _jinja_env() -> Any:
    """Jinja2 환경(자동 이스케이프). 템플릿 로더는 report_templates 디렉터리."""

    import jinja2

    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=jinja2.select_autoescape(["html", "j2"]),
    )


def _won(amount: int) -> str:
    return f"{amount:,}원"


def _amount_text(item: dict[str, Any]) -> str:
    """견적 항목 1줄의 금액 문구 — page.tsx 의 amountText 와 동일 규칙."""

    amount_min = item.get("amount_min")
    if isinstance(amount_min, int):
        return f"{_won(amount_min)}~"
    unit_amount = item.get("unit_amount")
    if isinstance(unit_amount, int):
        unit = item.get("unit")
        suffix = ""
        if isinstance(unit, str) and unit:
            # "원/m" → " / m"
            cleaned = unit[2:] if unit.startswith("원/") else unit
            suffix = f" / {cleaned}"
        return f"{_won(unit_amount)}{suffix}~"
    return "별도 견적"


def _estimate_view(
    estimate_dict: dict[str, Any] | None, *, origin: str
) -> dict[str, Any] | None:
    """compute_estimate 결과 → 템플릿용 견적 뷰(금액 문구·합계·절대 출처 링크)."""

    if not isinstance(estimate_dict, dict):
        return None
    raw_items = estimate_dict.get("items")
    items: list[dict[str, Any]] = []
    for it in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(it, dict):
            continue
        items.append(
            {
                "label": it.get("label", ""),
                "amount_text": _amount_text(it),
                "note": it.get("note"),
            }
        )
    if not items:
        return None

    fixed_total_min = estimate_dict.get("fixed_total_min")
    fixed_total_text: str | None = None
    if isinstance(fixed_total_min, int) and fixed_total_min > 0:
        suffix = " + 현장 항목" if estimate_dict.get("has_variable_items") else ""
        fixed_total_text = f"{_won(fixed_total_min)}~{suffix}"

    # 견적의 source_url 은 상대경로("/faq?category=cost")일 수 있어 절대화한다.
    source_url = estimate_dict.get("source_url")
    if isinstance(source_url, str) and source_url.startswith("/"):
        source_url = f"{origin.rstrip('/')}{source_url}"

    return {
        "items": items,
        "fixed_total_text": fixed_total_text,
        "disclaimer": estimate_dict.get("disclaimer"),
        "source_url": source_url,
    }


def _address_line(address: dict[str, Any] | None) -> str | None:
    """주소 dict → 사람이 읽는 한 줄. 없으면 None."""

    if not isinstance(address, dict):
        return None
    base = address.get("road_address") or address.get("jibun_address")
    parts: list[str] = []
    if isinstance(base, str) and base:
        parts.append(base)
    apt = address.get("apartment_name")
    if isinstance(apt, str) and apt and apt not in (base or ""):
        parts.append(apt)
    dong = address.get("building_dong")
    if isinstance(dong, str) and dong:
        parts.append(dong if dong.endswith("동") else f"{dong}동")
    ho = address.get("unit_ho")
    if isinstance(ho, str) and ho:
        parts.append(ho if ho.endswith("호") else f"{ho}호")
    line = " ".join(parts).strip()
    return line or None


def _wall_groups(judgment_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """selected_walls → 종류별로 묶은 요약. 사용자는 비내력벽만 선택할 수 있어
    벽마다 같은 문단을 반복하지 않고, 같은 종류는 번호만 모아 한 줄로 보여준다."""

    entries = report_overlay.selected_wall_entries(judgment_schema)
    order: list[str] = []
    numbers: dict[str, list[str]] = {}
    for e in entries:
        wt = e.get("wall_type") or "UNKNOWN"
        if wt not in numbers:
            numbers[wt] = []
            order.append(wt)
        numbers[wt].append(report_overlay.circled(e["index"]))
    groups: list[dict[str, Any]] = []
    for wt in order:
        view = report_content.wall_view(wt)
        groups.append(
            {
                "numbers": numbers[wt],
                "label": view["label"],
                "tone": view["tone"],
                "short": report_content.wall_short(wt),
            }
        )
    return groups


def _report_id(session_id: uuid.UUID) -> str:
    return "JP-" + session_id.hex[:6].upper()


def _generated_at_kr(now: datetime) -> str:
    return f"{now.year}년 {now.month}월 {now.day}일"


def _build_context(
    *,
    session_id: uuid.UUID,
    rule_eval_result: dict[str, Any],
    estimate_dict: dict[str, Any] | None,
    address: dict[str, Any] | None,
    judgment_schema: dict[str, Any],
    overlay: dict[str, Any],
    origin: str,
    now: datetime,
) -> dict[str, Any]:
    """템플릿 ``report`` 컨텍스트 조립 — 모든 섹션 데이터를 한 객체로."""

    facilities = report_content.facility_views(rule_eval_result)
    return {
        "report": {
            "generated_at_kr": _generated_at_kr(now),
            "report_id": _report_id(session_id),
            "address_line": _address_line(address),
            "verdict": report_content.verdict_view(rule_eval_result),
            "overlay": overlay,
            "wall_groups": _wall_groups(judgment_schema),
            "wall_edu": report_content.WALL_EDU,
            "wall_caveat": report_content.WALL_CAVEAT,
            "facilities": facilities,
            "facilities_empty_note": (
                None if facilities else report_content.FACILITIES_EMPTY_NOTE
            ),
            "estimate": _estimate_view(estimate_dict, origin=origin),
            "schedule": report_content.SCHEDULE,
            "consultation": report_content.consultation_view(origin),
            "legal_notice": report_content.LEGAL_NOTICE,
        }
    }


def render_html(context: dict[str, Any]) -> str:
    """컨텍스트 → HTML 문자열(Jinja2). WeasyPrint 없이도 검증 가능."""

    return _jinja_env().get_template(_TEMPLATE_NAME).render(**context)


def _html_to_pdf(html: str) -> bytes:
    """HTML → PDF 바이트(WeasyPrint). 시스템 라이브러리 미설치면 임포트에서 실패."""

    from weasyprint import HTML  # 지연 임포트 — pango/cairo 의존.

    return HTML(string=html).write_pdf()


def _origin(settings: Settings) -> str:
    return settings.public_web_origin or _DEFAULT_WEB_ORIGIN


async def _load_floorplan_image(
    settings: Settings,
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
) -> tuple[bytes | None, str | None]:
    """세션에 선택된 도면 asset 의 원본 바이트+content_type. 없거나 실패면 (None, None)."""

    try:
        asset = await main_flow.get_selected_floorplan_asset(
            session_id=session_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
        )
    except Exception:  # noqa: BLE001 — 도면 부재는 치명 아님(오버레이만 degrade).
        return None, None
    if not isinstance(asset, dict):
        return None, None
    bucket = asset.get("bucket")
    object_key = asset.get("object_key")
    if not (isinstance(bucket, str) and isinstance(object_key, str)):
        return None, None
    image_bytes = await storage.download_object(
        settings, bucket=bucket, object_path=object_key
    )
    content_type = asset.get("content_type")
    return image_bytes, content_type if isinstance(content_type, str) else None


async def generate_session_report_pdf(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """PDF 리포트를 생성·보관하고 다운로드용 서명 URL 번들을 반환한다.

    판정 미준비면 ``main_flow.get_session_report`` 가 404 REPORT_NOT_READY 를 던진다.
    Storage 미설정/업로드/서명 실패는 명시적 ZippinException 으로 변환한다.
    """

    settings = get_settings()
    origin = _origin(settings)

    # 1) 리포트 번들(판정 정본). 판정 없으면 여기서 404.
    data = await main_flow.get_session_report(
        session_id=session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    session = data["session"]
    address = data["address"]
    rule_eval_result = session["rule_eval_result"]
    judgment_schema = session.get("judgment_schema") or {}
    estimate_dict = estimate_svc.compute_estimate(rule_eval_result)

    # 2) 도면 오버레이(있으면). 도면 부재/해석 실패는 degrade.
    image_bytes, content_type = await _load_floorplan_image(
        settings,
        session_id=session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    entries = report_overlay.selected_wall_entries(judgment_schema)
    overlay = report_overlay.build_overlay(
        image_bytes=image_bytes,
        content_type=content_type,
        judgment_schema=judgment_schema,
        entries=entries,
    )

    # 3) 컨텍스트 → HTML → PDF.
    now = datetime.now(timezone.utc)
    context = _build_context(
        session_id=session_id,
        rule_eval_result=rule_eval_result,
        estimate_dict=estimate_dict,
        address=address,
        judgment_schema=judgment_schema,
        overlay=overlay,
        origin=origin,
        now=now,
    )
    html = render_html(context)
    try:
        pdf_bytes = _html_to_pdf(html)
    except Exception as exc:  # noqa: BLE001
        logger.error("report_pdf_render_failed", session_id=str(session_id), error=str(exc))
        raise ZippinException(
            "리포트 PDF 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="REPORT_PDF_RENDER_FAILED",
            http_status=502,
        ) from exc

    # 4) Storage 보관(upsert) + 서명 URL.
    bucket = settings.session_report_bucket
    object_path = f"{session_id}/ai-precheck-report.pdf"
    uploaded = await storage.upload_object(
        settings,
        bucket=bucket,
        object_path=object_path,
        content=pdf_bytes,
        content_type="application/pdf",
        operation="upload_session_report_pdf",
    )
    if not uploaded:
        raise ZippinException(
            "리포트 PDF 저장에 실패했습니다.",
            code="REPORT_PDF_STORAGE_FAILED",
            http_status=502,
        )
    url = await storage.sign_object_url(
        settings,
        bucket=bucket,
        object_path=object_path,
        expires_in=3600,
        operation="sign_session_report_pdf",
    )
    if not url:
        raise ZippinException(
            "리포트 PDF 다운로드 링크 발급에 실패했습니다.",
            code="REPORT_PDF_SIGN_FAILED",
            http_status=502,
        )

    return {
        "url": url,
        "report_id": _report_id(session_id),
        "byte_size": len(pdf_bytes),
        "generated_at": now,
        "expires_in": 3600,
    }
