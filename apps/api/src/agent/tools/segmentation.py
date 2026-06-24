"""평면도 세그멘테이션 도구(HuggingFace Inference Endpoint) — 실패 처리 핵심.

모델: ``youjunhyeok/floorplan-mask2former-cmp180-full`` (Mask2Former, 18클래스 =
STR 5 door/window/wall_reinforced_concrete/wall_other/wall_unknown + SPA 13 공간).
요청 계약: ``{"inputs": <data URL|base64|HTTP(S) URL>, "parameters": {threshold,
mask_threshold, max_inference_side}}``. 응답: per-region ``predictions[]``(class_name/
score/polygon/bbox…) — 여기서 라벨별 count + score 평균으로 집계해 segmentation-result
계약(instances)으로 환원한다(좌표는 계약상 미포함).

엔드포인트는 CPU + scale-to-zero(15분)라 유휴 후 첫 요청은 **503 으로 스케일업**되며
수 분 걸릴 수 있다 — 폴링 재시도로 흡수한다. 어떤 실패도 **절대 uncaught raise 하지
않고** 구조화 dict 를 반환한다(미배포/콜드스타트/타임아웃 모두 ok=false). 에이전트는
ok=false 면 ASK_MORE 로 degrade, 반복 실패 시 HOLD_OR_HANDOFF 한다.
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

SCHEMA_VERSION = "1.1.0"

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


def _retry_delay(resp: httpx.Response, fallback: float) -> float:
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
    # 전용 엔드포인트는 503 에 힌트를 안 주기도 한다 — 설정된 폴링 간격으로 폴백.
    return min(fallback, _MAX_RETRY_DELAY_SECONDS)


def _parse_ok(data: Any) -> dict[str, Any]:
    """200 응답 파싱 — 모델 카드(cmp180_full)의 per-region ``predictions[]`` 를 라벨별로
    집계해 계약의 ``instances[{label, count, mean_confidence}]`` 로 환원한다.

    모델은 인스턴스마다 한 region(class_name/score/polygon/bbox…)을 낸다. 계약(다운스트림
    에이전트 추론·evaluate_rules)은 라벨별 집계만 쓰므로 여기서 count(=region 수)와
    mean_confidence(=score 평균)로 줄인다. 폴리곤/bbox 등 좌표는 계약상 싣지 않는다
    (오버레이 UI 는 계약 확장이 필요한 별도 작업).
    """

    if not isinstance(data, dict):
        return _result(
            False, error_code="SEGMENTATION_BAD_RESPONSE", summary="응답 형식 오류."
        )

    raw_predictions = data.get("predictions")
    if not isinstance(raw_predictions, list):
        return _result(
            False,
            error_code="SEGMENTATION_BAD_RESPONSE",
            summary="응답에 predictions 가 없습니다.",
        )

    counts: dict[str, int] = {}
    score_sum: dict[str, float] = {}
    score_n: dict[str, int] = {}
    for item in raw_predictions:
        if not isinstance(item, dict):
            continue
        label = item.get("class_name")
        # 18 클래스(모델 id2label) 밖이면 드롭 — 모델/버전 불일치 방어.
        if label not in _KNOWN_LABELS:
            continue
        counts[label] = counts.get(label, 0) + 1
        score = item.get("score")
        # score 는 [0,1] 만 평균에 반영(bool 은 int subclass 라 배제). 범위 밖은 무시.
        if (
            isinstance(score, (int, float))
            and not isinstance(score, bool)
            and 0 <= score <= 1
        ):
            score_sum[label] = score_sum.get(label, 0.0) + float(score)
            score_n[label] = score_n.get(label, 0) + 1

    instances: list[dict[str, Any]] = []
    for label in sorted(counts):  # 결정적 순서.
        entry: dict[str, Any] = {"label": label, "count": counts[label]}
        if score_n.get(label):
            entry["mean_confidence"] = round(score_sum[label] / score_n[label], 4)
        instances.append(entry)

    wall_other = counts.get("wall_other", 0)
    rc = counts.get("wall_reinforced_concrete", 0)
    summary = (
        f"세그멘테이션 완료 — 비내력벽 후보 {wall_other}, 내력(RC)벽 후보 {rc}."
        if instances
        else "세그멘테이션 완료(검출된 영역 없음)."
    )
    # 현재 모델 응답엔 저장된 마스크 자산이 없다(폴리곤만). 다만 핸들러가 향후
    # mask_asset_id(UUID)를 줄 수 있으니 방어적으로 보존한다.
    mask = _valid_uuid(data.get("mask_asset_id"))
    return _result(True, summary=summary, instances=instances, mask_asset_id=mask)


async def segment_session_floorplan(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
    settings: "Settings",
    client: httpx.AsyncClient | None = None,
    run_context: Any | None = None,
    run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """세션에 선택된 도면 asset 을 서명해 세그멘테이션한다.

    LLM 이 임의 ``image_url`` 을 넘기지 않게 한다(SSRF/세션 경계) — 도면 출처는 항상
    세션의 ``selected_floorplan_asset_id`` 다. 도면 미업로드면 ``SEGMENTATION_NO_IMAGE``,
    서명 실패(스토리지/설정 문제)는 ``ENDPOINT_UNAVAILABLE`` 로 degrade 한다.

    ``run_context`` 가 주어지면 분석 시작 시점의 입력 지문(asset_id/address_id)을 기록해
    evaluate_rules 가 verdict 영속을 그 지문 기준 조건부로 만들 수 있게 한다 — 분석
    도중 도면/주소가 바뀌면 옛 판정이 새 입력에 붙는 race 차단(#analysis-input-fingerprint).
    ``run_id`` 가 함께 오면 그 지문을 런에 **내구화**해 SSE 단절→resume 로 RunContext 가
    새로 생겨도 복원되게 한다(메모리 지문만 두면 resume 가 현재 입력으로 폴백해 stale
    판정이 새 입력에 붙는다).
    """

    from ...services import main_flow, storage

    asset = await main_flow.get_selected_floorplan_asset(
        session_id=session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    if asset is None:
        return _result(
            False,
            error_code="SEGMENTATION_NO_IMAGE",
            summary="분석할 도면이 아직 업로드되지 않았습니다. 도면을 먼저 올려 주세요.",
        )
    # 분석 입력 지문을 한 번만 기록(첫 분석 도구). 도면을 분석하는 시점의 (asset, address).
    # resume 로 RunContext 가 비어 새로 생긴 경우 런너가 내구 지문을 복원하므로
    # analysis_inputs 가 이미 채워져 있어 재기록하지 않는다.
    if (
        run_context is not None
        and getattr(run_context, "analysis_inputs", None) is None
    ):
        inputs = await main_flow.get_session_inputs(session_id)
        if inputs is not None:
            run_context.analysis_inputs = inputs
            if run_id is not None:
                await main_flow.set_run_analysis_inputs(
                    run_id=run_id,
                    asset_id=inputs[0],
                    address_id=inputs[1],
                )
    # 보안 스캔 가드: 사용자 업로드 원본은 clean(또는 not_required)일 때만 분석한다.
    # pending 은 설정(agent_allow_unscanned_floorplans)이 허용할 때만. infected 등은 항상
    # 차단 — 미검사 콘텐츠를 HF 로 전달하지 않는다(#scan-gate).
    scan_status = asset.get("scan_status")
    allowed_unscanned = bool(
        getattr(settings, "agent_allow_unscanned_floorplans", False)
    )
    analyzable = scan_status in ("clean", "not_required") or (
        scan_status == "pending" and allowed_unscanned
    )
    if not analyzable:
        return _result(
            False,
            error_code="SEGMENTATION_NOT_SCANNED",
            summary="도면 보안 검사가 끝난 뒤 분석할 수 있습니다.",
        )
    signed = await storage.sign_object_url(
        settings,
        bucket=asset["bucket"],
        object_path=asset["object_key"],
        operation="sign_floorplan_asset",
    )
    if not signed:
        return _result(
            False,
            error_code="SEGMENTATION_ENDPOINT_UNAVAILABLE",
            summary="도면 접근 URL 발급에 실패했습니다.",
        )
    return await segment_floorplan_impl(
        image_url=signed, settings=settings, client=client
    )


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
                # 모델 카드(cmp180_full) 계약: inputs 는 data URL/base64/HTTP(S) URL 중
                # 하나. 우리는 스토리지 서명 URL(1h TTL)을 그대로 inputs 로 넘긴다 — 핸들러가
                # HTTP(S) URL 을 디코드한다(백엔드에서 별도 다운로드/base64 불필요).
                resp = await client.post(
                    endpoint,
                    json={
                        "inputs": image_url,
                        "parameters": {
                            "threshold": settings.hf_segmentation_threshold,
                            "mask_threshold": settings.hf_segmentation_mask_threshold,
                            "max_inference_side": (
                                settings.hf_segmentation_max_inference_side
                            ),
                        },
                    },
                    headers=headers,
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
                await asyncio.sleep(
                    _retry_delay(resp, settings.hf_segmentation_cold_start_poll_seconds)
                )
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
