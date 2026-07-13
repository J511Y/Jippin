"""Worker가 Fly 6PN(.internal) 잡 요청을 수신할 수 있는지에 대한 컨테이너 회귀 가드."""

from __future__ import annotations

from pathlib import Path
import unittest


class ContainerListenerTest(unittest.TestCase):
    def test_uvicorn_binds_dual_stack_listener_for_internal_job_requests(self) -> None:
        dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
        contents = dockerfile.read_text(encoding="utf-8")

        self.assertIn('"--host", "::"', contents)
        self.assertNotIn('"--host", "0.0.0.0"', contents)
