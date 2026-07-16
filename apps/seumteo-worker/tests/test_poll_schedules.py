"""폴링 백오프 스케줄 회귀 — 빠른 상류 조기 완료 + 느린 상류 총예산 보존.

고정 간격 폴을 백오프로 바꿀 때의 계약은 두 가지다: ① 총 대기 예산이 기존보다
줄지 않는다(느린 정부 서버에서 조기 실패 금지), ② 조건이 이미 충족돼 있으면
첫 간격 수준에서 끝난다(빠른 상류에서 잡 시간 단축).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src import clip
from src.flow import (
    _R03_POLL_WAITS_MS,
    _RECP_POLL_WAITS_MS,
    FlowError,
    SeumteoFlow,
)
from src.models import BuildingRegisterRequest


class _RecordingPage:
    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class _FakeFrame:
    """_clipdata_total 이 순회하는 프레임 흉내 — evaluate 가 시퀀스를 소진한다."""

    def __init__(self, totals: list[int]) -> None:
        self._totals = totals

    async def evaluate(self, _js: str) -> int:
        if len(self._totals) > 1:
            return self._totals.pop(0)
        return self._totals[0]


class _FakePopup(_RecordingPage):
    def __init__(self, totals: list[int]) -> None:
        super().__init__()
        self.frames = [_FakeFrame(totals)]


class PollBudgetTest(unittest.TestCase):
    def test_recp_schedule_keeps_legacy_budget(self) -> None:
        # 기존: 4회 조회, 사이 대기 3×1500ms.
        self.assertGreaterEqual(sum(_RECP_POLL_WAITS_MS), 3 * 1500)
        self.assertGreaterEqual(len(_RECP_POLL_WAITS_MS) + 1, 4)

    def test_r03_schedule_keeps_legacy_budget(self) -> None:
        # 기존: 6회 조회, 각 실패 후 1500ms 대기.
        self.assertGreaterEqual(sum(_R03_POLL_WAITS_MS), 6 * 1500)
        self.assertGreaterEqual(len(_R03_POLL_WAITS_MS) + 1, 6)

    def test_pdf_ready_schedule_keeps_legacy_budget(self) -> None:
        # 기존: 20회 폴 × 500ms.
        self.assertGreaterEqual(sum(clip._PDF_READY_WAITS_MS), 20 * 500)

    def test_backoff_starts_short(self) -> None:
        # 백오프의 목적 — 첫 간격이 기존 균등 간격보다 짧아야 빠른 상류가 이득을 본다.
        self.assertLess(_RECP_POLL_WAITS_MS[0], 1500)
        self.assertLess(_R03_POLL_WAITS_MS[0], 1500)
        self.assertLess(clip._PDF_READY_WAITS_MS[0], 500)


class RecpPollScheduleTest(unittest.IsolatedAsyncioTestCase):
    async def test_exhausts_backoff_schedule_before_failing(self) -> None:
        flow = object.__new__(SeumteoFlow)
        flow._s = SimpleNamespace(eais_base_url="https://www.eais.go.kr")
        flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [],
                "caisMessage": {"resultCode": "S00000"},
            }
        )
        req = BuildingRegisterRequest(
            road_addr="대구광역시 달서구 달서대로 67",
            dong="105동",
            ho="2001호",
            register_kind="exclusive",
        )
        page = _RecordingPage()

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await flow._find_recp_no(page, req, {"loc": {}}, set())

        # 스케줄 그대로 대기하고(마지막 조회 뒤 대기 없음), 조회 횟수 = 스케줄+1.
        self.assertEqual(page.waits, list(_RECP_POLL_WAITS_MS))
        self.assertEqual(flow._post.await_count, len(_RECP_POLL_WAITS_MS) + 1)


class ClipdataStableWaitTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_after_first_stable_sample(self) -> None:
        popup = _FakePopup(totals=[100, 100])

        await clip._wait_clipdata_stable(popup, cap_ms=1800)

        self.assertEqual(popup.waits, [150])

    async def test_waits_full_cap_when_no_data(self) -> None:
        # 데이터가 전혀 없으면(캔버스 전용 등) 기존 고정 sleep 과 동일하게 cap 을 소진.
        popup = _FakePopup(totals=[0])

        await clip._wait_clipdata_stable(popup, cap_ms=50, interval_ms=10)

        self.assertGreaterEqual(len(popup.waits), 1)

    async def test_keeps_waiting_while_data_grows(self) -> None:
        popup = _FakePopup(totals=[100, 200, 300, 300])

        await clip._wait_clipdata_stable(popup, cap_ms=1800)

        self.assertEqual(popup.waits, [150, 150, 150])


if __name__ == "__main__":
    unittest.main()
