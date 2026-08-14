"""평면도 세그멘테이션 도구(HuggingFace Inference Endpoint) — 실패 처리 핵심.

모델: ``confirmed573v4_ft_tile_19c`` (Mask2Former, **19클래스** = STR 6 door/window/
wall_reinforced_concrete/wall_nonbearing/wall_other/wall_unknown + SPA 13 공간).

v4(2026-08-12)에서 두 가지가 바뀌었다:

1. **벽 어휘 3종의 의미가 갈렸다.** ``wall_nonbearing`` 은 라벨 작업자가 *확정한*
   비내력벽, ``wall_other`` 는 도면만으로 판단을 *보류한* 미확정 벽이다(v3 까지는
   비내력벽이 매핑 누락으로 wall_unknown 에 조용히 폴백돼, 오히려 wall_other 를
   비내력으로 읽던 반전이 있었다). ``wall_unknown`` 은 과거 데이터 호환용으로만
   남는다 — v4 확정 라벨 경로에서는 산출되지 않는다.
2. **입력을 축소하면 성능이 붕괴한다.** 핸들러가 원본 픽셀을 1536 타일/256 겹침으로
   잘라 각각 추론한 뒤 전체 좌표로 합친다. 앱은 도면을 **원본 해상도 그대로** 보내야
   하며(리사이즈 파라미터 금지), 입력이 작으면 응답 ``notes`` 에
   ``input_long_side_below_expected`` 가 실려 온다(경고 로깅 대상).

요청 계약: ``{"inputs": <data URL|base64|HTTP(S) URL>, "parameters": {threshold,
mask_threshold, max_tiles}}``. tile_size/tile_overlap 은 학습값이라 넘기지 않고 핸들러
기본값을 쓴다. threshold 는 어휘 세대로 고른다 — v4 의 벽 후보(특히 비내력 계열)는 점수가
낮게 나와 0.5 에서 상당수가 걸러지므로 0.35(모델 평가 축과 동일), v3 은 기존 운영값 0.5.
**요청 파라미터는 응답을 보기 전에 정해야 해서** 아래 응답 기반 판별로는 못 맞춘다 —
설정 ``hf_segmentation_expected_vocab_version`` 을 엔드포인트 교체와 함께 뒤집는다.

응답: per-region ``predictions[]``(class_name/score/polygon/bbox/tile_index/
touches_tile_border…) — 여기서 라벨별 count + score 평균으로 집계해
segmentation-result 계약(instances)으로 환원한다(좌표는 계약상 미포함).

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

SCHEMA_VERSION = "1.4.0"

# segmentation-result 계약의 라벨 enum(검증·요약용).
_KNOWN_LABELS: frozenset[str] = frozenset(
    {
        "door",
        "window",
        "wall_reinforced_concrete",
        "wall_nonbearing",
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

# 미확정 벽 라벨 — 비내력 후보군에는 들되(커버리지) 신뢰 등급이 낮아 HITL 우선순위가
# 높은 벽들. wall_other 는 v4 의 '판단 보류' 벽, wall_unknown 은 v3 이하 과거 데이터.
_UNCERTAIN_WALL_LABELS: frozenset[str] = frozenset({"wall_other", "wall_unknown"})

# 콜드스타트(503) 재시도 대기 상한(초). Retry-After 가 더 커도 이 값으로 캡한다.
_MAX_RETRY_DELAY_SECONDS = 30.0

# 핸들러가 "입력이 학습 해상도보다 작다"고 알리는 note 키. 이 값이 오면 앱이 도면을
# 축소해 보내고 있다는 뜻이고, v4 는 축소 입력에서 성능이 붕괴하므로 경고로 남긴다.
_NOTE_INPUT_TOO_SMALL = "input_long_side_below_expected"

# v4 클래스 수. 응답이 이 어휘인지 판별하는 1차 기준.
_V4_NUM_CLASSES = 19
# v3 → v4 라벨 대응. **엔드포인트 모델 교체는 앱 배포와 별개의 수동 작업**이라, 앱이 먼저
# 나가면 v3 응답에 v4 의미를 씌우게 된다. 그러면 v3 이 비내력벽을 흘려보내던 wall_unknown
# 은 여전히 UNKNOWN 이고 wall_other 마저 UNKNOWN 으로 강등돼 **초록 후보가 하나도 남지 않아
# 모든 세션이 HOLD 로 떨어진다**(기능 정지). 그래서 응답 어휘를 판별해 v3 이면 옛 역할대로
# (wall_other = 선택 가능한 비내력 후보) 되돌려 놓는다 — 교체 전까지는 오늘과 동일하게
# 동작하고, 엔드포인트가 19클래스를 서빙하는 순간 자동으로 v4 의미로 넘어간다.
_V3_TO_V4_LABEL: dict[str, str] = {"wall_other": "wall_nonbearing"}

# 어휘 세대별 기본 threshold. v3 은 기존 운영값(0.5), v4 는 비내력 계열의 낮은 점수를
# 감안한 0.35. **요청 파라미터는 응답을 보기 전에 정해야 해서** 응답 기반 판별로는 못
# 맞춘다 — 설정의 expected_vocab_version 으로 고른다(#threshold-cutover).
_THRESHOLD_BY_VOCAB: dict[int, float] = {3: 0.5, 4: 0.35}


def _expected_vocab_version(settings: "Settings") -> int:
    raw = getattr(settings, "hf_segmentation_expected_vocab_version", 3)
    return raw if isinstance(raw, int) and raw in _THRESHOLD_BY_VOCAB else 3


def _resolve_threshold(settings: "Settings") -> float:
    """요청에 실을 threshold — 명시값이 있으면 그 값, 없으면 어휘 세대 기본값."""
    override = getattr(settings, "hf_segmentation_threshold", None)
    if isinstance(override, (int, float)) and not isinstance(override, bool):
        return float(override)
    return _THRESHOLD_BY_VOCAB[_expected_vocab_version(settings)]


def _detect_vocab_version(
    data: dict[str, Any], raw_predictions: list[Any], *, fallback: int
) -> int:
    """응답이 v4(19클래스) 어휘인지 v3 인지 판별한다.

    1순위는 핸들러가 싣는 ``model.num_classes``, 2순위는 ``model.source_run`` 표기,
    3순위는 v4 에만 있는 ``wall_nonbearing`` 의 실제 등장이다(있으면 v4 확정 — 다만
    **없다고 v3 인 건 아니다**: v4 도 확정 비내력벽이 하나도 없는 도면을 낼 수 있다).

    메타데이터가 전혀 없으면 ``fallback``(설정의 expected_vocab_version)을 따른다.
    여기서 무조건 v3 으로 떨어뜨리면, 메타데이터 없는 **v4** 응답이 wall_other 만 담았을 때
    미확정 벽이 전부 wall_nonbearing 으로 승격돼 초록으로 그려지고 NON_LOAD_BEARING 으로
    영속된다 — HOLD 를 우회하는, 이 마이그레이션이 없애려던 바로 그 반전이다
    (#metadata-free-fallback).
    """

    model = data.get("model")
    model = model if isinstance(model, dict) else {}
    num_classes = model.get("num_classes")
    if isinstance(num_classes, int) and not isinstance(num_classes, bool):
        return 4 if num_classes >= _V4_NUM_CLASSES else 3
    source_run = model.get("source_run")
    if isinstance(source_run, str) and f"{_V4_NUM_CLASSES}c" in source_run:
        return 4
    if any(
        isinstance(p, dict) and p.get("class_name") == "wall_nonbearing"
        for p in raw_predictions
    ):
        return 4
    log.warning("segmentation_vocab_metadata_missing", fallback=fallback)
    return fallback


def _normalize_v3_predictions(raw_predictions: list[Any]) -> list[Any]:
    """v3 응답의 라벨을 v4 어휘로 옮긴다(역할 보존).

    ``wall_other``(v3 의 '선택 가능한 비내력 후보' 역할)만 ``wall_nonbearing`` 으로 바꾼다.
    ``wall_unknown`` 은 v3 에서도 회색 '확인 필요'였으므로 그대로 두면 v4 의 미확정 벽과
    같은 취급을 받는다. 이후 파이프라인(매핑·오버레이·판단객체·요약)은 v4 어휘 하나만 안다.
    """

    out: list[Any] = []
    for item in raw_predictions:
        if isinstance(item, dict) and item.get("class_name") in _V3_TO_V4_LABEL:
            item = {**item, "class_name": _V3_TO_V4_LABEL[item["class_name"]]}
        out.append(item)
    return out


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


def _parse_ok(data: Any, *, expected_vocab: int = 4) -> dict[str, Any]:
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

    # 배포된 모델의 어휘로 해석한다 — 앱 배포와 엔드포인트 모델 교체는 별개 작업이다.
    # 응답에 단서가 없으면 설정값(expected_vocab)을 따른다.
    vocab_version = _detect_vocab_version(
        data, raw_predictions, fallback=expected_vocab
    )
    if vocab_version < 4:
        raw_predictions = _normalize_v3_predictions(raw_predictions)

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

    summary = summarize_counts(counts)
    _log_tiling_notes(data, vocab_version=vocab_version, expected_vocab=expected_vocab)
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


def summarize_counts(counts: dict[str, int]) -> str:
    """라벨별 count → 사용자·에이전트가 읽는 한 줄 요약.

    타일 병합 전/후 어느 시점에서든 같은 문장을 만들 수 있게 분리했다 —
    ``segment_session_floorplan`` 은 조각 병합·VLM 교정이 끝난 뒤 이 함수로 요약을
    **다시** 만든다(#summary-after-merge). 그러지 않으면 "비내력벽 후보 5"라고
    말해 놓고 실제 선택 가능한 벽은 2곳인 불일치가 난다.
    """

    if not counts:
        return "세그멘테이션 완료(검출된 영역 없음)."
    nonbearing = counts.get("wall_nonbearing", 0)
    rc = counts.get("wall_reinforced_concrete", 0)
    uncertain = sum(counts.get(label, 0) for label in _UNCERTAIN_WALL_LABELS)
    window_count = counts.get("window", 0)
    # 미확정 벽(wall_other/wall_unknown)은 도면만으로 내력/비내력을 가르지 못한 벽 —
    # 검출됐을 때만 요약에 노출해 에이전트가 '확인 필요' 흐름을 타게 한다.
    uncertain_txt = f", 미확정 벽 {uncertain}" if uncertain else ""
    return (
        f"세그멘테이션 완료 — 비내력벽 후보 {nonbearing}, 내력(RC)벽 후보 {rc}, "
        f"창호 {window_count}{uncertain_txt}."
    )


def _counts_by_class(regions: list[dict[str, Any]]) -> dict[str, int]:
    """region 목록 → 클래스별 개수(요약 재계산용)."""
    counts: dict[str, int] = {}
    for r in regions:
        cls = r.get("class_name") if isinstance(r, dict) else None
        if isinstance(cls, str):
            counts[cls] = counts.get(cls, 0) + 1
    return counts


def _log_tiling_notes(
    data: dict[str, Any], *, vocab_version: int = 4, expected_vocab: int = 4
) -> None:
    """응답의 ``notes``/``tiling``/``timing`` 을 로그로 남긴다(계약엔 싣지 않음).

    핵심은 ``input_long_side_below_expected`` 다 — 앱이 도면을 축소해 보내고 있다는
    신호이고, v4 는 축소 입력에서 성능이 붕괴하므로(structure mean IoU 0.67 → 0.0007)
    운영에서 알림 대상으로 잡아야 한다. 나머지는 타일 수·지연 추적용 info.
    """

    notes = data.get("notes")
    notes = [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else []
    if any(_NOTE_INPUT_TOO_SMALL in n for n in notes):
        log.warning("segmentation_input_downscaled", notes=notes)
    tiling = data.get("tiling") if isinstance(data.get("tiling"), dict) else {}
    timing = data.get("timing") if isinstance(data.get("timing"), dict) else {}
    if vocab_version < 4:
        # 엔드포인트가 아직 옛 모델을 서빙 중 — 교체 완료 시 이 경고가 멈춘다.
        log.warning("segmentation_legacy_vocab", vocab_version=vocab_version)
    if vocab_version != expected_vocab:
        # 설정(expected_vocab_version)과 실제 서빙 모델이 어긋났다. 응답 의미는 실제
        # 기준으로 해석하지만 **요청 threshold 는 설정 기준으로 나갔다** — 교체 전후로
        # 스위치 뒤집기를 잊으면 여기서 드러난다(#threshold-cutover).
        log.warning(
            "segmentation_vocab_mismatch",
            detected=vocab_version,
            expected=expected_vocab,
        )
    log.info(
        "segmentation_tiling",
        vocab_version=vocab_version,
        windows=tiling.get("windows"),
        raw_predictions=tiling.get("raw_predictions"),
        deduplicated_predictions=tiling.get("deduplicated_predictions"),
        returned_predictions=tiling.get("returned_predictions"),
        seconds=timing.get("seconds"),
        notes=notes or None,
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
    polygon 이 비었거나(짝수 좌표 < 6=삼각형 미만) 라벨이 19클래스 밖이면 드롭한다.
    ``tile_index``/``touches_tile_border`` 는 타일 경계에서 쪼개진 조각을 뒤에서 병합
    (``_merge_overlapping_regions``)하기 위해 함께 보존한다.
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
            # 계약(1.4.0)이 boolean 인 필드 — **실제 bool 만** 받는다. bool(...) 로 넘기면
            # 핸들러가 잘못 보낸 문자열 "false" 가 truthy 라 True 가 되고, 그 region 이
            # 병합 단계에서 부풀려져 남남 벽까지 한 덩어리로 묶인다(#tile-meta-validation).
            "touches_tile_border": item.get("touches_tile_border") is True,
        }
        tile_index = item.get("tile_index")
        # 계약상 0 이상 정수. 음수/실수/bool 은 형식 위반이라 싣지 않는다.
        if isinstance(tile_index, int) and not isinstance(tile_index, bool):
            if tile_index >= 0:
                region["tile_index"] = tile_index
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
#
# v4 어휘 반영(#wall-vocab-v4): 비내력 후보군 = wall_nonbearing ∪ wall_other 이지만
# **신뢰 등급을 나누는 것이 이 분리의 목적**이다. wall_nonbearing 만 NON_LOAD_BEARING
# 으로 승격하고, 판단 보류 벽(wall_other)과 과거 데이터(wall_unknown)는 UNKNOWN 으로
# 둬 룰엔진의 HOLD(추가 확인 필요) 경로를 타게 한다 — v3 까지는 wall_other 를 비내력으로
# 읽어 미확정 벽에 철거 가능성 판단이 붙던 반전이 있었다.
_WALL_TYPE_BY_CLASS: dict[str, str] = {
    "wall_nonbearing": "NON_LOAD_BEARING",
    "wall_reinforced_concrete": "LOAD_BEARING",
    "wall_other": "UNKNOWN",
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


# 오버레이 payload 의 벽 어휘 버전. 카드가 class_name 을 해석하는 규칙이 v4 에서 바뀌어
# (wall_other: 비내력 후보 → 미확정), **저장된 옛 카드를 새 규칙으로 읽으면 안 된다** —
# chat_messages.ui_components 에 남은 v3 카드는 wall_other 를 초록 비내력 후보로 그렸고,
# 그 세션의 judgment_schema.wall_objects 도 NON_LOAD_BEARING 으로 굳어 있다. 이 값이 없는
# payload = v3 로 보고 옛 규칙으로 그린다(#overlay-vocab-version).
OVERLAY_VOCAB_VERSION = 4


def build_overlay_spec(
    *, asset_id: Any, image: dict[str, Any] | None, regions: list[dict[str, Any]]
) -> dict[str, Any]:
    """오버레이 카드(FloorplanOverlay) json-render spec — 서버가 구성한다(LLM 미관여).

    asset_id 로 프론트가 표시용 서명 URL 을 발급받고, image(원본 크기)로 좌표를 스케일해
    polygon 을 그린다. ``crop`` 은 검출 엔티티를 감싼 크롭 프레임으로, 프론트가 viewBox 로
    써서 도면 외곽 여백(치수·표제란)을 잘라낸 채 확대 표시한다(MASK 대체).

    ``vocab_version`` 은 카드가 class_name 을 어느 어휘로 읽어야 하는지 알려 준다 — 저장된
    옛 카드가 새 의미로 재해석되지 않게 하는 판별자다.
    """
    props: dict[str, Any] = {
        "asset_id": str(asset_id),
        "image": image or {},
        "regions": regions,
        "vocab_version": OVERLAY_VOCAB_VERSION,
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """regions → (wall_objects, space_objects, window_objects) 계약 형태. door 는 제외.

    좌표가 부족하면(벽·창호 <2점, 공간 <3점) 그 객체는 드롭한다(계약 minItems 준수).
    region_id 를 객체 id 로 써서 OVERLAY 의 selected_walls/selected_windows(region_id[])
    와 정합시킨다. ``vlm_ids`` 에 든 region 은 VLM(AI-002)이 교정한 것이라 source_engine
    을 VLM 으로 둔다. 창호(window)는 1.1.0 부터 별도 객체로 담는다 — 발코니-실 경계
    창호 철거(거실 통합) 검토를 오버레이 선택으로 받기 위함. 외창/내창 구분은 세그멘테
    이션이 못 하므로 객체에 두지 않고 CHAT(LLM) 판단으로 위임한다.
    """
    vlm_ids = vlm_ids or set()
    walls: list[dict[str, Any]] = []
    spaces: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
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
        elif cls == "window":
            if len(pts) < 2:
                continue
            windows.append(
                {
                    "id": rid,
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
    return walls, spaces, windows


# 타일 경계에서 갈라진 조각을 이어 붙일 때 허용하는 최대 틈(원본 픽셀). 겹침(256px)
# 구간에서 나온 조각들은 보통 실제로 겹쳐 unary_union 이 그대로 합치지만, 경계에서
# 딱 맞아떨어지게 잘린 조각은 미세한 틈을 두고 떨어져 있을 수 있다. 양쪽 모두
# touches_tile_border 인 경우에만 이 만큼의 틈을 메워 하나로 본다.
_TILE_BORDER_JOIN_PX = 3.0
# 틈을 메울 때 쓰는 closing(팽창→수축) 반지름 — closing 은 2×반지름 만큼의 틈을 메우므로
# 허용 틈의 절반이어야 한다(#join-gap-doubling).
_TILE_BORDER_JOIN_RADIUS_PX = _TILE_BORDER_JOIN_PX / 2


def _uf_find(parent: list[int], i: int) -> int:
    """union-find 루트 찾기(경로 압축)."""
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _border_tiles(members: list[dict[str, Any]]) -> set[int]:
    """경계 조각들이 나온 타일 번호 집합(없으면 빈 집합)."""
    return {
        m["tile_index"]
        for m in members
        if m.get("touches_tile_border") and isinstance(m.get("tile_index"), int)
    }


def _joinable_border_components(
    a_members: list[dict[str, Any]], b_members: list[dict[str, Any]]
) -> bool:
    """두 연결 성분을 '타일 경계에서 갈라진 한 벽'으로 볼 수 있으면 True.

    조건은 **양쪽 모두** 경계 조각을 품고 있을 것 — 한쪽만 경계 조각인데 이어 붙이면
    경계와 무관한 이웃 벽이 딸려 들어온다(#both-sides-border). 그리고 두 타일 집합이
    **양쪽 모두 알려져 있고 겹치지 않을 것**: 한 타일 안에서 서로 떨어져 나온 두 인스턴스는
    경계로 갈라진 조각이 아니라 원래 다른 벽이다. 집합이 '같을 때'만 막으면 ``{1,2}`` 와
    ``{2}`` 처럼 일부만 겹치는 쌍이 빠져나간다(#tile-overlap-not-equality).

    **출처를 모르면 잇지 않는다.** 타일 번호가 없으면 '경계로 갈린 한 벽'인지 '가까운 남남
    벽'인지 구분할 근거가 없다 — 이때 이어 붙이면 서로 다른 벽이 하나의 선택 대상·판단
    객체가 되므로, 조각으로 남겨 두는 쪽(과소 병합)을 택한다(#unknown-tile-provenance).
    1차 병합 결과는 타일 번호를 갖지 않으므로 2차(VLM 후) 병합에서 자동으로 이 규칙에
    걸린다 — 겹치는 조각은 그대로 합쳐지고, 틈을 사이에 둔 결합만 보류된다.
    """

    if not any(m.get("touches_tile_border") for m in a_members):
        return False
    if not any(m.get("touches_tile_border") for m in b_members):
        return False
    a_tiles, b_tiles = _border_tiles(a_members), _border_tiles(b_members)
    if not a_tiles or not b_tiles:
        return False  # 출처 불명 → 보수적으로 병합하지 않는다.
    return a_tiles.isdisjoint(b_tiles)


def _merge_overlapping_regions(
    regions: list[dict[str, Any]],
    *,
    id_prefix: str = "merged",
) -> list[dict[str, Any]]:
    """겹치거나(intersect) 타일 경계에서 갈라진 같은-클래스 region 을 하나로 병합(후처리).

    ``id_prefix`` 는 새로 부여할 병합 id 의 접두사다. VLM 교정 뒤 **다시** 병합할 때
    기본값을 그대로 쓰면 1차 병합이 남긴 ``merged:1`` 과 2차 병합의 ``merged:1`` 이
    충돌해 서로 다른 벽이 같은 id 를 갖는다 — 2차는 다른 접두사를 넘긴다.

    세그멘테이션이 한 벽을 여러 인스턴스로 쪼개 내보내 오버레이가 서로 겹쳐 보이던 문제를
    정리한다 — shapely unary_union 으로 클래스별 폴리곤을 합쳐 연결된 영역을 단일 region 으로
    만든다. region_id 는 ``merged:N`` 으로 새로 부여(선택은 이 id 기준). shapely 부재/실패는
    원본을 그대로 돌려 degrade 한다.

    v4(원본 해상도 타일 추론)부터는 **긴 벽이 타일 경계에서 조각으로 나뉘어** 반환된다.
    핸들러의 mask-IoU dedup 은 겹침 구간의 중복만 지우고, 경계를 걸친 좌/우 조각은 서로
    다른 부분이라 남긴다(``touches_tile_border=true`` 가 그 신호). 그래서 2단계로 묶는다:
    ① 실제로 겹치는 것들을 연결 성분으로 만들고, ② **양쪽 모두 경계 조각인** 성분 쌍만
    원본 도형 사이 거리가 ``_TILE_BORDER_JOIN_PX`` 이내일 때 잇는다. 최종 좌표는 원본
    폴리곤의 합집합이고, 그래도 끊겨 있으면 closing(팽창→수축)으로 틈만 메운다.
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

        # 1단계 — 실제로 겹치는 것들만 연결 성분으로 묶는다(팽창 없음).
        merged = unary_union([g for g, _ in shaped])
        parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        comps: list[tuple[Any, list[dict[str, Any]]]] = []
        for part in parts:
            if part.is_empty or part.geom_type != "Polygon":
                continue
            # 소속 판정은 **양(+)의 면적 겹침**으로 한다. intersects 는 꼭짓점 한 점만
            # 닿아도 True 라, 모서리로 맞닿은 두 벽이 각각의 part 에 **양쪽 다** 배정돼
            # 같은 멤버 집합이 두 번 처리되고 병합본이 중복 생성된다(오버레이·요약·판단
            # 객체가 모두 부풀려짐, #point-touch-duplication). 폴리곤은 연결 성분 하나에만
            # 면적을 겹칠 수 있으므로 이 기준이면 정확히 한 곳에 배정된다.
            part_members = [r for g, r in shaped if part.intersection(g).area > 0]
            if part_members:
                comps.append((part, part_members))

        # 2단계 — 타일 경계 조각끼리만 허용 틈 이내에서 잇는다. 도형을 부풀려 판정하면
        # 경계 조각 하나가 옆의 평범한 벽까지 끌어당기므로, **원본 도형 사이의 실제
        # 거리**를 재고 양쪽 모두 경계 조각인 쌍에만 적용한다(#both-sides-border).
        parent = list(range(len(comps)))
        # 합쳐진 그룹이 지금까지 품은 타일 집합. 쌍 단위 검사만으로는 **전이적 결합**을
        # 막지 못한다 — 타일 1·2·1 이 사슬로 이어지면 1→2, 2→1 이 각각 통과해 결국 타일 1
        # 두 조각이 한 덩어리가 된다. 실제로 합치기 직전에 **루트의 누적 집합**으로 다시
        # 확인한다(#transitive-tile-union).
        root_tiles = [_border_tiles(members) for _, members in comps]
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                if not _joinable_border_components(comps[i][1], comps[j][1]):
                    continue
                if comps[i][0].distance(comps[j][0]) > _TILE_BORDER_JOIN_PX:
                    continue
                root_i, root_j = _uf_find(parent, i), _uf_find(parent, j)
                if root_i == root_j:
                    continue
                tiles_i, tiles_j = root_tiles[root_i], root_tiles[root_j]
                if not tiles_i.isdisjoint(tiles_j):
                    continue  # 누적 기준으로 타일이 겹침 → 남남 벽이 섞인다.
                parent[root_j] = root_i
                root_tiles[root_i] = tiles_i | tiles_j

        grouped: dict[int, list[int]] = {}
        for i in range(len(comps)):
            grouped.setdefault(_uf_find(parent, i), []).append(i)

        for idxs in grouped.values():
            members = [m for i in idxs for m in comps[i][1]]
            if len(members) <= 1:
                # 겹친 게 없음 → 원본 region 그대로(id·좌표 보존, 불필요한 변형 방지).
                out.extend(members)
                continue
            member_ids = {id(r) for r in members}
            body = unary_union([g for g, r in shaped if id(r) in member_ids])
            if body.geom_type == "MultiPolygon":
                # 경계 틈으로만 이어진 조각들 — 틈만 메우고(closing) 도형 두께는 보존.
                body = body.buffer(_TILE_BORDER_JOIN_RADIUS_PX).buffer(
                    -_TILE_BORDER_JOIN_RADIUS_PX
                )
            if body.is_empty or body.geom_type != "Polygon":
                out.extend(members)  # 끝내 하나로 못 이으면 병합 포기(원본 유지).
                continue
            counter += 1
            flat: list[float] = []
            for x, y in body.exterior.coords:
                flat += [float(x), float(y)]
            scores = [
                m["score"] for m in members if isinstance(m.get("score"), (int, float))
            ]
            merged_region: dict[str, Any] = {
                "region_id": f"{id_prefix}:{counter}",
                "class_name": cls,
                "polygon": flat,
                "score": (sum(scores) / len(scores)) if scores else None,
                "requires_hitl": any(bool(m.get("requires_hitl")) for m in members)
                or cls.startswith("wall_"),
                "touches_tile_border": any(
                    bool(m.get("touches_tile_border")) for m in members
                ),
            }
            # VLM 이 교정한 조각이 하나라도 섞였으면 병합본도 VLM 출처다 — 이 값을 잃으면
            # 판단객체의 source_engine 이 MASK2FORMER 로 되돌아가 교정 이력이 사라진다.
            if any(m.get("source_engine") == "VLM" for m in members):
                merged_region["source_engine"] = "VLM"
            out.append(merged_region)
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

    # VLM 이 "평면도가 아니다(is_floorplan=false)"라고 판단하면, 사진·스크린샷 등에서 나온
    # 오탐 영역으로 오버레이/판정까지 흘러가지 않게 여기서 degrade 한다 — 다른(진짜) 도면을
    # 요청하도록 ok=false 로 돌린다(#not-floorplan).
    if supplement is not None and supplement.get("is_floorplan") is False:
        return _result(
            False,
            error_code="SEGMENTATION_NOT_FLOORPLAN",
            summary=(
                "업로드하신 이미지가 평면도가 아닌 것 같아요. 집 평면도(도면) 이미지를 "
                "올려 주세요."
            ),
        )

    # 분석 성공(세그멘테이션 + VLM 평면도 검증 통과) 시에만 status 를 analyzing 으로 전진한다 —
    # 서명/엔드포인트/도면판정/not-floorplan 실패로 early-return 하는 경로에서 배지가 analyzing
    # 에 stuck 되지 않게(리뷰 지적). 직후 merge_judgment_schema 가 awaiting_overlay 로 전진한다.
    await main_flow.advance_session_status(
        session_id=session_id, target="analyzing", reason="segmentation_succeeded"
    )

    # AI-003 정합성 검증·정규화 — VLM 교정(reclassifications)을 regions 에 머지한다.
    vlm_ids: set[str] = set()
    if supplement and supplement.get("reclassifications"):
        by_id = {r.get("region_id"): r for r in regions if isinstance(r, dict)}
        reclassified = False
        for rc in supplement["reclassifications"]:
            reg = by_id.get(rc.get("object_id"))
            if reg is not None:
                reg["class_name"] = rc["new_label"]  # VLM 교정 적용
                reg["source_engine"] = "VLM"
                vlm_ids.add(rc["object_id"])
                reclassified = True
        if reclassified:
            # 교정으로 **클래스가 같아진 조각들**을 다시 병합한다(#remerge-after-vlm).
            # 1차 병합은 클래스별로 묶으므로, 한 벽의 타일 조각이 서로 다른 클래스로
            # 나왔다면 그때는 남남으로 남는다. VLM 이 그 불일치를 정리해 같은 클래스로
            # 만들면 비로소 하나로 합칠 수 있고, 그러지 않으면 오버레이에 같은 벽이 둘로
            # 뜨고 개수도 부풀려진다. id 접두사를 달리해 1차 병합 id 와의 충돌을 피하고,
            # VLM 출처는 병합본에 보존된다.
            regions = _merge_overlapping_regions(regions, id_prefix="vlm-merged")
            # 병합으로 region_id 가 바뀌므로 출처는 id 목록이 아니라 region 자체에서 읽는다.
            vlm_ids = {
                str(r.get("region_id"))
                for r in regions
                if isinstance(r, dict) and r.get("source_engine") == "VLM"
            }

    if run_context is not None and run_id is not None:
        from .domain import emit_ui_component_impl

        # 오버레이는 머지된(VLM 교정 반영) regions 로 띄운다.
        spec = build_overlay_spec(asset_id=asset["id"], image=image, regions=regions)
        with contextlib.suppress(Exception):
            await emit_ui_component_impl(
                run_context=run_context, run_id=run_id, components=[spec]
            )

    walls, spaces, windows = build_judgment_objects(regions, vlm_ids=vlm_ids)
    patch: dict[str, Any] = {
        "wall_objects": walls,
        "space_objects": spaces,
        "window_objects": windows,
    }
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
    #
    # 요약은 **병합·VLM 교정이 끝난 최종 regions 로 다시 만든다**(#summary-after-merge).
    # segment_floorplan_impl 이 낸 요약은 원시 predictions 기준이라, v4 타일 추론에서
    # 한 벽이 경계로 쪼개져 온 조각들이 그대로 세어진다 — 그 값을 그대로 쓰면 에이전트가
    # "비내력벽 후보 5곳"이라 말하는데 오버레이엔 선택 가능한 벽이 2곳만 보이는 불일치가
    # 난다. VLM 교정으로 클래스가 바뀐 것도 여기서 함께 반영된다.
    summary = summarize_counts(_counts_by_class(regions))
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
                # 모델 카드 계약: inputs 는 data URL/base64/HTTP(S) URL 중 하나. 우리는
                # 스토리지 서명 URL(1h TTL)을 그대로 inputs 로 넘긴다 — 핸들러가 HTTP(S)
                # URL 을 디코드한다(백엔드에서 별도 다운로드/base64 불필요).
                #
                # 리사이즈 파라미터는 **절대 넘기지 않는다**(#v4-original-resolution).
                # v4 는 원본 픽셀을 타일로 잘라 추론하는 전제라, 입력을 축소하면 성능이
                # 붕괴한다(structure mean IoU 0.672 → 0.0007). tile_size/tile_overlap 도
                # 학습값이라 건드리지 않고 핸들러 기본값(1536/256)을 쓴다.
                #
                # 대신 max_tiles 로 **작업량 상한을 명시**한다(#tile-budget). 원본을 그대로
                # 보내는 이상 픽셀 수가 곧 비용인데, 업로드 게이트는 인코딩 크기(50MiB)만
                # 보므로 고압축 이미지가 디코드 후 거대한 캔버스로 펼쳐지면 타일 루프가
                # 폭주한다. 초과 시 핸들러가 추론 전에 거절(400 → BAD_REQUEST)해 에이전트가
                # 곧바로 degrade 한다 — 긴 타임아웃을 끝까지 태우지 않는다.
                resp = await client.post(
                    endpoint,
                    json={
                        "inputs": image_url,
                        "parameters": {
                            "threshold": _resolve_threshold(settings),
                            "mask_threshold": settings.hf_segmentation_mask_threshold,
                            "max_tiles": settings.hf_segmentation_max_tiles,
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
            return _parse_ok(data, expected_vocab=_expected_vocab_version(settings))
    finally:
        if owns_client:
            await client.aclose()
