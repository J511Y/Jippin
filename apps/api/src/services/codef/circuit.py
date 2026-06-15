"""단일 세움터 계정 보호 서킷브레이커 (ADR-0008 §2.2).

자격증명/계정잠금류 오류가 윈도우 내 임계치 이상 누적되면 회로를 open 해 추가 호출을
막는다 — 단일 세움터 계정이 반복 실패로 영구 잠기는 것을 방지한다. 상태는 Redis 에
공유(다중 워커 일관)하되, Redis 비가용 시 in-process 카운터로 폴백한다.

브레이커는 "자격증명/계정잠금" 오류(``CodefAuthError`` 류)만 카운트한다. 상류 점검·
타임아웃(``CodefUpstreamError``)은 계정 문제가 아니므로 카운트하지 않는다.
"""

from __future__ import annotations

import time

import redis.asyncio as redis
from redis.exceptions import RedisError

from .types import CodefCircuitOpen

_FAIL_COUNT_KEY = "codef:breaker:failcount"
_OPEN_UNTIL_KEY = "codef:breaker:open_until"


class CodefCircuitBreaker:
    """실패 카운트 + open 상태를 관리한다.

    ``redis_client`` None 이면 in-process 폴백. 윈도우는 Redis TTL 로 근사한다
    (카운트 키에 window TTL 을 걸어 자연 감쇠).
    """

    def __init__(
        self,
        *,
        error_threshold: int,
        window_seconds: int,
        open_seconds: int,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._threshold = max(1, error_threshold)
        self._window = max(1, window_seconds)
        self._open_seconds = max(1, open_seconds)
        self._redis = redis_client
        # in-process 폴백 상태.
        self._local_count = 0
        self._local_window_start = 0.0
        self._local_open_until = 0.0

    async def ensure_closed(self) -> None:
        """회로가 open 이면 ``CodefCircuitOpen`` 을 발생시킨다(호출 전 가드)."""

        open_until = await self._get_open_until()
        if open_until > time.time():
            raise CodefCircuitOpen(
                "CODEF 연동이 일시 차단되었습니다. 잠시 후 다시 시도해 주세요."
            )

    async def record_success(self) -> None:
        """성공 시 실패 카운트를 리셋한다."""

        if self._redis is not None:
            try:
                await self._redis.delete(_FAIL_COUNT_KEY)
                return
            except RedisError:
                pass
        self._local_count = 0
        self._local_window_start = 0.0

    async def record_auth_failure(self) -> None:
        """자격증명/계정잠금 오류 1건을 카운트하고, 임계 도달 시 회로를 open."""

        count = await self._increment()
        if count >= self._threshold:
            await self._open()

    async def _increment(self) -> int:
        if self._redis is not None:
            try:
                count = await self._redis.incr(_FAIL_COUNT_KEY)
                if count == 1:
                    await self._redis.expire(_FAIL_COUNT_KEY, self._window)
                return int(count)
            except RedisError:
                pass
        now = time.time()
        if now - self._local_window_start > self._window:
            self._local_window_start = now
            self._local_count = 0
        self._local_count += 1
        return self._local_count

    async def _open(self) -> None:
        open_until = time.time() + self._open_seconds
        if self._redis is not None:
            try:
                await self._redis.set(
                    _OPEN_UNTIL_KEY, str(open_until), ex=self._open_seconds
                )
                return
            except RedisError:
                pass
        self._local_open_until = open_until

    async def _get_open_until(self) -> float:
        if self._redis is not None:
            try:
                raw = await self._redis.get(_OPEN_UNTIL_KEY)
            except RedisError:
                raw = None
            if raw is not None:
                value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                try:
                    return float(value)
                except ValueError:
                    return 0.0
            # Redis 가용하지만 키 없음 → 닫힘.
            if self._redis is not None:
                return 0.0
        return self._local_open_until
