"""HF 세그멘테이션 엔드포인트 사전 워밍업 — 콜드스타트 체감 제거(CMP-DIRECT).

엔드포인트는 scale-to-zero(15분)라 유휴 후 첫 도면 분석이 수 분 걸린다. 사용자가
``/sessions/*`` 에 진입하면(=곧 도면을 올릴 가능성) 미리 replica 를 깨워 둔다 — 분석
시점엔 이미 warm 이도록. 어떤 실패(503 스케일업/타임아웃)도 무시한다: 목적은 응답이
아니라 스케일업 트리거 + idle 타이머 리셋뿐이다(요청 한 번이 15분 타이머를 리셋한다).

per-process 스로틀로 과도한 핑을 막는다(여러 워커는 각자 스로틀 — 약간의 중복 워밍은
무해). 토큰은 백엔드에서만 실어 보낸다(브라우저 비노출).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import httpx

from ..logging import get_logger

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger("zippin.agent.warmup")

# 워밍업 핑 최소 간격(초). 15분 idle 타이머보다 충분히 짧게 잡아 활성 세션 동안 warm
# 유지하되, 페이지 진입마다 HF 를 때리지 않게 스로틀한다.
_WARMUP_THROTTLE_SECONDS = 120.0

# 1x1 투명 PNG (data URL) — 스케일업 트리거용 최소 입력. 이미 warm 이면 사소한 추론만.
_TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

_last_warm_monotonic: float = 0.0
# 백그라운드 태스크가 GC 되지 않도록 참조를 잡아 둔다.
_bg_tasks: set[asyncio.Task[None]] = set()


async def _fire(endpoint: str, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = {
        "inputs": _TINY_PNG_DATA_URL,
        # 워밍업은 디테일 불필요 — 작은 해상도로 비용 최소화.
        "parameters": {"max_inference_side": 256},
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(endpoint, json=body, headers=headers)
        log.info("hf_warmup_ping", status=resp.status_code)
    except Exception as exc:  # noqa: BLE001 - 503/타임아웃 등 모두 무시(스케일업만 목적)
        log.info("hf_warmup_ping_ignored", error_type=type(exc).__name__)


def maybe_warm_segmentation(settings: "Settings") -> bool:
    """엔드포인트가 설정돼 있고 스로틀 창이 지났으면 fire-and-forget 워밍업을 띄운다.

    True=핑을 띄움, False=미설정이거나 스로틀로 스킵. 요청 핸들러를 절대 블로킹하지
    않는다(asyncio 백그라운드 태스크). 이벤트 루프가 없으면(동기 컨텍스트) 조용히 스킵.
    """

    global _last_warm_monotonic
    endpoint = settings.hf_segmentation_endpoint_url
    if not endpoint:
        return False
    now = time.monotonic()
    if now - _last_warm_monotonic < _WARMUP_THROTTLE_SECONDS:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _last_warm_monotonic = now
    task = loop.create_task(_fire(endpoint, settings.hf_segmentation_token))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return True
