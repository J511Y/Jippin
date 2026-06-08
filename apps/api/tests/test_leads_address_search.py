"""도로명주소 검색 프록시 테스트 (CMP-DIRECT)."""

from __future__ import annotations

import pytest

from src.config import get_settings
from src.errors import ZippinException
from src.services import leads as leads_service


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []

    async def get(self, url: str, params: dict):
        self.calls.append({"url": url, "params": params})
        return _FakeResponse(self._payload)


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_search_addresses_normalizes_juso_payload(monkeypatch) -> None:
    monkeypatch.setenv("JUSO_CONFM_KEY", "test-confm-key")
    get_settings.cache_clear()
    payload = {
        "results": {
            "common": {"errorCode": "0", "errorMessage": "정상", "totalCount": "1"},
            "juso": [
                {
                    "roadAddr": "서울특별시 강남구 테헤란로 1 (역삼동)",
                    "roadAddrPart1": "서울특별시 강남구 테헤란로 1",
                    "roadAddrPart2": " (역삼동)",
                    "jibunAddr": "서울특별시 강남구 역삼동 1",
                    "zipNo": "06232",
                    "bdNm": "아무빌딩",
                    "siNm": "서울특별시",
                    "sggNm": "강남구",
                    "emdNm": "역삼동",
                }
            ],
        }
    }
    fake = _FakeClient(payload)
    result = await leads_service.search_addresses(
        keyword="테헤란로 1", page=1, http_client=fake
    )
    assert result["total_count"] == 1
    assert result["items"][0]["road_addr_part1"] == "서울특별시 강남구 테헤란로 1"
    assert result["items"][0]["zip_no"] == "06232"
    # 승인키가 서버측에서 주입됐는지.
    assert fake.calls[0]["params"]["confmKey"] == "test-confm-key"
    assert fake.calls[0]["params"]["resultType"] == "json"


@pytest.mark.asyncio
async def test_search_addresses_missing_key_raises_503(monkeypatch) -> None:
    monkeypatch.setenv("JUSO_CONFM_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ZippinException) as exc:
        await leads_service.search_addresses(keyword="테헤란로", http_client=None)
    assert exc.value.http_status == 503
    assert exc.value.code == "JUSO_CONFM_KEY_MISSING"


@pytest.mark.asyncio
async def test_search_addresses_juso_error_is_mapped(monkeypatch) -> None:
    monkeypatch.setenv("JUSO_CONFM_KEY", "test-confm-key")
    get_settings.cache_clear()
    payload = {
        "results": {
            "common": {
                "errorCode": "E0005",
                "errorMessage": "검색어가 너무 짧습니다.",
                "totalCount": "0",
            },
            "juso": None,
        }
    }
    fake = _FakeClient(payload)
    with pytest.raises(ZippinException) as exc:
        await leads_service.search_addresses(keyword="x", http_client=fake)
    assert exc.value.http_status == 502
    assert exc.value.code == "JUSO_API_ERROR"
