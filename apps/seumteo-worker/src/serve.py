"""듀얼스택(IPv4+IPv6) 리스닝 소켓으로 uvicorn을 기동하는 런처.

Fly에서 이 워커는 두 경로로 트래픽을 받는다:
- fly-proxy(Flycast wake-up + [[http_service.checks]] 헬스체크)는 머신의 사설 IPv4로 접속한다.
- API의 실제 발급 잡은 6PN ``.internal:8080`` 주소(IPv6)로 직결된다.

uvicorn CLI는 단일 ``--host`` 바인드만 지원하는데, ``--host 0.0.0.0`` 은 .internal(v6)이,
``--host ::`` 는 Flycast/헬스체크(v4)가 connection refused 가 된다 — Linux 기본과 달리
asyncio ``create_server`` 가 AF_INET6 소켓에 IPV6_V6ONLY=1 을 명시 설정하기 때문이다.
따라서 IPV6_V6ONLY=0 소켓을 직접 만들어 uvicorn 에 넘긴다.
"""

from __future__ import annotations

import socket

import uvicorn

PORT = 8080


def create_dual_stack_socket(port: int = PORT) -> socket.socket:
    return socket.create_server(("", port), family=socket.AF_INET6, dualstack_ipv6=True)


def main() -> None:
    # 단일 프로세스(workers=1 상당) — 브라우저 1개를 프로세스 내에서 공유한다
    # (멀티프로세스면 Chromium 중복 기동 → OOM).
    config = uvicorn.Config("src.main:app", port=PORT)
    uvicorn.Server(config).run(sockets=[create_dual_stack_socket()])


if __name__ == "__main__":
    main()
