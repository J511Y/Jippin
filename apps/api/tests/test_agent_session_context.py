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


def test_floorplan_unknown_wall_counts_and_guidance() -> None:
    # 미확정 벽(UNKNOWN)은 스냅샷에 별도 카운트 + 단정 금지 지침으로 노출된다.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [
                {"id": "pred:1", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:2", "wall_type": "UNKNOWN"},
            ]
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "미확정 벽 1곳" in ctx
    assert "단정하지 말고" in ctx


def test_selected_unknown_wall_flags_confirmation() -> None:
    # 선택에 UNKNOWN 이 섞이면 '모두 비내력벽 후보' 대신 확인 필요 노트가 붙는다.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [
                {"id": "pred:5", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:9", "wall_type": "UNKNOWN"},
            ],
            "selected_walls": ["pred:5", "pred:9"],
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "모두 비내력벽 후보" not in ctx
    assert "미확정 벽 포함" in ctx and "단정 금지" in ctx


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


def test_selected_windows_surface_with_boundary_delegation() -> None:
    # 창호 선택은 개수·region_id 와 함께 경계 판단(window_demolition_boundary) 위임
    # 지침을 싣는다 — 에이전트가 외기/발코니-실 경계를 판단해 룰 평가로 넘기게.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [{"id": "pred:1", "wall_type": "NON_LOAD_BEARING"}],
            "window_objects": [{"id": "pred:7"}, {"id": "pred:8"}],
            "selected_windows": ["pred:7"],
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "창호 2곳" in ctx  # 분석된 창호 수가 평면도 라인에 실린다
    assert "직접 선택한 창호: 1곳" in ctx
    assert "pred:7" in ctx
    assert "window_demolition_boundary" in ctx
    assert "EXTERIOR|BALCONY_BOUNDARY" in ctx


def test_floorplan_no_candidates_requests_reupload() -> None:
    # #floorplan-reupload-exception: 분석은 끝났지만(wall_objects 키 존재) 벽·창호 후보가
    # 0 이면 '분석 진행/대기'가 아니라 재업로드 예외 안내를 준다 — 운영에서 벽이 하나도
    # 안 잡힌 도면(wall_objects=[]) 이 "다시 요청 금지"로 굳어 사용자가 갇히던 케이스.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [],
            "space_objects": [{"id": "pred:25", "type": "ETC"}],
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "emit_floorplan_request" in ctx
    assert "다른" in ctx and "평면도" in ctx
    assert "분석 진행/대기" not in ctx
    assert "검토를 이어갈 수 없다" in ctx


def test_floorplan_windows_only_still_reviewable() -> None:
    # 벽 후보 0 이어도 창호가 있으면 창호 철거 검토는 가능 — 재업로드 예외가 아니라
    # 분석 완료 카운트로 안내한다.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [],
            "window_objects": [{"id": "win:1"}],
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "창호 1곳" in ctx
    assert "emit_floorplan_request" not in ctx


def test_floorplan_attached_without_analysis_stays_pending() -> None:
    # 분석 전(wall_objects 키 자체가 없음)엔 종전대로 '분석 진행/대기' + 재요청 금지.
    session = {"selected_floorplan_asset_id": "asset-1", "judgment_schema": {}}
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "분석 진행/대기" in ctx
    assert "emit_floorplan_request" not in ctx


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


# --- region_assessments 반영 (#region-assessments) --------------------------


def _vlm(assessments: list[dict]) -> dict:
    return {
        "provider": "OPENAI",
        "model": "m",
        "notes": [],
        "reclassifications": [],
        "region_assessments": assessments,
    }


def test_selected_walls_carry_location_and_vlm_opinion() -> None:
    # 선택 벽마다 분석 분류 + VLM 위치/의견/근거가 한 줄씩 실리고, 되풀이 금지 규칙이 붙는다.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [
                {"id": "pred:5", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:9", "wall_type": "NON_LOAD_BEARING"},
            ],
            "selected_walls": ["pred:5", "pred:9"],
            "vlm_supplement": _vlm(
                [
                    {
                        "region_id": "pred:5",
                        "kind": "wall",
                        "location": "거실과 침실1 사이",
                        "assessment": "NON_LOAD_BEARING",
                        "reason": "얇은 단선 벽체",
                    }
                ]
            ),
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "pred:5 — 분석 분류: 비내력벽 후보 / VLM 위치: «거실과 침실1 사이»" in ctx
    assert "VLM 의견: 비내력 추정" in ctx and "근거: «얇은 단선 벽체»" in ctx
    assert "pred:9 — 분석 분류: 비내력벽 후보 / VLM 위치/의견: 없음" in ctx
    assert "되풀이하지 말고" in ctx
    assert "두 근거가 일치하면" in ctx


