"""HF 워밍업 스로틀/게이트 테스트 — CMP-DIRECT.

maybe_warm_segmentation 이 (1) 엔드포인트 미설정 시 스킵, (2) 스로틀 창 안에서 1회만
fire, (3) 실제 핑은 fire-and-forget(요청 핸들러 비블로킹)인지 검증한다. LLM/네트워크
미사용 — _fire 를 모킹한다.
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
    monkeypatch.setattr(warmup, "_last_warm_monotonic", 0.0)
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
    monkeypatch.setattr(warmup, "_last_warm_monotonic", 0.0)

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
