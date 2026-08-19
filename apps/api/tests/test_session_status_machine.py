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


async def test_empty_selection_patch_reopens_overlay_stage(monkeypatch) -> None:
    # #selection-invalidation-reopen: 재분석 프루닝이 selected_walls 를 비우면
    # walls_selected 마일스톤이 아니고(키 존재만으로 전진 금지), 살아 있는 선택이
    # 하나도 없으므로 forward-only 배지를 awaiting_overlay 로 명시 재개한다 —
    # 사용자가 다시 골라야 하는 현실과 SSE/퍼널 상태를 일치시킨다.
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"wall_objects": [{"id": "w1", "wall_type": "NON_LOAD_BEARING"}]},
    )
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1"]},
    )
    assert fake.sessions[sid]["status"] == "collecting_info"
    # 재분석: 새 분석 산출 + 전부 무효화된 선택.
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={
            "wall_objects": [{"id": "w1:1", "wall_type": "NON_LOAD_BEARING"}],
            "selected_walls": [],
        },
    )
    assert fake.sessions[sid]["status"] == "awaiting_overlay"
    assert _events(fake, sid)[-1] == "awaiting_overlay"  # 재개 이벤트 기록


async def test_empty_wall_selection_keeps_status_when_window_selection_alive(
    monkeypatch,
) -> None:
    # 벽 선택이 비워져도 창호 선택이 살아 있으면 아직 검토할 선택이 있다 — 재개하지
    # 않는다(선택 키 별 부분 무효화).
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1"], "selected_windows": ["g1"]},
    )
    assert fake.sessions[sid]["status"] == "collecting_info"
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": []},
    )
    assert fake.sessions[sid]["status"] == "collecting_info"


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


async def test_reopen_skipped_when_selection_alive_at_regress_time(monkeypatch) -> None:
    # #reopen-recheck-selection: 프루닝(빈 선택) 기록과 재개 사이에 사용자의 새 선택
    # PATCH 가 끼어들 수 있다 — 재개는 되돌리기 직전 저장된 선택이 여전히 비어 있을
    # 때만 수행한다(only_if_no_selection).
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1"]},
    )
    assert fake.sessions[sid]["status"] == "collecting_info"

    # 동시 PATCH 가 선택을 되살린 상태를 재현 — 살아 있는 선택이 있으면 no-op.
    res = await main_flow.reopen_session_status(
        session_id=sid,
        target="awaiting_overlay",
        reason="selection_invalidated",
        only_if_no_selection=True,
    )
    assert res is None
    assert fake.sessions[sid]["status"] == "collecting_info"

    # 선택이 실제로 비어 있으면 되돌린다.
    fake.sessions[sid]["judgment_schema"]["selected_walls"] = []
    res = await main_flow.reopen_session_status(
        session_id=sid,
        target="awaiting_overlay",
        reason="selection_invalidated",
        only_if_no_selection=True,
    )
    assert res is not None
    assert fake.sessions[sid]["status"] == "awaiting_overlay"


async def test_analysis_patch_prunes_selection_atomically(monkeypatch) -> None:
    # #atomic-merge-prune: 분석 패치가 **선택 키 없이** wall_objects 만 갈아끼워도,
    # 저장된 선택은 같은 병합 안에서 새 선택 가능 id 와 교집합으로 줄어든다 — 프루닝
    # 스냅숏과 영속 사이에 옛 카드 제출이 끼어드는 창(TOCTOU)이 없다. 전부 걸러지면
    # 오버레이 단계로 재개까지 이어진다.
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"wall_objects": [{"id": "w1", "wall_type": "NON_LOAD_BEARING"}]},
    )
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1"]},
    )
    assert fake.sessions[sid]["status"] == "collecting_info"
    # 재분석: 선택 키 없는 분석 패치 — w1 이 사라지고 w2 만 남는다.
    merged = await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"wall_objects": [{"id": "w2", "wall_type": "NON_LOAD_BEARING"}]},
    )
    assert merged["selected_walls"] == []  # 병합과 같은 단계에서 프루닝
    assert fake.sessions[sid]["judgment_schema"]["selected_walls"] == []
    assert fake.sessions[sid]["status"] == "awaiting_overlay"  # 재개까지 연쇄


