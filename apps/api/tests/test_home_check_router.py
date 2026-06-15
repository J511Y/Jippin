"""우리집 체크(home-check) 라우터/서비스 테스트 (ADR-0008).

CODEF 클라이언트(``services.home_check._new_client``)와 Supabase Storage 는 전부
monkeypatch 해 실제 외부 호출 없이 라우터·판정·직렬화·인증 경로를 검증한다. DB 쓰기/읽기는
``services.home_check`` 의 좁은 seam 함수들을 patch 한다(TEST_MODE 에서 DB 미접속).

응답 payload 는 정본 계약(``zippin_contracts.home_check.HomeCheckJob``)으로 재검증해
런타임 ``src.schemas.home_check`` 의 shape 가 contract 와 일치함을 보장한다(런타임 src 는
contract 패키지를 import 하지 않으므로 — apps/api/Dockerfile 은 src 만 복사 — 이 교차검증이
계약 일치의 단일 게이트다).
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import create_app
from src.services import home_check as svc
from src.services.codef import (
    BuildingHeadingResult,
    CodefNeedsUserInput,
    CodefNotFound,
    ExclusivePartResult,
)

from . import _supabase_helpers as helpers

# 정본 계약(생성 모델) — 런타임 의존성 추가 없이 응답 shape 를 교차검증한다.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "packages" / "contracts" / "python"))
from zippin_contracts.home_check import HomeCheckJob as ContractHomeCheckJob  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _auth_client(monkeypatch, *, is_anonymous: bool = False):
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    token, subject = helpers.mint_token(pem, "test-key-1", is_anonymous=is_anonymous)
    client = TestClient(create_app())
    return client, token, subject


def _exclusive(violation: str | None = None) -> ExclusivePartResult:
    return ExclusivePartResult(
        res_doc_no="DOC-1",
        comm_unique_no="UNIQUE-1",
        addr_dong="101",
        addr_ho="1001",
        res_user_addr=None,
        road_addr="서울특별시 강남구 테헤란로 1",
        jibun_addr=None,
        owned=[
            {
                "resType": "0",
                "resArea": "84.99",
                "resUseType": "공동주택",
                "resStructure": "철근콘크리트구조",
                "resFloor": "10층",
            }
        ],
        change_list=[{"resChangeDate": "20200101", "resChangeReason": "신규작성"}],
        price_list=[{"resReferenceDate": "20230101", "resBasePrice": "500000000"}],
        violation_status=violation,
        issue_date="20240101",
        issue_org="강남구청",
        original_pdf_base64=None,
    )


def _heading(violation: str | None = None) -> BuildingHeadingResult:
    return BuildingHeadingResult(
        res_doc_no="HDOC-1",
        comm_unique_no="HUNIQUE-1",
        res_user_addr=None,
        detail_list=[
            {"resType": "주용도", "resContents": "공동주택"},
            {"resType": "층수", "resContents": "지하 1층 지상 12층"},
            {"resType": "사용승인일", "resContents": "20191231"},
        ],
        building_status_list=[],
        change_list=[{"resChangeDate": "20191231", "resChangeReason": "사용승인"}],
        violation_status=violation,
        issue_date="20240101",
        issue_org="강남구청",
        original_pdf_base64=None,
    )


def _patch_create(monkeypatch) -> dict[str, object]:
    """create_home_check 를 in-memory row 반환으로 대체하고 박스에 저장한다."""

    box: dict[str, object] = {}

    async def fake_create(**kwargs):
        row = {
            "id": uuid.uuid4(),
            "status": "querying",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            **kwargs,
        }
        box["row"] = row
        box["create_kwargs"] = kwargs
        return {
            "id": row["id"],
            "status": "querying",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    monkeypatch.setattr(svc, "create_home_check", fake_create)
    return box


def _block_background(monkeypatch) -> None:
    """run_home_check 백그라운드를 no-op 으로 막는다(POST 응답 경로만 검증)."""

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(svc, "run_home_check", noop)


# ---------------------------------------------------------------------------
# POST /home-check
# ---------------------------------------------------------------------------
def test_create_requires_bearer_token() -> None:
    client = TestClient(create_app())
    with client:
        response = client.post(
            "/home-check", json={"road_addr": "서울 테헤란로 1", "ho": "1001"}
        )
    assert response.status_code == 401


def test_create_returns_202_querying_job(monkeypatch) -> None:
    _patch_create(monkeypatch)
    _block_background(monkeypatch)
    client, token, subject = _auth_client(monkeypatch, is_anonymous=True)
    with client:
        response = client.post(
            "/home-check",
            headers={"authorization": f"Bearer {token}"},
            json={
                "road_addr": "서울특별시 강남구 테헤란로 1",
                "dong": "101",
                "ho": "1001",
            },
        )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "querying"
    assert body["report"] is None
    # 정본 계약으로 재검증.
    ContractHomeCheckJob.model_validate(body)


# ---------------------------------------------------------------------------
# 백그라운드 처리 — 판정 (a)~(d)
# ---------------------------------------------------------------------------
class _FakeClient:
    def __init__(
        self, *, exclusive=None, heading=None, exclusive_exc=None, heading_exc=None
    ):
        self._exclusive = exclusive
        self._heading = heading
        self._exclusive_exc = exclusive_exc
        self._heading_exc = heading_exc

    async def fetch_exclusive_part(self, _query):
        if self._exclusive_exc is not None:
            raise self._exclusive_exc
        return self._exclusive

    async def fetch_building_heading(self, _query):
        if self._heading_exc is not None:
            raise self._heading_exc
        return self._heading


def _capture_updates(monkeypatch) -> dict[str, dict]:
    """_update_row / _store_pdfs 를 in-memory 로 잡아 판정 결과를 검증한다."""

    captured: dict[str, dict] = {}

    async def fake_update(home_check_id, values):
        captured.setdefault(str(home_check_id), {}).update(values)

    async def fake_store(*_args, **_kwargs):
        captured["_store_called"] = {"called": True}

    monkeypatch.setattr(svc, "_update_row", fake_update)
    monkeypatch.setattr(svc, "_store_pdfs", fake_store)
    return captured


def _run(coro):
    return asyncio.run(coro)


def test_signal_violation_when_heading_violation(monkeypatch) -> None:
    captured = _capture_updates(monkeypatch)
    hid = uuid.uuid4()
    monkeypatch.setattr(
        svc,
        "_new_client",
        lambda: _FakeClient(exclusive=_exclusive(None), heading=_heading("위반건축물")),
    )
    _run(
        svc.run_home_check(
            hid, road_addr="addr", jibun_addr=None, dong="101", ho="1001"
        )
    )
    values = captured[str(hid)]
    assert values["status"] == "completed"
    assert values["signal"] == "violation"
    assert values["violation"] is True
    assert values["heading_violation"] is True
    assert values["exclusive_violation"] is False


def test_signal_normal_when_both_clean(monkeypatch) -> None:
    captured = _capture_updates(monkeypatch)
    hid = uuid.uuid4()
    monkeypatch.setattr(
        svc,
        "_new_client",
        lambda: _FakeClient(exclusive=_exclusive(None), heading=_heading(None)),
    )
    _run(
        svc.run_home_check(
            hid, road_addr="addr", jibun_addr=None, dong="101", ho="1001"
        )
    )
    values = captured[str(hid)]
    assert values["status"] == "completed"
    assert values["signal"] == "normal"
    assert values["violation"] is False
    # 요약/변동/가격 매핑.
    assert float(values["exclusive_area_m2"]) == 84.99
    assert values["building_main_use"] == "공동주택"
    assert values["building_floors"] == "지하 1층 지상 12층"
    assert len(values["change_list"]) == 2  # 전유부 + 표제부
    assert values["price_list"][0]["base_price"] == 500000000


def test_signal_caution_when_heading_fails(monkeypatch) -> None:
    captured = _capture_updates(monkeypatch)
    hid = uuid.uuid4()
    monkeypatch.setattr(
        svc,
        "_new_client",
        lambda: _FakeClient(
            exclusive=_exclusive(None),
            heading_exc=CodefNotFound("표제부 없음"),
        ),
    )
    _run(
        svc.run_home_check(
            hid, road_addr="addr", jibun_addr=None, dong="101", ho="1001"
        )
    )
    values = captured[str(hid)]
    assert values["status"] == "completed"
    assert values["signal"] == "caution"
    assert values["violation"] is False
    assert values["heading_violation"] is False
    reasons = values["result_fields"]["caution_reasons"]
    assert any("표제부" in r for r in reasons)


def test_needs_input_records_resume_token(monkeypatch) -> None:
    captured = _capture_updates(monkeypatch)
    hid = uuid.uuid4()
    monkeypatch.setattr(
        svc,
        "_new_client",
        lambda: _FakeClient(
            exclusive_exc=CodefNeedsUserInput(
                "dong_ho", "RESUME-XYZ", "동·호를 선택해 주세요."
            )
        ),
    )
    _run(svc.run_home_check(hid, road_addr="addr", jibun_addr=None, dong="", ho="1001"))
    values = captured[str(hid)]
    assert values["status"] == "needs_input"
    fields = values["result_fields"]
    assert fields["resume_token"] == "RESUME-XYZ"
    assert fields["product"] == "exclusive"
    assert fields["kind"] == "dong_ho"


# ---------------------------------------------------------------------------
# 직렬화 — needs_input → HomeCheckJob.needs_input (정본 계약 검증)
# ---------------------------------------------------------------------------
def test_serialize_needs_input_job() -> None:
    row = {
        "id": uuid.uuid4(),
        "status": "needs_input",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "result_fields": {
            "resume_token": "RESUME-1",
            "product": "exclusive",
            "kind": "secure_no",
            "message": "보안문자 입력이 필요합니다.",
        },
    }
    job = _run(svc.serialize_job(row))
    payload = job.model_dump(mode="json")
    assert payload["needs_input"]["kind"] == "secure_no"
    # resume_token 은 응답 payload 에 노출되지 않는다.
    assert "resume_token" not in str(payload["needs_input"])
    contract = ContractHomeCheckJob.model_validate(payload)
    assert contract.needs_input is not None
    assert contract.needs_input.kind.value == "secure_no"


def test_serialize_completed_report_validates_against_contract() -> None:
    row = {
        "id": uuid.uuid4(),
        "status": "completed",
        "signal": "violation",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "road_addr": "서울특별시 강남구 테헤란로 1",
        "jibun_addr": None,
        "addr_dong": "101",
        "addr_ho": "1001",
        "violation": True,
        "exclusive_violation": True,
        "heading_violation": False,
        "exclusive_area_m2": 84.99,
        "exclusive_use_type": "공동주택",
        "exclusive_structure": "철근콘크리트구조",
        "exclusive_floor": "10층",
        "building_main_use": "공동주택",
        "building_floors": "지하 1층 지상 12층",
        "building_approval_date": None,
        "building_permit_date": None,
        "comm_unique_no": "UNIQUE-1",
        "heading_comm_unique_no": "HUNIQUE-1",
        "res_doc_no": "DOC-1",
        "res_issue_date": None,
        "queried_at": datetime.now(UTC),
        "change_list": [
            {"date": "20200101", "reason": "신규작성", "source": "exclusive"}
        ],
        "price_list": [{"reference_date": "20230101", "base_price": 500000000}],
        "result_fields": {"caution_reasons": None},
    }
    # documents 발급(외부 호출) 생략.
    job = _run(svc.serialize_job(row, with_documents=False))
    payload = job.model_dump(mode="json")
    assert payload["report"]["signal"] == "violation"
    assert payload["report"]["disclaimer"].startswith("본 결과는")
    ContractHomeCheckJob.model_validate(payload)


# ---------------------------------------------------------------------------
# GET /home-check/{id} — 소유자 검증
# ---------------------------------------------------------------------------
def test_get_other_owner_returns_404(monkeypatch) -> None:
    async def fake_get(*, home_check_id, user_id):  # noqa: ARG001
        return None  # 타인/없음 → None

    monkeypatch.setattr(svc, "get_home_check_row", fake_get)
    client, token, _subject = _auth_client(monkeypatch)
    with client:
        response = client.get(
            f"/home-check/{uuid.uuid4()}",
            headers={"authorization": f"Bearer {token}"},
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HOME_CHECK_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /home-check/mine — 익명 403
# ---------------------------------------------------------------------------
def test_mine_rejects_anonymous(monkeypatch) -> None:
    client, token, _subject = _auth_client(monkeypatch, is_anonymous=True)
    with client:
        response = client.get(
            "/home-check/mine", headers={"authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED"


def test_mine_returns_items_with_address_and_signal(monkeypatch) -> None:
    rows = [
        {
            "id": uuid.uuid4(),
            "status": "completed",
            "signal": "normal",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "road_addr": "서울특별시 강남구 테헤란로 1",
            "jibun_addr": None,
            "addr_dong": "101",
            "addr_ho": "1001",
            "violation": False,
            "exclusive_violation": False,
            "heading_violation": False,
            "change_list": [],
            "price_list": [],
            "result_fields": {},
        }
    ]

    async def fake_list(*, user_id):  # noqa: ARG001
        return rows

    monkeypatch.setattr(svc, "list_home_checks_for_user", fake_list)
    client, token, _subject = _auth_client(monkeypatch)
    with client:
        response = client.get(
            "/home-check/mine", headers={"authorization": f"Bearer {token}"}
        )
    assert response.status_code == 200
    body = response.json()
    item = body["items"][0]
    assert item["report"]["address"]["road_addr"] == "서울특별시 강남구 테헤란로 1"
    assert item["report"]["signal"] == "normal"
    ContractHomeCheckJob.model_validate(item)


# ---------------------------------------------------------------------------
# PDF 업로드 실패해도 completed (g)
# ---------------------------------------------------------------------------
def test_completed_even_if_pdf_upload_fails(monkeypatch) -> None:
    updates: dict[str, dict] = {}

    async def fake_update(home_check_id, values):
        updates.setdefault(str(home_check_id), {}).update(values)

    # _store_pdfs 는 실제 로직을 타되 업로드만 실패시킨다 → completed 유지.
    monkeypatch.setattr(svc, "_update_row", fake_update)

    async def fake_upload(*_args, **_kwargs):
        raise RuntimeError("boom")  # _store_pdfs 내부에서 흡수되어야 한다

    # supabase storage 설정이 있어야 _store_pdfs 가 업로드를 시도한다.
    monkeypatch.setenv("SUPABASE_URL", "https://example-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test")
    get_settings.cache_clear()
    monkeypatch.setattr(svc, "_upload_pdf", fake_upload)

    async def fake_insert_doc(**_kwargs):
        raise AssertionError("문서 insert 가 호출되면 안 된다(업로드 실패)")

    monkeypatch.setattr(svc, "_insert_document", fake_insert_doc)

    hid = uuid.uuid4()
    exclusive = _exclusive(None)
    exclusive.original_pdf_base64 = "aGVsbG8="  # 'hello'
    monkeypatch.setattr(
        svc,
        "_new_client",
        lambda: _FakeClient(exclusive=exclusive, heading=_heading(None)),
    )
    _run(
        svc.run_home_check(
            hid, road_addr="addr", jibun_addr=None, dong="101", ho="1001"
        )
    )
    values = updates[str(hid)]
    assert values["status"] == "completed"
    assert values["signal"] == "normal"
