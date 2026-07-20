from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from src.browser import LoginError
from src.main import app, healthz, readyz


class _RecoveringManager:
    def __init__(self) -> None:
        self.healthy = False
        self.restart_attempts = 0

    def is_healthy(self) -> bool:
        return self.healthy

    async def ensure_logged_in(self) -> None:
        self.restart_attempts += 1
        self.healthy = True

    async def prepare_authenticated(self) -> None:
        await self.ensure_logged_in()


class _BrokenManager(_RecoveringManager):
    async def ensure_logged_in(self) -> None:
        self.restart_attempts += 1
        raise RuntimeError("browser restart failed")


class _LoginFailureManager(_RecoveringManager):
    async def ensure_logged_in(self) -> None:
        self.restart_attempts += 1
        raise LoginError("login failed")

    async def prepare_authenticated(self) -> None:
        await self.ensure_logged_in()


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

    async def test_readyz_requires_worker_token(self) -> None:
        app.state.mgr = _RecoveringManager()
        settings = SimpleNamespace(seumteo_worker_token="secret")

        with patch("src.main.get_settings", return_value=settings):
            with self.assertRaises(HTTPException) as raised:
                await readyz(authorization=None)

        self.assertEqual(raised.exception.status_code, 401)

    async def test_readyz_logs_in_before_reporting_authenticated(self) -> None:
        mgr = _RecoveringManager()
        app.state.mgr = mgr
        settings = SimpleNamespace(seumteo_worker_token="secret")

        with patch("src.main.get_settings", return_value=settings):
            response = await readyz(authorization="Bearer secret")

        self.assertEqual(response, {"ok": True, "browser": True, "authenticated": True})
        self.assertEqual(mgr.restart_attempts, 1)

    async def test_readyz_returns_503_when_login_fails(self) -> None:
        mgr = _LoginFailureManager()
        app.state.mgr = mgr
        settings = SimpleNamespace(seumteo_worker_token=None)

        with patch("src.main.get_settings", return_value=settings):
            response = await readyz(authorization=None)

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(mgr.restart_attempts, 1)
