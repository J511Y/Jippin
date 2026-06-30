"""세션 상태 머신 — forward-only 전이 + 이력 기록 (CMP-DIRECT, 0020).

도구/플로우 마일스톤마다 sessions.status 가 전진하고 session_status_events 에 이력이
1행씩 쌓이는지, 그리고 전이가 단조(뒤로 안 감)·종료상태 보호인지 검증한다. DB 는
TEST_MODE 라 ``_main_flow_db_fake`` 가 seam 을 대체한다(reference-scope 트리거는 미적용).
"""

from __future__ import annotations

import uuid

from src.services import main_flow
from tests._main_flow_db_fake import install_main_flow_fake


async def _new_session(fake):
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    return owner, session["id"]


def _events(fake, session_id):
    return [
        e["to_status"]
        for e in fake.session_status_events
        if e["session_id"] == session_id
    ]


async def test_create_session_records_draft_event(monkeypatch) -> None:
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    assert _events(fake, sid) == ["draft"]
    assert fake.sessions[sid]["status"] == "draft"


async def test_address_upsert_advances_to_address_ready(monkeypatch) -> None:
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.upsert_session_address(
        session_id=sid,
        owner_user_id=owner,
        payload={"road_address": "서울 강남구 테헤란로 1"},
    )
    assert fake.sessions[sid]["status"] == "address_ready"
    assert _events(fake, sid) == ["draft", "address_ready"]


async def test_floorplan_asset_advances_to_floorplan_selected(monkeypatch) -> None:
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.create_floorplan_asset(
        session_id=sid,
        owner_user_id=owner,
        payload={
            "bucket": "floorplans",
            "object_key": f"{owner}/plan.png",
            "content_type": "image/png",
            "byte_size": 1234,
        },
    )
    assert fake.sessions[sid]["status"] == "floorplan_selected"
    assert _events(fake, sid)[-1] == "floorplan_selected"


async def test_merge_schema_advances_overlay_then_collecting(monkeypatch) -> None:
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    # 분석 산출(wall_objects) → awaiting_overlay.
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"wall_objects": [{"id": "w1", "wall_type": "NON_LOAD_BEARING"}]},
    )
    assert fake.sessions[sid]["status"] == "awaiting_overlay"
    # 사용자 벽 선택(selected_walls) → collecting_info.
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1"]},
    )
    assert fake.sessions[sid]["status"] == "collecting_info"
    assert _events(fake, sid) == ["draft", "awaiting_overlay", "collecting_info"]


async def test_set_verdict_advances_to_report_ready(monkeypatch) -> None:
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    await main_flow.set_session_verdict(
        session_id=sid, rule_eval_result={"verdict": "ALLOW"}
    )
    assert fake.sessions[sid]["status"] == "report_ready"
    assert _events(fake, sid)[-1] == "report_ready"


async def test_status_is_forward_only_but_milestone_recorded(monkeypatch) -> None:
    # 더 낮은 단계 target: status(배지)는 전진하지 않지만 마일스톤 이벤트는 기록된다.
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    await main_flow.advance_session_status(session_id=sid, target="report_ready")
    res = await main_flow.advance_session_status(session_id=sid, target="address_ready")
    assert res is None  # status 전진 안 함
    assert fake.sessions[sid]["status"] == "report_ready"  # 배지 유지
    assert "address_ready" in _events(fake, sid)  # 마일스톤은 기록됨


async def test_milestone_deduped_per_stage(monkeypatch) -> None:
    # 같은 단계로 두 번 advance 해도 이벤트는 1건(퍼널 distinct 와 별개로 로그도 깔끔).
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    await main_flow.advance_session_status(session_id=sid, target="report_ready")
    await main_flow.advance_session_status(session_id=sid, target="report_ready")
    assert _events(fake, sid).count("report_ready") == 1


async def test_out_of_order_milestone_recorded(monkeypatch) -> None:
    # 도면 먼저(floorplan_selected) → 주소 나중(address_ready): 둘 다 이벤트로 잡혀야 한다
    # (forward-only no-op 가 address_ready 마일스톤을 떨어뜨리던 문제, 리뷰 지적).
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    await main_flow.advance_session_status(session_id=sid, target="floorplan_selected")
    await main_flow.advance_session_status(session_id=sid, target="address_ready")
    ev = _events(fake, sid)
    assert "floorplan_selected" in ev and "address_ready" in ev
    assert (
        fake.sessions[sid]["status"] == "floorplan_selected"
    )  # 배지는 더 높은 단계 유지


async def test_terminal_status_is_untouched(monkeypatch) -> None:
    # 종료 상태는 advance 가 status 도 이벤트도 건드리지 않는다.
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    fake.sessions[sid]["status"] = "deleted"
    res = await main_flow.advance_session_status(session_id=sid, target="handoff")
    assert res is None
    assert fake.sessions[sid]["status"] == "deleted"
    assert "handoff" not in _events(fake, sid)


async def test_advance_rejects_unknown_status(monkeypatch) -> None:
    fake = install_main_flow_fake(monkeypatch)
    _owner, sid = await _new_session(fake)
    import pytest

    with pytest.raises(ValueError):
        await main_flow.advance_session_status(session_id=sid, target="bogus")
