"""도메인 도구 실서비스 연결 테스트 — CMP-DIRECT.

search_address(juso)·check_building_register(CODEF)·evaluate_rules(rule_engine) 가
실제 서비스에 연결되고, 실패를 구조화 결과로 degrade 하는지 검증한다. juso/CODEF 는
monkeypatch 로 대체하고, rule_engine 은 순수 함수라 실호출한다.
"""

from __future__ import annotations

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


async def test_check_building_register_returns_serialized_job(monkeypatch) -> None:
    job_id = uuid.uuid4()
    owner = uuid.uuid4()

    async def fake_create(**_: object) -> dict[str, object]:
        return {"id": job_id, "status": "querying"}

    async def fake_run(_id: uuid.UUID, **__: object) -> None:
        return None

    async def fake_get_row(*, home_check_id: uuid.UUID, user_id: uuid.UUID):
        assert home_check_id == job_id and user_id == owner
        return {"id": job_id, "status": "completed"}

    def fake_serialize(row: dict, *, with_documents: bool = True):
        return {"schema_version": "1.1.0", "id": str(row["id"]), "status": "completed"}

    monkeypatch.setattr(home_check, "create_home_check", fake_create)
    monkeypatch.setattr(home_check, "run_home_check", fake_run)
    monkeypatch.setattr(home_check, "get_home_check_row", fake_get_row)
    monkeypatch.setattr(home_check, "serialize_job", fake_serialize)

    res = await domain.check_building_register_impl(
        owner_user_id=owner,
        owner_is_anonymous=False,
        road_addr="서울시 강남구 테헤란로 1",
        dong="101",
        ho="1502",
    )
    assert res["ok"] is True
    assert res["home_check_id"] == str(job_id)
    assert res["job"]["status"] == "completed"


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
