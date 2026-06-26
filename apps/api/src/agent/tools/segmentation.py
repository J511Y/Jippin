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
import contextlib
import ipaddress
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from ...logging import get_logger

if TYPE_CHECKING:
    from ...config import Settings

log = get_logger("zippin.agent.tools.segmentation")

SCHEMA_VERSION = "1.2.0"

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
    image: dict[str, Any] | None = None,
    regions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "error_code": error_code,
        "mask_asset_id": mask_asset_id,
        "instances": instances or [],
        # 오버레이 렌더용(좌표 포함). LLM 컨텍스트엔 싣지 않고 카드로만 전달한다 —
        # segment_session_floorplan 이 카드 방출 후 LLM 반환분에서 떼어 낸다.
        "image": image,
        "regions": regions or [],
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
    image = _parse_image(data.get("image"))
    regions = _parse_regions(raw_predictions)
    return _result(
        True,
        summary=summary,
        instances=instances,
        mask_asset_id=mask,
        image=image,
        regions=regions,
    )


def _parse_image(raw: Any) -> dict[str, Any] | None:
    """원본 이미지 크기(width/height)만 추려 계약(Image)으로 환원. 좌표 스케일에 쓴다."""
    if not isinstance(raw, dict):
        return None
    w = raw.get("width")
    h = raw.get("height")
    if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        return {"width": w, "height": h}
    return None


def _parse_regions(raw_predictions: list[Any]) -> list[dict[str, Any]]:
    """per-region predictions 를 오버레이 계약(Region)으로 환원.

    좌표(polygon/bbox)는 원본 픽셀 그대로 보존한다(오버레이가 표시 크기로 스케일).
    polygon 이 비었거나(짝수 좌표 < 6=삼각형 미만) 라벨이 18클래스 밖이면 드롭한다.
    """
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_predictions):
        if not isinstance(item, dict):
            continue
        label = item.get("class_name")
        if label not in _KNOWN_LABELS:
            continue
        polygon = item.get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2 != 0:
            continue  # 최소 삼각형(3점=6좌표) + 짝수만.
        if not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in polygon
        ):
            continue
        region: dict[str, Any] = {
            "region_id": str(item.get("region_id") or f"pred:{idx + 1}"),
            "class_name": label,
            "polygon": [float(v) for v in polygon],
            "requires_hitl": bool(item.get("requires_hitl"))
            or str(label).startswith("wall_"),
        }
        score = item.get("score")
        if (
            isinstance(score, (int, float))
            and not isinstance(score, bool)
            and 0 <= score <= 1
        ):
            region["score"] = float(score)
        bbox = item.get("bbox")
        if (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox
            )
        ):
            region["bbox"] = [float(v) for v in bbox]
        out.append(region)
    return out


# class_name → 계약 WallObject.wall_type (common-judgment-schema). 모델 출력은 후보일
# 뿐 확정 아님 — UI 어휘는 '후보/검토 필요'로 표시한다.
_WALL_TYPE_BY_CLASS: dict[str, str] = {
    "wall_other": "NON_LOAD_BEARING",
    "wall_reinforced_concrete": "LOAD_BEARING",
    "wall_unknown": "UNKNOWN",
}
# class_name → 계약 SpaceObject.type. 매핑 없는 공간은 ETC.
_SPACE_TYPE_BY_CLASS: dict[str, str] = {
    "space_living_room": "LIVING_ROOM",
    "space_kitchen": "KITCHEN",
    "space_bedroom": "BEDROOM",
    "space_bathroom": "BATHROOM",
    "space_balcony": "BALCONY",
    "space_stairwell": "STAIRWELL",
    "space_elevator_hall": "CORRIDOR",
    "space_entrance": "CORRIDOR",
}
# class_name → 사람이 읽는 라벨(SpaceObject.label).
_SPACE_LABEL_BY_CLASS: dict[str, str] = {
    "space_living_room": "거실",
    "space_kitchen": "주방",
    "space_bedroom": "침실",
    "space_bathroom": "욕실",
    "space_balcony": "발코니",
    "space_stairwell": "계단실",
    "space_elevator_hall": "엘리베이터홀",
    "space_entrance": "현관",
    "space_multipurpose": "다목적실",
    "space_ac_room": "실외기실",
    "space_dress_room": "드레스룸",
    "space_elevator": "엘리베이터",
    "space_other": "기타 공간",
}


