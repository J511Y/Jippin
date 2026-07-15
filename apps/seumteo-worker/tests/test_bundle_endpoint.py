"""통합 잡 엔드포인트 — 공유 단계 실패 시 동일 오류 봉투를 양쪽 종류에 복제한다."""

from __future__ import annotations

import asyncio
import json
import unittest

from fastapi.responses import JSONResponse

from src.browser import LoginError
from src.flow import FlowError
from src.main import app, building_register_bundle
from src.models import (
    BuildingRegisterBundleRequest,
    BuildingRegisterBundleResponse,
    BuildingRegisterResult,
)


class _StubFlow:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc

    async def run_bundle(self, _req):
        if self._exc is not None:
            raise self._exc
        return BuildingRegisterBundleResponse(
            exclusive=BuildingRegisterResult(register_kind="exclusive"),
            heading=BuildingRegisterResult(register_kind="heading"),
        )


class _StubManager:
    async def ensure_logged_in(self) -> None:
        return None


def _payload(response: JSONResponse) -> dict:
    return json.loads(bytes(response.body))


def _req() -> BuildingRegisterBundleRequest:
    return BuildingRegisterBundleRequest(
        road_addr="대구광역시 달서구 달서대로 67", dong="105동", ho="2001호"
    )


class BundleEndpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        app.state.mgr = _StubManager()

    async def test_success_returns_both_results(self) -> None:
        app.state.flow = _StubFlow()

        result = await building_register_bundle(_req(), authorization=None)

        self.assertTrue(result.exclusive.ok)
        self.assertTrue(result.heading.ok)

    async def test_needs_input_duplicated_to_both_envelopes(self) -> None:
        app.state.flow = _StubFlow(
            FlowError("not_found", "입력한 동을 찾지 못했습니다.", field="dong")
        )

        response = await building_register_bundle(_req(), authorization=None)

        body = _payload(response)
        for kind in ("exclusive", "heading"):
            self.assertFalse(body[kind]["ok"])
            self.assertEqual(body[kind]["category"], "not_found")
            self.assertEqual(body[kind]["field"], "dong")

    async def test_auth_error_duplicated(self) -> None:
        app.state.flow = _StubFlow(LoginError("로그인 실패"))

        response = await building_register_bundle(_req(), authorization=None)

        body = _payload(response)
        self.assertEqual(body["exclusive"]["category"], "auth")
        self.assertEqual(body["heading"]["category"], "auth")

    async def test_timeout_maps_to_upstream(self) -> None:
        app.state.flow = _StubFlow(asyncio.TimeoutError())

        response = await building_register_bundle(_req(), authorization=None)

        body = _payload(response)
        self.assertEqual(body["exclusive"]["category"], "upstream")
        self.assertEqual(body["heading"]["category"], "upstream")

    async def test_unexpected_error_returns_502(self) -> None:
        app.state.flow = _StubFlow(RuntimeError("browser crashed"))

        response = await building_register_bundle(_req(), authorization=None)

        self.assertEqual(response.status_code, 502)
        body = _payload(response)
        self.assertEqual(body["exclusive"]["category"], "upstream")


if __name__ == "__main__":
    unittest.main()
