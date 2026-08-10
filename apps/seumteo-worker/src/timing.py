"""PII 없는 워커 단계별 타이밍 로그 도우미.

주소·동·호·접수번호는 절대 넣지 않고, 무작위 job id 와 고정된 stage 이름만 남긴다.
ContextVar 를 써서 flow/clip 깊은 호출도 같은 job id 로 묶는다.
"""

from __future__ import annotations

import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_job_id: ContextVar[str | None] = ContextVar("seumteo_worker_job_id", default=None)


def new_job_id(candidate: str | None = None) -> str:
    """API가 보낸 16자리 hex trace만 수용하고, 나머지는 새 ID로 교체한다."""

    value = str(candidate or "").strip().lower()
    if len(value) == 16 and all(ch in "0123456789abcdef" for ch in value):
        return value
    return secrets.token_hex(8)


@contextmanager
def bind_job(job_id: str) -> Iterator[None]:
    token = _job_id.set(job_id)
    try:
        yield
    finally:
        _job_id.reset(token)


def log_stage(logger: Any, stage: str, started: float, **fields: Any) -> None:
    """성공 단계의 monotonic 경과시간을 기록한다."""

    logger.info(
        "job.stage",
        worker_job_id=_job_id.get(),
        stage=stage,
        duration_ms=round((time.monotonic() - started) * 1000),
        **fields,
    )


@contextmanager
def timed_stage(logger: Any, stage: str, **fields: Any) -> Iterator[None]:
    """await 를 포함한 블록의 성공/실패 시간을 모두 기록한다."""

    started = time.monotonic()
    try:
        yield
    except BaseException as exc:
        logger.info(
            "job.stage",
            worker_job_id=_job_id.get(),
            stage=stage,
            outcome="error",
            error_type=type(exc).__name__,
            duration_ms=round((time.monotonic() - started) * 1000),
            **fields,
        )
        raise
    else:
        log_stage(logger, stage, started, outcome="ok", **fields)