def test_selected_wall_conflict_between_segmentation_and_vlm_is_flagged() -> None:
    # 분류는 비내력 후보인데 VLM 이 내력/미확정으로 보면 '어긋남' 지침이 붙는다(단정 금지).
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [{"id": "pred:5", "wall_type": "NON_LOAD_BEARING"}],
            "selected_walls": ["pred:5"],
            "vlm_supplement": _vlm(
                [
                    {
                        "region_id": "pred:5",
                        "kind": "wall",
                        "location": "PS 옆 짧은 벽",
                        "assessment": "LOAD_BEARING",
                        "reason": "두꺼운 해칭",
                    }
                ]
            ),
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "VLM 의견: 내력 추정(주의)" in ctx
    assert "어긋나는 벽이 있다" in ctx


def test_analyzed_floorplan_lists_region_locations_for_orientation() -> None:
    # 선택 전에도 어느 영역이 어디인지 안내할 수 있게 선택 가능 영역의 위치를 나열한다.
    # 내력벽(선택 불가)은 제외, 창호는 경계 판정 라벨과 함께.
    session = {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [
                {"id": "pred:1", "wall_type": "NON_LOAD_BEARING"},
                {"id": "pred:2", "wall_type": "LOAD_BEARING"},
            ],
            "window_objects": [{"id": "pred:7"}],
            "vlm_supplement": _vlm(
                [
                    {
                        "region_id": "pred:1",
                        "kind": "wall",
                        "location": "거실과 침실1 사이",
                        "assessment": "NON_LOAD_BEARING",
                    },
                    {
                        "region_id": "pred:2",
                        "kind": "wall",
                        "location": "외곽 벽",
                        "assessment": "LOAD_BEARING",
                    },
                    {
                        "region_id": "pred:7",
                        "kind": "window",
                        "location": "거실과 발코니 사이",
                        "assessment": "BALCONY_BOUNDARY",
                    },
                ]
            ),
        },
    }
    ctx = build_session_state_context(session, None)
    assert ctx is not None
    assert "선택 가능한 영역의 도면상 위치" in ctx
    assert "pred:1=«거실과 침실1 사이»(비내력벽 후보)" in ctx
    assert "pred:7=«거실과 발코니 사이»(창호, 발코니-실내 사이 경계 창(분합창))" in ctx
    assert "pred:2=" not in ctx


def _window_session(assessments: dict[str, str]) -> dict:
    return {
        "selected_floorplan_asset_id": "asset-1",
        "judgment_schema": {
            "wall_objects": [],
            "window_objects": [{"id": "pred:7"}, {"id": "pred:8"}],
            "selected_windows": ["pred:7", "pred:8"],
            "vlm_supplement": _vlm(
                [
                    {
                        "region_id": rid,
                        "kind": "window",
                        "location": f"{rid} 위치",
                        "assessment": a,
                    }
                    for rid, a in assessments.items()
                ]
            ),
        },
    }


def test_selected_windows_all_boundary_skips_question() -> None:
    ctx = build_session_state_context(
        _window_session({"pred:7": "BALCONY_BOUNDARY", "pred:8": "BALCONY_BOUNDARY"}),
        None,
    )
    assert ctx is not None
    assert "다시 묻지 말고" in ctx
    assert "BALCONY_BOUNDARY 를 자동 반영" in ctx
    assert "pred:7 — 분석 분류: 창호 / VLM 위치: «pred:7 위치»" in ctx


def test_selected_windows_exterior_warns_and_offers_reshow() -> None:
    ctx = build_session_state_context(
        _window_session({"pred:7": "EXTERIOR", "pred:8": "BALCONY_BOUNDARY"}), None
    )
    assert ctx is not None
    assert "외기와 직접 닿는 바깥 창" in ctx
    assert "show_floorplan_overlay" in ctx


def test_selected_windows_uncertain_asks_only_that_window() -> None:
    ctx = build_session_state_context(
        _window_session({"pred:7": "BALCONY_BOUNDARY", "pred:8": "UNCERTAIN"}), None
    )
    assert ctx is not None
    assert "그 창에 대해서만" in ctx
    assert "window_demolition_boundary(EXTERIOR|BALCONY_BOUNDARY)" in ctx
