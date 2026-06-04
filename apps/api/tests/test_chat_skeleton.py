"""Phase A skeleton tests for /sessions/{id}/chat/* (CMP-609).

Coverage:

- ``chat_messages`` append (user / assistant / tool 역할).
- ``chat_tool_calls`` lifecycle: start → succeeded, start → failed.
- ``ui_components`` (message-level UI payload) 와 ``output`` (tool 결과) 의
  분리 — 둘은 다른 컬럼이다.
- UI 로 렌더링되지 않는 tool output 도 ``output_summary`` 로 저장 가능.
- 이미 완료된 tool call 을 다시 complete 하려 하면 409.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import create_app
from src.services import main_flow

from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    main_flow._reset_for_tests()
    yield
    main_flow._reset_for_tests()
    get_settings.cache_clear()


def _bootstrap(monkeypatch) -> tuple[TestClient, str, str]:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    client = TestClient(create_app())
    token, _ = helpers.mint_token(pem, jwk["kid"])
    with client:
        session_id = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()["id"]
    return client, token, session_id


def test_append_user_chat_message_records_owner(monkeypatch):
    client, token, session_id = _bootstrap(monkeypatch)
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


def test_chat_message_endpoint_rejects_non_user_role(monkeypatch):
    """공개 endpoint 가 assistant/system/tool role 을 흉내내지 못하게 막는다.

    Client 가 assistant 인 척 ui_components/judgment_snapshot 을 주입하는 회귀.
    """

    client, token, session_id = _bootstrap(monkeypatch)
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


def test_internal_assistant_message_records_ui_components(monkeypatch):
    """``ui_components`` (A2UI payload) 는 internal service 함수로만 기록된다.

    runtime/agent 가 직접 ``main_flow.append_internal_chat_message`` 를 호출한다.
    """

    import uuid as uuid_module

    client, token, session_id = _bootstrap(monkeypatch)
    with client:
        # noop - 위 _bootstrap 이 이미 client 생성/세션 만들기를 끝냈다.
        pass

    components = [
        {"kind": "candidate_picker", "items": [{"id": "fp-1", "label": "84A"}]},
    ]
    row = main_flow.append_internal_chat_message(
        session_id=uuid_module.UUID(session_id),
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


def test_internal_chat_message_rejects_user_role(monkeypatch):
    """internal 함수는 ``user`` role 을 허용하지 않는다 — depth-in-defense.

    client 입력은 항상 공개 endpoint 경로를 거치게 강제하기 위함.
    """

    import uuid as uuid_module

    client, token, session_id = _bootstrap(monkeypatch)
    with client:
        pass
    with pytest.raises(ValueError):
        main_flow.append_internal_chat_message(
            session_id=uuid_module.UUID(session_id),
            role="user",
            content="should be rejected",
        )


def test_tool_call_success_records_output_and_output_summary(monkeypatch):
    client, token, session_id = _bootstrap(monkeypatch)
    with client:
        start = client.post(
            f"/sessions/{session_id}/chat/tool-calls",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tool_name": "search_floorplan_catalog",
                "tool_kind": "retrieval",
                "input": {"apartment_name": "예시아파트", "size_type": "84A"},
            },
        )
        assert start.status_code == 201
        started = start.json()
        assert started["status"] == "started"
        assert started["completed_at"] is None
        assert started["output"] is None

        finish = client.patch(
            f"/sessions/{session_id}/chat/tool-calls/{started['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "status": "succeeded",
                "output": {"candidates": [{"id": "fp-1"}]},
                "output_summary": "후보 1건 반환",
                "duration_ms": 412,
            },
        )
    assert finish.status_code == 200
    finished = finish.json()
    assert finished["status"] == "succeeded"
    assert finished["output"] == {"candidates": [{"id": "fp-1"}]}
    assert finished["output_summary"] == "후보 1건 반환"
    assert finished["duration_ms"] == 412
    assert finished["completed_at"] is not None


def test_tool_call_failure_records_error_envelope(monkeypatch):
    client, token, session_id = _bootstrap(monkeypatch)
    with client:
        start = client.post(
            f"/sessions/{session_id}/chat/tool-calls",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tool_name": "fetch_building_ledger",
                "tool_kind": "external_api",
                "input": {"address": "서울 강남구 …"},
            },
        ).json()

        fail = client.patch(
            f"/sessions/{session_id}/chat/tool-calls/{start['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "status": "failed",
                "error_code": "BUILDING_LEDGER_PROVIDER_TIMEOUT",
                "error_message": "Provider timed out after 5s.",
                "duration_ms": 5000,
            },
        )
    assert fail.status_code == 200
    failed = fail.json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "BUILDING_LEDGER_PROVIDER_TIMEOUT"
    assert failed["output"] is None
    assert failed["output_summary"] is None


def test_tool_call_with_output_summary_only_when_not_rendered(monkeypatch):
    """UI 로 렌더링되지 않는 tool 도 ``output_summary`` 로 저장 가능해야 한다."""

    client, token, session_id = _bootstrap(monkeypatch)
    with client:
        start = client.post(
            f"/sessions/{session_id}/chat/tool-calls",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tool_name": "notify_admin_review",
                "tool_kind": "notification",
                "input": {"channel": "slack"},
            },
        ).json()
        finish = client.patch(
            f"/sessions/{session_id}/chat/tool-calls/{start['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "status": "succeeded",
                "output_summary": "관리자 슬랙 채널에 알림 전송",
            },
        )
    assert finish.status_code == 200
    body = finish.json()
    assert body["status"] == "succeeded"
    assert body["output"] is None
    assert body["output_summary"] == "관리자 슬랙 채널에 알림 전송"


def test_completing_tool_call_twice_returns_409(monkeypatch):
    client, token, session_id = _bootstrap(monkeypatch)
    with client:
        start = client.post(
            f"/sessions/{session_id}/chat/tool-calls",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tool_name": "search_floorplan_catalog",
                "tool_kind": "retrieval",
                "input": {},
            },
        ).json()
        first = client.patch(
            f"/sessions/{session_id}/chat/tool-calls/{start['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "succeeded"},
        )
        assert first.status_code == 200

        second = client.patch(
            f"/sessions/{session_id}/chat/tool-calls/{start['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "failed"},
        )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CHAT_TOOL_CALL_ALREADY_COMPLETED"
