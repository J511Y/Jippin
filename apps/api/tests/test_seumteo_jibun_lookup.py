"""도로명주소 → 지번 보강(lookup_jibun_addr) — 도로명 정확 일치만 채택, 실패는 None."""

from __future__ import annotations

import httpx

from src.services.seumteo.jibun import lookup_jibun_addr, road_key

_URL = "https://juso.example/addrLinkApi.do"
_ROAD = "서울특별시 영등포구 여의대방로43나길 25"


class _Resp:
    def __init__(self, body: dict, status: int = 200) -> None:
        self._body = body
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "bad",
                request=httpx.Request("GET", _URL),
                response=None,  # type: ignore[arg-type]
            )

    def json(self) -> dict:
        return self._body


class _Http:
    def __init__(self, resp: _Resp | Exception) -> None:
        self._resp = resp
        self.params: dict | None = None

    async def get(self, url, *, params=None, timeout=None):
        self.params = params
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _body(*items: dict, error_code: str = "0") -> dict:
    return {"results": {"common": {"errorCode": error_code}, "juso": list(items)}}


async def test_returns_jibun_of_exact_road_match_only():
    http = _Http(
        _Resp(
            _body(
                {
                    "roadAddrPart1": "서울특별시 영등포구 여의대방로43나길 251",
                    "jibunAddr": "남의 지번",
                },
                {
                    "roadAddrPart1": _ROAD,
                    "jibunAddr": "서울특별시 영등포구 신길동 897-1 삼환아파트",
                },
            )
        )
    )

    jibun = await lookup_jibun_addr(
        _ROAD + " (신길동, 삼환아파트)", confm_key="k", api_url=_URL, http_client=http
    )

    assert jibun == "서울특별시 영등포구 신길동 897-1 삼환아파트"
    # 괄호 참고항목은 검색어에서 뗀다.
    assert http.params is not None and http.params["keyword"] == _ROAD


async def test_no_exact_match_returns_none():
    http = _Http(
        _Resp(_body({"roadAddrPart1": "서울특별시 다른로 1", "jibunAddr": "x"}))
    )
    assert (
        await lookup_jibun_addr(_ROAD, confm_key="k", api_url=_URL, http_client=http)
        is None
    )


async def test_api_error_and_transport_error_return_none():
    http = _Http(_Resp(_body(error_code="E0001")))
    assert (
        await lookup_jibun_addr(_ROAD, confm_key="k", api_url=_URL, http_client=http)
        is None
    )

    http = _Http(httpx.ConnectTimeout("slow"))
    assert (
        await lookup_jibun_addr(_ROAD, confm_key="k", api_url=_URL, http_client=http)
        is None
    )


async def test_missing_key_skips_call():
    http = _Http(AssertionError("호출하면 안 된다"))
    assert (
        await lookup_jibun_addr(_ROAD, confm_key=None, api_url=_URL, http_client=http)
        is None
    )


def test_road_key_ignores_spaces_and_reference():
    assert road_key("서울특별시  영등포구 여의대방로43나길 25(신길동)") == road_key(
        _ROAD
    )
