"""Flycast(IPv4)와 Fly 6PN .internal(IPv6) 요청을 모두 수신하는지에 대한 회귀 가드.

한쪽만 들으면: v4 미수신 → fly-proxy 헬스체크/Flycast wake-up 실패(warmup_timeout),
v6 미수신 → API의 .internal 잡 직결이 connection refused.
"""

from __future__ import annotations

import socket
import unittest
from pathlib import Path

from src.serve import create_dual_stack_socket


class ContainerListenerTest(unittest.TestCase):
    def test_dockerfile_launches_dual_stack_launcher(self) -> None:
        dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
        contents = dockerfile.read_text(encoding="utf-8")

        self.assertIn('CMD ["python", "-m", "src.serve"]', contents)
        # uvicorn 단일 --host 바인드는 v4/v6 중 한쪽이 반드시 refused 된다.
        self.assertNotIn('"--host"', contents)

    def test_socket_accepts_both_ipv4_and_ipv6_loopback(self) -> None:
        sock = create_dual_stack_socket(0)
        try:
            self.assertEqual(sock.family, socket.AF_INET6)
            self.assertEqual(
                sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY), 0
            )
            port = sock.getsockname()[1]
            for family, addr in (
                (socket.AF_INET, ("127.0.0.1", port)),
                (socket.AF_INET6, ("::1", port)),
            ):
                with socket.socket(family, socket.SOCK_STREAM) as client:
                    client.settimeout(5)
                    client.connect(addr)
        finally:
            sock.close()
