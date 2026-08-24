"""AI-002 VLM 문맥 해석 — 파싱/정규화/게이트 테스트 (CMP-DIRECT).

모델 호출(langchain) 없이 순수 로직(_parse_json/_normalize_supplement)과 비활성 게이트를
검증한다. 머지(AI-003)는 test_agent_tools_segmentation 에서 interpret 를 모킹해 검증한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.tools import vlm


def test_parse_json_strips_fences_and_noise() -> None:
    assert vlm._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert vlm._parse_json('앞 텍스트 {"x": 2} 뒤 텍스트') == {"x": 2}
    assert vlm._parse_json("그냥 텍스트") is None
    assert vlm._parse_json([{"text": '{"y": 3}'}]) == {"y": 3}


def test_normalize_hints_keeps_valid_drops_invalid() -> None:
    hints = vlm._normalize_hints(
        {
            "has_sprinkler": True,
            "has_evacuation_space": "yes",  # bool 아님 → None
            "stairwell_count": 2,
            "window_form": "FIXED",
            "fire_zone": False,
            "balcony_attached": False,
            "extra": 1,  # 어휘 밖 → 무시
        }
    )
    assert hints["has_sprinkler"] is True
    assert hints["has_evacuation_space"] is None
    assert hints["stairwell_count"] == 2
    assert hints["window_form"] == "FIXED"
    assert hints["fire_zone"] is False
    assert hints["balcony_attached"] is False
    assert "extra" not in hints


def test_normalize_hints_bad_window_and_count() -> None:
    hints = vlm._normalize_hints({"window_form": "BANANA", "stairwell_count": -1})
    assert hints["window_form"] is None
    assert hints["stairwell_count"] is None


def test_normalize_hints_non_dict() -> None:
    assert vlm._normalize_hints(None) == {}
    assert vlm._normalize_hints("x") == {}


def test_normalize_supplement_filters_invalid() -> None:
    data = {
        "is_floorplan": True,
        "confidence": 0.7,
        "notes": ["관찰1", "", 5, "관찰2"],
        "reclassifications": [
            {
                "object_id": "pred:1",
                "new_label": "wall_reinforced_concrete",
                "reason": "r",
            },
            {"object_id": "pred:99", "new_label": "wall_other"},  # 알 수 없는 id
            {"object_id": "pred:2", "new_label": "BANANA"},  # 어휘 밖 label
        ],
    }
    s = vlm._normalize_supplement(
        data, model="gpt-5.4-mini", valid_ids={"pred:1", "pred:2"}
    )
    assert s["provider"] == "OPENAI"
    assert s["model"] == "gpt-5.4-mini"
    assert s["notes"] == ["관찰1", "관찰2"]  # 빈/비문자 제거
    assert len(s["reclassifications"]) == 1
    assert s["reclassifications"][0]["object_id"] == "pred:1"
    assert s["confidence"] == 0.7
    assert s["is_floorplan"] is True


def test_normalize_supplement_wall_labels_only() -> None:
    # #vlm-wall-only: 교정 라벨은 벽 3종만 — 창/공간으로의 계약 밖 교정(창호가 '확정
    # 비내력벽'으로 선택·평가되는 경로)을 정규화에서 차단한다(Codex P1).
    data = {
        "reclassifications": [
            {"object_id": "pred:1", "new_label": "window"},  # 벽→창 금지
            {"object_id": "pred:1", "new_label": "space_living_room"},  # 벽→공간 금지
            {"object_id": "pred:1", "new_label": "wall_unknown"},  # 벽→벽 허용
        ]
    }
    s = vlm._normalize_supplement(data, model="m", valid_ids={"pred:1"})
    assert [r["new_label"] for r in s["reclassifications"]] == ["wall_unknown"]


def test_normalize_drops_out_of_range_confidence() -> None:
    s = vlm._normalize_supplement(
        {"confidence": 1.5, "notes": [], "reclassifications": []},
        model="m",
        valid_ids=set(),
    )
    assert s["confidence"] is None


def test_is_floorplan_only_explicit_false_rejects() -> None:
    # #explicit-false-only: 명시적 boolean False 만 '평면도 아님'. null/누락/형식오류
    # (불확실)는 True 로 둬, 세그멘테이션이 이미 찾은 유효 도면을 NOT_FLOORPLAN 으로
    # 막지 않는다(bool(None)→False 강등 회귀 방지).
    base = {"notes": [], "reclassifications": []}

    def flag(value: object) -> bool:
        data = dict(base)
        if value is not ...:
            data["is_floorplan"] = value
        return vlm._normalize_supplement(data, model="m", valid_ids=set())[
            "is_floorplan"
        ]

    assert flag(False) is False  # 명시적 거부만 False
    assert flag(True) is True
    assert flag(None) is True  # 불확실 → 통과(과거엔 bool(None)=False 로 오차단)
    assert flag(...) is True  # 키 누락 → 통과
    assert flag("maybe") is True  # 형식오류 → 통과


async def test_interpret_uses_dedicated_vlm_model(monkeypatch) -> None:
    # VLM 은 대화 에이전트(agent_model)와 분리된 vlm_model 로 호출한다(2026-08-19,
    # 기본 gpt-5.6-luna). supplement.model 표기도 실제 호출 모델을 따른다.
    import sys

    captured: dict[str, object] = {}

    class _FakeChat:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def ainvoke(self, messages: object) -> SimpleNamespace:
            return SimpleNamespace(
                content='{"is_floorplan": true, "confidence": 0.9, "notes": [],'
                ' "reclassifications": []}'
            )

    monkeypatch.setitem(
        sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=_FakeChat)
    )
    settings = SimpleNamespace(
        vlm_floorplan_enabled=True,
        vlm_model="openai:gpt-5.6-luna",
        agent_model="openai:gpt-5.4-mini",
        openai_api_key="k",
        openai_store_logs=False,
        app_env="test",
        vlm_floorplan_timeout_seconds=5,
    )
    res = await vlm.interpret_floorplan_impl(
        image_url="https://x/y.png",
        regions=[
            {
                "region_id": "pred:1",
                "class_name": "wall_other",
                "polygon": [0, 0, 1, 1, 2, 2],
            }
        ],
        image={"width": 10, "height": 10},
        settings=settings,
    )
    assert captured["model"] == "gpt-5.6-luna"
    assert captured["use_responses_api"] is True
    assert captured["extra_body"] == {"metadata": {"app": "jippin-vlm", "env": "test"}}
    assert res is not None and res["model"] == "gpt-5.6-luna"


async def test_interpret_falls_back_to_agent_model_without_vlm_override(
    monkeypatch,
) -> None:
    # 실제 Settings 기본(vlm_model=None)은 agent_model 로 폴백 — AGENT_MODEL 만 바꾼
    # 롤백도 VLM 에 적용된다. 빈 문자열 compose 주입도 같은 경로다.
    import sys

    captured: dict[str, object] = {}

    class _FakeChat:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def ainvoke(self, messages: object) -> SimpleNamespace:
            return SimpleNamespace(
                content='{"is_floorplan": true, "notes": [], "reclassifications": []}'
            )

    monkeypatch.setitem(
        sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=_FakeChat)
    )
    settings = SimpleNamespace(
        vlm_floorplan_enabled=True,
        vlm_model="",  # compose 의 빈 override 경로
        agent_model="openai:gpt-5.4-mini",
        openai_api_key="k",
        openai_store_logs=False,
        app_env="test",
        vlm_floorplan_timeout_seconds=5,
    )
    res = await vlm.interpret_floorplan_impl(
        image_url="https://x/y.png",
        regions=[
            {
                "region_id": "pred:1",
                "class_name": "wall_other",
                "polygon": [0, 0, 1, 1, 2, 2],
            }
        ],
        image={"width": 10, "height": 10},
        settings=settings,
    )
    assert captured["model"] == "gpt-5.4-mini"
    assert res is not None


async def test_interpret_disabled_returns_none() -> None:
    settings = SimpleNamespace(
        vlm_floorplan_enabled=False,
        agent_model="openai:gpt-5.4-mini",
        openai_api_key="k",
        app_env="test",
        vlm_floorplan_timeout_seconds=60,
    )
    res = await vlm.interpret_floorplan_impl(
        image_url="https://x/y.png",
        regions=[
            {
                "region_id": "pred:1",
                "class_name": "wall_other",
                "polygon": [0, 0, 1, 1, 2, 2],
            }
        ],
        image={"width": 10, "height": 10},
        settings=settings,
    )
    assert res is None


async def test_interpret_no_key_returns_none() -> None:
    settings = SimpleNamespace(
        vlm_floorplan_enabled=True,
        agent_model="openai:gpt-5.4-mini",
        openai_api_key=None,  # 키 없음 → degrade
        app_env="test",
        vlm_floorplan_timeout_seconds=60,
    )
    res = await vlm.interpret_floorplan_impl(
        image_url="https://x/y.png",
        regions=[
            {
                "region_id": "pred:1",
                "class_name": "wall_other",
                "polygon": [0, 0, 1, 1, 2, 2],
            }
        ],
        image={"width": 10, "height": 10},
        settings=settings,
    )
    assert res is None
