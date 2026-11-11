"""파트너(서버 간) 건축물대장 발급 잡 (ADR-0012).

사내 업무 시스템 "워크"가 의뢰 생성 시 전유부+표제부를 백그라운드로 발급받기 위한
제출/폴링 잡이다. 우리집 체크(``services.home_check``)와 같은 세움터 워커·서킷브레이커를
쓰지만 다음이 다르다.

- **DB·Supabase Storage 에 아무것도 쓰지 않는다.** 잡 상태와 결과(PDF base64 포함)는
  Redis 에 TTL 로만 두고, 호출자가 받아 간 뒤 DELETE 로 즉시 지우거나 TTL 로 사라진다.
- **구조화 추출을 하지 않는다.** 소유자·세대수 해석은 호출자가 PDF 로 직접 한다
  (ADR-0008 §2.3 의 PII 비구조화 정책 유지). 여기서는 발급일·위반 여부·문서번호만 중계한다.
- needs_input 재개(resume)를 구현하지 않는다 — 호출자가 주소를 고쳐 새로 제출한다.

개인정보: 주소·동·호·PDF 는 로그에 남기지 않는다(잡 ID·종류·결과 분류만 기록).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any, Literal

from redis.exceptions import RedisError

from ..config import get_settings
from ..logging import get_logger
from . import home_check as home_check_service
from .codef import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefAuthError,
    CodefCircuitOpen,
    CodefError,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    ExclusivePartResult,
)

logger = get_logger("zippin.partner_building_register")

RegisterKind = Literal["exclusive", "heading"]
JobStatus = Literal["queued", "running", "done"]

JOB_KEY_PREFIX = "partner:bldg:job:"
IDEM_KEY_PREFIX = "partner:bldg:idem:"
# queued/running 표식 — 처리하던 프로세스가 죽으면 잡이 스스로 사라져 GET 이 404 가 된다.
PENDING_TTL_SECONDS = 15 * 60
# 완료 결과(PDF base64 포함) 보관 — 호출자가 DELETE 로 ack 하지 않아도 이 뒤에는 없다.
RESULT_TTL_SECONDS = 30 * 60

_SEUMTEO_DISABLED_MESSAGE = "세움터 연동이 꺼져 있습니다"
_UPSTREAM_MESSAGE = "건축물대장 발급에 실패했습니다."
_HEADING_FAILED_MESSAGE = "표제부 발급에 실패했습니다."
_PDF_MISSING_MESSAGE = "발급 결과에 PDF 원본이 없습니다."


class PartnerJobStoreUnavailable(Exception):
    """잡 저장소(Redis) 장애 — 라우터가 503 으로 바꾼다."""


# ---------------------------------------------------------------------------
# 저장소 — Redis(운영) / 프로세스 내 dict(테스트·로컬 폴백)
# ---------------------------------------------------------------------------
class _RedisStore:
    def __init__(self, client: Any) -> None:
        self._redis = client

    async def set(
        self, key: str, value: str, ttl: int, *, nx: bool = False, xx: bool = False
    ) -> bool:
        try:
            return bool(await self._redis.set(key, value, ex=ttl, nx=nx, xx=xx))
        except RedisError as exc:
            raise PartnerJobStoreUnavailable() from exc

    async def get(self, key: str) -> str | None:
        try:
            raw = await self._redis.get(key)
        except RedisError as exc:
            raise PartnerJobStoreUnavailable() from exc
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self._redis.delete(*keys)
        except RedisError as exc:
            raise PartnerJobStoreUnavailable() from exc


class _MemoryStore:
    """Redis 와 같은 TTL 의미를 갖는 프로세스 내 저장소.

    gunicorn 워커 프로세스 간에 공유되지 않으므로 **테스트·로컬 전용**이다. 운영(프로세스
    2개)에서 쓰면 제출을 받은 프로세스와 폴링을 받은 프로세스가 달라 404 가 난다.
    """

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, str]] = {}

    def _live(self, key: str) -> str | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item[0] <= time.monotonic():
            self._items.pop(key, None)
            return None
        return item[1]

    async def set(
        self, key: str, value: str, ttl: int, *, nx: bool = False, xx: bool = False
    ) -> bool:
        exists = self._live(key) is not None
        if (nx and exists) or (xx and not exists):
            return False
        self._items[key] = (time.monotonic() + ttl, value)
        return True

    async def get(self, key: str) -> str | None:
        return self._live(key)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._items.pop(key, None)


_memory_store: _MemoryStore | None = None


def _get_store() -> _RedisStore | _MemoryStore:
    """잡 저장소. Redis URL 이 없거나 TEST_MODE 면 프로세스 내 dict 로 폴백한다.

    Redis 는 우리집 체크와 같은 클라이언트(``home_check._get_codef_redis`` —
    ``CODEF_TOKEN_REDIS_URL`` 또는 ``REDIS_URL``)를 재사용한다.
    """

    global _memory_store
    settings = get_settings()
    url = settings.codef_token_redis_url or settings.redis_url
    if settings.test_mode or not (url or "").strip():
        if _memory_store is None:
            _memory_store = _MemoryStore()
            logger.warning("partner_building_register_memory_store")
        return _memory_store
    return _RedisStore(home_check_service._get_codef_redis())


def _job_key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


def _idem_key(idem_hash: str) -> str:
    return f"{IDEM_KEY_PREFIX}{idem_hash}"


def _dump(job: dict[str, Any]) -> str:
    return json.dumps(job, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 제출 / 조회 / 삭제
# ---------------------------------------------------------------------------
async def submit_job(
    *, idempotency_key: str, kinds: list[RegisterKind]
) -> tuple[dict[str, Any], bool]:
    """잡을 만들거나, 같은 Idempotency-Key 의 기존 잡을 돌려준다.

    반환 ``(job, created)`` — ``created`` 가 False 면 발급을 다시 시작하지 않는다.
    """

    store = _get_store()
    idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    idem_key = _idem_key(idem_hash)

    job_id = secrets.token_urlsafe(24)
    job: dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "kinds": list(kinds),
        "idem": idem_hash,
    }
    # 잡을 먼저 쓰고 멱등 키를 NX 로 잡는다 — 키를 본 쪽은 항상 잡을 읽을 수 있다.
    await store.set(_job_key(job_id), _dump(job), PENDING_TTL_SECONDS)
    if await store.set(idem_key, job_id, PENDING_TTL_SECONDS, nx=True):
        return job, True

    existing_id = await store.get(idem_key)
    existing = await get_job(existing_id) if existing_id else None
    if existing is not None:
        await store.delete(_job_key(job_id))
        return existing, False
    # 멱등 키만 남고 잡이 사라진 경우(삭제·만료) — 새 잡으로 갈아 끼운다.
    await store.set(idem_key, job_id, PENDING_TTL_SECONDS)
    return job, True


async def get_job(job_id: str) -> dict[str, Any] | None:
    raw = await _get_store().get(_job_key(job_id))
    if raw is None:
        return None
    try:
        job = json.loads(raw)
    except ValueError:
        return None
    return job if isinstance(job, dict) else None


async def delete_job(job_id: str) -> None:
    """잡과 결과(PDF)를 즉시 지운다. 이미 없어도 조용히 끝난다."""

    store = _get_store()
    job = await get_job(job_id)
    keys = [_job_key(job_id)]
    if job is not None and isinstance(job.get("idem"), str):
        keys.append(_idem_key(job["idem"]))
    await store.delete(*keys)


# ---------------------------------------------------------------------------
# 백그라운드 발급
# ---------------------------------------------------------------------------
def _new_client() -> Any:
    """세움터 워커 클라이언트 — 우리집 체크와 같은 Redis(서킷브레이커 공유)를 주입한다.

    테스트는 ``src.services.partner_building_register._new_client`` 를 monkeypatch 한다.
    """

    from .seumteo import SeumteoBuildingRegisterClient

    return SeumteoBuildingRegisterClient(
        get_settings(), redis_client=home_check_service._get_codef_redis()
    )


def _failure(
    category: str,
    message: str,
    *,
    field: str | None = None,
    options: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "category": category,
        "message": message,
        "field": field,
        "options": options,
    }


def _failure_from_exception(exc: BaseException) -> dict[str, Any]:
    message = getattr(exc, "message", "") or _UPSTREAM_MESSAGE
    if isinstance(exc, CodefNeedsUserInput):
        return _failure(
            "needs_input",
            message,
            field=exc.field,
            options=exc.options,
        )
    if isinstance(exc, CodefAuthError):
        return _failure("auth", message)
    if isinstance(exc, CodefNotFound):
        return _failure("not_found", message)
    if isinstance(exc, CodefInvalidInput):
        return _failure("invalid", message)
    if isinstance(exc, CodefCircuitOpen):
        return _failure("busy", message)
    # CodefUpstreamError·그 밖의 CodefError 는 메시지를 그대로, 예상 밖 예외는 내부 문구가
    # 새지 않게 고정 문구로 낸다.
    if isinstance(exc, CodefError):
        return _failure("upstream", message)
    return _failure("upstream", _UPSTREAM_MESSAGE)


def _success(
    kind: RegisterKind, result: ExclusivePartResult | BuildingHeadingResult
) -> dict[str, Any]:
    if not result.original_pdf_base64:
        return _failure("upstream", _PDF_MISSING_MESSAGE)
    return {
        "ok": True,
        "register_kind": kind,
        "issue_date": result.issue_date,
        "violation_status": result.violation_status,
        "res_doc_no": result.res_doc_no,
        "pdf_base64": result.original_pdf_base64,
    }


async def _issue(
    query: BuildingRegisterQuery, kinds: list[RegisterKind]
) -> dict[str, dict[str, Any]]:
    if not get_settings().seumteo_enabled:
        return {k: _failure("upstream", _SEUMTEO_DISABLED_MESSAGE) for k in kinds}
    try:
        client = _new_client()
        if "exclusive" in kinds and "heading" in kinds:
            # fetch_bundle 은 전유부 실패를 예외로, 표제부 실패를 플래그로 알린다.
            exclusive, heading, heading_error = await client.fetch_bundle(query)
            return {
                "exclusive": _success("exclusive", exclusive),
                "heading": (
                    _success("heading", heading)
                    if heading is not None and not heading_error
                    else _failure("upstream", _HEADING_FAILED_MESSAGE)
                ),
            }
        if "exclusive" in kinds:
            return {
                "exclusive": _success(
                    "exclusive", await client.fetch_exclusive_part(query)
                )
            }
        return {
            "heading": _success("heading", await client.fetch_building_heading(query))
        }
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 잡은 실패 봉투로 끝나야 한다.
        envelope = _failure_from_exception(exc)
        logger.info(
            "partner_building_register_failed",
            error_type=type(exc).__name__,
            category=envelope["category"],
        )
        return {k: dict(envelope) for k in kinds}


async def run_job(
    job_id: str,
    *,
    road_addr: str,
    jibun_addr: str | None,
    dong: str,
    ho: str,
    kinds: list[RegisterKind],
) -> None:
    """잡 1건을 처리해 결과를 저장한다. 예외를 밖으로 내지 않는다."""

    started = time.monotonic()
    try:
        store = _get_store()
        job = await get_job(job_id)
        if job is None:
            return
        job["status"] = "running"
        # XX — 그 사이 DELETE 된 잡을 되살리지 않는다.
        if not await store.set(
            _job_key(job_id), _dump(job), PENDING_TTL_SECONDS, xx=True
        ):
            return

        query = BuildingRegisterQuery(
            road_addr=road_addr, dong=dong, ho=ho, jibun_addr=jibun_addr
        )
        results = await _issue(query, kinds)

        job["status"] = "done"
        job["results"] = results
        stored = await store.set(
            _job_key(job_id), _dump(job), RESULT_TTL_SECONDS, xx=True
        )
        if stored and isinstance(job.get("idem"), str):
            await store.set(_idem_key(job["idem"]), job_id, RESULT_TTL_SECONDS, xx=True)
        logger.info(
            "partner_building_register_done",
            job_id=job_id,
            kinds=kinds,
            outcome={
                k: ("ok" if v.get("ok") else v.get("category"))
                for k, v in results.items()
            },
            stored=stored,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
    except PartnerJobStoreUnavailable:
        logger.warning("partner_building_register_store_unavailable", job_id=job_id)
    except Exception as exc:  # noqa: BLE001 — 백그라운드 태스크는 조용히 끝난다.
        logger.warning(
            "partner_building_register_unexpected",
            job_id=job_id,
            error_type=type(exc).__name__,
        )


__all__ = [
    "PENDING_TTL_SECONDS",
    "RESULT_TTL_SECONDS",
    "PartnerJobStoreUnavailable",
    "delete_job",
    "get_job",
    "run_job",
    "submit_job",
]
