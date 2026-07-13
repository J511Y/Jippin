"""SeumteoBuildingRegisterClient — 워커 응답 매핑 + 오류 승격 (ADR-0009).

워커 HTTP 는 fake 로 주입한다(외부 호출 없음). 결과 dataclass·예외가 CODEF 와 동형인지
확인해 home_check 무변경 계약을 지킨다.
"""

from __future__ import annotations

import pytest

from src.services.codef.types import (
    CodefAuthError,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    CodefUpstreamError,
)
from src.services.seumteo import (
    BuildingRegisterQuery,
    ExclusivePartResult,
    SeumteoBuildingRegisterClient,
)


class _Settings:
    seumteo_worker_url = "http://worker.flycast"
    seumteo_worker_job_url = "http://worker.internal:8080"
    seumteo_worker_token = "t0ken"
    seumteo_worker_timeout_seconds = 30
    seumteo_worker_warmup_timeout_seconds = 2
    seumteo_worker_warmup_poll_seconds = 0.01
    codef_breaker_error_threshold = 5
    codef_breaker_window_seconds = 300
    codef_breaker_open_seconds = 600


class _FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class _FakeHttp:
    """httpx.AsyncClient 대역 — post 호출을 기록하고 큐에서 응답을 돌려준다."""

    def __init__(
        self,
        responses: list[_FakeResponse],
        health_responses: list[_FakeResponse] | None = None,
    ) -> None:
        self._responses = list(responses)
        self._health_responses = list(health_responses or [])
        self.calls: list[dict] = []
        self.health_calls: list[dict] = []

    async def get(self, url, *, headers=None, timeout=None):
        self.health_calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self._health_responses:
            return self._health_responses.pop(0)
        return _FakeResponse(200, {"ok": True, "browser": True})

    async def post(self, url, *, json=None, headers=None):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._responses.pop(0)


def _client(responses, *, health_responses=None):
    http = _FakeHttp(responses, health_responses)
    client = SeumteoBuildingRegisterClient(
        _Settings(), redis_client=None, http_client=http
    )
    return client, http


_EXCLUSIVE_OK = {
    "ok": True,
    "register_kind": "exclusive",
    "comm_unique_no": "102011442",
    "road_addr": "서울특별시 영등포구 여의대방로43나길 25",
    "jibun_addr": "서울특별시 영등포구 신길동 897-1 삼환아파트",
    "addr_dong": "104동",
    "addr_ho": "504호",
    "violation_status": "위반건축물",
    "owned": [{"resType": "0", "resArea": "84.84", "resUseType": "공동주택"}],
    "change_list": [{"resChangeDate": "2020.01.01", "resChangeReason": "표시변경"}],
    "price_list": [],
    "original_pdf_base64": "JVBERi0xLjQK",
    "extraction": {"violation_source": "report_text", "report_text_len": 1234},
}

_HEADING_OK = {
    "ok": True,
    "register_kind": "heading",
    "comm_unique_no": "1020129529",
    "violation_status": None,
    "detail_list": [{"resType": "주용도", "resContents": "공동주택(아파트)"}],
    "building_status_list": [],
    "change_list": [],
    "original_pdf_base64": "JVBERi0xLjQK",
}


async def test_fetch_exclusive_maps_result():
    client, http = _client([_FakeResponse(200, _EXCLUSIVE_OK)])
    q = BuildingRegisterQuery(
        road_addr="서울특별시 영등포구 여의대방로43나길 25", dong="104동", ho="504호"
    )
    result = await client.fetch_exclusive_part(q)

    assert isinstance(result, ExclusivePartResult)
    assert result.violation_status == "위반건축물"
    assert result.comm_unique_no == "102011442"
    assert result.owned[0]["resArea"] == "84.84"
    assert result.change_list[0]["resChangeReason"] == "표시변경"
    assert result.original_pdf_base64 == "JVBERi0xLjQK"

    # 요청 payload/헤더 확인
    call = http.calls[0]
    assert call["url"] == "http://worker.internal:8080/jobs/building-register"
    assert call["json"]["register_kind"] == "exclusive"
    assert call["json"]["road_addr"] == "서울특별시 영등포구 여의대방로43나길 25"
    assert call["json"]["dong"] == "104동"
    assert call["json"]["ho"] == "504호"
    assert call["headers"]["Authorization"] == "Bearer t0ken"
    assert http.health_calls[0]["url"] == "http://worker.flycast/healthz"


