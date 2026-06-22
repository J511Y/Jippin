"""HF 세그멘테이션 도구 실패 분류 테스트 — CMP-DIRECT.

httpx MockTransport 로 미배포/404/503-콜드스타트/타임아웃/연결오류/200/5xx/4xx 를
재현하고, segment_floorplan_impl 이 raise 없이 구조화 결과 + 안정적 error_code 로
매핑하는지 검증한다. LLM 미사용.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from src.agent.tools.segmentation import segment_floorplan_impl


def _settings(**override: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "hf_segmentation_endpoint_url": "https://hf.example/seg",
        "hf_segmentation_token": "tok",
        "hf_segmentation_timeout_seconds": 5,
        "hf_segmentation_cold_start_max_retries": 0,
    }
    base.update(override)
    return SimpleNamespace(**base)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_unset_endpoint_is_unavailable() -> None:
    res = await segment_floorplan_impl(
        image_url="x", settings=_settings(hf_segmentation_endpoint_url=None)
    )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_404_is_unavailable() -> None:
    async with _client(lambda req: httpx.Response(404)) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_503_cold_start_timeout_when_no_retries() -> None:
    async with _client(lambda req: httpx.Response(503)) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_COLD_START_TIMEOUT"


async def test_read_timeout_is_timeout() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=req)

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_TIMEOUT"


async def test_connect_error_is_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=req)

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_500_is_upstream_error() -> None:
    async with _client(lambda req: httpx.Response(500)) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_UPSTREAM_ERROR"


async def test_422_is_bad_request() -> None:
    async with _client(lambda req: httpx.Response(422)) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_BAD_REQUEST"


async def test_200_parses_instances() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instances": [
                    {"label": "wall_other", "count": 3, "mean_confidence": 0.8},
                    {"label": "wall_reinforced_concrete", "count": 1},
                    {"label": "bogus", "count": 9},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["ok"] is True
    labels = {i["label"]: i["count"] for i in res["instances"]}
    assert labels == {"wall_other": 3, "wall_reinforced_concrete": 1}
    assert "비내력벽 후보 3" in res["summary"]


async def test_200_non_json_is_bad_response() -> None:
    async with _client(lambda req: httpx.Response(200, content=b"not json")) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_BAD_RESPONSE"


async def test_request_error_is_upstream() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset", request=req)

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_UPSTREAM_ERROR"


async def test_200_drops_out_of_range_confidence() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instances": [
                    {"label": "door", "count": 1, "mean_confidence": 1.4},
                    {"label": "window", "count": 1, "mean_confidence": 0.5},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    by_label = {i["label"]: i for i in res["instances"]}
    assert "mean_confidence" not in by_label["door"]  # 1.4 는 드롭
    assert by_label["window"]["mean_confidence"] == 0.5


async def test_200_preserves_mask_asset_id() -> None:
    mask_id = "11111111-1111-1111-1111-111111111111"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"instances": [], "mask_asset_id": mask_id})

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url="x", settings=_settings(), client=client
        )
    assert res["ok"] is True
    assert res["mask_asset_id"] == mask_id
