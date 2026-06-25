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


def test_normalize_drops_out_of_range_confidence() -> None:
    s = vlm._normalize_supplement(
        {"confidence": 1.5, "notes": [], "reclassifications": []},
        model="m",
        valid_ids=set(),
    )
    assert s["confidence"] is None


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
