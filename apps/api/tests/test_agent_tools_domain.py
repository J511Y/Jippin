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
from src.services import home_check, leads, main_flow


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

    async def no_reuse(**_: object) -> None:
        return None

    monkeypatch.setattr(home_check, "find_reusable_home_check", no_reuse)
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


async def test_check_building_register_reuses_active_job(monkeypatch) -> None:
    # #codef-idempotent: 같은 입력으로 진행 중 잡이 있으면 재사용(중복 생성/run 없음).
    job_id = uuid.uuid4()
    created = False

    async def reuse(**_: object) -> dict[str, object]:
        return {"id": job_id, "status": "querying"}

    async def fake_create(**_: object) -> dict[str, object]:
        nonlocal created
        created = True
        return {"id": uuid.uuid4(), "status": "querying"}

    async def fake_run(_id: uuid.UUID, **__: object) -> None:
        raise AssertionError("재사용 시 새 run 을 띄우면 안 된다")

    monkeypatch.setattr(home_check, "find_reusable_home_check", reuse)
    monkeypatch.setattr(home_check, "create_home_check", fake_create)
    monkeypatch.setattr(home_check, "run_home_check", fake_run)

    res = await domain.check_building_register_impl(
        owner_user_id=uuid.uuid4(),
        owner_is_anonymous=False,
        road_addr="서울시 강남구 테헤란로 1",
        dong="101",
        ho="1502",
    )
    assert res["ok"] is True
    assert res["home_check_id"] == str(job_id)
    assert created is False
    await asyncio.sleep(0)


async def test_check_building_register_degrades_on_codef_error(monkeypatch) -> None:
    async def no_reuse(**_: object) -> None:
        return None

    async def fake_create(**_: object) -> dict[str, object]:
        raise ZippinException("점검중", code="UPSTREAM_UNAVAILABLE", http_status=502)

    monkeypatch.setattr(home_check, "find_reusable_home_check", no_reuse)
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


async def test_confirm_address_sanitizes_non_domain_exception(monkeypatch) -> None:
    # #sanitize-tool-message: 비-도메인 예외의 str(exc)(주소·SQL·URL 가능)를 노출하지 않고
    # 안정적 문구만 반환한다. message 는 runner 가 output_summary 로 승격해 영속하므로.
    secret = "강남구 테헤란로 99, password=hunter2"

    async def boom(**_: object) -> dict[str, object]:
        raise RuntimeError(secret)

    monkeypatch.setattr(main_flow, "upsert_session_address", boom)
    res = await domain.confirm_address_impl(
        session_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        owner_is_anonymous=False,
        road_address="강남구 테헤란로 99",
    )
    assert res["ok"] is False
    assert res["error_code"] == "ADDRESS_UPSERT_FAILED"
    assert secret not in res["message"]
    assert "hunter2" not in res["message"]


async def _session_for_rules(monkeypatch) -> tuple[uuid.UUID, object]:
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    return session["id"], fake


async def test_evaluate_rules_load_bearing_denies(monkeypatch) -> None:
    session_id, fake = await _session_for_rules(monkeypatch)
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={
            "wall_type": "LOAD_BEARING",
            "floor_count": 5,
            "has_sprinkler": True,
            "has_evacuation_space": True,
            "stairwell_count": 2,
            "window_form": "FIXED",
            "fire_zone": False,
        },
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "DENY"
    assert res["result"]["schema_version"]
    # 판정이 세션에 영속돼 리포트 정본이 된다(#session-verdict).
    assert fake.sessions[session_id]["rule_eval_result"]["verdict"] == "DENY"
    assert fake.sessions[session_id]["rule_evaluated_at"] is not None


async def test_evaluate_rules_missing_field_holds(monkeypatch) -> None:
    session_id, _fake = await _session_for_rules(monkeypatch)
    res = await domain.evaluate_rules_impl(
        session_id=session_id, judgment_values={"wall_type": "NON_LOAD_BEARING"}
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "HOLD"


async def test_evaluate_rules_invalid_input_is_structured_error(monkeypatch) -> None:
    session_id, fake = await _session_for_rules(monkeypatch)
    res = await domain.evaluate_rules_impl(
        session_id=session_id, judgment_values={"unknown_key": 1}
    )
    assert res["ok"] is False
    assert res["error_code"] == "RULE_INPUT_INVALID"
    # 잘못된 입력은 판정을 영속하지 않는다.
    assert fake.sessions[session_id]["rule_eval_result"] is None


async def test_emit_ui_component_accumulates_across_calls(monkeypatch) -> None:
    # #multi-emit: 한 턴에 여러 번 호출하면 메모리·내구 버퍼 모두에 누적.
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    ctx = domain.RunContext()
    await domain.emit_ui_component_impl(
        run_context=ctx, run_id=run["id"], components=[{"kind": "result"}]
    )
    await domain.emit_ui_component_impl(
        run_context=ctx,
        run_id=run["id"],
        components=[{"kind": "cta"}],
        judgment_snapshot={"v": 1},
    )
    ui, snapshot = ctx.drain_ui()
    assert [c["kind"] for c in ui] == ["result", "cta"]
    assert snapshot == {"v": 1}
    # 내구 버퍼에도 동일하게 누적되어 resume 에서 살아남는다.
    assert [c["kind"] for c in fake.agent_runs[run["id"]]["pending_ui"]] == [
        "result",
        "cta",
    ]
    assert fake.agent_runs[run["id"]]["pending_judgment_snapshot"] == {"v": 1}
