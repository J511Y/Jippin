"""CODEF OAuth2 access_token 발급 + Redis 캐시 (ADR-0008 §2.2).

``POST {codef_oauth_url}`` 에 Basic auth(``base64(client_id:client_secret)``) +
``grant_type=client_credentials&scope=read`` 로 토큰을 받는다. 만료 시 자동 재발급한다.
Redis 는 OAuth state store 패턴과 동일하게 ``redis.asyncio`` 를 쓴다.

토큰 문자열은 로깅하지 않는다(log_http_call 은 status/duration 만 남긴다).
"""

from __future__ import annotations

import base64
import time

import httpx
import redis.asyncio as redis
from redis.exceptions import RedisError

from ...logging import log_http_call
from .types import CodefAuthError, CodefUpstreamError

# Redis 캐시 키 + 만료 직전 안전 마진(초). 토큰 만료 경계에서 401 을 피한다.
_TOKEN_CACHE_KEY = "codef:oauth_token"
_EXPIRY_SAFETY_MARGIN_SECONDS = 60
# CODEF 가 expires_in 을 주지 않을 때의 보수적 기본 수명(초). 통상 7일이나 짧게 잡는다.
_DEFAULT_TOKEN_TTL_SECONDS = 3600


class CodefTokenProvider:
    """access_token 을 발급/캐시하고, 만료 시 재발급한다.

    ``redis_client`` 가 None 이면 Redis 캐시 없이 매번 in-process 캐시만 사용한다
    (테스트/Redis 비가용 환경). ``http_client`` 주입으로 전송을 mock 할 수 있다.
    """

    def __init__(
        self,
        *,
        oauth_url: str,
        client_id: str | None,
        client_secret: str | None,
        redis_client: redis.Redis | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._oauth_url = oauth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._redis = redis_client
        self._http = http_client
        # in-process 캐시 (Redis 비가용 시 폴백 + 동일 프로세스 재요청 절감).
        self._cached_token: str | None = None
        self._cached_expiry: float = 0.0

    async def get_token(self, *, force_refresh: bool = False) -> str:
        now = time.time()
        if not force_refresh:
            if self._cached_token and now < self._cached_expiry:
                return self._cached_token
            cached = await self._read_redis_cache()
            if cached is not None:
                return cached
        return await self._issue_and_cache()

    async def _read_redis_cache(self) -> str | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(_TOKEN_CACHE_KEY)
        except RedisError:
            return None  # 캐시 실패는 치명적이지 않다 — 재발급으로 폴백.
        if raw is None:
            return None
        token = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        self._cached_token = token
        # Redis TTL 이 캐시 수명을 관리하므로 in-process 만료는 짧게 신뢰.
        self._cached_expiry = time.time() + _EXPIRY_SAFETY_MARGIN_SECONDS
        return token

    async def _issue_and_cache(self) -> str:
        if not self._client_id or not self._client_secret:
            raise CodefAuthError("CODEF client_id/secret 이 설정되지 않았습니다.")

        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials", "scope": "read"}

        async def _run(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(self._oauth_url, headers=headers, data=data)

        async def _do() -> httpx.Response:
            if self._http is not None:
                return await _run(self._http)
            async with httpx.AsyncClient(timeout=20.0) as client:
                return await _run(client)

        try:
            response = await log_http_call("codef", "oauth_token", _do)
        except httpx.HTTPError as exc:
            raise CodefUpstreamError("CODEF 토큰 발급 호출에 실패했습니다.") from exc

        if response.status_code in (401, 403):
            # 잘못된 client 자격증명 — 재시도 무의미.
            raise CodefAuthError(
                "CODEF 토큰 발급 인증에 실패했습니다.",
                code=str(response.status_code),
            )
        if response.status_code >= 400:
            raise CodefUpstreamError(
                "CODEF 토큰 발급이 거부되었습니다.",
                code=str(response.status_code),
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise CodefUpstreamError("CODEF 토큰 응답을 해석할 수 없습니다.") from exc

        token = body.get("access_token")
        if not token:
            raise CodefAuthError("CODEF 토큰 응답에 access_token 이 없습니다.")

        expires_in = int(body.get("expires_in") or _DEFAULT_TOKEN_TTL_SECONDS)
        ttl = max(1, expires_in - _EXPIRY_SAFETY_MARGIN_SECONDS)
        self._cached_token = token
        self._cached_expiry = time.time() + ttl
        await self._write_redis_cache(token, ttl)
        return token

    async def _write_redis_cache(self, token: str, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(_TOKEN_CACHE_KEY, token, ex=ttl)
        except RedisError:
            return  # 캐시 쓰기 실패는 무시 — 다음 호출이 재발급한다.
