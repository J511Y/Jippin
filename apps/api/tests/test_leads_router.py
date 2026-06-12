"""상담 리드 라우터 테스트 (CMP-DIRECT).

DB 는 TEST_MODE 에서 미접속이므로 ``services.leads._insert_lead`` 를 monkeypatch 해
실제 INSERT 없이 라우터/검증/인증 경로를 검증한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import create_app

from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def captured(monkeypatch):
    box: dict[str, object] = {}

    async def fake_insert(lead_values, attachments):
        box["lead_values"] = lead_values
        box["attachments"] = attachments
        return {
            "id": uuid.uuid4(),
            "source_form": lead_values["source_form"],
            "status": "new",
            "created_at": datetime.now(UTC),
        }

    monkeypatch.setattr("src.services.leads._insert_lead", fake_insert)
    return box


def _auth_client(monkeypatch, *, is_anonymous: bool = False):
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    token, subject = helpers.mint_token(pem, "test-key-1", is_anonymous=is_anonymous)
    client = TestClient(create_app())
    return client, token, subject


def test_create_lead_requires_bearer_token() -> None:
    client = TestClient(create_app())
    with client:
        response = client.post(
            "/leads",
            json={
                "source_form": "main_page",
                "applicant_name": "홍길동",
                "applicant_phone": "01012345678",
            },
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SUPABASE_SESSION_BEARER_REQUIRED"


def test_create_main_page_lead_succeeds(monkeypatch, captured) -> None:
    client, token, subject = _auth_client(monkeypatch, is_anonymous=True)
    with client:
        response = client.post(
            "/leads",
            headers={"authorization": f"Bearer {token}"},
            json={
                "source_form": "main_page",
                "applicant_kind": "individual",
                "applicant_name": "홍길동",
                "applicant_phone": "01012345678",
                "message": "상담 원해요",
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["source_form"] == "main_page"
    assert body["status"] == "new"
    # 익명 owner + user_id 전파.
    assert captured["lead_values"]["is_anonymous"] is True
    assert captured["lead_values"]["user_id"] == subject
    # 연락처 정규화.
    assert captured["lead_values"]["applicant_phone"] == "010-1234-5678"


def test_create_lead_schedules_alimtalk_notification(monkeypatch, captured) -> None:
    # 리드 생성 성공 시 접수 알림톡이 background task 로 예약된다(정규화된 연락처 사용).
    calls: list[dict[str, str]] = []

    async def fake_notify(*, phone, applicant_name, source_form):
        calls.append(
            {
                "phone": phone,
                "applicant_name": applicant_name,
                "source_form": source_form,
            }
        )

    monkeypatch.setattr("src.services.alimtalk.notify_lead_received", fake_notify)
    client, token, _subject = _auth_client(monkeypatch, is_anonymous=True)
    with client:
        response = client.post(
            "/leads",
            headers={"authorization": f"Bearer {token}"},
            json={
                "source_form": "main_page",
                "applicant_name": "홍길동",
                "applicant_phone": "01012345678",
            },
        )
    assert response.status_code == 201
    assert calls == [
        {
            "phone": "010-1234-5678",
            "applicant_name": "홍길동",
            "source_form": "main_page",
        }
    ]


def test_create_lead_with_owner_attachment_succeeds(monkeypatch, captured) -> None:
    client, token, subject = _auth_client(monkeypatch)
    with client:
        response = client.post(
            "/leads",
            headers={"authorization": f"Bearer {token}"},
            json={
                "source_form": "lead_page",
                "applicant_name": "홍길동",
                "applicant_phone": "01012345678",
                "road_addr_part1": "서울특별시 강남구 테헤란로 1",
                "road_addr_detail": "101동 1001호",
                "expansion_location": "거실",
                "ownership_status": "owner",
                "attachments": [
                    {
                        "object_path": f"{subject}/abc-floorplan.png",
                        "file_name": "floorplan.png",
                        "content_type": "image/png",
                        "byte_size": 1234,
                    }
                ],
            },
        )
    assert response.status_code == 201
    assert len(captured["attachments"]) == 1
    assert captured["attachments"][0]["bucket"] == "lead-floorplans"


def test_attachment_owner_folder_mismatch_is_rejected(monkeypatch, captured) -> None:
    client, token, _subject = _auth_client(monkeypatch)
    other = uuid.uuid4()
    with client:
        response = client.post(
            "/leads",
            headers={"authorization": f"Bearer {token}"},
            json={
                "source_form": "main_page",
                "applicant_name": "홍길동",
                "applicant_phone": "01012345678",
                "attachments": [{"object_path": f"{other}/evil.png"}],
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LEAD_ATTACHMENT_OWNER_MISMATCH"
    assert "lead_values" not in captured  # 검증 실패 시 INSERT 미도달.


def test_lead_page_missing_fields_returns_422(monkeypatch, captured) -> None:
    client, token, _subject = _auth_client(monkeypatch)
    with client:
        response = client.post(
            "/leads",
            headers={"authorization": f"Bearer {token}"},
            json={
                "source_form": "lead_page",
                "applicant_name": "홍길동",
                "applicant_phone": "01012345678",
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
