"""Phase A skeleton tests for /sessions/{id}/floorplan-* (CMP-609).

Coverage:

- 사용자 업로드 metadata row 생성 (``POST /floorplan-uploads``).
- 후보 snapshot 저장 — 다른 ``lookup_revision`` 사이엔 독립이지만 동일
  revision 안에서 같은 ``floorplan_id`` 또는 같은 ``rank`` 가 들어오면 409.
- 다른 owner 의 session 에는 접근 불가 (404).
"""

from __future__ import annotations

import uuid

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


def _bootstrap_session(monkeypatch) -> tuple[TestClient, str, str]:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    client = TestClient(create_app())
    token, _ = helpers.mint_token(pem, jwk["kid"])
    return client, token, _create_session(client, token)


def _create_session(client: TestClient, token: str) -> str:
    with client:
        return client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()["id"]


def test_create_floorplan_upload_metadata_row(monkeypatch):
    client, token, session_id = _bootstrap_session(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-uploads",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_name": "84a-floorplan.pdf",
                "source_note": "관리사무소 제공",
                "upload_metadata": {"page_count": 2},
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "uploaded"
    assert body["file_name"] == "84a-floorplan.pdf"
    assert body["upload_metadata"] == {"page_count": 2}
    # original_asset_id 는 asset 생성 후 별도 PATCH 로 채우므로 skeleton 단계엔 None.
    assert body["original_asset_id"] is None


def test_candidate_snapshot_distinguishes_lookup_revisions(monkeypatch):
    client, token, session_id = _bootstrap_session(monkeypatch)
    fp_a = str(uuid.uuid4())
    fp_b = str(uuid.uuid4())

    payload_r1 = {
        "lookup_revision": 1,
        "items": [
            {
                "floorplan_id": fp_a,
                "rank": 1,
                "confidence": "0.9100",
                "match_reasons": ["apartment_name+size_type"],
                "lookup_input": {"apartment_name": "예시아파트"},
            },
            {
                "floorplan_id": fp_b,
                "rank": 2,
                "confidence": "0.7300",
                "match_reasons": ["apartment_name"],
                "lookup_input": {"apartment_name": "예시아파트"},
            },
        ],
    }
    with client:
        first = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {token}"},
            json=payload_r1,
        )
        assert first.status_code == 201
        first_body = first.json()
        assert first_body["lookup_revision"] == 1
        assert [c["rank"] for c in first_body["candidates"]] == [1, 2]

        # 같은 revision 에 같은 floorplan_id 가 다시 들어오면 409.
        conflict = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "lookup_revision": 1,
                "items": [
                    {
                        "floorplan_id": fp_a,
                        "rank": 3,
                        "confidence": "0.6000",
                    }
                ],
            },
        )
        assert conflict.status_code == 409
        assert (
            conflict.json()["error"]["code"] == "FLOORPLAN_CANDIDATE_REVISION_CONFLICT"
        )

        # 같은 revision, 같은 batch 안에서 rank 충돌도 409.
        dup_rank = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "lookup_revision": 1,
                "items": [
                    {
                        "floorplan_id": str(uuid.uuid4()),
                        "rank": 1,  # already 1 ranked in revision 1
                        "confidence": "0.5",
                    }
                ],
            },
        )
        assert dup_rank.status_code == 409
        assert (
            dup_rank.json()["error"]["code"] == "FLOORPLAN_CANDIDATE_REVISION_CONFLICT"
        )

        # 다른 lookup_revision 은 동일 floorplan_id 재사용을 허용한다.
        second = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "lookup_revision": 2,
                "items": [
                    {
                        "floorplan_id": fp_a,
                        "rank": 1,
                        "confidence": "0.9500",
                    }
                ],
            },
        )
        assert second.status_code == 201
        body2 = second.json()
        assert body2["lookup_revision"] == 2
        assert body2["candidates"][0]["floorplan_id"] == fp_a


def test_candidate_snapshot_rejects_in_batch_duplicate_rank(monkeypatch):
    client, token, session_id = _bootstrap_session(monkeypatch)
    fp_a = str(uuid.uuid4())
    fp_b = str(uuid.uuid4())
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "lookup_revision": 1,
                "items": [
                    {"floorplan_id": fp_a, "rank": 1, "confidence": "0.9"},
                    {"floorplan_id": fp_b, "rank": 1, "confidence": "0.8"},
                ],
            },
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FLOORPLAN_CANDIDATE_DUPLICATE_RANK"


def test_candidate_snapshot_blocks_non_owner(monkeypatch):
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    client = TestClient(create_app())
    owner_token, _ = helpers.mint_token(pem, jwk["kid"])
    other_token, _ = helpers.mint_token(pem, jwk["kid"])
    session_id = _create_session(client, owner_token)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {other_token}"},
            json={
                "lookup_revision": 1,
                "items": [
                    {
                        "floorplan_id": str(uuid.uuid4()),
                        "rank": 1,
                        "confidence": "0.9",
                    }
                ],
            },
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
