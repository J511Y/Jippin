"""평면도 세그멘테이션 도구(HuggingFace 엣지 엔드포인트) — 실패 처리 핵심.

모델은 STR 5클래스(door/window/wall_reinforced_concrete/wall_other/wall_unknown)
+ SPA 13 공간클래스를 낸다(floor-plan-model-train 정합). 엔드포인트는 아직 배포
전일 수 있으므로 **절대 uncaught raise 하지 않고** segmentation-result 계약 형태의
구조화 dict 를 반환한다 — 미배포/콜드스타트/타임아웃도 ok=false 로 표현된다.
에이전트는 ok=false 면 ASK_MORE 로 degrade, 반복 실패 시 HOLD_OR_HANDOFF 한다.
"""

from __future__ import annotations

import asyncio
import ipaddress
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ...logging import get_logger

if TYPE_CHECKING:
    from ...config import Settings

log = get_logger("zippin.agent.tools.segmentation")

SCHEMA_VERSION = "1.0.0"

# segmentation-result 계약의 라벨 enum(검증·요약용).
_KNOWN_LABELS: frozenset[str] = frozenset(
    {
        "door",
        "window",
        "wall_reinforced_concrete",
        "wall_other",
        "wall_unknown",
        "space_multipurpose",
        "space_elevator_hall",
        "space_stairwell",
        "space_living_room",
        "space_bedroom",
        "space_kitchen",
        "space_entrance",
        "space_balcony",
        "space_bathroom",
        "space_ac_room",
        "space_dress_room",
        "space_other",
        "space_elevator",
    }
)

# 콜드스타트(503) 재시도 대기 상한(초). Retry-After 가 더 커도 이 값으로 캡한다.
_MAX_RETRY_DELAY_SECONDS = 30.0


def _result(
    ok: bool,
    *,
    error_code: str | None = None,
    summary: str | None = None,
    instances: list[dict[str, Any]] | None = None,
    mask_asset_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "error_code": error_code,
        "mask_asset_id": mask_asset_id,
        "instances": instances or [],
        "summary": summary,
    }


def _image_url_rejected(url: str, settings: "Settings") -> bool:
    """이미지 URL 을 거절해야 하면 True.

    image_url 은 LLM/도구 인자(대화에서 유도)라 임의 URL 이 우리 bearer 와 함께 HF 로
    전달될 수 있다. SSRF 가드(https 강제 + 사설/로컬/링크로컬/메타데이터 차단)를 항상
    적용하고, 허용 호스트가 설정돼 있으면 그 목록만 통과시킨다(세션 경계).
    """

    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    if parsed.scheme != "https" or not parsed.hostname:
        return True
    host = parsed.hostname.lower()
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    except ValueError:
        pass  # 호스트명(IP 아님) — DNS 단계 차단은 어려우므로 allowlist 로 보강
    allowed = settings.hf_segmentation_allowed_image_hosts
    if allowed and host not in {h.lower() for h in allowed}:
        return True
    return False


def _valid_uuid(value: Any) -> str | None:
    """UUID 로 파싱되는 문자열만 반환(아니면 None) — 계약의 mask_asset_id 형식 보장."""
    if not isinstance(value, str) or not value:
        return None
    try:
        uuid.UUID(value)
    except ValueError:
        return None
    return value


