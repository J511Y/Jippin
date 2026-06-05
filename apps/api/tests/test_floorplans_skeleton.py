"""Phase A skeleton tests for /sessions/{id}/floorplan-* (CMP-609).

Coverage:

- 사용자 업로드 metadata row 생성 (``POST /floorplan-uploads``).
- 후보 snapshot 저장 (``floorplan_candidates``) 은 사용자-facing route 가
  아니다 (board P2-3). HTTP 401/404/405 회귀 가드 + internal service 호출
  conflict 동작은 ``main_flow.save_floorplan_candidate_snapshot`` 직접 호출로
  검증한다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.errors import ZippinException
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


def _bootstrap_session(monkeypatch) -> tuple[TestClient, str, str, uuid.UUID]:
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


def test_create_floorplan_upload_metadata_row(monkeypatch):
    client, token, session_id, _ = _bootstrap_session(monkeypatch)
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


def test_floorplan_candidate_snapshot_route_is_not_public(monkeypatch):
    """board P2-3: client 가 candidate snapshot 을 persist 하지 못해야 한다.

    Phase A skeleton 은 본 endpoint 를 public 라우터에 mount 하지 않는다.
    """

    client, token, session_id, _ = _bootstrap_session(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-candidates",
            headers={"Authorization": f"Bearer {token}"},
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
    # mount 되지 않은 경로는 FastAPI 가 404 로 응답한다.
    assert response.status_code == 404


def test_candidate_snapshot_service_distinguishes_lookup_revisions(monkeypatch):
    """후보 snapshot 의 lookup_revision 분리는 internal service 단에서 검증.

    HTTP 노출이 없어도 검색/매칭 서비스가 같은 conflict 의미를 받는다.
    """

    _client_, _token, session_id, subject = _bootstrap_session(monkeypatch)
    sid = uuid.UUID(session_id)
    fp_a = uuid.uuid4()
    fp_b = uuid.uuid4()

    rev1 = main_flow.save_floorplan_candidate_snapshot(
        session_id=sid,
        owner_user_id=subject,
        lookup_revision=1,
        items=[
            {
                "floorplan_id": fp_a,
                "rank": 1,
                "confidence": "0.91",
                "match_reasons": ["apartment_name+size_type"],
                "lookup_input": {"apartment_name": "예시아파트"},
                "floorplan_snapshot": {
                    "display_label": "84A 표준 평면",
                    "size_type": "84A",
                },
            },
            {
                "floorplan_id": fp_b,
                "rank": 2,
                "confidence": "0.73",
                "match_reasons": ["apartment_name"],
                "lookup_input": {"apartment_name": "예시아파트"},
                "floorplan_snapshot": {"display_label": "84B 표준 평면"},
            },
        ],
    )
    assert [c["rank"] for c in rev1] == [1, 2]

    # 같은 revision 에 같은 floorplan_id 가 다시 들어오면 409.
    with pytest.raises(ZippinException) as conflict:
        main_flow.save_floorplan_candidate_snapshot(
            session_id=sid,
            owner_user_id=subject,
            lookup_revision=1,
            items=[
                {
                    "floorplan_id": fp_a,
                    "rank": 3,
                    "confidence": "0.6",
                    "floorplan_snapshot": {"display_label": "84A 표준 평면"},
                }
            ],
        )
    assert conflict.value.code == "FLOORPLAN_CANDIDATE_REVISION_CONFLICT"
    assert conflict.value.http_status == 409

    # 다른 revision 은 같은 floorplan_id 재사용을 허용한다.
    rev2 = main_flow.save_floorplan_candidate_snapshot(
        session_id=sid,
        owner_user_id=subject,
        lookup_revision=2,
        items=[
            {
                "floorplan_id": fp_a,
                "rank": 1,
                "confidence": "0.95",
                "floorplan_snapshot": {"display_label": "84A 재검색 결과"},
            }
        ],
    )
    assert rev2[0]["floorplan_id"] == fp_a


def test_candidate_snapshot_service_rejects_in_batch_duplicate_rank(monkeypatch):
    _client_, _token, session_id, subject = _bootstrap_session(monkeypatch)
    sid = uuid.UUID(session_id)
    with pytest.raises(ZippinException) as conflict:
        main_flow.save_floorplan_candidate_snapshot(
            session_id=sid,
            owner_user_id=subject,
            lookup_revision=1,
            items=[
                {
                    "floorplan_id": uuid.uuid4(),
                    "rank": 1,
                    "confidence": "0.9",
                    "floorplan_snapshot": {"display_label": "A"},
                },
                {
                    "floorplan_id": uuid.uuid4(),
                    "rank": 1,
                    "confidence": "0.8",
                    "floorplan_snapshot": {"display_label": "B"},
                },
            ],
        )
    assert conflict.value.code == "FLOORPLAN_CANDIDATE_DUPLICATE_RANK"


def test_candidate_snapshot_service_blocks_non_owner(monkeypatch):
    _client_, _token, session_id, _ = _bootstrap_session(monkeypatch)
    sid = uuid.UUID(session_id)
    other_user = uuid.uuid4()
    with pytest.raises(ZippinException) as not_found:
        main_flow.save_floorplan_candidate_snapshot(
            session_id=sid,
            owner_user_id=other_user,
            lookup_revision=1,
            items=[
                {
                    "floorplan_id": uuid.uuid4(),
                    "rank": 1,
                    "confidence": "0.9",
                    "floorplan_snapshot": {"display_label": "A"},
                }
            ],
        )
    assert not_found.value.code == "SESSION_NOT_FOUND"


def test_candidate_snapshot_service_requires_non_empty_snapshot(monkeypatch):
    """board round-3 #4 회귀: 빈 ``floorplan_snapshot`` 은 422 로 거절된다.

    DB ``floorplan_candidates.floorplan_snapshot`` JSONB NOT NULL DEFAULT '{}' 가
    있지만 default 값으로 들어가면 사용자가 본 후보 표시값이 영구 손실된다.
    Service 단에서 caller 가 명시적으로 snapshot 을 제공하도록 강제한다.
    """

    _client_, _token, session_id, subject = _bootstrap_session(monkeypatch)
    sid = uuid.UUID(session_id)
    for empty_snapshot in (None, {}):
        with pytest.raises(ZippinException) as rejected:
            main_flow.save_floorplan_candidate_snapshot(
                session_id=sid,
                owner_user_id=subject,
                lookup_revision=1,
                items=[
                    {
                        "floorplan_id": uuid.uuid4(),
                        "rank": 1,
                        "confidence": "0.9",
                        "floorplan_snapshot": empty_snapshot,
                    }
                ],
            )
        assert rejected.value.code == "FLOORPLAN_CANDIDATE_SNAPSHOT_REQUIRED"
        assert rejected.value.http_status == 422


def test_candidate_snapshot_service_preserves_snapshot_in_response(monkeypatch):
    """board round-3 #4 회귀: 저장된 ``floorplan_snapshot`` 이 그대로 반환된다.

    이후 ``floorplans`` catalog row 가 ``ON DELETE SET NULL`` 로 사라져도
    사용자가 본 후보 화면 (label / type / thumbnail) 이 재현 가능해야 한다.
    """

    _client_, _token, session_id, subject = _bootstrap_session(monkeypatch)
    sid = uuid.UUID(session_id)
    snapshot = {
        "display_label": "84A 표준 평면",
        "size_type": "84A",
        "thumbnail_url": "r2://floorplans/abc.png",
        "match_score": 0.91,
    }
    saved = main_flow.save_floorplan_candidate_snapshot(
        session_id=sid,
        owner_user_id=subject,
        lookup_revision=1,
        items=[
            {
                "floorplan_id": uuid.uuid4(),
                "rank": 1,
                "confidence": "0.91",
                "floorplan_snapshot": snapshot,
            }
        ],
    )
    assert saved[0]["floorplan_snapshot"] == snapshot
    # 호출자가 dict 를 mutate 해도 저장된 row 는 영향받지 않아야 한다 — 라이브
    # 참조가 새지 않도록 ``dict(...)`` 로 복사해 저장한다.
    snapshot["display_label"] = "MUTATED"
    assert saved[0]["floorplan_snapshot"]["display_label"] == "84A 표준 평면"
