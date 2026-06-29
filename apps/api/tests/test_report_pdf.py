"""사전검토 PDF 리포트 발부 — report_content / report_overlay / report_pdf 단위 테스트.

WeasyPrint 시스템 라이브러리가 없는 환경(로컬 Windows/CI)에서도 컨텍스트 조립과
HTML 렌더(Jinja2)까지는 검증한다. 실제 PDF 바이트 생성은 라이브러리가 있을 때만.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest

from src.services import report_content, report_overlay, report_pdf


# ─────────────────────────── report_content ────────────────────────────────


def _rule(**over):
    base = {
        "verdict": "WARN",
        "permit_required": True,
        "required_facilities": [
            {"code": "FIRE_PANEL", "label": "방화판"},
            {"code": "FIRE_DETECTOR", "label": "화재감지기"},
        ],
        "user_message": "조건부로 가능해요.",
    }
    base.update(over)
    return base


def test_verdict_view_maps_label_tone_and_permit() -> None:
    v = report_content.verdict_view(_rule(verdict="ALLOW"))
    assert v["label"] == "철거 가능성 있음"
    assert v["tone"] == "success"
    assert v["permit_text"] == "행위허가 필요"
    assert v["summary"] == "조건부로 가능해요."


def test_verdict_view_hold_is_permit_undecided() -> None:
    v = report_content.verdict_view(_rule(verdict="HOLD", permit_required=True))
    assert v["tone"] == "info"
    assert "미정" in v["permit_text"]


def test_verdict_view_unknown_verdict_is_neutral() -> None:
    v = report_content.verdict_view(_rule(verdict="???", user_message=None))
    assert v["tone"] == "neutral"
    assert v["summary"] is None


def test_wall_view_known_and_unknown() -> None:
    nlb = report_content.wall_view("NON_LOAD_BEARING")
    assert nlb["tone"] == "success" and "비내력벽" in nlb["label"]
    lb = report_content.wall_view("LOAD_BEARING")
    assert lb["tone"] == "danger"
    unk = report_content.wall_view("WEIRD")
    assert unk["tone"] == "info"  # UNKNOWN 폴백


def test_facility_views_dedup_order_and_label_override() -> None:
    views = report_content.facility_views(
        _rule(
            required_facilities=[
                {"code": "FIRE_PANEL", "label": "맞춤 방화판"},
                {"code": "FIRE_PANEL", "label": "중복"},  # 중복 제거
                {"code": "NOT_A_CODE", "label": "무시"},  # 미지원 코드 무시
                {"code": "FIRE_GLASS"},  # 라벨 없으면 기본값
            ]
        )
    )
    codes = [v["code"] for v in views]
    assert codes == ["FIRE_PANEL", "FIRE_GLASS"]
    assert views[0]["label"] == "맞춤 방화판"  # 룰 라벨 우선
    assert views[1]["label"] == "방화유리 설치"  # 기본 라벨
    assert views[0]["points"] and isinstance(views[0]["points"], list)


def test_facility_views_empty() -> None:
    assert report_content.facility_views(_rule(required_facilities=[])) == []


def test_consultation_and_faq_urls() -> None:
    c = report_content.consultation_view("https://jippin.ai/")
    assert c["url"] == "https://jippin.ai/leads/new"
    assert c["site"] == "jippin.ai"
    assert report_content.faq_cost_url("https://jippin.ai") == (
        "https://jippin.ai/faq?category=cost"
    )


def test_schedule_is_three_steps() -> None:
    assert [s["step"] for s in report_content.SCHEDULE] == [
        "STEP 1",
        "STEP 2",
        "STEP 3",
    ]


# ─────────────────────────── report_overlay ────────────────────────────────


def test_circled_numbers() -> None:
    assert report_overlay.circled(1) == "①"
    assert report_overlay.circled(3) == "③"
    assert report_overlay.circled(99) == "(99)"


def test_selected_wall_entries_preserve_order_and_type() -> None:
    judgment = {
        "selected_walls": ["w2", "w1"],
        "wall_objects": [
            {"id": "w1", "wall_type": "NON_LOAD_BEARING"},
            {"id": "w2", "wall_type": "LOAD_BEARING"},
        ],
    }
    entries = report_overlay.selected_wall_entries(judgment)
    assert [e["id"] for e in entries] == ["w2", "w1"]
    assert [e["index"] for e in entries] == [1, 2]
    assert entries[0]["wall_type"] == "LOAD_BEARING"


def test_selected_wall_entries_unknown_when_missing() -> None:
    entries = report_overlay.selected_wall_entries(
        {"selected_walls": ["ghost"], "wall_objects": []}
    )
    assert entries == [{"index": 1, "id": "ghost", "wall_type": "UNKNOWN"}]


def test_build_overlay_degrades_without_image() -> None:
    ov = report_overlay.build_overlay(
        image_bytes=None, content_type=None, judgment_schema={}, entries=[]
    )
    assert ov["available"] is False
    assert ov["svg"] is None
    assert ov["unavailable_reason"]


def _png(width: int = 400, height: int = 300) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, "PNG")
    return buf.getvalue()


def test_build_overlay_renders_svg_with_image_and_badges() -> None:
    judgment = {
        "selected_walls": ["w1"],
        "wall_objects": [
            {
                "id": "w1",
                "wall_type": "NON_LOAD_BEARING",
                "coords": [{"x": 10, "y": 10}, {"x": 200, "y": 10}],
            },
            {
                "id": "w2",
                "wall_type": "LOAD_BEARING",
                "coords": [{"x": 10, "y": 80}, {"x": 200, "y": 80}],
            },
        ],
    }
    entries = report_overlay.selected_wall_entries(judgment)
    ov = report_overlay.build_overlay(
        image_bytes=_png(),
        content_type="image/png",
        judgment_schema=judgment,
        entries=entries,
    )
    assert ov["available"] is True
    svg = ov["svg"]
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'viewBox="0 0 400 300"' in svg
    assert "data:image/png;base64," in svg
    assert "polyline" in svg
    # 선택 벽 번호 배지(①=1) 가 텍스트로 들어간다.
    assert ">1</text>" in svg


def test_build_overlay_handles_corrupt_image() -> None:
    ov = report_overlay.build_overlay(
        image_bytes=b"not-an-image",
        content_type="image/png",
        judgment_schema={},
        entries=[],
    )
    assert ov["available"] is False
    assert ov["unavailable_reason"]


# ─────────────────────────── report_pdf (assembly) ─────────────────────────


def test_amount_text_variants() -> None:
    assert report_pdf._amount_text({"amount_min": 330_000}) == "330,000원~"
    assert (
        report_pdf._amount_text({"unit_amount": 50_000, "unit": "원/m"})
        == "50,000원 / m~"
    )
    assert report_pdf._amount_text({"note": "x"}) == "별도 견적"


def test_estimate_view_absolutizes_source_and_builds_total() -> None:
    est = {
        "items": [
            {"label": "행위허가 대행", "amount_min": 330_000, "note": "n"},
            {"label": "방화판 시공", "unit_amount": 50_000, "unit": "원/m"},
        ],
        "fixed_total_min": 495_000,
        "has_variable_items": True,
        "source_url": "/faq?category=cost",
        "disclaimer": "예상 범위예요.",
    }
    view = report_pdf._estimate_view(est, origin="https://jippin.ai")
    assert view is not None
    assert view["items"][0]["amount_text"] == "330,000원~"
    assert view["fixed_total_text"] == "495,000원~ + 현장 항목"
    assert view["source_url"] == "https://jippin.ai/faq?category=cost"


def test_estimate_view_none_when_no_items() -> None:
    assert report_pdf._estimate_view(None, origin="https://jippin.ai") is None
    assert report_pdf._estimate_view({"items": []}, origin="https://x") is None


def test_address_line_composes_with_suffixes() -> None:
    line = report_pdf._address_line(
        {
            "road_address": "서울특별시 강남구 테헤란로 101",
            "apartment_name": "래미안아파트",
            "building_dong": "103",
            "unit_ho": "1201",
        }
    )
    assert line == "서울특별시 강남구 테헤란로 101 래미안아파트 103동 1201호"
    assert report_pdf._address_line(None) is None


def _sample_context() -> dict:
    judgment = {
        "selected_walls": ["w1"],
        "wall_objects": [
            {
                "id": "w1",
                "wall_type": "NON_LOAD_BEARING",
                "coords": [{"x": 10, "y": 10}, {"x": 200, "y": 10}],
            }
        ],
    }
    entries = report_overlay.selected_wall_entries(judgment)
    overlay = report_overlay.build_overlay(
        image_bytes=_png(),
        content_type="image/png",
        judgment_schema=judgment,
        entries=entries,
    )
    return report_pdf._build_context(
        session_id=uuid.UUID("2a4f1c00-0000-4000-8000-000000000000"),
        rule_eval_result=_rule(),
        estimate_dict={
            "items": [{"label": "행위허가 대행", "amount_min": 330_000}],
            "fixed_total_min": 330_000,
            "has_variable_items": False,
            "source_url": "/faq?category=cost",
            "disclaimer": "예상 범위예요.",
        },
        address={"road_address": "서울특별시 강남구 테헤란로 101"},
        judgment_schema=judgment,
        overlay=overlay,
        origin="https://jippin.ai",
        now=datetime(2026, 6, 29, tzinfo=timezone.utc),
    )


def test_build_context_shape() -> None:
    ctx = _sample_context()["report"]
    assert ctx["report_id"] == "JP-2A4F1C"
    assert ctx["generated_at_kr"] == "2026년 6월 29일"
    assert ctx["verdict"]["label"] == "조건부 가능"
    # 벽체는 종류별로 묶인다 — 한 비내력벽 선택 → 그룹 1개, 번호 ①.
    assert ctx["wall_groups"][0]["numbers"] == ["①"]
    assert ctx["wall_groups"][0]["tone"] == "success"
    assert ctx["wall_edu"] == report_content.WALL_EDU
    assert ctx["wall_caveat"] == report_content.WALL_CAVEAT
    assert [f["code"] for f in ctx["facilities"]] == ["FIRE_PANEL", "FIRE_DETECTOR"]
    assert ctx["facilities_empty_note"] is None
    assert ctx["consultation"]["url"] == "https://jippin.ai/leads/new"
    assert ctx["legal_notice"] == report_content.LEGAL_NOTICE


def test_build_context_empty_facilities_sets_note() -> None:
    ctx = report_pdf._build_context(
        session_id=uuid.uuid4(),
        rule_eval_result=_rule(required_facilities=[]),
        estimate_dict=None,
        address=None,
        judgment_schema={},
        overlay={"available": False, "svg": None, "caption": "", "unavailable_reason": "x"},
        origin="https://jippin.ai",
        now=datetime(2026, 6, 29, tzinfo=timezone.utc),
    )["report"]
    assert ctx["facilities"] == []
    assert ctx["facilities_empty_note"] == report_content.FACILITIES_EMPTY_NOTE
    assert ctx["estimate"] is None


def test_render_html_contains_all_sections() -> None:
    html = report_pdf.render_html(_sample_context())
    assert len(html) > 3000
    # 5개 섹션 + 핵심 데이터가 HTML 에 실제로 박혀 있어야 한다.
    assert "AI 사전검토 리포트" in html
    assert "조건부 가능" in html  # 판정 배너
    assert "<svg" in html and "data:image/png;base64," in html  # 도면 오버레이
    assert "내력벽과 비내력벽" in html  # 벽체 교육 박스
    assert "철거 시 챙겨야 할 요소" in html
    assert "방화판" in html  # 시설 고정 설명
    assert "예상 견적" in html  # 견적 섹션
    assert "진행 일정" in html  # 일정 섹션
    assert "STEP 1" in html  # 일정 스테퍼
    assert "https://jippin.ai/leads/new" in html  # 상담 링크
    assert report_content.LEGAL_NOTICE in html  # 법적 고지


def test_pdf_bytes_when_weasyprint_available() -> None:
    """WeasyPrint 시스템 라이브러리가 있으면 실제 PDF 바이트(%PDF)까지 검증."""

    html = report_pdf.render_html(_sample_context())
    try:
        pdf = report_pdf._html_to_pdf(html)
    except (ImportError, OSError) as exc:  # GTK/pango 미설치 환경은 스킵.
        pytest.skip(f"WeasyPrint unavailable: {exc}")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000
