from __future__ import annotations

import unittest

from fastapi.responses import JSONResponse

from src.main import app, healthz


class _RecoveringManager:
    def __init__(self) -> None:
        self.healthy = False
        self.restart_attempts = 0

    def is_healthy(self) -> bool:
        return self.healthy

    async def ensure_logged_in(self) -> None:
        self.restart_attempts += 1
        self.healthy = True


class _BrokenManager(_RecoveringManager):
    async def ensure_logged_in(self) -> None:
        self.restart_attempts += 1
        raise RuntimeError("browser restart failed")


class HealthzTest(unittest.IsolatedAsyncioTestCase):
    async def test_healthz_recovers_browser_before_reporting_ready(self) -> None:
        mgr = _RecoveringManager()
        app.state.mgr = mgr

        response = await healthz()

        self.assertEqual(response, {"ok": True, "browser": True})
        self.assertEqual(mgr.restart_attempts, 1)

    async def test_healthz_returns_503_when_browser_recovery_fails(self) -> None:
        mgr = _BrokenManager()
        app.state.mgr = mgr

        response = await healthz()

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(mgr.restart_attempts, 1)
