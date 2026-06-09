"""휴대폰 OTP(문자 인증) 저장·검증 서비스 (CMP-DIRECT).

인증번호와 인증 성공 토큰을 Redis 에 TTL 로 저장한다(OAuth state store 와 동일한 Redis
인프라를 공유). 일반적인 전화번호 인증 프로세스를 따른다:

  1. ``send_code(phone)`` — 재발송 쿨다운/일일 한도 확인 → 6자리 코드 생성/저장 → SMS 발송.
  2. ``verify_code(phone, code)`` — 코드 검증(시도 횟수 제한) → 성공 시 단기 ``phone_token`` 발급.
  3. ``consume_token(token)`` — 가입/아이디찾기/비번재설정 단계에서 1회용으로 소비, 검증된
     휴대폰 번호를 반환한다.

코드/토큰은 모두 Redis 에만 두며 DB 마이그레이션이 필요 없다.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from functools import lru_cache

import redis.asyncio as redis
from redis.exceptions import RedisError

from ..config import get_settings
from ..errors import ZippinException
from ..schemas.leads import normalize_korean_phone

_OTP_KEY = "phone:otp:code:"
_OTP_ATTEMPTS_KEY = "phone:otp:attempts:"
_COOLDOWN_KEY = "phone:otp:cooldown:"
_DAILY_KEY = "phone:otp:daily:"
_TOKEN_KEY = "phone:otp:token:"
_SIGNUP_LOCK_KEY = "phone:signup:lock:"
_IP_RATE_KEY = "phone:otp:ip:"
_GLOBAL_RATE_KEY = "phone:otp:global"
_DAILY_TTL_SECONDS = 86_400
_HOURLY_TTL_SECONDS = 3_600
_SIGNUP_LOCK_TTL_SECONDS = 30
# 토큰이 일치할 때만 삭제하는 compare-and-delete (자기 락만 해제).
_RELEASE_LOCK_LUA = (
    'if redis.call("GET", KEYS[1]) == ARGV[1] '
    'then return redis.call("DEL", KEYS[1]) else return 0 end'
)


def _backend_unavailable(exc: Exception) -> ZippinException:  # noqa: ARG001
    return ZippinException(
        "문자 인증 백엔드를 사용할 수 없습니다.",
        code="PHONE_VERIFICATION_BACKEND_UNAVAILABLE",
        http_status=503,
    )


@dataclass(frozen=True)
class SendCodeResult:
    expires_in_seconds: int


class PhoneVerificationStore:
    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        code_length: int,
        ttl_seconds: int,
        token_ttl_seconds: int,
        max_attempts: int,
        resend_cooldown_seconds: int,
        daily_send_limit: int,
        ip_hourly_limit: int,
        global_hourly_limit: int,
    ) -> None:
        self._redis = redis_client
        self._code_length = code_length
        self._ttl_seconds = ttl_seconds
        self._token_ttl_seconds = token_ttl_seconds
        self._max_attempts = max_attempts
        self._resend_cooldown_seconds = resend_cooldown_seconds
        self._daily_send_limit = daily_send_limit
        self._ip_hourly_limit = ip_hourly_limit
        self._global_hourly_limit = global_hourly_limit

    @classmethod
    def from_url(cls, redis_url: str, **kwargs: int) -> "PhoneVerificationStore":
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        return cls(client, **kwargs)

    def _generate_code(self) -> str:
        upper = 10**self._code_length
        return str(secrets.randbelow(upper)).zfill(self._code_length)

    async def _incr_hourly(self, key: str) -> int:
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, _HOURLY_TTL_SECONDS)
        return count

    async def rollback_send_rate(self, ip: str | None) -> None:
        """실제 발송이 실패했을 때 check_send_rate 가 올린 IP/글로벌 카운터를 되돌린다."""

        try:
            if ip:
                await self._redis.decr(f"{_IP_RATE_KEY}{ip}")
            await self._redis.decr(_GLOBAL_RATE_KEY)
        except RedisError:
            return

    async def check_send_rate(self, ip: str | None) -> None:
        """발송 전 호출. 번호가 아닌 IP/글로벌 시간당 한도로 번호 회전 남용을 막는다.

        ``reserve_send`` 는 휴대폰 번호 단위라 공격자가 번호를 바꿔가며 무제한 발송을
        유발할 수 있다(직접적 SMS 비용/스팸). IP·글로벌 한도를 먼저 적용한다.
        """

        try:
            if ip:
                ip_count = await self._incr_hourly(f"{_IP_RATE_KEY}{ip}")
                if ip_count > self._ip_hourly_limit:
                    raise ZippinException(
                        "잠시 후 다시 시도해 주세요. 요청이 너무 많습니다.",
                        code="PHONE_OTP_IP_LIMIT",
                        http_status=429,
                    )
            global_count = await self._incr_hourly(_GLOBAL_RATE_KEY)
            if global_count > self._global_hourly_limit:
                raise ZippinException(
                    "현재 인증 요청이 많아 잠시 후 다시 시도해 주세요.",
                    code="PHONE_OTP_GLOBAL_LIMIT",
                    http_status=429,
                )
        except RedisError as exc:
            raise _backend_unavailable(exc) from exc

    async def reserve_send(self, phone: str) -> str:
        """재발송 쿨다운/일일 한도를 확인하고 새 코드를 저장한 뒤 코드를 반환한다.

        실제 SMS 발송은 호출자(라우터)가 ``services.sms`` 로 수행한다 — 발송 실패 시
        본 함수의 저장 상태가 남아도 코드 자체는 무해하며 TTL 로 만료된다.
        """

        try:
            cooldown_active = not await self._redis.set(
                f"{_COOLDOWN_KEY}{phone}",
                "1",
                ex=self._resend_cooldown_seconds,
                nx=True,
            )
            if cooldown_active:
                raise ZippinException(
                    "잠시 후 다시 인증번호를 요청해 주세요.",
                    code="PHONE_OTP_RESEND_COOLDOWN",
                    http_status=429,
                )

            daily_count = await self._redis.incr(f"{_DAILY_KEY}{phone}")
            if daily_count == 1:
                await self._redis.expire(f"{_DAILY_KEY}{phone}", _DAILY_TTL_SECONDS)
            if daily_count > self._daily_send_limit:
                raise ZippinException(
                    "일일 인증 요청 한도를 초과했습니다. 내일 다시 시도해 주세요.",
                    code="PHONE_OTP_DAILY_LIMIT",
                    http_status=429,
                )

            code = self._generate_code()
            await self._redis.set(f"{_OTP_KEY}{phone}", code, ex=self._ttl_seconds)
            await self._redis.set(
                f"{_OTP_ATTEMPTS_KEY}{phone}", "0", ex=self._ttl_seconds
            )
        except RedisError as exc:
            raise _backend_unavailable(exc) from exc
        return code

    async def rollback_send(self, phone: str) -> None:
        """SMS 발송 실패 시 reserve_send 의 쿨다운/일일 카운트를 되돌린다.

        provider 장애로 코드가 전달되지 않았는데 쿨다운/일일 한도만 소진돼 번호가
        잠기는 회귀(P2)를 막는다. 베스트 에포트 — Redis 오류는 조용히 무시한다.
        """

        try:
            await self._redis.delete(f"{_COOLDOWN_KEY}{phone}")
            await self._redis.delete(f"{_OTP_KEY}{phone}")
            await self._redis.delete(f"{_OTP_ATTEMPTS_KEY}{phone}")
            remaining = await self._redis.decr(f"{_DAILY_KEY}{phone}")
            if remaining is not None and remaining < 0:
                await self._redis.delete(f"{_DAILY_KEY}{phone}")
        except RedisError:
            return

    async def acquire_signup_lock(self, phone: str) -> str | None:
        """가입 임계 구역(중복 확인 + 계정 생성) 직렬화용 짧은 락.

        소유자 토큰을 값으로 저장하고 획득 시 그 토큰을 반환한다(없으면 None). TTL 만료 후
        다른 요청이 잡은 락을 이 요청이 잘못 해제하지 못하도록 release 에서 토큰을 대조한다.
        """

        token = secrets.token_urlsafe(16)
        try:
            acquired = await self._redis.set(
                f"{_SIGNUP_LOCK_KEY}{phone}",
                token,
                ex=_SIGNUP_LOCK_TTL_SECONDS,
                nx=True,
            )
        except RedisError as exc:
            raise _backend_unavailable(exc) from exc
        return token if acquired else None

    async def release_signup_lock(self, phone: str, token: str) -> None:
        """자신이 보유한 락(토큰 일치)일 때만 삭제한다(compare-and-delete)."""

        try:
            await self._redis.eval(
                _RELEASE_LOCK_LUA, 1, f"{_SIGNUP_LOCK_KEY}{phone}", token
            )
        except RedisError:
            return

    async def verify_code(self, phone: str, code: str) -> str:
        """코드를 검증하고 성공 시 단기 ``phone_token`` 을 발급한다."""

        try:
            stored = await self._redis.get(f"{_OTP_KEY}{phone}")
            if stored is None:
                raise ZippinException(
                    "인증번호가 만료되었거나 발급되지 않았습니다.",
                    code="PHONE_OTP_NOT_FOUND",
                    http_status=400,
                )

            attempts = await self._redis.incr(f"{_OTP_ATTEMPTS_KEY}{phone}")
            if attempts > self._max_attempts:
                await self._redis.delete(f"{_OTP_KEY}{phone}")
                await self._redis.delete(f"{_OTP_ATTEMPTS_KEY}{phone}")
                raise ZippinException(
                    "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해 주세요.",
                    code="PHONE_OTP_TOO_MANY_ATTEMPTS",
                    http_status=429,
                )

            if not secrets.compare_digest(stored, code):
                raise ZippinException(
                    "인증번호가 일치하지 않습니다.",
                    code="PHONE_OTP_MISMATCH",
                    http_status=400,
                )

            # 성공 — 코드/시도 카운트를 비우고 1회용 토큰을 발급한다.
            await self._redis.delete(f"{_OTP_KEY}{phone}")
            await self._redis.delete(f"{_OTP_ATTEMPTS_KEY}{phone}")
            token = secrets.token_urlsafe(32)
            await self._redis.set(
                f"{_TOKEN_KEY}{token}", phone, ex=self._token_ttl_seconds
            )
        except RedisError as exc:
            raise _backend_unavailable(exc) from exc
        return token

    async def consume_token(self, token: str) -> str | None:
        """1회용 토큰을 소비하고 검증된 휴대폰 번호를 반환한다(없으면 None)."""

        key = f"{_TOKEN_KEY}{token}"
        try:
            try:
                phone = await self._redis.execute_command("GETDEL", key)
            except RedisError:
                phone = await self._redis.get(key)
                if phone is not None:
                    await self._redis.delete(key)
        except RedisError as exc:
            raise _backend_unavailable(exc) from exc
        return phone

    async def close(self) -> None:
        await self._redis.aclose()


def assert_token_phone_match(token_phone: str | None, requested_phone: str) -> str:
    """consume_token 결과가 요청 휴대폰과 일치하는지 검증한다."""

    if token_phone is None or normalize_korean_phone(
        token_phone
    ) != normalize_korean_phone(requested_phone):
        raise ZippinException(
            "휴대폰 인증이 만료되었거나 일치하지 않습니다. 다시 인증해 주세요.",
            code="PHONE_TOKEN_INVALID",
            http_status=400,
        )
    return normalize_korean_phone(requested_phone)


@lru_cache
def get_phone_verification_store() -> PhoneVerificationStore:
    settings = get_settings()
    return PhoneVerificationStore.from_url(
        settings.oauth_state_redis_url or settings.redis_url,
        code_length=settings.phone_otp_code_length,
        ttl_seconds=settings.phone_otp_ttl_seconds,
        token_ttl_seconds=settings.phone_otp_token_ttl_seconds,
        max_attempts=settings.phone_otp_max_attempts,
        resend_cooldown_seconds=settings.phone_otp_resend_cooldown_seconds,
        daily_send_limit=settings.phone_otp_daily_send_limit,
        ip_hourly_limit=settings.phone_otp_ip_hourly_limit,
        global_hourly_limit=settings.phone_otp_global_hourly_limit,
    )


async def close_phone_verification_store() -> None:
    if get_phone_verification_store.cache_info().currsize == 0:
        return
    store = get_phone_verification_store()
    await store.close()
    get_phone_verification_store.cache_clear()
