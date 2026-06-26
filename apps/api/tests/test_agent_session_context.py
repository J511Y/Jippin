"""세션 상태 스냅샷 빌더 테스트 — CMP-DIRECT.

build_session_state_context 가 '이미 확보된 사실'만 한국어 블록으로 정리하는지
(선택/도면/주소/판단값), 빈 세션엔 None 인지 검증한다.
"""

from __future__ import annotations

from src.agent.session_context import build_session_state_context


def test_none_when_empty() -> None:
    assert build_session_state_context(None, None) is None
    assert build_session_state_context({"judgment_schema": {}}, None) is None


def test_includes_address_and_floor() -> None:
    ctx = build_session_state_context(
        {"judgment_schema": {}},
        {
            "road_address": "서울 강서구 양천로 400-12",
            "apartment_name": "더리브골드타워",
            "unit_ho": "612호",
            "floor_no": 6,
        },
    )
    assert ctx is not None
    assert "확정 주소" in ctx and "양천로 400-12" in ctx and "612호" in ctx
    assert "층수 6" in ctx
    assert "다시 묻지" in ctx


def test_floorplan_analyzed_counts_and_priority() -> None:
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [
                {"id": "pred:1", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:2", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:3", "wall_type": "LOAD_BEARING"},
            ]
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "비내력벽 후보 2곳" in ctx and "내력벽 후보 1곳" in ctx
    # 도면 우선 + 재요청 금지 지침.
    assert "도면을 다시" in ctx and "도면 기준으로 진행" in ctx


def test_selected_walls_surface_to_agent() -> None:
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [
                {"id": "pred:5", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:9", "wall_type": "NON_LOAD_BEARING"},
            ],
            "selected_walls": ["pred:5", "pred:9"],
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "직접 선택한 벽: 2곳" in ctx
    assert "pred:5" in ctx and "pred:9" in ctx
    assert "모두 비내력벽 후보" in ctx
    assert "선택을 모른다고 하지 말 것" in ctx


def test_known_judgment_values_listed() -> None:
    session = {
        "judgment_schema": {
            "judgment_values": {
                "floor_count": 6,
                "has_sprinkler": None,
                "stairwell_count": 2,
            }
        }
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "이미 수집된 판단값" in ctx
    assert "floor_count" in ctx and "stairwell_count" in ctx
    # None 값은 제외.
    assert "has_sprinkler" not in ctx
