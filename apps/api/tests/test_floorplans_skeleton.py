"""Phase A DB-backed tests for /sessions/{id}/floorplan-* (CMP-609 → DB 영속화).

TEST_MODE 에서는 실 DB 미접속이므로 ``services.main_flow`` 의 ``_db_*`` seam
을 stateful fake (``_main_flow_db_fake``) 로 대체한다 (``test_leads_router``
의 ``_insert_lead`` monkeypatch 패턴 확장).

Coverage:

- 사용자 업로드 metadata row 생성 (``POST /floorplan-uploads``) — DB seam 에
  row 가 기록된다.
- ownership: user B 는 user A 세션에 업로드 record 를 만들 수 없다 (404).
- 후보 snapshot 저장 (``floorplan_candidates``) 은 사용자-facing route 가
  아니다 (board P2-3). HTTP 404 회귀 가드 + internal service 호출
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
from src.services import main_flow, storage

from . import _main_flow_db_fake as db_fake
from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    fake = db_fake.install_main_flow_fake(monkeypatch)
    yield fake
    get_settings.cache_clear()


def _bootstrap_session(monkeypatch) -> tuple[TestClient, str, str, uuid.UUID]:
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


def test_create_floorplan_upload_metadata_row(monkeypatch, fake_db):
    client, token, session_id, subject = _bootstrap_session(monkeypatch)
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
    # original_asset_id 는 asset 생성 후 별도 PATCH 로 채우므로 본 단계엔 None.
    assert body["original_asset_id"] is None
    # DB-backed 경로 회귀: upload row 가 seam (fake) 을 통해 영속화됐다.
    stored = list(fake_db.floorplan_uploads.values())
    assert len(stored) == 1
    assert stored[0]["user_id"] == subject
    assert stored[0]["file_name"] == "84a-floorplan.pdf"


def _patch_head_ok(monkeypatch, *, content_type="image/png", size=12345):
    async def fake_head(settings, *, bucket, object_path, **_: object):
        return content_type, size

    monkeypatch.setattr(storage, "head_object", fake_head)


def test_create_floorplan_asset_links_session(monkeypatch, fake_db):
    """업로드된 도면 메타가 asset 으로 기록되고 세션에 연결된다(#a2ui/segmentation source)."""

    client, token, session_id, subject = _bootstrap_session(monkeypatch)
    _patch_head_ok(monkeypatch)
    object_key = f"{subject}/{session_id}/abc-floorplan.png"
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "bucket": "session-floorplans",
                "object_key": object_key,
                "content_type": "image/png",
                "byte_size": 12345,
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["session_id"] == session_id
    assert body["kind"] == "original"
    assert body["object_key"] == object_key
    # 세션이 이 asset 으로 연결됐다(세그멘테이션이 여기서 도면을 가져온다).
    assert fake_db.sessions[uuid.UUID(session_id)]["selected_floorplan_asset_id"] == (
        uuid.UUID(body["id"])
    )


def test_create_floorplan_asset_rejects_foreign_owner_folder(monkeypatch, fake_db):
    """owner-folder 가드: 남의 user 폴더 object_key 는 403."""

    client, token, session_id, _subject = _bootstrap_session(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "bucket": "session-floorplans",
                "object_key": f"{uuid.uuid4()}/x/evil.png",
                "content_type": "image/png",
                "byte_size": 1,
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FLOORPLAN_ASSET_OWNER_MISMATCH"
    assert fake_db.floorplan_assets == {}


def test_create_floorplan_asset_rejects_path_traversal(monkeypatch, fake_db):
    """#path-traversal: '..' 세그먼트는 owner 폴더로 시작해도 거절(HTTP 정규화 우회 방지)."""

    client, token, session_id, subject = _bootstrap_session(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "bucket": "session-floorplans",
                "object_key": f"{subject}/{session_id}/../{uuid.uuid4()}/evil.png",
                "content_type": "image/png",
                "byte_size": 1,
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FLOORPLAN_ASSET_OWNER_MISMATCH"
    assert fake_db.floorplan_assets == {}


def test_create_floorplan_asset_rejects_non_image(monkeypatch, fake_db):
    """엣지 검증: image/* 가 아니면 422(세그멘테이션은 래스터 이미지만, PDF 미지원)."""

    client, token, session_id, subject = _bootstrap_session(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "bucket": "session-floorplans",
                "object_key": f"{subject}/{session_id}/doc.pdf",
                "content_type": "application/pdf",
                "byte_size": 100,
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FLOORPLAN_ASSET_UNSUPPORTED_TYPE"
    assert fake_db.floorplan_assets == {}


def test_create_floorplan_asset_rejects_foreign_bucket(monkeypatch, fake_db):
    """#bucket-boundary: 세션 도면 버킷이 아니면 422(다른 비공개 버킷 객체 등록 차단)."""

    client, token, session_id, subject = _bootstrap_session(monkeypatch)
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "bucket": "lead-floorplans",
                "object_key": f"{subject}/{session_id}/x.png",
                "content_type": "image/png",
                "byte_size": 10,
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FLOORPLAN_ASSET_UNSUPPORTED_BUCKET"
    assert fake_db.floorplan_assets == {}


def test_create_floorplan_asset_rejects_unverified_or_oversize(monkeypatch, fake_db):
    """#verify-object: 저장된 객체 HEAD 가 비이미지/초과면 거절(클라 JSON 불신)."""

    client, token, session_id, subject = _bootstrap_session(monkeypatch)
    base = {
        "bucket": "session-floorplans",
        "object_key": f"{subject}/{session_id}/x.png",
        "content_type": "image/png",
        "byte_size": 10,
    }
    # 검증 불가(객체 없음/HEAD 실패) → 422.
    _patch_head_ok(monkeypatch, content_type=None, size=None)

    async def head_none(settings, **_: object):
        return None

    monkeypatch.setattr(storage, "head_object", head_none)
    with client:
        unverified = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json=base,
        )
    assert unverified.status_code == 422
    assert unverified.json()["error"]["code"] == "FLOORPLAN_ASSET_UNVERIFIED"

    # 실제 객체가 초과 크기 → 422(클라 JSON 의 작은 byte_size 무시).
    _patch_head_ok(monkeypatch, content_type="image/png", size=60 * 1024 * 1024)
    with client:
        oversize = client.post(
            f"/sessions/{session_id}/floorplan-assets",
            headers={"Authorization": f"Bearer {token}"},
            json=base,
        )
    assert oversize.status_code == 422
    assert oversize.json()["error"]["code"] == "FLOORPLAN_ASSET_TOO_LARGE"
    assert fake_db.floorplan_assets == {}


async def test_list_sessions_clears_expiry_for_converted_owner(fake_db):
    """#list-clear-expiry: 익명→전환 사용자가 목록만 봐도 anon TTL 이 해제된다."""

    owner = uuid.uuid4()
    s = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=True, judgment_schema_version=None
    )
    assert fake_db.sessions[s["id"]]["expires_at"] is not None
    await main_flow.list_owned_sessions(owner_user_id=owner, owner_is_anonymous=False)
    assert fake_db.sessions[s["id"]]["expires_at"] is None


async def test_new_floorplan_invalidates_persisted_verdict(fake_db):
    """#verdict-input-consistency: 새 도면을 붙이면 영속된 판정이 무효화돼 리포트가
    옛 결과를 새 도면에 붙이지 않는다(service-role 경로 포함)."""

    session_id, subject = await _create_session_direct()
    await main_flow.set_session_verdict(
        session_id=session_id, rule_eval_result={"verdict": "ALLOW"}
    )
    # 옛 입력 기준 흐름 결정도 함께 무효화 대상.
    await main_flow.set_session_decision(
        session_id=session_id, completion_decision="PROCEED_RULE"
    )
    assert fake_db.sessions[session_id]["rule_eval_result"] is not None
    # 새 도면 asset 첨부 → 입력 변경 → verdict + decision 무효화.
    await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "bucket": "session-floorplans",
            "object_key": f"{subject}/{session_id}/new.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )
    assert fake_db.sessions[session_id]["rule_eval_result"] is None
    assert fake_db.sessions[session_id]["rule_evaluated_at"] is None
    assert fake_db.sessions[session_id]["completion_decision"] is None


async def test_set_session_verdict_skips_on_input_change(fake_db):
    """#stale-verdict-write: 분석 시작 때 본 입력과 현재 입력이 다르면 verdict 를 쓰지
    않고 None 반환(분석 도중 도면 교체 race)."""

    session_id, subject = await _create_session_direct()
    a1 = await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "bucket": "session-floorplans",
            "object_key": f"{subject}/{session_id}/a1.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )
    # 분석 시작 스냅샷 = a1. 그 사이 a2 로 교체.
    await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=subject,
        payload={
            "bucket": "session-floorplans",
            "object_key": f"{subject}/{session_id}/a2.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )
    # a1 기준 verdict 영속 시도 → 입력이 바뀌었으므로 skip(None).
    res = await main_flow.set_session_verdict(
        session_id=session_id,
        rule_eval_result={"verdict": "ALLOW"},
        expected_asset_id=a1["id"],
        expected_address_id=None,
    )
    assert res is None
    assert fake_db.sessions[session_id]["rule_eval_result"] is None


async def test_session_has_report_flag(fake_db):
    """#report-readiness: has_report 는 verdict 존재로만 파생된다(completion_decision 무관)."""

    session_id, subject = await _create_session_direct()
    from src.schemas.sessions import SessionResponse

    row = await main_flow.get_owned_session(session_id, owner_user_id=subject)
    assert SessionResponse.model_validate(row).has_report is False
    await main_flow.set_session_verdict(
        session_id=session_id, rule_eval_result={"verdict": "ALLOW"}
    )
    row2 = await main_flow.get_owned_session(session_id, owner_user_id=subject)
    assert SessionResponse.model_validate(row2).has_report is True


async def test_address_edit_invalidates_verdict(fake_db):
    """#address-row-edit: 주소를 고치면(같은 행 in-place upsert) 옛 판정이 무효화된다."""

    session_id, subject = await _create_session_direct()
    await main_flow.upsert_session_address(
        session_id=session_id,
        owner_user_id=subject,
        payload={"road_address": "서울 강남구 테헤란로 1"},
    )
    await main_flow.set_session_verdict(
        session_id=session_id, rule_eval_result={"verdict": "ALLOW"}
    )
    assert fake_db.sessions[session_id]["rule_eval_result"] is not None
    # 같은 세션 주소 행을 부분 수정(포인터 동일) → verdict 무효화.
    await main_flow.upsert_session_address(
        session_id=session_id,
        owner_user_id=subject,
        payload={"unit_ho": "1502"},
    )
    assert fake_db.sessions[session_id]["rule_eval_result"] is None
    assert fake_db.sessions[session_id]["rule_evaluated_at"] is None


async def test_address_reconfirm_same_value_keeps_verdict(fake_db):
    """#address-noop-update: 같은 주소를 재확인하는 no-op upsert 는 verdict 를 안 지운다.

    PUT /sessions/{id}/address 는 같은 주소 재확인 때도 ON CONFLICT DO UPDATE 로 행을
    다시 쓴다 — 값이 그대로면 입력이 안 바뀐 것이라 리포트를 떨어뜨리면 안 된다.
    """

    session_id, subject = await _create_session_direct()
    await main_flow.upsert_session_address(
        session_id=session_id,
        owner_user_id=subject,
        payload={"road_address": "서울 강남구 테헤란로 1", "unit_ho": "1502"},
    )
    await main_flow.set_session_verdict(
        session_id=session_id, rule_eval_result={"verdict": "ALLOW"}
    )
    assert fake_db.sessions[session_id]["rule_eval_result"] is not None
    # 같은 값으로 다시 확정(no-op) → verdict 보존.
    await main_flow.upsert_session_address(
        session_id=session_id,
        owner_user_id=subject,
        payload={"road_address": "서울 강남구 테헤란로 1", "unit_ho": "1502"},
    )
    assert fake_db.sessions[session_id]["rule_eval_result"] is not None
    assert fake_db.sessions[session_id]["rule_evaluated_at"] is not None


def test_create_floorplan_upload_blocks_non_owner(monkeypatch, fake_db):
    """ownership 회귀: user B 는 user A 세션에 업로드 record 를 못 만든다."""

    client, _owner_token, session_id, _ = _bootstrap_session(monkeypatch)
    pem2, jwk2 = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk2]})
    intruder_token, _ = helpers.mint_token(pem2, jwk2["kid"])
    with client:
        response = client.post(
            f"/sessions/{session_id}/floorplan-uploads",
            headers={"Authorization": f"Bearer {intruder_token}"},
            json={"file_name": "evil.pdf"},
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert fake_db.floorplan_uploads == {}


def test_floorplan_candidate_snapshot_route_is_not_public(monkeypatch):
    """board P2-3: client 가 candidate snapshot 을 persist 하지 못해야 한다.

    Phase A 는 본 endpoint 를 public 라우터에 mount 하지 않는다.
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


async def test_candidate_snapshot_service_distinguishes_lookup_revisions(fake_db):
    """후보 snapshot 의 lookup_revision 분리는 internal service 단에서 검증.

    HTTP 노출이 없어도 검색/매칭 서비스가 같은 conflict 의미를 받는다.
    """

    session_id, subject = await _create_session_direct()
    fp_a = uuid.uuid4()
    fp_b = uuid.uuid4()

    rev1 = await main_flow.save_floorplan_candidate_snapshot(
        session_id=session_id,
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
        await main_flow.save_floorplan_candidate_snapshot(
            session_id=session_id,
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
    rev2 = await main_flow.save_floorplan_candidate_snapshot(
        session_id=session_id,
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


async def test_candidate_snapshot_service_rejects_in_batch_duplicate_rank(fake_db):
    session_id, subject = await _create_session_direct()
    with pytest.raises(ZippinException) as conflict:
        await main_flow.save_floorplan_candidate_snapshot(
            session_id=session_id,
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
    # 검증 실패 batch 는 단일 트랜잭션 원칙에 따라 아무 row 도 남기지 않는다.
    assert fake_db.floorplan_candidates == {}


async def test_candidate_snapshot_service_blocks_non_owner(fake_db):
    session_id, _subject = await _create_session_direct()
    other_user = uuid.uuid4()
    with pytest.raises(ZippinException) as not_found:
        await main_flow.save_floorplan_candidate_snapshot(
            session_id=session_id,
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


async def test_candidate_snapshot_service_requires_non_empty_snapshot(fake_db):
    """board round-3 #4 회귀: 빈 ``floorplan_snapshot`` 은 422 로 거절된다.

    DB ``floorplan_candidates.floorplan_snapshot`` JSONB NOT NULL DEFAULT '{}' 가
    있지만 default 값으로 들어가면 사용자가 본 후보 표시값이 영구 손실된다.
    Service 단에서 caller 가 명시적으로 snapshot 을 제공하도록 강제한다.
    """

    session_id, subject = await _create_session_direct()
    for empty_snapshot in (None, {}):
        with pytest.raises(ZippinException) as rejected:
            await main_flow.save_floorplan_candidate_snapshot(
                session_id=session_id,
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


async def test_candidate_snapshot_service_preserves_snapshot_in_response(fake_db):
    """board round-3 #4 회귀: 저장된 ``floorplan_snapshot`` 이 그대로 반환된다.

    이후 ``floorplans`` catalog row 가 ``ON DELETE SET NULL`` 로 사라져도
    사용자가 본 후보 화면 (label / type / thumbnail) 이 재현 가능해야 한다.
    """

    session_id, subject = await _create_session_direct()
    snapshot = {
        "display_label": "84A 표준 평면",
        "size_type": "84A",
        "thumbnail_url": "r2://floorplans/abc.png",
        "match_score": 0.91,
    }
    saved = await main_flow.save_floorplan_candidate_snapshot(
        session_id=session_id,
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