def _polygon_to_maskcoords(polygon: list[float]) -> list[dict[str, float]]:
    """평면 [x1,y1,x2,y2,...] → 계약 MaskCoord[{x,y}]."""
    return [
        {"x": float(polygon[i]), "y": float(polygon[i + 1])}
        for i in range(0, len(polygon) - 1, 2)
    ]


# 도면 여백(치수·표제란 등)을 잘라내기 위한 크롭 패딩(원본 픽셀). 검출된 엔티티
# 전체를 감싸는 최대 박스에 이만큼 여유를 둔다(MASK 대체: 인퍼런스 결과 기반 크롭).
_CROP_PADDING_PX = 24.0


def _compute_crop_box(
    regions: list[dict[str, Any]], image: dict[str, Any] | None
) -> dict[str, float] | None:
    """검출된 모든 region 폴리곤을 감싸는 최대 박스 + 24px 크롭 영역을 계산한다.

    MASK-001(수치 마스킹) 대체 구현 — 도면 외곽 여백(치수·면적 수치·표제란)을 잘라
    내기 위해, 세그멘테이션이 잡아낸 엔티티 전체의 bounding box 에 패딩을 둔 크롭
    프레임을 돌려준다. 프론트(FloorplanOverlay)가 이 프레임을 SVG viewBox 로 써서
    이미지와 오버레이를 같은 비율로 확대·표시한다(좌표 변환 없음 — 같은 좌표계).

    검출 region 이 없으면 None(전체 표시로 폴백). image 크기가 있으면 그 안으로 클램프.
    """

    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for r in regions:
        poly = r.get("polygon") if isinstance(r, dict) else None
        if not isinstance(poly, list):
            continue
        for i in range(0, len(poly) - 1, 2):
            x, y = poly[i], poly[i + 1]
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                continue
            min_x, max_x = min(min_x, float(x)), max(max_x, float(x))
            min_y, max_y = min(min_y, float(y)), max(max_y, float(y))
    if min_x == float("inf") or max_x <= min_x or max_y <= min_y:
        return None

    x0 = min_x - _CROP_PADDING_PX
    y0 = min_y - _CROP_PADDING_PX
    x1 = max_x + _CROP_PADDING_PX
    y1 = max_y + _CROP_PADDING_PX
    # 이미지 경계로 클램프(여백을 둔 박스가 캔버스 밖으로 나가지 않게).
    img_w = (
        float(image["width"])
        if isinstance(image, dict) and image.get("width")
        else None
    )
    img_h = (
        float(image["height"])
        if isinstance(image, dict) and image.get("height")
        else None
    )
    x0 = max(0.0, x0)
    y0 = max(0.0, y0)
    if img_w is not None:
        x1 = min(img_w, x1)
    if img_h is not None:
        y1 = min(img_h, y1)
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return None
    return {
        "x": round(x0, 2),
        "y": round(y0, 2),
        "w": round(w, 2),
        "h": round(h, 2),
    }


def build_overlay_spec(
    *, asset_id: Any, image: dict[str, Any] | None, regions: list[dict[str, Any]]
) -> dict[str, Any]:
    """오버레이 카드(FloorplanOverlay) json-render spec — 서버가 구성한다(LLM 미관여).

    asset_id 로 프론트가 표시용 서명 URL 을 발급받고, image(원본 크기)로 좌표를 스케일해
    polygon 을 그린다. ``crop`` 은 검출 엔티티를 감싼 크롭 프레임으로, 프론트가 viewBox 로
    써서 도면 외곽 여백(치수·표제란)을 잘라낸 채 확대 표시한다(MASK 대체).
    """
    props: dict[str, Any] = {
        "asset_id": str(asset_id),
        "image": image or {},
        "regions": regions,
    }
    crop = _compute_crop_box(regions, image)
    if crop is not None:
        props["crop"] = crop
    return {
        "root": "ov",
        "elements": {"ov": {"type": "FloorplanOverlay", "props": props}},
    }


