"""도로명주소 → 지번주소 보강 (세움터 지번 우선 발급, #jibun-first).

세움터 대장은 지번이 정본이라 지번으로 찾는 편이 도로명보다 잘 맞는다(도로명이 비었거나 표기가
다른 레코드가 실재). 사용자 입력은 도로명주소로 받되, 호출측이 지번을 넘기지 않았으면 도로명주소
API(business.juso.go.kr)로 같은 건물의 지번주소를 찾아 워커에 함께 보낸다.

best-effort 다 — 승인키가 없거나, 호출이 실패하거나, 도로명이 **정확히 같은** 결과가 없으면
None 을 돌려주고 워커는 종전처럼 도로명으로 찾는다. 도로명이 다른 결과를 받아 쓰면 남의 건물
지번으로 발급할 수 있으므로 근사 일치는 쓰지 않는다. 주소(PII)는 로그에 남기지 않는다.
"""

from __future__ import annotations

import re
import time

import httpx
import structlog

_log = structlog.get_logger(__name__)

_TIMEOUT_SECONDS = 5.0


def road_key(addr: str | None) -> str:
    """도로명주소 비교 키 — 괄호 참고항목('(신길동, 삼환아파트)')을 떼고 공백을 없앤다."""

    return re.sub(r"\s+", "", str(addr or "").split("(", 1)[0])


async def lookup_jibun_addr(
    road_addr: str,
    *,
    confm_key: str | None,
    api_url: str,
    http_client: httpx.AsyncClient | None = None,
) -> str | None:
    """``road_addr`` 와 도로명이 정확히 같은 건물의 지번주소(jibunAddr)를 찾는다."""

    key = road_key(road_addr)
    if not key or not confm_key:
        return None
    params = {
        "confmKey": confm_key,
        "currentPage": "1",
        "countPerPage": "10",
        "keyword": str(road_addr).split("(", 1)[0].strip(),
        "resultType": "json",
    }
    started = time.monotonic()

    def _done(outcome: str, **extra: object) -> None:
        _log.info(
            "seumteo.jibun_lookup",
            outcome=outcome,
            duration_ms=round((time.monotonic() - started) * 1000),
            **extra,
        )

    try:
        if http_client is not None:
            resp = await http_client.get(
                api_url, params=params, timeout=_TIMEOUT_SECONDS
            )
        else:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.get(api_url, params=params)
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        _done("error", error_type=type(exc).__name__)
        return None

    results = (body or {}).get("results") or {}
    error_code = (results.get("common") or {}).get("errorCode")
    if error_code not in (None, "0"):
        _done("api_error", juso_error_code=error_code)
        return None
    for juso in results.get("juso") or []:
        if road_key(juso.get("roadAddrPart1")) != key:
            continue
        jibun = str(juso.get("jibunAddr") or "").strip()
        if jibun:
            _done("ok")
            return jibun
    _done("no_match")
    return None


__all__ = ["lookup_jibun_addr", "road_key"]
