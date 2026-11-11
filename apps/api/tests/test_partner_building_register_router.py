"""파트너 건축물대장 발급 API 테스트 (ADR-0012).

세움터 클라이언트(``services.partner_building_register._new_client``)를 monkeypatch 해 외부
호출 없이 인증·멱등·봉투 매핑·삭제를 검증한다. 잡 저장소는 TEST_MODE 의 프로세스 내
폴백을 쓴다(Redis 미접속).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.config import get_settings
from src.main import create_app
from src.middleware.request_log import build_request_log_record
from src.services import partner_building_register as svc
from src.services.codef import (
    BuildingHeadingResult,
    CodefAuthError,
    CodefCircuitOpen,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    CodefUpstreamError,
    ExclusivePartResult,
)

BASE = "/partner/building-registers"
TOKEN = "partner-test-token"
BODY = {"road_addr": "서울특별시 강남구 테헤란로 1", "dong": "101", "ho": "1001"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    monkeypatch.setenv("SEUMTEO_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(svc, "_memory_store", None)
    yield
    get_settings.cache_clear()


def _headers(key: str | None = "idem-1", token: str = TOKEN) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _exclusive(pdf: str | None = "RVhDTA==") -> ExclusivePartResult:
    return ExclusivePartResult(
        res_doc_no="DOC-1",
        comm_unique_no="UNIQUE-1",
        addr_dong="101",
        addr_ho="1001",
        res_user_addr=None,
        road_addr="서울특별시 강남구 테헤란로 1",
        jibun_addr=None,
        owned=[],
        change_list=[],
        price_list=[],
        violation_status=None,
        issue_date="20261111",
        issue_org="강남구청",
        original_pdf_base64=pdf,
    )


def _heading(pdf: str | None = "SEVBRA==") -> BuildingHeadingResult:
    return BuildingHeadingResult(
        res_doc_no="HDOC-1",
        comm_unique_no="HUNIQUE-1",
        res_user_addr=None,
        detail_list=[],
        building_status_list=[],
        change_list=[],
        violation_status="위반건축물",
        issue_date="20261111",
        issue_org="강남구청",
        original_pdf_base64=pdf,
    )


class _FakeClient:
    def __init__(
        self,
        *,
        bundle=None,
        exclusive=None,
        heading=None,
        error: Exception | None = None,
    ) -> None:
        self._bundle = bundle
        self._exclusive = exclusive
        self._heading = heading
        self._error = error
        self.calls: list[str] = []
        self.queries: list[object] = []

    async def fetch_bundle(self, query):
        self.calls.append("bundle")
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return self._bundle

    async def fetch_exclusive_part(self, query):
        self.calls.append("exclusive")
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return self._exclusive

    async def fetch_building_heading(self, query):
        self.calls.append("heading")
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return self._heading


def _install(monkeypatch, fake: _FakeClient) -> _FakeClient:
    monkeypatch.setattr(svc, "_new_client", lambda: fake)
    return fake


def _client() -> TestClient:
    return TestClient(create_app())


def _submit_and_poll(client: TestClient, body: dict = BODY, key: str = "idem-1"):
    resp = client.post(BASE, json=body, headers=_headers(key))
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    polled = client.get(f"{BASE}/{job_id}", headers=_headers(None))
    assert polled.status_code == 200, polled.text
    return resp.json(), polled.json()


# ---------------------------------------------------------------------------
# 인증 / 입력
# ---------------------------------------------------------------------------
def test_disabled_when_token_unset(monkeypatch):
    monkeypatch.delenv("PARTNER_API_TOKEN", raising=False)
    get_settings.cache_clear()
    client = _client()

    for resp in (
        client.post(BASE, json=BODY, headers=_headers()),
        client.get(f"{BASE}/abc", headers=_headers(None)),
        client.delete(f"{BASE}/abc", headers=_headers(None)),
    ):
        assert resp.status_code == 503
        assert resp.json() == {"detail": "partner api disabled"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": TOKEN},
        {"Authorization": f"Basic {TOKEN}"},
    ],
)
def test_bad_token_is_401(monkeypatch, headers):
    fake = _install(monkeypatch, _FakeClient())
    client = _client()

    resp = client.post(BASE, json=BODY, headers={**headers, "Idempotency-Key": "k"})
    assert resp.status_code == 401
    assert client.get(f"{BASE}/abc", headers=headers).status_code == 401
    assert client.delete(f"{BASE}/abc", headers=headers).status_code == 401
    assert fake.calls == []


def test_missing_idempotency_key_is_400(monkeypatch):
    fake = _install(monkeypatch, _FakeClient())
    client = _client()

    assert client.post(BASE, json=BODY, headers=_headers(None)).status_code == 400
    too_long = client.post(BASE, json=BODY, headers=_headers("k" * 201))
    assert too_long.status_code == 400
    assert fake.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"road_addr": ""},
        {"road_addr": "가" * 256},
        {**BODY, "kinds": []},
        {**BODY, "kinds": ["owner"]},
        {**BODY, "unknown": 1},
        {"dong": "101"},
    ],
)
def test_invalid_body_is_422(monkeypatch, body):
    fake = _install(monkeypatch, _FakeClient())
    resp = _client().post(BASE, json=body, headers=_headers())
    assert resp.status_code == 422
    assert fake.calls == []


# ---------------------------------------------------------------------------
# 발급
# ---------------------------------------------------------------------------
def test_submit_then_poll_done_with_both_envelopes(monkeypatch):
    fake = _install(monkeypatch, _FakeClient(bundle=(_exclusive(), _heading(), False)))
    accepted, polled = _submit_and_poll(
        _client(), {**BODY, "jibun_addr": "서울특별시 강남구 역삼동 1"}
    )

    assert accepted["status"] in ("queued", "running", "done")
    assert set(accepted) == {"job_id", "status"}
    assert polled == {
        "job_id": accepted["job_id"],
        "status": "done",
        "results": {
            "exclusive": {
                "ok": True,
                "register_kind": "exclusive",
                "issue_date": "20261111",
                "violation_status": None,
                "res_doc_no": "DOC-1",
                "pdf_base64": "RVhDTA==",
            },
            "heading": {
                "ok": True,
                "register_kind": "heading",
                "issue_date": "20261111",
                "violation_status": "위반건축물",
                "res_doc_no": "HDOC-1",
                "pdf_base64": "SEVBRA==",
            },
        },
    }
    assert fake.calls == ["bundle"]
    query = fake.queries[0]
    assert (query.road_addr, query.dong, query.ho, query.jibun_addr) == (
        BODY["road_addr"],
        "101",
        "1001",
        "서울특별시 강남구 역삼동 1",
    )


def test_idempotent_repost_returns_same_job(monkeypatch):
    fake = _install(monkeypatch, _FakeClient(bundle=(_exclusive(), _heading(), False)))
    client = _client()

    first = client.post(BASE, json=BODY, headers=_headers("same-key"))
    second = client.post(BASE, json=BODY, headers=_headers("same-key"))
    other = client.post(BASE, json=BODY, headers=_headers("other-key"))

    assert first.status_code == second.status_code == 202
    assert second.json() == {"job_id": first.json()["job_id"], "status": "done"}
    assert other.json()["job_id"] != first.json()["job_id"]
    assert fake.calls == ["bundle", "bundle"]


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (CodefAuthError("로그인 실패"), "auth"),
        (CodefNotFound("대장을 찾을 수 없습니다."), "not_found"),
        (CodefInvalidInput("주소 형식 오류"), "invalid"),
        (CodefCircuitOpen("차단 중"), "busy"),
        (CodefUpstreamError("세움터 점검"), "upstream"),
    ],
)
def test_exclusive_failure_gives_both_failure_envelopes(monkeypatch, error, category):
    _install(monkeypatch, _FakeClient(error=error))
    _, polled = _submit_and_poll(_client())

    expected = {
        "ok": False,
        "category": category,
        "message": error.message,
        "field": None,
        "options": None,
    }
    assert polled["status"] == "done"
    assert polled["results"] == {"exclusive": expected, "heading": expected}


def test_unexpected_error_is_upstream_without_leaking_message(monkeypatch):
    _install(monkeypatch, _FakeClient(error=RuntimeError("secret internals")))
    _, polled = _submit_and_poll(_client())

    for envelope in polled["results"].values():
        assert envelope["ok"] is False
        assert envelope["category"] == "upstream"
        assert "secret" not in envelope["message"]


def test_heading_error_gives_mixed_envelopes(monkeypatch):
    _install(monkeypatch, _FakeClient(bundle=(_exclusive(), None, True)))
    _, polled = _submit_and_poll(_client())

    assert polled["results"]["exclusive"]["ok"] is True
    assert polled["results"]["exclusive"]["pdf_base64"] == "RVhDTA=="
    heading = polled["results"]["heading"]
    assert heading["ok"] is False
    assert heading["category"] == "upstream"
    assert heading["field"] is None and heading["options"] is None


def test_needs_input_carries_field_and_options(monkeypatch):
    options = [{"value": "101", "label": "101동", "area": None}]
    _install(
        monkeypatch,
        _FakeClient(
            error=CodefNeedsUserInput(
                "dong_ho",
                "resume-token",
                "동을 선택해 주세요.",
                field="dong",
                options=options,
            )
        ),
    )
    _, polled = _submit_and_poll(_client())

    for envelope in polled["results"].values():
        assert envelope == {
            "ok": False,
            "category": "needs_input",
            "message": "동을 선택해 주세요.",
            "field": "dong",
            "options": options,
        }
        assert "resume_token" not in envelope


def test_success_without_pdf_is_upstream_failure(monkeypatch):
    _install(monkeypatch, _FakeClient(bundle=(_exclusive(pdf=None), _heading(), False)))
    _, polled = _submit_and_poll(_client())

    assert polled["results"]["exclusive"]["ok"] is False
    assert polled["results"]["exclusive"]["category"] == "upstream"
    assert polled["results"]["heading"]["ok"] is True


@pytest.mark.parametrize(
    ("kind", "call"), [("exclusive", "exclusive"), ("heading", "heading")]
)
def test_single_kind_request(monkeypatch, kind, call):
    fake = _install(
        monkeypatch, _FakeClient(exclusive=_exclusive(), heading=_heading())
    )
    _, polled = _submit_and_poll(_client(), {**BODY, "kinds": [kind]})

    assert fake.calls == [call]
    assert list(polled["results"]) == [kind]
    assert polled["results"][kind]["ok"] is True
    assert polled["results"][kind]["register_kind"] == kind


def test_seumteo_disabled_finishes_with_upstream(monkeypatch):
    monkeypatch.setenv("SEUMTEO_ENABLED", "false")
    get_settings.cache_clear()
    fake = _install(monkeypatch, _FakeClient())
    _, polled = _submit_and_poll(_client())

    assert fake.calls == []
    for envelope in polled["results"].values():
        assert envelope["category"] == "upstream"
        assert envelope["message"] == "세움터 연동이 꺼져 있습니다"


# ---------------------------------------------------------------------------
# 폴링 / 삭제 / 만료
# ---------------------------------------------------------------------------
def test_queued_job_has_no_results(monkeypatch):
    # 백그라운드 발급을 막아 queued 상태를 그대로 본다.
    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(svc, "run_job", noop)
    client = _client()
    accepted = client.post(BASE, json=BODY, headers=_headers()).json()
    polled = client.get(f"{BASE}/{accepted['job_id']}", headers=_headers(None))

    assert accepted["status"] == "queued"
    assert polled.json() == {"job_id": accepted["job_id"], "status": "queued"}


def test_unknown_job_is_404(monkeypatch):
    client = _client()
    assert client.get(f"{BASE}/nope", headers=_headers(None)).status_code == 404
    assert client.get(f"{BASE}/bad.id", headers=_headers(None)).status_code == 404


def test_delete_then_get_is_404_and_delete_is_idempotent(monkeypatch):
    fake = _install(monkeypatch, _FakeClient(bundle=(_exclusive(), _heading(), False)))
    client = _client()
    accepted, _ = _submit_and_poll(client, key="del-key")
    url = f"{BASE}/{accepted['job_id']}"

    deleted = client.delete(url, headers=_headers(None))
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(url, headers=_headers(None)).status_code == 404
    assert client.delete(url, headers=_headers(None)).status_code == 204

    # 삭제 뒤 같은 키로 다시 제출하면 새 잡으로 다시 발급한다.
    again = client.post(BASE, json=BODY, headers=_headers("del-key")).json()
    assert again["job_id"] != accepted["job_id"]
    assert fake.calls == ["bundle", "bundle"]


def test_jobs_expire_on_their_own(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(svc.time, "monotonic", lambda: now["t"])

    async def noop(*_args, **_kwargs):
        return None

    client = _client()

    # queued 표식은 15분 뒤 사라진다(처리 프로세스가 죽은 잡).
    monkeypatch.setattr(svc, "run_job", noop)
    stuck = client.post(BASE, json=BODY, headers=_headers("stuck")).json()
    now["t"] += svc.PENDING_TTL_SECONDS - 1
    assert (
        client.get(f"{BASE}/{stuck['job_id']}", headers=_headers(None)).status_code
        == 200
    )
    now["t"] += 2
    assert (
        client.get(f"{BASE}/{stuck['job_id']}", headers=_headers(None)).status_code
        == 404
    )
    monkeypatch.undo()

    # 완료 결과는 30분 뒤 사라진다.
    monkeypatch.setenv("PARTNER_API_TOKEN", TOKEN)
    monkeypatch.setenv("SEUMTEO_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(svc.time, "monotonic", lambda: now["t"])
    _install(monkeypatch, _FakeClient(bundle=(_exclusive(), _heading(), False)))
    done, _ = _submit_and_poll(client, key="done")
    now["t"] += svc.RESULT_TTL_SECONDS + 1
    assert (
        client.get(f"{BASE}/{done['job_id']}", headers=_headers(None)).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# 개인정보 — 요청 본문은 request_logs 에 저장하지 않는다
# ---------------------------------------------------------------------------
def test_partner_body_is_not_stored_by_request_log():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": BASE,
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "server": ("testserver", 443),
            "scheme": "https",
            "client": ("testclient", 50000),
        }
    )
    request.state.request_id = "00000000-0000-0000-0000-000000000003"
    record = build_request_log_record(
        request=request,
        request_body='{"road_addr":"서울특별시 강남구 테헤란로 1","ho":"1001"}'.encode(),
        response_body=b'{"job_id":"abc","status":"queued"}',
        response_status=202,
        duration_ms=1,
    )

    assert record["body"] is None
    assert record["url"] == BASE


# ---------------------------------------------------------------------------
# Redis 저장소 어댑터 — 운영 경로(TTL·NX·XX 전달, bytes 디코드, 장애 → 503)
# ---------------------------------------------------------------------------
class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, key, value, ex=None, nx=False, xx=False):
        if (nx and key in self.data) or (xx and key not in self.data):
            return None
        self.data[key] = value.encode("utf-8")
        self.ttl[key] = ex
        return True

    async def get(self, key):
        return self.data.get(key)

    async def eval(self, _script, _numkeys, key, expected, value, ttl):
        if self.data.get(key) != expected.encode("utf-8"):
            return 0
        self.data[key] = value.encode("utf-8")
        self.ttl[key] = ttl
        return 1

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)


def test_redis_store_keys_and_ttls(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(svc, "_get_store", lambda: svc._RedisStore(fake_redis))
    _install(monkeypatch, _FakeClient(bundle=(_exclusive(), _heading(), False)))
    client = _client()

    accepted, polled = _submit_and_poll(client, key="redis-key")
    job_key = f"partner:bldg:job:{accepted['job_id']}"
    idem_keys = [k for k in fake_redis.data if k.startswith("partner:bldg:idem:")]

    assert polled["results"]["exclusive"]["ok"] is True
    assert fake_redis.ttl[job_key] == 30 * 60
    assert len(idem_keys) == 1 and len(idem_keys[0].split(":")[-1]) == 64
    # 멱등 표식은 잡보다 먼저 만료된다(표식이 잡보다 오래 남지 않게).
    assert fake_redis.ttl[idem_keys[0]] == 30 * 60 - svc.IDEM_TTL_MARGIN_SECONDS
    assert "redis-key" not in idem_keys[0]
    # 주소는 저장소에 남기지 않는다.
    assert BODY["road_addr"].encode("utf-8") not in fake_redis.data[job_key]

    assert client.delete(f"{BASE}/{accepted['job_id']}", headers=_headers(None))
    assert fake_redis.data == {}


def test_redis_outage_is_503(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    class _Down:
        async def set(self, *_a, **_k):
            raise RedisConnectionError("down")

        async def get(self, *_a, **_k):
            raise RedisConnectionError("down")

        async def delete(self, *_a, **_k):
            raise RedisConnectionError("down")

    monkeypatch.setattr(svc, "_get_store", lambda: svc._RedisStore(_Down()))
    client = _client()

    for resp in (
        client.post(BASE, json=BODY, headers=_headers()),
        client.get(f"{BASE}/abc", headers=_headers(None)),
        client.delete(f"{BASE}/abc", headers=_headers(None)),
    ):
        assert resp.status_code == 503
        assert resp.json() == {"detail": "partner job store unavailable"}


# ---------------------------------------------------------------------------
# 멱등 표식 회수 경합 / 프로세스 내 저장소 만료 청소
# ---------------------------------------------------------------------------
def _stale_marker_race(store):
    """잡 없는 표식을 두 제출이 동시에 본 상황을 강제한다.

    A 가 낡은 표식을 읽는 순간 B 의 제출 전체를 끼워 넣는다 — B 가 먼저 회수하고,
    A 는 낡은 값을 손에 쥔 채 회수를 시도한다.
    """

    import asyncio
    import hashlib

    idem_key = svc._idem_key(hashlib.sha256(b"race-key").hexdigest())
    box: dict[str, object] = {}
    original_get = store.get

    async def racing_get(key):
        value = await original_get(key)
        if key == idem_key and "b" not in box:
            box["b"] = None  # 재진입 방지
            box["b"] = await svc.submit_job(
                idempotency_key="race-key", kinds=["exclusive", "heading"]
            )
        return value

    async def scenario():
        await store.set(idem_key, "gone-job", svc.PENDING_TTL_SECONDS)
        store.get = racing_get
        return await svc.submit_job(
            idempotency_key="race-key", kinds=["exclusive", "heading"]
        )

    a = asyncio.run(scenario())
    return a, box["b"]


def test_stale_marker_reclaim_has_single_winner_memory(monkeypatch):
    store = svc._MemoryStore()
    monkeypatch.setattr(svc, "_get_store", lambda: store)

    (job_a, created_a), (job_b, created_b) = _stale_marker_race(store)

    assert sorted([created_a, created_b]) == [False, True]
    assert job_a["job_id"] == job_b["job_id"]
    # 진 쪽이 만든 잡은 남지 않는다.
    job_keys = [k for k in store._items if k.startswith(svc.JOB_KEY_PREFIX)]
    assert job_keys == [f"{svc.JOB_KEY_PREFIX}{job_a['job_id']}"]


def test_stale_marker_reclaim_has_single_winner_redis(monkeypatch):
    fake_redis = _FakeRedis()
    store = svc._RedisStore(fake_redis)
    monkeypatch.setattr(svc, "_get_store", lambda: store)

    (job_a, created_a), (job_b, created_b) = _stale_marker_race(store)

    assert sorted([created_a, created_b]) == [False, True]
    assert job_a["job_id"] == job_b["job_id"]
    job_keys = [k for k in fake_redis.data if k.startswith(svc.JOB_KEY_PREFIX)]
    assert job_keys == [f"{svc.JOB_KEY_PREFIX}{job_a['job_id']}"]


def test_memory_store_sweeps_expired_pdf_on_next_write(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(svc.time, "monotonic", lambda: now["t"])
    _install(monkeypatch, _FakeClient(bundle=(_exclusive(), _heading(), False)))
    client = _client()

    first, _ = _submit_and_poll(client, key="sweep-1")
    store = svc._get_store()
    first_key = f"{svc.JOB_KEY_PREFIX}{first['job_id']}"
    assert "RVhDTA==" in store._items[first_key][1]

    # 첫 잡을 다시 읽지 않아도, 만료 뒤 다른 잡이 쓰이면 PDF 가 메모리에서 사라진다.
    now["t"] += svc.RESULT_TTL_SECONDS + 1
    second, _ = _submit_and_poll(client, key="sweep-2")

    assert first_key not in store._items
    job_keys = [k for k in store._items if k.startswith(svc.JOB_KEY_PREFIX)]
    assert job_keys == [f"{svc.JOB_KEY_PREFIX}{second['job_id']}"]
    assert len([k for k in store._items if k.startswith(svc.IDEM_KEY_PREFIX)]) == 1
