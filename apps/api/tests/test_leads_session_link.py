"""사전검토 세션 ↔ 상담 리드 연결 + 주소 폴백 테스트 (CMP-DIRECT, 0019).

``leads.create_lead`` 가 본인 세션이면 ``session_id`` 를 연결하고, road_addr_part1 이
비어 있을 때 세션 확정 주소(아파트명 포함)로 폴백하는지 — 그리고 타인 세션 id 는
무시하는지(IDOR 방지) 검증한다. DB 는 TEST_MODE 라 seam(``_insert_lead``/
``main_flow._db_select_session``/``main_flow.get_session_address``)을 monkeypatch 한다.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.services import leads, main_flow


def test_session_address_display_prefers_road() -> None:
    assert (
        leads.session_address_display(
            {"road_address": "서울 강남구 테헤란로 1", "apartment_name": "무시"}
        )
        == "서울 강남구 테헤란로 1"
    )


def test_session_address_display_falls_back_to_jibun_then_apartment() -> None:
    assert (
        leads.session_address_display({"jibun_address": "강남동 1-2"}) == "강남동 1-2"
    )
    assert (
        leads.session_address_display(
            {
                "road_address": None,
                "jibun_address": None,
                "apartment_name": "장미마을",
                "building_dong": "802동",
                "unit_ho": "1406호",
            }
        )
        == "장미마을 802동 1406호"
    )


def test_session_address_display_empty_is_none() -> None:
    assert leads.session_address_display(None) is None
    assert leads.session_address_display({}) is None
    assert leads.session_address_display({"road_address": "  "}) is None


def _patch_insert(monkeypatch) -> dict[str, Any]:
    """``_insert_lead`` 를 가로채 lead_values 를 캡처한다."""

    captured: dict[str, Any] = {}

    async def fake_insert(lead_values, attachments):  # type: ignore[no-untyped-def]
        captured.update(lead_values)
        return {
            "id": uuid.uuid4(),
            "source_form": lead_values["source_form"],
            "status": "new",
            "created_at": "2026-06-30T00:00:00+00:00",
        }

    monkeypatch.setattr(leads, "_insert_lead", fake_insert)
    return captured


async def test_create_lead_links_owned_session_and_fills_address(monkeypatch) -> None:
    owner = uuid.uuid4()
    session_id = uuid.uuid4()
    captured = _patch_insert(monkeypatch)

    async def fake_select_session(sid):  # type: ignore[no-untyped-def]
        assert sid == session_id
        return {"id": session_id, "user_id": owner}

    async def fake_get_address(sid):  # type: ignore[no-untyped-def]
        return {"apartment_name": "장미마을", "building_dong": "802동", "unit_ho": "1406호"}

    monkeypatch.setattr(main_flow, "_db_select_session", fake_select_session)
    monkeypatch.setattr(main_flow, "get_session_address", fake_get_address)

    await leads.create_lead(
        user_id=owner,
        is_anonymous=False,
        payload={
            "source_form": "precheck_session",
            "applicant_name": "홍길동",
            "applicant_phone": "010-1234-5678",
            "road_addr_part1": None,
            "session_id": session_id,
        },
    )
    assert captured["session_id"] == session_id
    assert captured["road_addr_part1"] == "장미마을 802동 1406호"


async def test_create_lead_keeps_provided_address(monkeypatch) -> None:
    owner = uuid.uuid4()
    session_id = uuid.uuid4()
    captured = _patch_insert(monkeypatch)

    async def fake_select_session(sid):  # type: ignore[no-untyped-def]
        return {"id": session_id, "user_id": owner}

    async def fake_get_address(sid):  # type: ignore[no-untyped-def]
        return {"apartment_name": "세션아파트"}

    monkeypatch.setattr(main_flow, "_db_select_session", fake_select_session)
    monkeypatch.setattr(main_flow, "get_session_address", fake_get_address)

    await leads.create_lead(
        user_id=owner,
        is_anonymous=False,
        payload={
            "source_form": "precheck_session",
            "applicant_name": "홍길동",
            "applicant_phone": "010-1234-5678",
            "road_addr_part1": "사용자 입력 주소",
            "session_id": session_id,
        },
    )
    assert captured["session_id"] == session_id
    # 사용자가 입력한 주소는 폴백으로 덮어쓰지 않는다.
    assert captured["road_addr_part1"] == "사용자 입력 주소"


async def test_create_lead_ignores_foreign_session(monkeypatch) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    session_id = uuid.uuid4()
    captured = _patch_insert(monkeypatch)

    async def fake_select_session(sid):  # type: ignore[no-untyped-def]
        return {"id": session_id, "user_id": other}  # 타인 소유

    async def fake_get_address(sid):  # type: ignore[no-untyped-def]
        raise AssertionError("타인 세션은 주소 조회까지 가면 안 된다")

    monkeypatch.setattr(main_flow, "_db_select_session", fake_select_session)
    monkeypatch.setattr(main_flow, "get_session_address", fake_get_address)

    await leads.create_lead(
        user_id=owner,
        is_anonymous=False,
        payload={
            "source_form": "precheck_session",
            "applicant_name": "홍길동",
            "applicant_phone": "010-1234-5678",
            "road_addr_part1": None,
            "session_id": session_id,
        },
    )
    assert captured.get("session_id") is None
    assert captured.get("road_addr_part1") is None
