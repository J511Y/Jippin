"""HF 세그멘테이션 엔드포인트 웨이크업 핑 — 콜드스타트 체감 제거(CMP-DIRECT).

엔드포인트는 GPU(nvidia-l4, 2026-08-26 전환) + scale-to-zero(15분)다: 15분간 요청이
없으면 잠들고, 깨어나는 데 약 26초 걸린다. 실측(모델 레포 docs/30_실험_기록/
2026-08-26_endpoint_L4_전환_지연_실측.md)으로 확인된 ``GET {URL}/health`` 의 동작:

- 잠든 상태면 **503 을 반환하며 스케일업이 시작**된다(요청 하나로 웨이크 트리거).
- 웜 상태면 200 이고 **idle 타이머(15분)가 리셋**된다 — 실추론 없이 핑만으로 세션
  동안 웜 유지가 가능하다(과거의 1x1 PNG 추론 핑을 대체).

호출 지점은 전부 **사전검토 세션 스코프**다 — 세션 생성(POST /sessions)·에이전트 런
시작/재개, 그리고 프론트(SessionChat)의 세션 진입 1회 + 세션 활성 동안 10분 간격
keep-alive(POST /sessions/agent/warmup). 깨어 있는 시간이 곧 GPU 과금 시간이므로 세션
밖에서는 핑을 보내지 않고, per-process 스로틀로 과도한 핑을 막는다(여러 워커는 각자
스로틀 — 약간의 중복 핑은 idle 타이머 리셋일 뿐이라 무해).

어떤 실패(503 스케일업/타임아웃/미설정)도 세션 흐름을 막지 않는다: 목적은 응답이
아니라 스케일업 트리거 + idle 타이머 리셋뿐이다. 토큰은 백엔드에서만 실어 보낸다
(브라우저 비노출).
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

# 워밍업 핑 최소 간격(초). 15분 idle 타이머·10분 keep-alive 간격보다 충분히 짧게 잡아
# 활성 세션 동안 warm 유지하되, 페이지 진입/런 시작마다 HF 를 때리지 않게 스로틀한다.
_WARMUP_THROTTLE_SECONDS = 120.0

# /health 핑 타임아웃(초). 잠든 상태의 503 도, 웜 상태의 200 도 즉시 돌아온다 —
# 이보다 오래 걸리면 네트워크 문제라 끊는다(fire-and-forget 이라 아무도 안 기다린다).
_PING_TIMEOUT_SECONDS = 15.0

# None = 아직 한 번도 워밍 안 함. 0.0 같은 숫자 기본값을 쓰면, 프로세스 부팅 직후
# time.monotonic() 이 throttle 창보다 작은 동안(예: 컨테이너 부팅 후 120s 이내) 첫 워밍이
# now - 0.0 < throttle 로 스로틀돼 **영영 안 뜨는** 버그가 된다(#warmup-fresh-boot).
_last_warm_monotonic: float | None = None
# 백그라운드 태스크가 GC 되지 않도록 참조를 잡아 둔다.
_bg_tasks: set[asyncio.Task[None]] = set()


async def _fire(endpoint: str, token: str | None) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # 추론 POST(base URL)와 달리 웨이크는 GET /health 로 충분하다(실측 1·2) — 실추론이
    # 없어 GPU 를 점유하지 않으면서 스케일업 트리거와 idle 타이머 리셋이 모두 된다.
    url = endpoint.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=_PING_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001 - 타임아웃/연결오류 모두 무시(스케일업만 목적)
        log.info("hf_warmup_ping_ignored", error_type=type(exc).__name__)
        return
    if resp.status_code == 503:
        # 잠들어 있었고 지금 스케일업이 시작됐다 — 약 26초 뒤 서빙 가능. 그 전에 도면이
        # 제출되면 추론 경로의 503 폴링(segmentation.segment_floorplan_impl)이 흡수한다.
        log.info("hf_warmup_ping", status=resp.status_code, state="waking")
    elif resp.status_code == 200:
        log.info("hf_warmup_ping", status=resp.status_code, state="warm")
    else:
        # 401(토큰)/404(URL) 등은 설정 문제 신호 — 워밍이 조용히 무력화되지 않게 경고.
        log.warning("hf_warmup_ping_unexpected", status=resp.status_code)


def maybe_warm_segmentation(settings: "Settings") -> bool:
    """엔드포인트가 설정돼 있고 스로틀 창이 지났으면 fire-and-forget 웨이크업 핑을 띄운다.

    True=핑을 띄움, False=미설정이거나 스로틀로 스킵. 세션 시작 핸들러 안에서 불리므로
    **어떤 예외도 밖으로 내보내지 않는다** — 핑 준비 실패가 세션 생성(201)/런 시작을
    막으면 안 된다. 요청 핸들러를 절대 블로킹하지 않는다(asyncio 백그라운드 태스크).
    이벤트 루프가 없으면(동기 컨텍스트) 조용히 스킵.
    """

    global _last_warm_monotonic
    try:
        endpoint = settings.hf_segmentation_endpoint_url
        if not endpoint:
            return False
        now = time.monotonic()
        if (
            _last_warm_monotonic is not None
            and now - _last_warm_monotonic < _WARMUP_THROTTLE_SECONDS
        ):
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
    except Exception:  # noqa: BLE001 - 웨이크업은 부가 기능 — 세션 흐름을 막지 않는다
        log.warning("hf_warmup_skip_failed", exc_info=True)
        return False
