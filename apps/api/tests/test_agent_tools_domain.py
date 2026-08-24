"""도메인 도구 실서비스 연결 테스트 — CMP-DIRECT.

search_address(juso)·check_building_register(CODEF)·evaluate_rules(rule_engine) 가
실제 서비스에 연결되고, 실패를 구조화 결과로 degrade 하는지 검증한다. juso/CODEF 는
monkeypatch 로 대체하고, rule_engine 은 순수 함수라 실호출한다.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

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


async def _session_with_apartment(monkeypatch):
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    sid = session["id"]
    # 주소(아파트명)를 페이크에 직접 세팅(upsert 는 road/jibun 검증이 있어 우회).
    fake.session_addresses[sid] = {
        "session_id": sid,
        "apartment_name": "만촌 메르디앙",
        "building_dong": None,
        "road_address": None,
        "jibun_address": None,
        "unit_ho": None,
    }
    return sid, fake


async def test_lookup_floorplan_candidates_empty_catalog(monkeypatch) -> None:
    # 카탈로그 미큐레이션(빈) → count 0 + 업로드 안내(직접 올려야 함).
    session_id, _fake = await _session_with_apartment(monkeypatch)
    res = await domain.lookup_floorplan_candidates_impl(session_id=session_id)
    assert res["ok"] is True
    assert res["count"] == 0
    assert "없어" in res["summary"]


async def test_lookup_floorplan_candidates_found(monkeypatch) -> None:
    # 카탈로그에 검증된 공개 도면이 있으면 후보로 반환.
    session_id, fake = await _session_with_apartment(monkeypatch)
    fp_id = uuid.uuid4()
    fake.floorplans[fp_id] = {
        "id": fp_id,
        "apartment_name": "만촌 메르디앙",
        "building_dong": None,
        "size_type": "84A",
        "exclusive_area_m2": None,
        "visibility": "public_catalog",
        "quality_status": "verified",
    }
    res = await domain.lookup_floorplan_candidates_impl(session_id=session_id)
    assert res["count"] == 1
    assert res["candidates"][0]["apartment_name"] == "만촌 메르디앙"
    assert res["candidates"][0]["size_type"] == "84A"


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


async def test_get_building_register_bad_and_missing_id(monkeypatch) -> None:
    res = await domain.get_building_register_impl(
        owner_user_id=uuid.uuid4(), home_check_id="not-a-uuid"
    )
    assert res["ok"] is False
    assert res["error_code"] == "BUILDING_REGISTER_BAD_ID"

    async def none_row(**_: object) -> None:
        return None

    monkeypatch.setattr(home_check, "get_home_check_row", none_row)
    res = await domain.get_building_register_impl(
        owner_user_id=uuid.uuid4(), home_check_id=str(uuid.uuid4())
    )
    assert res["ok"] is False
    assert res["error_code"] == "BUILDING_REGISTER_NOT_FOUND"


async def test_get_building_register_pending_returns_status_only(monkeypatch) -> None:
    async def querying_row(**_: object) -> dict[str, object]:
        return {"status": "querying"}

    monkeypatch.setattr(home_check, "get_home_check_row", querying_row)
    res = await domain.get_building_register_impl(
        owner_user_id=uuid.uuid4(), home_check_id=str(uuid.uuid4())
    )
    assert res["ok"] is True
    assert res["status"] == "querying"
    assert "change_history" not in res


async def test_get_building_register_completed_returns_permit_history(
    monkeypatch,
) -> None:
    # 완료된 잡은 위반 여부 + 변동/행위허가 이력을 돌려준다 — "거실-발코니 비내력벽 철거
    # 행위허가" 같은 이력이 에이전트 판단 근거로 도달해야 한다(#register-readback).
    # 저장 순서(전유부 전체→표제부 전체)와 무관하게 날짜 정렬 후 최근 이력을 남기고,
    # 핵심은 세션 judgment_schema.register_supplement 로 영속한다(Codex P1/P2).
    async def completed_row(**_: object) -> dict[str, object]:
        return {
            "status": "completed",
            "violation": False,
            "exclusive_violation": False,
            "heading_violation": False,
            "building_floors": "지상 15층",
            "exclusive_floor": "3층",
            # 조회 잡이 실행된 주소 — 세션 주소와 동일 세대(접미사 유무 혼재 표기).
            "road_addr": "서울시 강남구 테헤란로 1",
            "addr_dong": "802",
            "addr_ho": "1406",
            "change_list": [
                {
                    "date": "2009-03-17",
                    "reason": "행위허가:거실과(와) 발코니 사이 비내력벽 철거",
                    "source": "exclusive",
                },
                {
                    "date": "2018-05-01",
                    "reason": "표시변경(용도변경)",
                    "source": "heading",
                },
                {"date": "1998-11-02", "reason": "신규작성(신축)", "source": "heading"},
            ],
        }

    merged: dict[str, object] = {}
    address_row = {
        "road_address": "서울시 강남구 테헤란로 1",
        "apartment_name": "장미마을",
        "building_dong": "802동",
        "unit_ho": "1406호",
    }

    async def fake_merge(**kwargs: object) -> dict[str, object]:
        merged.update(kwargs)
        return {}

    async def fake_address(sid: uuid.UUID) -> dict[str, object]:
        return address_row

    monkeypatch.setattr(home_check, "get_home_check_row", completed_row)
    monkeypatch.setattr(main_flow, "merge_judgment_schema", fake_merge)
    monkeypatch.setattr(main_flow, "get_session_address", fake_address)
    session_id = uuid.uuid4()
    res = await domain.get_building_register_impl(
        owner_user_id=uuid.uuid4(),
        home_check_id=str(uuid.uuid4()),
        session_id=session_id,
    )
    assert res["ok"] is True
    assert res["status"] == "completed"
    assert res["violation"]["is_violation"] is False
    assert res["unit_floor"] == "3층"
    # 날짜 오름차순 정렬 — 소스(전유부/표제부) 저장 순서가 아니라 시간순.
    dates = [e["date"] for e in res["change_history"]]
    assert dates == sorted(dates)
    reasons = [e["reason"] for e in res["change_history"]]
    assert any("행위허가" in r and "비내력벽" in r for r in reasons)
    # 전유부/표제부 라벨로 환산돼 내부 enum(exclusive/heading)이 노출되지 않는다.
    assert {e["source"] for e in res["change_history"]} <= {"전유부", "표제부", "대장"}
    assert "행위허가 이력 1건" in res["summary"]
    # register_supplement 영속 — 리포트(웹/PDF)가 읽는 세션 상태로 전달됐다.
    assert merged["session_id"] == session_id
    patch = merged["patch"]
    assert patch["register_supplement"]["is_violation"] is False
    assert patch["register_supplement"]["unit_floor"] == "3층"
    # 내용 기반 주소 지문 — 주소 변경 시 리포트 조립이 stale supplement 를 걸러내는
    # 근거(session_addresses.id 는 upsert 가 보존해 지문으로 못 쓴다).
    from src.services import report_content

    assert patch["register_supplement"][
        "address_fingerprint"
    ] == report_content.address_fingerprint(address_row)
    assert patch["register_supplement"]["address_fingerprint"] != ""
    assert any(
        "행위허가" in str(e.get("reason"))
        for e in patch["register_supplement"]["permit_entries"]
    )


async def test_get_building_register_skips_persist_on_address_change(
    monkeypatch,
) -> None:
    # 조회가 도는 사이 세션 주소가 바뀌면(row 주소 ≠ 현재 주소) supplement 를 영속하지
    # 않는다 — 옛 건물 결과에 새 주소 지문이 찍히는 레이스 차단(Codex 5R P1).
    async def completed_row(**_: object) -> dict[str, object]:
        return {
            "status": "completed",
            "violation": True,
            "road_addr": "서울시 강남구 테헤란로 1",
            "addr_dong": "802",
            "addr_ho": "1406",
            "change_list": [],
        }

    async def fake_merge(**kwargs: object) -> dict[str, object]:
        raise AssertionError("주소 불일치면 영속까지 가면 안 된다")

    async def changed_address(sid: uuid.UUID) -> dict[str, object]:
        return {"road_address": "부산 해운대구 달맞이길 2", "unit_ho": "1406호"}

    monkeypatch.setattr(home_check, "get_home_check_row", completed_row)
    monkeypatch.setattr(main_flow, "merge_judgment_schema", fake_merge)
    monkeypatch.setattr(main_flow, "get_session_address", changed_address)
    res = await domain.get_building_register_impl(
        owner_user_id=uuid.uuid4(),
        home_check_id=str(uuid.uuid4()),
        session_id=uuid.uuid4(),
    )
    # 조회 결과 자체(대화 컨텍스트용)는 그대로 돌려준다 — 리포트 영속만 건너뛴다.
    assert res["ok"] is True
    assert res["violation"]["is_violation"] is True


def test_change_date_key_handles_unpadded_dates() -> None:
    # 구 워커의 무패딩 표기("2024.9.30")는 문자열 정렬이 깨진다 — (연,월,일) 파싱 키로
    # 시간순을 보장한다. 파싱 불가는 가장 오래된 것으로.
    assert domain._change_date_key("2024.9.30") < domain._change_date_key("2024.10.01")
    assert domain._change_date_key("2011.5.20") == (2011, 5, 20)
    assert domain._change_date_key("2009-03-17") == (2009, 3, 17)
    assert domain._change_date_key(None) == (0, 0, 0)
    assert domain._change_date_key("이하여백") == (0, 0, 0)


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


async def test_confirm_address_accepts_apartment_only(monkeypatch) -> None:
    # #address-apt-identity: 도로명/지번 없이 아파트명+동+호 만으로도 주소를 확정·저장한다
    # (building_identity 로 구성). 과거엔 INSUFFICIENT_ADDRESS_DATA 로 거절돼 아파트명조차
    # 저장 못 했다 — 보유 도면 검색·세션 주소 컨텍스트가 막히던 문제.
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    session_id = session["id"]
    res = await domain.confirm_address_impl(
        session_id=session_id,
        owner_user_id=owner,
        owner_is_anonymous=False,
        apartment_name="장미마을",
        building_dong="802동",
        unit_ho="1406호",
    )
    assert res["ok"] is True
    assert res["address"]["apartment_name"] == "장미마을"
    # 세션 주소가 실제로 저장됐고, building_identity 로 충분성 통과.
    saved = next(
        r for r in fake.session_addresses.values() if r["session_id"] == session_id
    )
    assert saved["apartment_name"] == "장미마을"
    assert saved["building_identity"]["apartment_name"] == "장미마을"
    assert saved["building_identity"]["unit_ho"] == "1406호"


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
    # 판정이 세션에 영속돼 리포트 정본이 된다(#session-verdict). status 는 건드리지
    # 않는다(asset-only 세션의 report_ready 전이를 reference-scope 트리거가 막으므로).
    assert fake.sessions[session_id]["rule_eval_result"]["verdict"] == "DENY"
    assert fake.sessions[session_id]["rule_evaluated_at"] is not None


async def test_evaluate_rules_minimal_input_is_conservative_warn(monkeypatch) -> None:
    # v2: 벽 종류만 알고 나머지 안전 변수가 미확인(발코니 확장 여부도 미상)이면 HOLD 가
    # 아니라 보수적 가정 + 미확인 caveat → WARN(리포트 생성). 벽 종류만 HOLD 사유다.
    session_id, _fake = await _session_for_rules(monkeypatch)
    res = await domain.evaluate_rules_impl(
        session_id=session_id, judgment_values={"wall_type": "NON_LOAD_BEARING"}
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "WARN"


def test_apply_vlm_hints_fills_missing_respects_llm() -> None:
    from src.services import rule_engine

    clean = {"has_sprinkler": True}  # LLM 이 직접 준 값
    js = {
        "vlm_supplement": {
            "judgment_hints": {
                "has_sprinkler": False,  # LLM 우선 → 무시
                "stairwell_count": 2,  # 채움
                "balcony_attached": False,  # 채움
                "window_form": None,  # None → 안 채움
            }
        }
    }
    accepted = set(rule_engine.JUDGMENT_VALUE_FIELDS) | set(rule_engine.CONTEXT_FIELDS)
    filled = domain._apply_vlm_hints(clean, js, accepted)
    assert clean["has_sprinkler"] is True  # LLM 값 보존
    assert clean["stairwell_count"] == 2
    assert clean["balcony_attached"] is False
    assert "window_form" not in clean
    assert set(filled) == {"stairwell_count", "balcony_attached"}


async def test_evaluate_rules_uses_vlm_hints_interior(monkeypatch) -> None:
    # VLM 힌트 balcony_attached=False(실내 가벽) + 선택으로 유도된 NON_LOAD_BEARING →
    # 발코니 확장 화재안전 룰 미적용 → ALLOW, 시설 0. 사용자에게 안전 변수를 안 물어도 됨.
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_walls": ["pred:1"],
        "wall_objects": [{"id": "pred:1", "wall_type": "NON_LOAD_BEARING"}],
        "vlm_supplement": {"judgment_hints": {"balcony_attached": False}},
    }
    res = await domain.evaluate_rules_impl(session_id=session_id, judgment_values={})
    assert res["ok"] is True
    assert res["result"]["verdict"] == "ALLOW"
    assert res["result"]["required_facilities"] == []


async def test_evaluate_rules_drops_unknown_keys(monkeypatch) -> None:
    # 계약 밖 key 는 hard-fail(RULE_INPUT_INVALID) 대신 조용히 드롭하고 평가를 진행한다 —
    # LLM 이 여분 key 를 넘겨 평가가 통째로 '실패'하는 걸 막는다. 남은 필수값이 없으면 HOLD.
    session_id, _fake = await _session_for_rules(monkeypatch)
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={"unknown_key": 1, "floor_count": 3, "has_sprinkler": True},
    )
    assert res["ok"] is True  # 실패가 아니라 정상 평가
    assert res["result"]["verdict"] == "HOLD"  # wall_type 등 미수집 → HOLD


async def test_evaluate_rules_derives_wall_type_from_selection(monkeypatch) -> None:
    # wall_type 을 안 넘겨도 selected_walls(비내력 후보)에서 서버가 자동 유도한다.
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_walls": ["pred:1"],
        "wall_objects": [{"id": "pred:1", "wall_type": "NON_LOAD_BEARING"}],
    }
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={
            "floor_count": 3,
            "has_sprinkler": True,
            "has_evacuation_space": True,
            "stairwell_count": 2,
            "window_form": "FIXED",
            "fire_zone": False,
        },
    )
    assert res["ok"] is True
    # wall_type=NON_LOAD_BEARING 으로 채워져 DENY 가 아니라 가능성 계열.
    assert res["result"]["verdict"] in ("ALLOW", "WARN")


async def test_evaluate_rules_unknown_selection_discards_model_wall_type(
    monkeypatch,
) -> None:
    # 구조 불확실 벽(UNKNOWN)이 선택에 섞여 유도가 실패하면, 모델이 넘긴
    # wall_type=NON_LOAD_BEARING 으로 HOLD 를 우회하지 못한다(#wall-unknown-hold,
    # Codex P1).
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_walls": ["pred:1", "pred:2"],
        "wall_objects": [
            {"id": "pred:1", "wall_type": "NON_LOAD_BEARING"},
            {"id": "pred:2", "wall_type": "UNKNOWN"},
        ],
    }
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={
            "wall_type": "NON_LOAD_BEARING",  # 모델의 근거 없는 단정 — 버려야 함
            "floor_count": 3,
            "has_sprinkler": True,
            "has_evacuation_space": True,
            "stairwell_count": 2,
            "window_form": "FIXED",
            "fire_zone": False,
        },
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "HOLD"


async def test_evaluate_rules_window_only_boundary_flow(monkeypatch) -> None:
    # 창호만 고른 세션(#window-only-target) — 벽 종류 미상 HOLD 를 건너뛰고 창호
    # 경계(R-WINDOW-01)를 본다. 경계 미상이면 HOLD(재확인), LLM 이 경계를 판단해
    # BALCONY_BOUNDARY 로 넘기면 발코니 확장 경로로 평가된다.
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_windows": ["pred:7"],
        "window_objects": [{"id": "pred:7"}],
    }
    res = await domain.evaluate_rules_impl(session_id=session_id, judgment_values={})
    assert res["ok"] is True
    assert res["result"]["verdict"] == "HOLD"
    assert all("내력벽" not in c for c in res["result"].get("additional_checks", []))

    res2 = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={
            "window_demolition_boundary": "BALCONY_BOUNDARY",
            "floor_count": 3,
            "has_sprinkler": False,
            "has_evacuation_space": True,
            "stairwell_count": 1,
            "window_form": "OPENABLE",
            "fire_zone": False,
        },
    )
    assert res2["ok"] is True
    assert res2["result"]["verdict"] in ("ALLOW", "WARN")
    # 창호-only 선택도 분석+선택 요건을 충족해 판정이 영속된다(#require-analyzed-selection).
    assert fake.sessions[session_id]["rule_eval_result"] is not None


async def test_evaluate_rules_window_only_discards_model_wall_type(monkeypatch) -> None:
    # 창호-only 세션에서 모델이 (검토와 무관한 벽의) wall_type=LOAD_BEARING 을 넘겨도
    # 내력벽 철거로 오판·DENY 되지 않아야 한다 — 벽 선택이 없으면 모델 wall_type 을 버리고
    # 창호 경계로만 판단한다(#window-only-target, Codex P2).
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_windows": ["pred:7"],
        "window_objects": [{"id": "pred:7"}],
    }
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={
            "wall_type": "LOAD_BEARING",  # 무관한 벽 — 창호 경로가 격리해야 함
            "window_demolition_boundary": "BALCONY_BOUNDARY",
            "floor_count": 3,
            "has_sprinkler": False,
            "has_evacuation_space": True,
            "stairwell_count": 1,
            "window_form": "OPENABLE",
            "fire_zone": False,
        },
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] != "DENY"


async def test_evaluate_rules_window_exterior_denies(monkeypatch) -> None:
    # 외기 직접 접촉 최외곽 창호 → DENY (LLM 이 EXTERIOR 로 판단해 넘긴 경우).
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_windows": ["pred:7"],
        "window_objects": [{"id": "pred:7"}],
    }
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={"window_demolition_boundary": "EXTERIOR"},
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "DENY"


async def test_evaluate_rules_uses_analysis_fingerprint(monkeypatch) -> None:
    # #analysis-input-fingerprint: 분석 시작 지문(run_context)이 현재 세션 입력과 다르면
    # (분석 도중 도면 교체) verdict 를 영속하지 않는다.
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    session_id = session["id"]
    a1 = await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=owner,
        payload={
            "bucket": "session-floorplans",
            "object_key": f"{owner}/{session_id}/a1.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )
    ctx = domain.RunContext()
    ctx.analysis_inputs = (a1["id"], None)  # 분석은 a1 기준으로 시작됨
    # 분석 도중 a2 로 교체.
    await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=owner,
        payload={
            "bucket": "session-floorplans",
            "object_key": f"{owner}/{session_id}/a2.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={"wall_type": "NON_LOAD_BEARING"},
        run_context=ctx,
    )
    assert res["ok"] is True  # 판정은 사용자에게 반환
    # 그러나 입력이 분석 시작 지문과 달라져 stale 판정은 영속되지 않는다.
    assert fake.sessions[session_id]["rule_eval_result"] is None


async def test_evaluate_rules_agent_cross_turn_persists_with_analysis(
    monkeypatch,
) -> None:
    # #report-cross-turn + #require-analyzed-selection: 에이전트 cross-turn(지문 없음)에서
    # 이전 턴 분석(wall_objects)+선택(selected_walls)이 세션에 있으면 현재 입력으로 폴백해
    # **영속**한다 → 리포트 준비. (멀티턴 정상 흐름.)
    session_id, fake = await _session_for_rules(monkeypatch)
    fake.sessions[session_id]["judgment_schema"] = {
        "selected_walls": ["pred:1"],
        "wall_objects": [{"id": "pred:1", "wall_type": "LOAD_BEARING"}],
    }
    ctx = domain.RunContext()  # analysis_inputs 미설정(None)
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={"floor_count": 5},
        run_context=ctx,
    )
    assert res["ok"] is True
    assert res["result"]["verdict"] == "DENY"  # 선택이 내력벽 → DENY
    assert fake.sessions[session_id]["rule_eval_result"] is not None
    assert fake.sessions[session_id]["rule_eval_result"]["verdict"] == "DENY"


async def test_evaluate_rules_agent_cross_turn_no_analysis_skips_persist(
    monkeypatch,
) -> None:
    # #require-analyzed-selection: 에이전트 cross-turn 인데 분석/선택이 없으면(segment 안
    # 돈 턴에서 모델이 wall_type 만 들고 온 경우) 판정은 보여 주되 **영속하지 않는다** —
    # 분석 없는 판정이 리포트로 발행되는 걸 막는다.
    session_id, fake = await _session_for_rules(monkeypatch)
    ctx = domain.RunContext()
    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={"wall_type": "NON_LOAD_BEARING", "balcony_attached": False},
        run_context=ctx,
    )
    assert res["ok"] is True
    assert fake.sessions[session_id]["rule_eval_result"] is None  # 영속 안 됨


async def test_legacy_stale_selection_cannot_advance_or_persist_verdict(
    monkeypatch,
) -> None:
    # 구 web 번들은 409 SELECTION_STALE 를 무시하고 "선택 완료" 채팅을 보낼 수 있다.
    # 서버는 stale 선택을 원자적으로 거절하고, 모델이 이어서 비내력 판정을 주장해도
    # 분석 객체+실제 저장 선택이 없으므로 상태/판정을 전진시키지 않는다.
    session_id, fake = await _session_for_rules(monkeypatch)
    owner = fake.sessions[session_id]["user_id"]
    fake.sessions[session_id]["status"] = "awaiting_overlay"
    fake.sessions[session_id]["judgment_schema"] = {
        "wall_objects": [{"id": "new:1", "wall_type": "NON_LOAD_BEARING"}]
    }

    with pytest.raises(ZippinException) as exc:
        await main_flow.merge_judgment_schema(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            patch={"selected_walls": ["stale:1"]},
            validate_selection=True,
        )
    assert exc.value.code == "SELECTION_STALE"
    assert "selected_walls" not in fake.sessions[session_id]["judgment_schema"]
    assert fake.sessions[session_id]["status"] == "awaiting_overlay"

    res = await domain.evaluate_rules_impl(
        session_id=session_id,
        judgment_values={
            "wall_type": "NON_LOAD_BEARING",
            "wall_demolition_target": True,
        },
        run_context=domain.RunContext(),
    )
    assert res["ok"] is True
    assert fake.sessions[session_id]["rule_eval_result"] is None
    assert fake.sessions[session_id]["status"] == "awaiting_overlay"


async def test_merge_judgment_schema_clears_stale_verdict(monkeypatch) -> None:
    # #stale-verdict-on-input-change: selected_walls/wall_objects 가 바뀌면 그 입력으로
    # 계산된 기존 rule_eval_result 를 비운다(옛 판정이 새 맥락에서 rule-backed 로 보이지 않게).
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    sid = session["id"]
    fake.sessions[sid]["rule_eval_result"] = {"verdict": "ALLOW"}
    fake.sessions[sid]["rule_evaluated_at"] = "2026-06-26T00:00:00Z"

    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["pred:2"]},
    )
    assert fake.sessions[sid]["rule_eval_result"] is None
    assert fake.sessions[sid]["rule_evaluated_at"] is None


async def test_merge_judgment_schema_keeps_verdict_for_non_input_patch(
    monkeypatch,
) -> None:
    # vlm_supplement 등 '입력'이 아닌 키만 바뀌면 verdict 를 유지한다.
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    sid = session["id"]
    fake.sessions[sid]["rule_eval_result"] = {"verdict": "ALLOW"}

    await main_flow.merge_judgment_schema(
        session_id=sid,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"vlm_supplement": {"notes": []}},
    )
    assert fake.sessions[sid]["rule_eval_result"] == {"verdict": "ALLOW"}


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


async def _session_run_ctx(monkeypatch):
    from tests._main_flow_db_fake import install_main_flow_fake

    fake = install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    return session["id"], run["id"], fake, domain.RunContext()


async def test_judgment_summary_uses_rule_verdict_when_present(monkeypatch) -> None:
    # 룰엔진 판정이 영속돼 있으면 그 verdict 가 카드 decision 의 정본(LLM 인자 무시).
    session_id, run_id, fake, ctx = await _session_run_ctx(monkeypatch)
    fake.sessions[session_id]["rule_eval_result"] = {"verdict": "DENY"}
    await domain.emit_judgment_summary_impl(
        run_context=ctx,
        run_id=run_id,
        session_id=session_id,
        decision="conditional",  # LLM 이 conditional 이라 우겨도
        title="t",
        summary="s",
    )
    ui, _snap = ctx.drain_ui()
    props = ui[0]["elements"]["j"]["props"]
    assert props["decision"] == "not_possible"  # DENY → not_possible 로 교정
    assert props["rule_backed"] is True


async def test_judgment_summary_flags_llm_only_without_rule(monkeypatch) -> None:
    # 룰엔진 판정이 없으면 LLM 단독 판정 — decision 은 유지하되 rule_backed=false 로 표시.
    session_id, run_id, _fake, ctx = await _session_run_ctx(monkeypatch)
    await domain.emit_judgment_summary_impl(
        run_context=ctx,
        run_id=run_id,
        session_id=session_id,
        decision="conditional",
        title="t",
        summary="s",
    )
    ui, _snap = ctx.drain_ui()
    props = ui[0]["elements"]["j"]["props"]
    assert props["rule_backed"] is False
    assert props["decision"] == "conditional"


async def test_handoff_emits_consultation_card(monkeypatch) -> None:
    # HOLD_OR_HANDOFF → 상담 인입 카드 자동 방출(reason 머리말 + 확정 주소 prefill).
    session_id, run_id, fake, ctx = await _session_run_ctx(monkeypatch)
    fake.session_addresses[uuid.uuid4()] = {
        "id": uuid.uuid4(),
        "session_id": session_id,
        "road_address": "서울특별시 강남구 테헤란로 1",
    }
    res = await domain.set_completion_decision_impl(
        session_id=session_id,
        completion_decision="HOLD_OR_HANDOFF",
        reason="자동으로 확인이 어려워 전문가가 봐 드릴게요.",
        run_context=ctx,
        run_id=run_id,
    )
    assert res["ok"] is True
    assert res["handoff_emitted"] is True
    ui, _snap = ctx.drain_ui()
    props = ui[0]["elements"]["ch"]["props"]
    assert ui[0]["elements"]["ch"]["type"] == "ConsultationHandoff"
    assert props["reason"] == "자동으로 확인이 어려워 전문가가 봐 드릴게요."
    assert props["prefill_address"] == "서울특별시 강남구 테헤란로 1"
    assert props["from_session"] == str(session_id)


async def test_handoff_prefill_falls_back_to_apartment(monkeypatch) -> None:
    # 도로명/지번이 없고 아파트명+동+호만 있는 세션도 prefill_address 가 채워져야 한다
    # (상담 리드 주소 공란 방지, 0019).
    session_id, run_id, fake, ctx = await _session_run_ctx(monkeypatch)
    fake.session_addresses[session_id] = {
        "id": uuid.uuid4(),
        "session_id": session_id,
        "road_address": None,
        "jibun_address": None,
        "apartment_name": "장미마을",
        "building_dong": "802동",
        "unit_ho": "1406호",
    }
    res = await domain.set_completion_decision_impl(
        session_id=session_id,
        completion_decision="HOLD_OR_HANDOFF",
        run_context=ctx,
        run_id=run_id,
    )
    assert res["handoff_emitted"] is True
    ui, _snap = ctx.drain_ui()
    props = ui[0]["elements"]["ch"]["props"]
    assert props["prefill_address"] == "장미마을 802동 1406호"


async def test_non_handoff_decision_emits_no_card(monkeypatch) -> None:
    # ASK_MORE 등 일반 결정은 카드를 방출하지 않는다(상담 인입은 handoff 전용).
    session_id, run_id, _fake, ctx = await _session_run_ctx(monkeypatch)
    res = await domain.set_completion_decision_impl(
        session_id=session_id,
        completion_decision="ASK_MORE",
        run_context=ctx,
        run_id=run_id,
    )
    assert res["ok"] is True
    assert res.get("handoff_emitted") is False
    ui, _snap = ctx.drain_ui()
    assert ui == []
