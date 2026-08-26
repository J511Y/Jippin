"""HF 웨이크업 핑 스로틀/게이트/전송 계약 테스트 — CMP-DIRECT.

maybe_warm_segmentation 이 (1) 엔드포인트 미설정 시 스킵, (2) 스로틀 창 안에서 1회만
fire, (3) 실제 핑은 fire-and-forget(요청 핸들러 비블로킹), (4) 세션 시작 핸들러 안에서
불리므로 어떤 실패도 raise 하지 않는지 검증한다. _fire 는 추론 POST 가 아니라
``GET {base}/health`` 를 보낸다(2026-08-26 GPU 전환 실측 계약 — 503=웨이크 트리거,
200=웜+idle 리셋). LLM/네트워크 미사용 — _fire 또는 httpx 클라이언트를 모킹한다.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.agent import warmup


def _settings(url: str | None = "https://hf.example/seg") -> SimpleNamespace:
    return SimpleNamespace(
        hf_segmentation_endpoint_url=url, hf_segmentation_token="tok"
    )


async def test_skips_when_endpoint_unset(monkeypatch) -> None:
    monkeypatch.setattr(warmup, "_last_warm_monotonic", 0.0)
    assert warmup.maybe_warm_segmentation(_settings(url=None)) is False


async def test_warms_once_then_throttles(monkeypatch) -> None:
    monkeypatch.setattr(warmup, "_last_warm_monotonic", None)  # 아직 워밍 안 함
    fired: list[tuple[str, str | None]] = []

    async def fake_fire(endpoint: str, token: str | None) -> None:
        fired.append((endpoint, token))

    monkeypatch.setattr(warmup, "_fire", fake_fire)

    # 1회차: fire.
    assert warmup.maybe_warm_segmentation(_settings()) is True
    # 2회차(즉시): 스로틀로 스킵.
    assert warmup.maybe_warm_segmentation(_settings()) is False

    # 백그라운드 태스크가 실제로 떴는지 확인(드레인).
    await asyncio.sleep(0)
    pending = [t for t in warmup._bg_tasks]
    for t in pending:
        await t
    assert fired == [("https://hf.example/seg", "tok")]


async def test_throttle_window_expiry(monkeypatch) -> None:
    # 스로틀 창이 지나면 다시 fire 한다(monotonic 을 과거로 밀어 흉내).
    monkeypatch.setattr(warmup, "_last_warm_monotonic", None)  # 아직 워밍 안 함

    async def noop(endpoint: str, token: str | None) -> None:
        return None

    monkeypatch.setattr(warmup, "_fire", noop)
    assert warmup.maybe_warm_segmentation(_settings()) is True
    # 마지막 워밍 시각을 throttle+1 만큼 과거로 — 창 만료.
    monkeypatch.setattr(
        warmup,
        "_last_warm_monotonic",
        warmup._last_warm_monotonic - (warmup._WARMUP_THROTTLE_SECONDS + 1),
    )
    assert warmup.maybe_warm_segmentation(_settings()) is True
    await asyncio.sleep(0)
    for t in list(warmup._bg_tasks):
        await t


async def test_never_raises_when_settings_access_fails(monkeypatch) -> None:
    # 세션 생성/런 시작 핸들러 안에서 직접 불린다 — 핑 준비 단계의 어떤 실패도 세션
    # 흐름(201/SSE 시작)을 막으면 안 된다. raise 대신 False 로 degrade 한다.
    monkeypatch.setattr(warmup, "_last_warm_monotonic", None)

    class _BrokenSettings:
        @property
        def hf_segmentation_endpoint_url(self) -> str:
            raise RuntimeError("settings backend broke")

    assert warmup.maybe_warm_segmentation(_BrokenSettings()) is False


async def test_fire_sends_health_get_with_bearer(monkeypatch) -> None:
    # 웨이크는 추론 POST 가 아니라 GET {base}/health 다(실측): 실추론 없이 스케일업
    # 트리거(503)와 idle 타이머 리셋(200)이 모두 된다. 토큰은 Authorization 헤더로만
    # 나간다(백엔드 전용 — 브라우저 비노출 경로).
    calls: list[tuple[str, dict[str, str]]] = []
    statuses: list[int] = []
    monkeypatch.setattr(
        warmup.log, "info", lambda event, **kw: statuses.append(kw.get("status"))
    )

    class _Resp:
        status_code = 503

    class _Client:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str]) -> _Resp:
            calls.append((url, headers))
            return _Resp()

    monkeypatch.setattr(warmup.httpx, "AsyncClient", _Client)
    # 후행 슬래시가 있어도 /health 경로가 정확히 조립된다.
    await warmup._fire("https://hf.example/seg/", "tok")
    assert calls == [("https://hf.example/seg/health", {"Authorization": "Bearer tok"})]
    # 응답 코드를 로깅한다(503=웨이크 시작, 200=이미 웜) — 운영 검증 포인트.
    assert statuses == [503]
