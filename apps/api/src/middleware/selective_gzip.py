"""SSE 경로를 gzip 에서 제외하는 GZipMiddleware 래퍼 — CMP-DIRECT.

Starlette ``GZipMiddleware`` 는 streaming 응답도 청크 단위로 압축하는데, 이는
SSE(text/event-stream)의 즉시 flush 를 방해해 토큰 지연/버퍼링을 유발한다. 에이전트
SSE 경로(``/agent/runs``)는 압축하지 않고 그대로 통과시킨다. 그 외 경로는 평소처럼
GZipMiddleware 로 위임한다.
"""

from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class SelectiveGZipMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        minimum_size: int = 1024,
        exclude_substrings: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)
        self._exclude = exclude_substrings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if any(token in path for token in self._exclude):
                await self.app(scope, receive, send)
                return
        await self._gzip(scope, receive, send)