async def test_analysis_patch_keeps_still_valid_selection(monkeypatch) -> None:
    # 원자 프루닝은 여전히 유효한 선택은 남긴다(전량 초기화가 아니라 교집합).
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={
            "wall_objects": [
                {"id": "w1", "wall_type": "NON_LOAD_BEARING"},
                {"id": "w2", "wall_type": "NON_LOAD_BEARING"},
            ]
        },
    )
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1", "w2"]},
    )
    merged = await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={
            "wall_objects": [
                {"id": "w1", "wall_type": "NON_LOAD_BEARING"},
                {"id": "w3", "wall_type": "LOAD_BEARING"},
            ]
        },
    )
    assert merged["selected_walls"] == ["w1"]  # w2(소멸)만 걸러짐
    assert fake.sessions[sid]["status"] == "collecting_info"  # 살아 있는 선택 → 유지


async def test_merge_validate_selection_rejects_atomically(monkeypatch) -> None:
    # #stale-overlay-submission: validate_selection 은 병합 트랜잭션 안에서 현행 객체와
    # 대조한다 — 어긋나면 아무것도 쓰지 않고 409 SELECTION_STALE. 스냅숏 검증과 달리
    # 재분석 커밋이 사이에 끼어들 창이 없다.
    import pytest

    from src.errors import ZippinException

    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"wall_objects": [{"id": "w1", "wall_type": "NON_LOAD_BEARING"}]},
    )
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["w1"]},
        validate_selection=True,
    )
    assert fake.sessions[sid]["status"] == "collecting_info"

    with pytest.raises(ZippinException) as exc:
        await main_flow.merge_judgment_schema(
            session_id=sid,
            owner_user_id=owner,
            owner_is_anonymous=False,
            patch={"selected_walls": ["ghost:1"]},
            validate_selection=True,
        )
    assert exc.value.code == "SELECTION_STALE"
    # 거절은 세션을 전혀 바꾸지 않는다 — 기존 선택·배지 유지.
    assert fake.sessions[sid]["judgment_schema"]["selected_walls"] == ["w1"]
    assert fake.sessions[sid]["status"] == "collecting_info"


async def test_advance_skipped_when_selection_pruned_before_advance(
    monkeypatch,
) -> None:
    # #advance-recheck-selection: 선택 커밋과 지연된 전진 사이에 재분석 프루닝이 그
    # 선택을 걷어냈으면(두 탭 경합), 빈 세션을 '선택 완료'(collecting_info)로 올리지
    # 않는다 — reopen 의 only_if_no_selection 과 대칭 가드.
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"wall_objects": [{"id": "w1", "wall_type": "NON_LOAD_BEARING"}]},
    )
    assert fake.sessions[sid]["status"] == "awaiting_overlay"

    # 프루닝이 선택을 비운 상태를 재현 — 살아 있는 선택이 없으면 전진 no-op.
    fake.sessions[sid]["judgment_schema"]["selected_walls"] = []
    res = await main_flow.advance_session_status(
        session_id=sid,
        target="collecting_info",
        reason="walls_selected",
        only_if_live_selection=True,
    )
    assert res is None
    assert fake.sessions[sid]["status"] == "awaiting_overlay"
    assert "collecting_info" not in _events(fake, sid)  # 마일스톤 이벤트도 생략

    # 선택이 실제로 살아 있으면 정상 전진.
    fake.sessions[sid]["judgment_schema"]["selected_walls"] = ["w1"]
    res = await main_flow.advance_session_status(
        session_id=sid,
        target="collecting_info",
        reason="walls_selected",
        only_if_live_selection=True,
    )
    assert res is not None
    assert fake.sessions[sid]["status"] == "collecting_info"


async def test_reopen_clears_interleaved_verdict(monkeypatch) -> None:
    # #reopen-clears-verdict: 병합(verdict 소거)과 재개 사이에 set_session_verdict 가
    # 끼어들어 무효화된 선택 기준의 판정을 되살릴 수 있다 — 재개가 같은 트랜잭션에서
    # rule_eval_result 도 함께 비워, 오버레이를 다시 골라야 하는 세션에서 GET /report
    # 가 stale 판정을 제공하지 않게 한다.
    fake = install_main_flow_fake(monkeypatch)
    owner, sid = await _new_session(fake)
    await main_flow.advance_session_status(session_id=sid, target="report_ready")
    # interleave 재현: 선택은 비었는데 판정이 남아 있는 상태.
    fake.sessions[sid]["judgment_schema"] = {"selected_walls": []}
    fake.sessions[sid]["rule_eval_result"] = {"verdict": "ALLOW"}
    res = await main_flow.reopen_session_status(
        session_id=sid,
        target="awaiting_overlay",
        reason="selection_invalidated",
        only_if_no_selection=True,
        clear_rule_eval=True,
    )
    assert res is not None
    assert fake.sessions[sid]["status"] == "awaiting_overlay"
    assert fake.sessions[sid]["rule_eval_result"] is None  # stale 판정 동시 소거
