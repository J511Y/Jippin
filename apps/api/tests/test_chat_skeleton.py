"""Phase A DB-backed tests for /sessions/{id}/chat/* (CMP-609 → DB 영속화).

TEST_MODE 에서는 실 DB 미접속이므로 ``services.main_flow`` 의 ``_db_*`` seam
을 stateful fake (``_main_flow_db_fake``) 로 대체한다 (``test_leads_router``
의 ``_insert_lead`` monkeypatch 패턴 확장).

Coverage:

- ``chat_messages`` append (role=user 만 공개 라우터에 허용) — DB seam 에
  row 가 기록된다.
- ownership: user B 는 user A 세션에 message 를 append 할 수 없다 (404).
- 공개 endpoint 가 assistant/system/tool role 을 흉내내지 못한다 (P2-4 회귀
  보완 — schema 단 거절).
- ``chat_tool_calls`` lifecycle 은 사용자-facing route 가 아니다 (board P2-4).
  HTTP 404 회귀 가드 + internal service 호출 동작은
  ``main_flow.start_chat_tool_call`` / ``complete_chat_tool_call`` 직접 호출로
  검증한다.
- UI 로 렌더링되지 않는 tool output 도 ``output_summary`` 로 저장 가능.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.errors import ZippinException
from src.main import create_app
from src.services import main_flow

from . import _main_flow_db_fake as db_fake
from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    fake = db_fake.install_main_flow_fake(monkeypatch)
    yield fake
    get_settings.cache_clear()


def _bootstrap(monkeypatch) -> tuple[TestClient, str, str, uuid.UUID]:
    """HTTP 경로 테스트용 — 라우터로 세션을 만들고 owner 토큰을 돌려준다."""

    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    client = TestClient(create_app())
    token, subject = helpers.mint_token(pem, jwk["kid"])
    with client:
        session_id = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()["id"]
    return client, token, session_id, subject


async def _create_session_direct() -> tuple[uuid.UUID, uuid.UUID]:
    """internal service 테스트용 — HTTP 우회 없이 서비스로 세션 생성."""

    subject = uuid.uuid4()
    row = await main_flow.create_session(
        user_id=subject,
        is_anonymous_owner=False,
        judgment_schema_version=None,
    )
    return row["id"], subject


def test_append_user_chat_message_records_owner(monkeypatch, fake_db):
    client, token, session_id, subject = _bootstrap(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/chat/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "user",
                "content": "84A 표준 평면도 후보 알려줘",
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["session_id"] == session_id
    assert body["role"] == "user"
    assert body["user_id"] is not None  # owner 토큰의 sub 가 그대로 들어간다
    assert body["ui_components"] == []
    # DB-backed 경로 회귀: message row 가 seam (fake) 을 통해 영속화됐다.
    stored = list(fake_db.chat_messages.values())
    assert len(stored) == 1
    assert stored[0]["user_id"] == subject
    assert stored[0]["content"] == "84A 표준 평면도 후보 알려줘"


def test_append_chat_message_blocks_non_owner(monkeypatch, fake_db):
    """ownership 회귀: user B 는 user A 세션에 message 를 쓸 수 없다 (404)."""

    client, _owner_token, session_id, _ = _bootstrap(monkeypatch)
    pem2, jwk2 = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk2]})
    intruder_token, _ = helpers.mint_token(pem2, jwk2["kid"])
    with client:
        response = client.post(
            f"/sessions/{session_id}/chat/messages",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"role": "user", "content": "남의 세션에 끼어들기"},
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert fake_db.chat_messages == {}


def test_chat_message_endpoint_rejects_non_user_role(monkeypatch):
    """공개 endpoint 가 assistant/system/tool role 을 흉내내지 못하게 막는다.

    Client 가 assistant 인 척 ui_components/judgment_snapshot 을 주입하는 회귀.
    """

    client, token, session_id, _ = _bootstrap(monkeypatch)
    components = [
        {"kind": "candidate_picker", "items": [{"id": "fp-1", "label": "84A"}]},
    ]
    with client:
        for forbidden_role in ("assistant", "system", "tool"):
            response = client.post(
                f"/sessions/{session_id}/chat/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "role": forbidden_role,
                    "content": "다음 후보 중 선택해 주세요.",
                    "ui_components": components,
                },
            )
            # Pydantic Literal['user'] 가 422 로 reject.
            assert response.status_code == 422, forbidden_role
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_internal_assistant_message_records_ui_components(fake_db):
    """``ui_components`` (A2UI payload) 는 internal service 함수로만 기록된다.

    runtime/agent 가 직접 ``main_flow.append_internal_chat_message`` 를 호출한다.
    """

    session_id, _subject = await _create_session_direct()
    components = [
        {"kind": "candidate_picker", "items": [{"id": "fp-1", "label": "84A"}]},
    ]
    row = await main_flow.append_internal_chat_message(
        session_id=session_id,
        role="assistant",
        content="다음 후보 중 선택해 주세요.",
        ui_components=components,
        judgment_snapshot={"step": "candidate_picker"},
    )
    assert row["role"] == "assistant"
    # assistant message 는 agent runtime 이 만든 것이므로 user_id 는 null 이 맞다.
    assert row["user_id"] is None
    assert row["ui_components"] == components
    assert row["judgment_snapshot"] == {"step": "candidate_picker"}


async def test_internal_chat_message_rejects_user_role(fake_db):
    """internal 함수는 ``user`` role 을 허용하지 않는다 — depth-in-defense.

    client 입력은 항상 공개 endpoint 경로를 거치게 강제하기 위함.
    """

    session_id, _subject = await _create_session_direct()
    with pytest.raises(ValueError):
        await main_flow.append_internal_chat_message(
            session_id=session_id,
            role="user",
            content="should be rejected",
        )


def test_chat_tool_call_routes_are_not_public(monkeypatch):
    """board P2-4 회귀: tool-call lifecycle 은 public 라우터에 없다."""

    client, token, session_id, _ = _bootstrap(monkeypatch)
    with client:
        post = client.post(
            f"/sessions/{session_id}/chat/tool-calls",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tool_name": "search_floorplan_catalog",
                "tool_kind": "retrieval",
                "input": {},
            },
        )
        patch = client.patch(
            f"/sessions/{session_id}/chat/tool-calls/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "succeeded"},
        )
    assert post.status_code == 404
    assert patch.status_code == 404


async def test_internal_tool_call_success_records_output_and_summary(fake_db):
    session_id, subject = await _create_session_direct()
    started = await main_flow.start_chat_tool_call(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "tool_name": "search_floorplan_catalog",
            "tool_kind": "retrieval",
            "input": {"apartment_name": "예시아파트", "size_type": "84A"},
        },
    )
    assert started["status"] == "started"
    assert started["completed_at"] is None
    assert started["output"] is None

    finished = await main_flow.complete_chat_tool_call(
        session_id=session_id,
        tool_call_id=started["id"],
        owner_user_id=subject,
        payload={
            "status": "succeeded",
            "output": {"candidates": [{"id": "fp-1"}]},
            "output_summary": "후보 1건 반환",
            "duration_ms": 412,
        },
    )
    assert finished["status"] == "succeeded"
    assert finished["output"] == {"candidates": [{"id": "fp-1"}]}
    assert finished["output_summary"] == "후보 1건 반환"
    assert finished["duration_ms"] == 412
    assert finished["completed_at"] is not None


async def test_internal_tool_call_failure_records_error_envelope(fake_db):
    session_id, subject = await _create_session_direct()
    started = await main_flow.start_chat_tool_call(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "tool_name": "fetch_building_ledger",
            "tool_kind": "external_api",
            "input": {"address": "서울 강남구 …"},
        },
    )
    failed = await main_flow.complete_chat_tool_call(
        session_id=session_id,
        tool_call_id=started["id"],
        owner_user_id=subject,
        payload={
            "status": "failed",
            "error_code": "BUILDING_LEDGER_PROVIDER_TIMEOUT",
            "error_message": "Provider timed out after 5s.",
            "duration_ms": 5000,
        },
    )
    assert failed["status"] == "failed"
    assert failed["error_code"] == "BUILDING_LEDGER_PROVIDER_TIMEOUT"
    assert failed["output"] is None
    assert failed["output_summary"] is None


async def test_internal_tool_call_with_output_summary_only_when_not_rendered(fake_db):
    """UI 로 렌더링되지 않는 tool 도 ``output_summary`` 로 저장 가능해야 한다."""

    session_id, subject = await _create_session_direct()
    started = await main_flow.start_chat_tool_call(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "tool_name": "notify_admin_review",
            "tool_kind": "notification",
            "input": {"channel": "slack"},
        },
    )
    finished = await main_flow.complete_chat_tool_call(
        session_id=session_id,
        tool_call_id=started["id"],
        owner_user_id=subject,
        payload={
            "status": "succeeded",
            "output_summary": "관리자 슬랙 채널에 알림 전송",
        },
    )
    assert finished["status"] == "succeeded"
    assert finished["output"] is None
    assert finished["output_summary"] == "관리자 슬랙 채널에 알림 전송"


async def test_internal_completing_tool_call_twice_raises_conflict(fake_db):
    session_id, subject = await _create_session_direct()
    started = await main_flow.start_chat_tool_call(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "tool_name": "search_floorplan_catalog",
            "tool_kind": "retrieval",
            "input": {},
        },
    )
    await main_flow.complete_chat_tool_call(
        session_id=session_id,
        tool_call_id=started["id"],
        owner_user_id=subject,
        payload={"status": "succeeded"},
    )
    with pytest.raises(ZippinException) as conflict:
        await main_flow.complete_chat_tool_call(
            session_id=session_id,
            tool_call_id=started["id"],
            owner_user_id=subject,
            payload={"status": "failed"},
        )
    assert conflict.value.code == "CHAT_TOOL_CALL_ALREADY_COMPLETED"
    assert conflict.value.http_status == 409


async def test_internal_tool_call_blocks_non_owner(fake_db):
    """internal 경로도 owner 불일치 세션에는 row 를 만들지 않는다."""

    session_id, _subject = await _create_session_direct()
    with pytest.raises(ZippinException) as not_found:
        await main_flow.start_chat_tool_call(
            session_id=session_id,
            owner_user_id=uuid.uuid4(),
            payload={
                "tool_name": "search_floorplan_catalog",
                "tool_kind": "retrieval",
                "input": {},
            },
        )
    assert not_found.value.code == "SESSION_NOT_FOUND"
    assert fake_db.chat_tool_calls == {}
