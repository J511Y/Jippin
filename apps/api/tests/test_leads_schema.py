"""상담 리드 Pydantic 계약 검증 (CMP-DIRECT)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.leads import LeadCreateRequest, normalize_korean_phone


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("010-1234-5678", "010-1234-5678"),
        ("01012345678", "010-1234-5678"),
        ("010 1234 5678", "010-1234-5678"),
        ("011-345-6789", "011-345-6789"),
        ("0212345678", "0212345678"),
    ],
)
def test_normalize_korean_phone_accepts_valid(raw: str, expected: str) -> None:
    assert normalize_korean_phone(raw) == expected


@pytest.mark.parametrize("raw", ["123", "abcd", "010-12-34", "999-9999-9999", ""])
def test_normalize_korean_phone_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_korean_phone(raw)


def test_main_page_minimal_payload_is_valid() -> None:
    req = LeadCreateRequest(
        source_form="main_page",
        applicant_name="홍길동",
        applicant_phone="01012345678",
        message="상담 원해요",
    )
    assert req.applicant_kind == "individual"
    assert req.applicant_phone == "010-1234-5678"


def test_lead_page_requires_full_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        LeadCreateRequest(
            source_form="lead_page",
            applicant_name="홍길동",
            applicant_phone="01012345678",
        )
    msg = str(exc.value)
    assert "road_addr_part1" in msg
    assert "expansion_location" in msg


def test_lead_page_full_payload_is_valid() -> None:
    req = LeadCreateRequest(
        source_form="lead_page",
        applicant_kind="company",
        applicant_name="홍길동",
        applicant_phone="010-1234-5678",
        road_addr_part1="서울특별시 강남구 테헤란로 1",
        road_addr_detail="101동 1001호",
        expansion_location="거실",
        ownership_status="owner",
        inflow_source="naver_search",
    )
    assert req.ownership_status == "owner"


def test_invalid_enum_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LeadCreateRequest(
            source_form="lead_page",
            applicant_kind="person",  # not in enum
            applicant_name="x",
            applicant_phone="01012345678",
            road_addr_part1="a",
            road_addr_detail="b",
            expansion_location="c",
            ownership_status="owner",
        )


def test_oversized_message_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LeadCreateRequest(
            source_form="main_page",
            applicant_name="홍길동",
            applicant_phone="01012345678",
            message="x" * 5001,
        )


def test_too_many_attachments_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LeadCreateRequest(
            source_form="main_page",
            applicant_name="홍길동",
            applicant_phone="01012345678",
            attachments=[{"object_path": f"u/{i}.png"} for i in range(6)],
        )


def test_construction_period_reversed_is_rejected() -> None:
    from datetime import date

    with pytest.raises(ValidationError):
        LeadCreateRequest(
            source_form="main_page",
            applicant_name="홍길동",
            applicant_phone="01012345678",
            construction_start_date=date(2026, 6, 10),
            construction_end_date=date(2026, 6, 1),
        )