def _retry_delay(resp: httpx.Response) -> float:
    raw = resp.headers.get("Retry-After")
    if raw is not None:
        try:
            return min(float(raw), _MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            pass
    # HF 추론 엔드포인트는 503 body 에 estimated_time(초)을 주기도 한다.
    try:
        body = resp.json()
        est = body.get("estimated_time")
        if isinstance(est, (int, float)):
            return min(float(est), _MAX_RETRY_DELAY_SECONDS)
    except Exception:  # noqa: BLE001 - body 파싱 실패는 무시
        pass
    return 2.0


def _parse_ok(data: Any) -> dict[str, Any]:
    """200 응답 파싱 — 모델 출력 포맷이 확정 전이라 방어적으로 요약만 만든다."""

    if not isinstance(data, dict):
        return _result(
            False, error_code="SEGMENTATION_BAD_RESPONSE", summary="응답 형식 오류."
        )

    raw_instances = data.get("instances")
    instances: list[dict[str, Any]] = []
    if isinstance(raw_instances, list):
        for item in raw_instances:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            count = item.get("count")
            # 계약은 count>=0. bool(True/False)은 int subclass 라 type() 로 배제하고
            # 음수도 드롭한다(모델/버전 불일치 시 잘못된 음수 카운트 방지).
            if label not in _KNOWN_LABELS or type(count) is not int or count < 0:
                continue
            entry: dict[str, Any] = {"label": label, "count": count}
            conf = item.get("mean_confidence")
            # 계약은 mean_confidence 를 [0,1] 로 제한한다 — 범위 밖(모델/버전 불일치)
            # 값은 fabricate 하지 않고 드롭한다.
            if isinstance(conf, (int, float)) and 0 <= conf <= 1:
                entry["mean_confidence"] = float(conf)
            instances.append(entry)

    wall_other = sum(i["count"] for i in instances if i["label"] == "wall_other")
    rc = sum(i["count"] for i in instances if i["label"] == "wall_reinforced_concrete")
    summary = (
        f"세그멘테이션 완료 — 비내력벽 후보 {wall_other}, 내력(RC)벽 후보 {rc}."
        if instances
        else "세그멘테이션 완료(인스턴스 요약 없음)."
    )
    # 성공 응답이 마스크 자산 id 를 주면 보존한다(downstream 오버레이/리포트용).
    # 계약은 UUID 형식이므로 UUID 로 파싱되는 값만 통과시키고, 잘못된 값(스토리지 키·
    # placeholder 등)은 드롭한다.
    mask = _valid_uuid(data.get("mask_asset_id"))
    return _result(True, summary=summary, instances=instances, mask_asset_id=mask)


async def segment_floorplan_impl(
    *,
    image_url: str,
    settings: "Settings",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """엔드포인트 호출 + 실패 분류. segmentation-result 형태 dict 반환(raise 안 함)."""

    endpoint = settings.hf_segmentation_endpoint_url
    if not endpoint:
        return _result(
            False,
            error_code="SEGMENTATION_ENDPOINT_UNAVAILABLE",
            summary="세그멘테이션 엔드포인트가 설정되지 않았습니다(미배포).",
        )

    # SSRF/세션 경계 가드 — 임의 URL 을 우리 bearer 와 함께 HF 로 보내지 않는다.
    if _image_url_rejected(image_url, settings):
        return _result(
            False,
            error_code="SEGMENTATION_BAD_REQUEST",
            summary="허용되지 않은 이미지 URL 입니다(허용 호스트의 https 자산만 가능).",
        )

    headers: dict[str, str] = {}
    if settings.hf_segmentation_token:
        headers["Authorization"] = f"Bearer {settings.hf_segmentation_token}"

    max_retries = settings.hf_segmentation_cold_start_max_retries
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.hf_segmentation_timeout_seconds)
    try:
        attempt = 0
        while True:
            try:
                resp = await client.post(
                    endpoint, json={"image_url": image_url}, headers=headers
                )
            except (httpx.ConnectError, httpx.ConnectTimeout):
                return _result(
                    False,
                    error_code="SEGMENTATION_ENDPOINT_UNAVAILABLE",
                    summary="엔드포인트에 연결할 수 없습니다(미배포/DNS).",
                )
            except httpx.TimeoutException:
                return _result(
                    False,
                    error_code="SEGMENTATION_TIMEOUT",
                    summary="추론 시간이 초과되었습니다.",
                )
            except httpx.RequestError:
                # ReadError/RemoteProtocolError 등(연결 리셋·중도 끊김) 도 raise 하지
                # 않고 구조화 에러로 degrade — 런 전체가 AGENT_RUNTIME_ERROR 되지 않게.
                return _result(
                    False,
                    error_code="SEGMENTATION_UPSTREAM_ERROR",
                    summary="세그멘테이션 요청이 전송/응답 중 실패했습니다.",
                )

            status = resp.status_code
            if status == 404:
                return _result(
                    False,
                    error_code="SEGMENTATION_ENDPOINT_UNAVAILABLE",
                    summary="엔드포인트가 아직 배포되지 않았습니다(404).",
                )
            if status == 503:
                if attempt >= max_retries:
                    return _result(
                        False,
                        error_code="SEGMENTATION_COLD_START_TIMEOUT",
                        summary="콜드스타트 대기 한도를 초과했습니다.",
                    )
                attempt += 1
                await asyncio.sleep(_retry_delay(resp))
                continue
            if status in (400, 422):
                return _result(
                    False,
                    error_code="SEGMENTATION_BAD_REQUEST",
                    summary="세그멘테이션 요청이 거부되었습니다.",
                )
            if status >= 500:
                return _result(
                    False,
                    error_code="SEGMENTATION_UPSTREAM_ERROR",
                    summary=f"세그멘테이션 업스트림 오류({status}).",
                )
            if status >= 400:
                return _result(
                    False,
                    error_code="SEGMENTATION_BAD_REQUEST",
                    summary=f"세그멘테이션 요청 오류({status}).",
                )

            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                return _result(
                    False,
                    error_code="SEGMENTATION_BAD_RESPONSE",
                    summary="응답 JSON 파싱에 실패했습니다.",
                )
            return _parse_ok(data)
    finally:
        if owns_client:
            await client.aclose()
