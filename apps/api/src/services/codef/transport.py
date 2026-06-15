"""CODEF 제품 API 전송 계층 — POST + URL-decode + 봉투 파싱 (ADR-0008 §2.2).

CODEF 본문은 URL-encoded(percent) 텍스트라서 ``unquote_plus`` 후 ``json.loads`` 한다.
봉투는 ``{ "result": {code,message,extraMessage,transactionId}, "data": {...}|[...] }``.

``result.code`` 분류:
  - CF-00000  : 성공
  - CF-03002  : 추가인증(2-way) 진행 — data 에 continue2Way + extraInfo
  - 그 외     : 오류 → ``classify_error`` 로 도메인 예외 매핑(building_register 에서 호출)

토큰/자격증명/응답 본문은 로깅하지 않는다(log_http_call 은 status/duration 만).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_plus

import httpx

from ...logging import log_http_call
from .types import CodefUpstreamError

CODEF_CODE_SUCCESS = "CF-00000"
CODEF_CODE_TWO_WAY = "CF-03002"


@dataclass(frozen=True)
class CodefEnvelope:
    """디코드된 CODEF 응답 봉투."""

    code: str
    message: str
    extra_message: str
    transaction_id: str
    data: Any  # dict | list | None

    @property
    def is_success(self) -> bool:
        return self.code == CODEF_CODE_SUCCESS

    @property
    def is_two_way(self) -> bool:
        return self.code == CODEF_CODE_TWO_WAY

    def data_dict(self) -> dict[str, Any]:
        """data 가 dict 면 그대로, list 면 첫 원소, 그 외엔 빈 dict."""
        if isinstance(self.data, dict):
            return self.data
        if isinstance(self.data, list) and self.data and isinstance(self.data[0], dict):
            return self.data[0]
        return {}


def decode_envelope(raw_text: str) -> CodefEnvelope:
    """URL-encoded 본문 → JSON 봉투 파싱."""

    decoded = unquote_plus(raw_text or "")
    try:
        body = json.loads(decoded)
    except ValueError as exc:
        raise CodefUpstreamError("CODEF 응답을 해석할 수 없습니다.") from exc
    if not isinstance(body, dict):
        raise CodefUpstreamError("CODEF 응답 형식이 올바르지 않습니다.")

    result = body.get("result") or {}
    return CodefEnvelope(
        code=str(result.get("code") or ""),
        message=str(result.get("message") or ""),
        extra_message=str(result.get("extraMessage") or ""),
        transaction_id=str(result.get("transactionId") or ""),
        data=body.get("data"),
    )


class CodefTransport:
    """제품 API 단건 POST 를 수행하고 봉투를 디코드한다.

    ``http_client`` 주입으로 테스트가 전송을 mock 할 수 있다. ``token_provider`` 는
    호출부(building_register)가 토큰 갱신을 제어할 수 있도록 토큰을 인자로 받는다.
    """

    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client

    async def post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        access_token: str,
        operation: str,
        timeout_seconds: float,
    ) -> CodefEnvelope:
        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json;charset=UTF-8",
        }

        async def _run(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(url, headers=headers, json=body)

        async def _do() -> httpx.Response:
            if self._http is not None:
                return await _run(self._http)
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                return await _run(client)

        try:
            response = await log_http_call("codef", operation, _do)
        except httpx.TimeoutException as exc:
            raise CodefUpstreamError("CODEF 응답이 시간 내 도착하지 않았습니다.") from exc
        except httpx.HTTPError as exc:
            raise CodefUpstreamError("CODEF 호출에 실패했습니다.") from exc

        if response.status_code >= 500:
            raise CodefUpstreamError(
                "CODEF 서버 오류입니다.", code=str(response.status_code)
            )
        if response.status_code == 401:
            # 토큰 만료/무효 — 호출부가 재발급 후 1회 재시도한다.
            raise CodefUpstreamError("CODEF 인증 토큰이 거부되었습니다.", code="401")
        if response.status_code >= 400:
            raise CodefUpstreamError(
                "CODEF 요청이 거부되었습니다.", code=str(response.status_code)
            )

        return decode_envelope(response.text)
