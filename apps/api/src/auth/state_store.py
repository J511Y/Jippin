from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import RedisError, ResponseError

from ..config import get_settings
from ..errors import ZippinException

STATE_KEY_PREFIX = "auth:oauth_state:"
GETDEL_FALLBACK_LUA = """
local value = redis.call("GET", KEYS[1])
if value then
  redis.call("DEL", KEYS[1])
end
return value
"""


class OAuthStateBackendUnavailable(ZippinException):
    code = "OAUTH_STATE_BACKEND_UNAVAILABLE"
    http_status = 503


@dataclass(frozen=True)
class OAuthStatePayload:
    anonymous_user_id: UUID | None
    provider: str
    return_url: str | None
    nonce: str
    created_at: datetime
    linking_user_id: UUID | None = None

    def to_json_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["anonymous_user_id"] = (
            str(self.anonymous_user_id) if self.anonymous_user_id is not None else None
        )
        value["linking_user_id"] = (
            str(self.linking_user_id) if self.linking_user_id is not None else None
        )
        value["created_at"] = self.created_at.isoformat()
        return value

    @classmethod
    def from_json_dict(cls, value: dict[str, Any]) -> "OAuthStatePayload":
        created_at = datetime.fromisoformat(value["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return cls(
            anonymous_user_id=(
                UUID(value["anonymous_user_id"])
                if value.get("anonymous_user_id")
                else None
            ),
            provider=value["provider"],
            return_url=value.get("return_url"),
            nonce=value["nonce"],
            created_at=created_at,
            linking_user_id=(
                UUID(value["linking_user_id"])
                if value.get("linking_user_id")
                else None
            ),
        )


class OAuthStateStore:
    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        ttl_seconds: int,
    ) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(cls, redis_url: str, *, ttl_seconds: int) -> "OAuthStateStore":
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        return cls(client, ttl_seconds=ttl_seconds)

    async def put(self, state: str, payload: OAuthStatePayload) -> bool:
        try:
            result = await self._redis.set(
                self._key(state),
                json.dumps(payload.to_json_dict(), separators=(",", ":")),
                ex=self._ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            raise OAuthStateBackendUnavailable(
                "OAuth state backend is unavailable."
            ) from exc
        return bool(result)

    async def consume(self, state: str) -> OAuthStatePayload | None:
        key = self._key(state)
        try:
            raw = await self._redis.execute_command("GETDEL", key)
        except ResponseError:
            raw = await self._consume_with_lua(key)
        except RedisError as exc:
            raise OAuthStateBackendUnavailable(
                "OAuth state backend is unavailable."
            ) from exc

        if raw is None:
            return None
        return OAuthStatePayload.from_json_dict(json.loads(raw))

    async def close(self) -> None:
        await self._redis.aclose()

    async def _consume_with_lua(self, key: str) -> str | None:
        try:
            return await self._redis.eval(GETDEL_FALLBACK_LUA, 1, key)
        except RedisError as exc:
            raise OAuthStateBackendUnavailable(
                "OAuth state backend is unavailable."
            ) from exc

    @staticmethod
    def _key(state: str) -> str:
        return f"{STATE_KEY_PREFIX}{state}"


@lru_cache
def get_oauth_state_store() -> OAuthStateStore:
    settings = get_settings()
    return OAuthStateStore.from_url(
        settings.oauth_state_redis_url or settings.redis_url,
        ttl_seconds=settings.auth_oauth_state_ttl_seconds,
    )


async def close_oauth_state_store() -> None:
    if get_oauth_state_store.cache_info().currsize == 0:
        return
    store = get_oauth_state_store()
    await store.close()
    get_oauth_state_store.cache_clear()