async def test_fetch_heading_maps_result():
    client, _ = _client([_FakeResponse(200, _HEADING_OK)])
    q = BuildingRegisterQuery(
        road_addr="서울특별시 영등포구 여의대방로43나길 25", dong="104동", ho=""
    )
    result = await client.fetch_building_heading(q)

    assert result.violation_status is None
    assert result.detail_list[0]["resContents"] == "공동주택(아파트)"
    assert result.comm_unique_no == "1020129529"


@pytest.mark.parametrize(
    "category,exc",
    [
        ("not_found", CodefNotFound),
        ("auth", CodefAuthError),
        ("invalid", CodefInvalidInput),
        ("upstream", CodefUpstreamError),
    ],
)
async def test_error_category_maps_to_exception(category, exc):
    body = {"ok": False, "category": category, "message": "실패"}
    client, _ = _client([_FakeResponse(200, body)])
    q = BuildingRegisterQuery(road_addr="서울시 어딘가 1", dong="1동", ho="1호")
    with pytest.raises(exc):
        await client.fetch_exclusive_part(q)


async def test_empty_road_addr_is_invalid():
    client, _ = _client([])
    q = BuildingRegisterQuery(road_addr="   ", dong="", ho="")
    with pytest.raises(CodefInvalidInput):
        await client.fetch_exclusive_part(q)


async def test_http_500_is_upstream():
    client, _ = _client([_FakeResponse(500, {})])
    q = BuildingRegisterQuery(road_addr="서울시 어딘가 1", dong="1동", ho="1호")
    with pytest.raises(CodefUpstreamError):
        await client.fetch_exclusive_part(q)


async def test_worker_token_401_is_upstream_not_auth():
    # 워커 토큰 401 = 인프라 오류 → upstream(계정 auth 아님, 서킷 오트립 방지).
    client, _ = _client([_FakeResponse(401, {})])
    q = BuildingRegisterQuery(road_addr="서울시 어딘가 1", dong="1동", ho="1호")
    with pytest.raises(CodefUpstreamError):
        await client.fetch_exclusive_part(q)


async def test_needs_input_normalizes_options():
    # 워커가 여분 키가 섞인 후보를 줘도 계약 shape {value,label,area?} 로 정규화한다.
    body = {
        "ok": False,
        "category": "needs_input",
        "message": "동을 선택해 주세요.",
        "field": "dong",
        "options": [
            {"value": "1020129529", "label": "104동", "area": None, "junk": "x"},
            {"label": "값없음"},  # value 없음 → 버려짐
        ],
    }
    client, _ = _client([_FakeResponse(200, body)])
    q = BuildingRegisterQuery(road_addr="서울시 어딘가 1", dong="104", ho="504호")
    with pytest.raises(CodefNeedsUserInput) as ei:
        await client.fetch_exclusive_part(q)
    exc = ei.value
    assert exc.kind == "dong_ho"
    assert exc.field == "dong"
    assert exc.resume_token  # 토큰 발급됨
    assert exc.options == [{"value": "1020129529", "label": "104동", "area": None}]


async def test_warmup_retries_flycast_until_browser_is_ready():
    client, http = _client(
        [],
        health_responses=[
            _FakeResponse(503, {"ok": False, "browser": False}),
            _FakeResponse(200, {"ok": True, "browser": True}),
        ],
    )

    await client.warmup()

    assert len(http.health_calls) == 2
    assert all(
        call["url"] == "http://worker.flycast/healthz" for call in http.health_calls
    )
