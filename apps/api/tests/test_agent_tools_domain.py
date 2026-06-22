"""도메인 도구 실서비스 연결 테스트 — CMP-DIRECT.

search_address(juso)·check_building_register(CODEF)·evaluate_rules(rule_engine) 가
실제 서비스에 연결되고, 실패를 구조화 결과로 degrade 하는지 검증한다. juso/CODEF 는
monkeypatch 로 대체하고, rule_engine 은 순수 함수라 실호출한다.
"""

from __future__ import annotations

import asyncio
import uuid

from src.agent.tools import domain
from src.errors import ZippinException
from src.services import home_check, leads


async def test_search_address_wraps_results(monkeypatch) -> None:
    async def fake_search(*, keyword: str, **_: object) -> dict[str, object]:
        assert keyword == "테헤란로"
        return {"total_count": 2, "items": [{"road_addr": "A"}, {"road_addr": "B"}]}

    monkeypatch.setattr(leads, "search_addresses", fake_search)
    res = await domain.search_address_impl(keyword="테헤란로")
    assert res["ok"] is True
    assert res["total_count"] == 2
    assert len(res["items"]) == 2


async def test_search_address_degrades_on_service_error(monkeypatch) -> None:
    async def fake_search(*, keyword: str, **_: object) -> dict[str, object]:
        raise ZippinException("키 없음", code="JUSO_CONFM_KEY_MISSING", http_status=503)

    monkeypatch.setattr(leads, "search_addresses", fake_search)
    res = await domain.search_address_impl(keyword="x")
    assert res["ok"] is False
    assert res["error_code"] == "JUSO_CONFM_KEY_MISSING"


async def test_check_building_register_starts_background_job(monkeypatch) -> None:
    # CODEF 는 느리고 취소-취약하므로 잡만 만들고 처리는 백그라운드로 돌린다.
    job_id = uuid.uuid4()
    owner = uuid.uuid4()
    ran: dict[str, object] = {}

    async def fake_create(**_: object) -> dict[str, object]:
        return {"id": job_id, "status": "querying"}

    async def fake_run(_id: uuid.UUID, **__: object) -> None:
        ran["id"] = _id

    monkeypatch.setattr(home_check, "create_home_check", fake_create)
    monkeypatch.setattr(home_check, "run_home_check", fake_run)

    res = await domain.check_building_register_impl(
        owner_user_id=owner,
        owner_is_anonymous=False,
        road_addr="서울시 강남구 테헤란로 1",
        dong="101",
        ho="1502",
    )
    assert res["ok"] is True
    assert res["status"] == "querying"
    assert res["home_check_id"] == str(job_id)
    # 백그라운드 태스크가 실행되도록 한 틱 양보.
    await asyncio.sleep(0)
    assert ran.get("id") == job_id


async def test_check_building_register_degrades_on_codef_error(monkeypatch) -> None:
    async def fake_create(**_: object) -> dict[str, object]:
        raise ZippinException("점검중", code="UPSTREAM_UNAVAILABLE", http_status=502)

    monkeypatch.setattr(home_check, "create_home_check", fake_create)
    res = await domain.check_building_register_impl(
        owner_user_id=uuid.uuid4(),
        owner_is_anonymous=False,
        road_addr="x",
        dong="1",
        ho="1",
    )
    assert res["ok"] is False
    assert res["error_code"] == "UPSTREAM_UNAVAILABLE"


def test_evaluate_rules_load_bearing_denies() -> None:
    res = domain.evaluate_rules_impl(
        judgment_values={
            "wall_type": "LOAD_BEARING",
            "floor_count": 5,
            "has_sprinkler": True,
            "has_evacuation_space": True,
            "stairwell_count": 2,
            "window_form": "FIXED",
            "fire_zone": False,
        }
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "DENY"
    assert res["result"]["schema_version"]


def test_evaluate_rules_missing_field_holds() -> None:
    res = domain.evaluate_rules_impl(judgment_values={"wall_type": "NON_LOAD_BEARING"})
    assert res["ok"] is True
    assert res["result"]["verdict"] == "HOLD"


def test_evaluate_rules_invalid_input_is_structured_error() -> None:
    res = domain.evaluate_rules_impl(judgment_values={"unknown_key": 1})
    assert res["ok"] is False
    assert res["error_code"] == "RULE_INPUT_INVALID"


def test_emit_ui_component_accumulates_across_calls() -> None:
    # #multi-emit: 한 턴에 여러 번 호출하면 누적(덮어쓰지 않음).
    ctx = domain.RunContext()
    domain.emit_ui_component_impl(run_context=ctx, components=[{"kind": "result"}])
    domain.emit_ui_component_impl(
        run_context=ctx, components=[{"kind": "cta"}], judgment_snapshot={"v": 1}
    )
    ui, snapshot = ctx.drain_ui()
    assert [c["kind"] for c in ui] == ["result", "cta"]
    assert snapshot == {"v": 1}
    # drain 후 비워진다.
    assert ctx.drain_ui() == ([], None)
