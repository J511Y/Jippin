"""AI-002 VLM 도면 문맥 해석 (SDD §4.4, 기능명세서 §2.4 AI-002).

Mask2Former(AI-001) 세그멘테이션 결과를 **OpenAI Vision(gpt-5.4-mini)**으로 보완한다 —
도면 이미지를 직접 보고 (1) 잘못 분류된 벽 레이블 교정(reclassifications), (2) 공간 명칭·
경계 모호 영역 자연어 해석(notes), (3) 전체 신뢰도/도면 여부를 낸다. LangChain 추상화로
프로바이더 교체 가능(SDD §4.4 "VLM 프로바이더").

호출부(segment_session_floorplan)가 ① 세그멘테이션 + ② 본 VLM 결과를 머지(AI-003)해
공통 판단 스키마(wall_objects/space_objects/vlm_supplement)로 정규화한다.

어떤 실패(미설정/타임아웃/파싱오류)도 raise 하지 않고 None 을 돌려 **세그멘테이션 단독으로
degrade** 한다(VLM_TIMEOUT). VLM 은 보완 단계이지 필수 경로가 아니다.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from ...logging import get_logger
from .segmentation import _KNOWN_LABELS

if TYPE_CHECKING:
    from ...config import Settings

log = get_logger("zippin.agent.tools.vlm")

_SYSTEM_PROMPT = (
    "당신은 한국 아파트 평면도를 검토하는 분석가입니다. 자동 세그멘테이션 모델"
    "(Mask2Former)이 벽과 공간을 분류했는데, 특히 벽 종류(내력벽/비내력벽) 분류 정확도가"
    " 낮습니다. 첨부된 평면도 이미지를 직접 보고 다음을 JSON 으로만 답하세요(설명 텍스트"
    " 금지):\n"
    "1) is_floorplan: 이미지가 실제 평면도면 true.\n"
    "2) confidence: 전체 분석 신뢰도 0~1.\n"
    "3) notes: 철거 검토에 도움되는 관찰/주의점(공간 명칭 확인, 애매한 경계, 구조 의심 등)"
    " 한국어 문장 배열. 확정 단정은 금지하고 '후보/추정/확인 필요' 어휘만 씁니다.\n"
    "4) reclassifications: 명백히 잘못 분류된 벽이 있으면 교정 목록. 각 항목은 "
    "{object_id, new_label, reason}. object_id 는 아래 제공된 region_id 만, new_label 은 "
    "제공된 클래스 어휘만 사용. 확신이 없으면 비웁니다(빈 배열).\n"
    '출력 예: {"is_floorplan":true,"confidence":0.7,"notes":["..."],'
    '"reclassifications":[{"object_id":"pred:5","new_label":'
    '"wall_reinforced_concrete","reason":"..."}]}'
)


def _centroid_norm(polygon: list[float], w: int, h: int) -> tuple[float, float]:
    xs = polygon[0::2]
    ys = polygon[1::2]
    if not xs or not ys or w <= 0 or h <= 0:
        return (0.0, 0.0)
    return (round(sum(xs) / len(xs) / w, 2), round(sum(ys) / len(ys) / h, 2))


def _region_digest(regions: list[dict[str, Any]], image: dict[str, Any] | None) -> str:
    """VLM 이 region 을 이미지 위치와 대응시킬 수 있도록 region_id·클래스·정규화 중심점을
    압축 텍스트로 만든다((0,0)=좌상단, (1,1)=우하단)."""
    w = int(image.get("width")) if isinstance(image, dict) and image.get("width") else 0
    h = (
        int(image.get("height"))
        if isinstance(image, dict) and image.get("height")
        else 0
    )
    lines: list[str] = []
    for r in regions:
        if not isinstance(r, dict):
            continue
        cx, cy = _centroid_norm(r.get("polygon") or [], w, h)
        lines.append(f"{r.get('region_id')} {r.get('class_name')} @({cx},{cy})")
    return "\n".join(lines)


def _parse_json(text: Any) -> dict[str, Any] | None:
    if isinstance(text, list):  # langchain content blocks
        text = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in text
        )
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):  # 코드펜스 제거
        s = s.strip("`")
        s = s[s.find("{") :] if "{" in s else s
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(s[start : end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_supplement(
    data: dict[str, Any], *, model: str, valid_ids: set[str]
) -> dict[str, Any]:
    notes = [
        str(n).strip()
        for n in (data.get("notes") or [])
        if isinstance(n, str) and n.strip()
    ][:8]
    reclass: list[dict[str, Any]] = []
    for item in data.get("reclassifications") or []:
        if not isinstance(item, dict):
            continue
        oid = item.get("object_id")
        new_label = item.get("new_label")
        if oid in valid_ids and new_label in _KNOWN_LABELS:
            reclass.append(
                {
                    "object_id": str(oid),
                    "new_label": str(new_label),
                    "reason": str(item.get("reason") or "")[:200],
                }
            )
    conf = data.get("confidence")
    confidence = (
        float(conf) if isinstance(conf, (int, float)) and 0 <= conf <= 1 else None
    )
    return {
        "provider": "OPENAI",
        "model": model,
        "notes": notes,
        "reclassifications": reclass[:20],
        "confidence": confidence,
        "is_floorplan": bool(data.get("is_floorplan", True)),
    }


async def interpret_floorplan_impl(
    *,
    image_url: str,
    regions: list[dict[str, Any]],
    image: dict[str, Any] | None,
    settings: "Settings",
    user_context: str | None = None,
) -> dict[str, Any] | None:
    """AI-002 — 도면 이미지 + Mask2Former regions 를 VLM 으로 해석해 vlm_supplement 를
    돌려준다(없거나 실패면 None=세그멘테이션 단독 degrade)."""

    if not getattr(settings, "vlm_floorplan_enabled", False):
        return None
    model_str = settings.agent_model
    api_key = settings.openai_api_key
    if (
        not isinstance(model_str, str)
        or not model_str.startswith("openai:")
        or not api_key
    ):
        return None
    if not regions:
        return None

    digest = _region_digest(regions, image)
    user_text = (
        "Mask2Former 가 분류한 영역(region_id 클래스 @정규화중심):\n"
        f"{digest}\n\n"
        "위 분류를 참고하되 **이미지를 직접 보고** 보완·교정하세요."
    )
    if user_context:
        user_text += f"\n\n참고 사용자 맥락: {user_context[:300]}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url, "detail": "high"},
                },
            ],
        },
    ]

    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=model_str.split(":", 1)[1],
            api_key=api_key,
            max_retries=1,
            store=True,
            model_kwargs={
                "metadata": {"app": "jippin-vlm", "env": str(settings.app_env)}
            },
        )
        resp = await asyncio.wait_for(
            model.ainvoke(messages),
            timeout=float(settings.vlm_floorplan_timeout_seconds),
        )
    except Exception as exc:  # noqa: BLE001 - 타임아웃/네트워크/SDK 모두 degrade(VLM_TIMEOUT)
        log.info("vlm_interpret_degraded", error_type=type(exc).__name__)
        return None

    data = _parse_json(getattr(resp, "content", None))
    if not data:
        log.info("vlm_interpret_unparsable")
        return None
    valid_ids = {str(r.get("region_id")) for r in regions if isinstance(r, dict)}
    supplement = _normalize_supplement(
        data, model=model_str.split(":", 1)[1], valid_ids=valid_ids
    )
    log.info(
        "vlm_interpret_completed",
        notes=len(supplement["notes"]),
        reclassifications=len(supplement["reclassifications"]),
        confidence=supplement["confidence"],
        is_floorplan=supplement["is_floorplan"],
    )
    return supplement