def build_judgment_objects(
    regions: list[dict[str, Any]],
    vlm_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """regions → (wall_objects, space_objects) 계약 형태. door/window 는 제외(둘 다 아님).

    좌표가 부족하면(벽 <2점, 공간 <3점) 그 객체는 드롭한다(계약 minItems 준수).
    region_id 를 객체 id 로 써서 OVERLAY 의 selected_walls(region_id[]) 와 정합시킨다.
    ``vlm_ids`` 에 든 region 은 VLM(AI-002)이 교정한 것이라 source_engine 을 VLM 으로 둔다.
    """
    vlm_ids = vlm_ids or set()
    walls: list[dict[str, Any]] = []
    spaces: list[dict[str, Any]] = []
    for r in regions:
        cls = r.get("class_name")
        rid = r.get("region_id")
        if not isinstance(cls, str) or not isinstance(rid, str):
            continue
        engine = "VLM" if rid in vlm_ids else "MASK2FORMER"
        pts = _polygon_to_maskcoords(r.get("polygon") or [])
        conf = float(r["score"]) if isinstance(r.get("score"), (int, float)) else 0.0
        if cls in _WALL_TYPE_BY_CLASS:
            if len(pts) < 2:
                continue
            walls.append(
                {
                    "id": rid,
                    "wall_type": _WALL_TYPE_BY_CLASS[cls],
                    "confidence": conf,
                    "coords": pts,
                    "source_engine": engine,
                }
            )
        elif cls in _SPACE_LABEL_BY_CLASS:
            if len(pts) < 3:
                continue
            spaces.append(
                {
                    "id": rid,
                    "label": _SPACE_LABEL_BY_CLASS[cls],
                    "type": _SPACE_TYPE_BY_CLASS.get(cls, "ETC"),
                    "mask_coords": pts,
                    "confidence": conf,
                    "source_engine": engine,
                }
            )
    return walls, spaces


def _merge_overlapping_regions(
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """겹치는(intersect) 같은-클래스 region 을 하나의 엔티티로 병합(후처리).

    세그멘테이션이 한 벽을 여러 인스턴스로 쪼개 내보내 오버레이가 서로 겹쳐 보이던 문제를
    정리한다 — shapely unary_union 으로 클래스별 폴리곤을 합쳐 연결된 영역을 단일 region 으로
    만든다. region_id 는 ``merged:N`` 으로 새로 부여(선택은 이 id 기준). shapely 부재/실패는
    원본을 그대로 돌려 degrade 한다.
    """

    if not regions:
        return regions
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except Exception:  # noqa: BLE001 - shapely 미존재 시 병합 없이 진행
        return regions

    by_class: dict[str, list[dict[str, Any]]] = {}
    for r in regions:
        cls = r.get("class_name")
        if isinstance(cls, str):
            by_class.setdefault(cls, []).append(r)

    out: list[dict[str, Any]] = []
    counter = 0
    for cls, group in by_class.items():
        shaped: list[tuple[Any, dict[str, Any]]] = []
        for r in group:
            poly = r.get("polygon") or []
            pts = [(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)]
            try:
                g = Polygon(pts)
                if not g.is_valid:
                    g = g.buffer(0)  # self-intersection 보정
                if g.is_empty or g.area <= 0:
                    out.append(r)  # 폴리곤화 불가 → 원본 유지
                    continue
                shaped.append((g, r))
            except Exception:  # noqa: BLE001
                out.append(r)
        if not shaped:
            continue
        merged = unary_union([g for g, _ in shaped])
        parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        for part in parts:
            if part.is_empty or part.geom_type != "Polygon":
                continue
            members = [r for g, r in shaped if part.intersects(g)]
            if len(members) <= 1:
                # 겹친 게 없음 → 원본 region 그대로(id·좌표 보존, 불필요한 변형 방지).
                out.extend(members)
                continue
            counter += 1
            flat: list[float] = []
            for x, y in part.exterior.coords:
                flat += [float(x), float(y)]
            scores = [
                m["score"] for m in members if isinstance(m.get("score"), (int, float))
            ]
            out.append(
                {
                    "region_id": f"merged:{counter}",
                    "class_name": cls,
                    "polygon": flat,
                    "score": (sum(scores) / len(scores)) if scores else None,
                    "requires_hitl": any(bool(m.get("requires_hitl")) for m in members)
                    or cls.startswith("wall_"),
                }
            )
    return out


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
    result = await segment_floorplan_impl(
        image_url=signed, settings=settings, client=client
    )
    if not result.get("ok") or not result.get("regions"):
        return result
    # 분석 성공 — 오버레이 카드 방출 + 공통 판단 스키마(wall/space objects) 누적 + LLM
    # 반환분에서 좌표 제거(컨텍스트 leanness). 카드 방출/판단 누적 실패는 분석 자체를
    # 무르지 않는다(best-effort) — 좌표 없는 요약만 LLM 에 돌려도 흐름은 유지된다.
    regions = result.get("regions") or []
    # 후처리: 겹치는 같은-클래스 엔티티를 하나로 병합(세그멘테이션이 한 벽을 여러 조각으로
    # 쪼개 오버레이가 겹치던 문제 정리). 이후 VLM/오버레이/선택이 모두 병합본 기준.
    regions = _merge_overlapping_regions(regions)
    image = result.get("image")

    # AI-002 VLM 문맥 해석 — 도면 이미지로 Mask2Former 레이블을 보완(실패 시 None=단독 degrade).
    supplement: dict[str, Any] | None = None
    with contextlib.suppress(Exception):
        from .vlm import interpret_floorplan_impl

        supplement = await interpret_floorplan_impl(
            image_url=signed, regions=regions, image=image, settings=settings
        )

    # AI-003 정합성 검증·정규화 — VLM 교정(reclassifications)을 regions 에 머지한다.
    vlm_ids: set[str] = set()
    if supplement and supplement.get("reclassifications"):
        by_id = {r.get("region_id"): r for r in regions if isinstance(r, dict)}
        for rc in supplement["reclassifications"]:
            reg = by_id.get(rc.get("object_id"))
            if reg is not None:
                reg["class_name"] = rc["new_label"]  # VLM 교정 적용
                reg["source_engine"] = "VLM"
                vlm_ids.add(rc["object_id"])

    if run_context is not None and run_id is not None:
        from .domain import emit_ui_component_impl

        # 오버레이는 머지된(VLM 교정 반영) regions 로 띄운다.
        spec = build_overlay_spec(asset_id=asset["id"], image=image, regions=regions)
        with contextlib.suppress(Exception):
            await emit_ui_component_impl(
                run_context=run_context, run_id=run_id, components=[spec]
            )

    walls, spaces = build_judgment_objects(regions, vlm_ids=vlm_ids)
    patch: dict[str, Any] = {"wall_objects": walls, "space_objects": spaces}
    if supplement is not None:
        patch["vlm_supplement"] = supplement
    with contextlib.suppress(Exception):
        await main_flow.merge_judgment_schema(
            session_id=session_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
            patch=patch,
        )

    # 요약 — 세그멘테이션 + VLM 보완. ANALYSIS_LOW_CONFIDENCE(0.6 미만)면 재확인 권장.
    summary = result.get("summary")
    low_conf = bool(
        supplement
        and supplement.get("confidence") is not None
        and supplement["confidence"] < 0.6
    )
    if supplement:
        summary = (summary or "") + " VLM 문맥 검토도 함께 반영했어요."
        if vlm_ids:
            summary += f" (벽 {len(vlm_ids)}곳은 이미지 기준으로 분류를 보정했어요.)"
        if low_conf:
            summary += " 다만 분석 신뢰도가 낮아 재확인이 필요할 수 있어요."
    # LLM 반환은 **최소·생활어 요약만** 싣는다. 좌표·instances·VLM notes/confidence/
    # reclassify 같은 원시 분석값은 절대 싣지 않는다 — 모델이 그 raw 데이터를 받으면 답변
    # 본문에 JSON/분석 덤프로 그대로 토해 내(스트리밍 중 raw JSON 이 보이고 끝나서야 카드가
    # 뜸) B2C 경험을 깬다(#no-analysis-dump). 상세는 오버레이 카드가 보여 주고, VLM 관찰은
    # 다음 턴 '[현재 세션 상태]' 스냅샷으로 에이전트에 전달돼 설명에 쓰인다.
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "summary": summary,
        "overlay_emitted": True,
        "region_count": len(regions),
        "analysis_low_confidence": low_conf,
    }


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
