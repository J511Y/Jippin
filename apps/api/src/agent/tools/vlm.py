"""AI-002 VLM 도면 문맥 해석 (SDD §4.4, 기능명세서 §2.4 AI-002).

Mask2Former(AI-001) 세그멘테이션 결과를 **OpenAI Vision**(설정 ``vlm_model``, 미설정 시
대화 에이전트의 ``agent_model`` 상속)으로 보완한다 —
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

#: 내부(도구 안) LLM 호출 식별 태그. LangGraph ``stream_mode="messages"`` 는 그래프
#: 안에서 도는 **모든** chat model 콜백을 스트림에 싣는데, 도구 실행 중의 VLM 호출도
#: config 전파(contextvars)로 같은 스트림에 잡혀 구조화 JSON 출력이 채팅 토큰으로
#: 노출된다(#vlm-token-leak). 런너의 translate_stream 이 이 태그로 걸러낸다.
INTERNAL_LLM_TAG = "jippin-internal-llm"

#: VLM 전체 신뢰도(confidence)가 이 값 미만이면 ANALYSIS_LOW_CONFIDENCE — 재확인 권장.
#: 영역별 평가(region_assessments)를 룰 입력(창호 경계)으로 **자동 승격하는 경로도 이
#: 문턱을 지킨다**: 저신뢰 추측이 HOLD 를 우회해 확정 판정이 되지 않게(#low-conf-gate).
LOW_CONFIDENCE_THRESHOLD = 0.6


def is_low_confidence(supplement: dict[str, Any] | None) -> bool:
    """vlm_supplement 의 confidence 가 문턱 미만이면 True(없거나 None 이면 False)."""

    if not isinstance(supplement, dict):
        return False
    conf = supplement.get("confidence")
    return (
        isinstance(conf, (int, float))
        and not isinstance(conf, bool)
        and conf < LOW_CONFIDENCE_THRESHOLD
    )


def remap_region_assessments(
    assessments: list[dict[str, Any]], regions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """VLM 평가의 region_id 를 **최종 region id 로 옮긴다**(#assessment-remap).

    VLM 은 1차 병합본 id(pred:N / merged:N)를 보고 평가하지만, 그 뒤 교정 재병합
    (vlm-merged:N)과 내력벽 우선 잘라내기(``{id}~digest``)가 id 를 바꾼다. 그대로 두면
    선택 벽에 평가가 붙지 않아 종합 판단이 정확히 교정된 도면에서만 사라진다. 최종
    region 의 출처 id(자기 id → 병합 구성원 ``member_ids`` → 잘라내기 전 base id)를
    차례로 대조해 첫 일치 평가를 최종 id 로 복사한다. 출처가 없는 평가는 버린다.
    """

    by_id = {
        a["region_id"]: a
        for a in assessments
        if isinstance(a, dict) and isinstance(a.get("region_id"), str)
    }
    if not by_id:
        return []
    out: list[dict[str, Any]] = []
    for r in regions:
        if not isinstance(r, dict) or not isinstance(r.get("region_id"), str):
            continue
        rid = r["region_id"]
        candidates: list[str] = [rid]
        base = rid.split("~", 1)[0]
        if base != rid:
            candidates.append(base)
        members = r.get("member_ids")
        if isinstance(members, list):
            for m in members:
                if isinstance(m, str):
                    candidates.append(m)
                    mbase = m.split("~", 1)[0]
                    if mbase != m:
                        candidates.append(mbase)
        for cand in candidates:
            found = by_id.get(cand)
            if found is not None:
                out.append({**found, "region_id": rid})
                break
    return out


_SYSTEM_PROMPT = (
    "당신은 한국 아파트 평면도를 검토하는 분석가입니다. 자동 세그멘테이션 모델"
    "(Mask2Former)이 벽과 공간을 분류했는데, 특히 벽 종류(내력벽/비내력벽) 분류 정확도가"
    " 낮습니다. 첨부된 평면도 이미지를 직접 보고 다음을 JSON 으로만 답하세요(설명 텍스트"
    " 금지):\n"
    "1) is_floorplan: 이미지가 실제 평면도면 true.\n"
    "2) confidence: 전체 분석 신뢰도 0~1.\n"
    "3) notes: 철거 검토에 도움되는 관찰/주의점(공간 명칭 확인, 애매한 경계, 구조 의심 등)"
    " 한국어 문장 배열. 확정 단정은 금지하고 '후보/추정/확인 필요' 어휘만 씁니다."
    " 창호(window) 영역이 있으면 각 창호가 외기(건물 바깥)와 직접 접하는 바깥쪽 창인지,"
    " 발코니와 실내(거실 등) 사이의 경계 창인지 관찰을 region_id 와 함께 남기세요"
    " (예: 'pred:7 은 거실-발코니 경계 창호로 추정').\n"
    "4) reclassifications: 명백히 잘못 분류된 벽이 있으면 교정 목록. 각 항목은 "
    "{object_id, new_label, reason}. object_id 는 아래 제공된 region_id 만, new_label 은 "
    "다음 벽 클래스 어휘만 사용: wall_reinforced_concrete(철근콘크리트 내력벽 후보), "
    "wall_nonbearing(비내력벽 후보), wall_other(도면만으로 구조를 가르기 어려운 미확정 "
    "벽). wall_other 로 분류된 벽이 도면 표기(해칭/두께/구조 기호)로 내력·비내력이 "
    "명백하면 wall_reinforced_concrete/wall_nonbearing 으로 교정하고, 반대로 다른 벽이라도 "
    "구조를 확신할 수 없으면 wall_other 로 교정할 수 있습니다. 확신이 없으면 "
    "비웁니다(빈 배열).\n"
    "5) judgment_hints: 도면에서 **직접 읽을 수 있는 것만** 채우고, 안 보이거나 확신이 "
    "없으면 각 항목을 null 로 두세요(절대 추측 금지). 이 값들은 리모델링 규정 판단의 입력이 "
    "되므로 정확해야 합니다. 각 항목:\n"
    "   - has_sprinkler: 천장 스프링클러 헤드 심볼(원/십자 등)이 발코니·거실에 보이면 true, "
    "명확히 없으면 false, 모르면 null.\n"
    "   - has_evacuation_space: 대피공간 또는 경량칸막이(파괴 가능 경계벽) 표기가 보이면 "
    "true, 명확히 없으면 false, 모르면 null.\n"
    "   - stairwell_count: 도면에 보이는 계단실(직통계단) 개수를 정수로. 모르면 null.\n"
    "   - window_form: 외부(발코니) 창호가 고정형(입면분할창)이면 FIXED, 여닫이 OPENABLE, "
    "접이 FOLDING, 미닫이 SLIDING, 그 외 OTHER, 모르면 null.\n"
    "   - fire_zone: 방화구획선/표기가 철거 대상 부위에 걸치면 true, 명확히 없으면 false, "
    "모르면 null.\n"
    "   - balcony_attached: 사용자가 고른(또는 검토 중인) 철거 대상 벽이 발코니와 접하면 "
    "true(발코니 확장에 해당), 발코니와 무관한 실내 공간 사이 벽이면 false, 모르면 null.\n"
    "6) region_assessments: 아래 제공된 **벽(wall_*)과 창호(window) region 각각**에 대한 "
    "구조화 평가 배열. 사용자가 나중에 이 중 어느 것을 골라도 대화 에이전트가 위치와 구조 "
    "의견을 바로 말할 수 있도록 **모든 벽·창호 region 을 빠짐없이** 채웁니다. 각 항목:\n"
    "   - region_id: 제공된 region_id 그대로.\n"
    "   - location: 그 벽/창이 도면상 어디에 있는지 비전문가가 알아듣는 생활어 한 구절 "
    "(예: '거실과 침실1 사이', '주방 옆 다용도실 쪽', '거실과 발코니 사이', "
    "'침실2 바깥쪽 외벽 창'). 공간 이름은 도면 표기를 우선합니다.\n"
    "   - assessment: 벽이면 NON_LOAD_BEARING(비내력 추정)/LOAD_BEARING(내력 추정)/"
    "UNCERTAIN(도면만으로 판단 어려움) 중 하나. 창호면 BALCONY_BOUNDARY(발코니와 실내 "
    "사이 경계 창, 흔히 분합창)/EXTERIOR(외기와 직접 닿는 최외곽 창)/UNCERTAIN 중 하나. "
    "창호 판단 기준: 창의 한쪽이 발코니 공간이고 다른 쪽이 거실·침실 등 실내면 "
    "BALCONY_BOUNDARY, 창의 한쪽이 도면 바깥(외기)이면 EXTERIOR. 확신이 없으면 "
    "UNCERTAIN 으로 두고 추측하지 않습니다.\n"
    "   - reason: 그렇게 본 근거 한 문장(두께·해칭·기호·인접 공간 등).\n"
    '출력 예: {"is_floorplan":true,"confidence":0.7,"notes":["..."],'
    '"reclassifications":[{"object_id":"pred:5","new_label":'
    '"wall_reinforced_concrete","reason":"..."}],'
    '"judgment_hints":{"has_sprinkler":null,"has_evacuation_space":true,'
    '"stairwell_count":2,"window_form":"FIXED","fire_zone":false,'
    '"balcony_attached":false},'
    '"region_assessments":[{"region_id":"pred:3","location":"거실과 침실1 사이",'
    '"assessment":"NON_LOAD_BEARING","reason":"얇은 단선 벽체로 표기"},'
    '{"region_id":"pred:7","location":"거실과 발코니 사이",'
    '"assessment":"BALCONY_BOUNDARY","reason":"한쪽이 발코니, 다른 쪽이 거실"}]}'
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


#: VLM 교정이 허용되는 라벨 — 벽 3종만. 프롬프트가 벽 교정만 지시하지만, 모델이
#: 계약 밖 교정(창→벽, 벽→공간)을 내면 오버레이/판단객체가 그대로 오염돼 창호가
#: '확정 비내력벽'으로 선택·평가될 수 있다 — 정규화에서 강제한다(#vlm-wall-only).
_WALL_LABELS: frozenset[str] = frozenset(
    label for label in _KNOWN_LABELS if label.startswith("wall_")
)


def _normalize_supplement(
    data: dict[str, Any],
    *,
    model: str,
    valid_ids: set[str],
    window_ids: set[str] | None = None,
) -> dict[str, Any]:
    """VLM 출력 정규화. ``valid_ids`` 는 **벽 region 만** 담아야 한다(호출자 책임) —
    교정의 원본도 벽, 교정 라벨도 벽(_WALL_LABELS)으로 이중 강제한다. ``window_ids``
    는 창호 region — 영역별 평가(region_assessments)의 창호 어휘 검증에만 쓴다."""

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
        if oid in valid_ids and new_label in _WALL_LABELS:
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
        # **명시적 boolean False 만** '평면도 아님'으로 본다. null/누락/형식오류(불확실)는
        # True 로 둔다 — `bool(None)` 이 False 로 강등되면 세그멘테이션이 이미 영역을 찾은
        # 유효 도면이 NOT_FLOORPLAN 으로 막혀 다른 이미지를 다시 요구하게 된다(#explicit-
        # false-only, segment_session_floorplan 의 not-floorplan 게이트가 이 값을 본다).
        "is_floorplan": data.get("is_floorplan") is not False,
        "judgment_hints": _normalize_hints(data.get("judgment_hints")),
        "region_assessments": _normalize_assessments(
            data.get("region_assessments"),
            wall_ids=valid_ids,
            window_ids=window_ids or set(),
        ),
    }


#: VLM 이 도면에서 읽어낸 룰 입력 힌트의 어휘/타입. 값은 계약 JudgmentValues 와 동일.
_HINT_WINDOW_FORMS: frozenset[str] = frozenset(
    {"FIXED", "OPENABLE", "FOLDING", "SLIDING", "OTHER"}
)


def _normalize_hints(raw: Any) -> dict[str, Any]:
    """VLM judgment_hints 를 엄격 정규화 — 어휘/타입 밖은 None(미확인)으로 강등.

    각 값은 evaluate_rules 가 judgment_values 로 그대로 병합할 수 있는 형태다(계약
    JudgmentValues 어휘). 모르면 null 로 두라고 지시했으므로, 누락/형식오류도 None 으로
    수렴해 '확인 안 됨 → 보수적 가정 + caveat' 경로(룰엔진 v2)로 흐른다.
    """

    if not isinstance(raw, dict):
        return {}

    def _bool(key: str) -> bool | None:
        v = raw.get(key)
        return v if isinstance(v, bool) else None

    def _int(key: str) -> int | None:
        v = raw.get(key)
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

    window = raw.get("window_form")
    return {
        "has_sprinkler": _bool("has_sprinkler"),
        "has_evacuation_space": _bool("has_evacuation_space"),
        "stairwell_count": _int("stairwell_count"),
        "window_form": window if window in _HINT_WINDOW_FORMS else None,
        "fire_zone": _bool("fire_zone"),
        "balcony_attached": _bool("balcony_attached"),
    }


#: 영역별 평가 어휘(#region-assessments). 벽/창호로 어휘가 갈리고, 어휘 밖·누락은
#: UNCERTAIN 으로 강등한다 — 대화 에이전트가 '확신 없음'을 확인 질문으로 잇게 한다.
_WALL_ASSESSMENTS: frozenset[str] = frozenset(
    {"NON_LOAD_BEARING", "LOAD_BEARING", "UNCERTAIN"}
)
_WINDOW_ASSESSMENTS: frozenset[str] = frozenset(
    {"BALCONY_BOUNDARY", "EXTERIOR", "UNCERTAIN"}
)
_MAX_ASSESSMENTS = 60
_MAX_LOCATION_CHARS = 80
_MAX_REASON_CHARS = 200


def _normalize_assessments(
    raw: Any, *, wall_ids: set[str], window_ids: set[str]
) -> list[dict[str, Any]]:
    """VLM 영역별 평가(region_assessments)를 엄격 정규화한다.

    - region_id 는 세그멘테이션이 낸 벽·창호 id 만(유효 id 밖은 드롭, 중복은 첫 항목).
    - kind 는 id 의 출처(벽/창호)로 서버가 정하고, assessment 는 kind 별 어휘 밖이면
      UNCERTAIN 으로 강등한다(창호 어휘를 벽에 붙이는 등의 계약 밖 출력 차단).
    - location/reason 은 문자열만, 길이 제한. location 이 비면 항목을 드롭한다 — 위치
      없는 평가는 에이전트가 사용자에게 짚어 줄 수 없어 쓸모가 없다.
    """

    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if len(out) >= _MAX_ASSESSMENTS:
            break
        if not isinstance(item, dict):
            continue
        rid = item.get("region_id")
        if not isinstance(rid, str) or rid in seen:
            continue
        if rid in wall_ids:
            kind, vocab = "wall", _WALL_ASSESSMENTS
        elif rid in window_ids:
            kind, vocab = "window", _WINDOW_ASSESSMENTS
        else:
            continue
        location = item.get("location")
        location = location.strip() if isinstance(location, str) else ""
        if not location:
            continue
        assessment = item.get("assessment")
        if not isinstance(assessment, str) or assessment.upper() not in vocab:
            assessment = "UNCERTAIN"
        reason = item.get("reason")
        reason = reason.strip() if isinstance(reason, str) else ""
        seen.add(rid)
        out.append(
            {
                "region_id": rid,
                "kind": kind,
                "location": location[:_MAX_LOCATION_CHARS],
                "assessment": assessment.upper(),
                "reason": reason[:_MAX_REASON_CHARS],
            }
        )
    return out


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
    # VLM 전용 override(vlm_model). 미설정/빈 문자열/구 테스트 스텁이면 agent_model 로
    # 폴백한다 — 형식·키 검증은 아래에서 동일하게 적용.
    model_str = getattr(settings, "vlm_model", None) or settings.agent_model
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

        # store 는 openai_store_logs 가 켜진 경우에만 — 도면 이미지 URL/영역 다이제스트가
        # 프로바이더 Logs 에 저장되지 않게 기본 미저장(프로덕션 보호).
        model = ChatOpenAI(
            model=model_str.split(":", 1)[1],
            api_key=api_key,
            max_retries=1,
            use_responses_api=True,
            store=getattr(settings, "openai_store_logs", False),
            # 내부 호출 태그 — 에이전트 런 안에서 실행될 때 이 호출의 콜백 이벤트가
            # SSE 토큰으로 새지 않게 translate_stream 이 필터한다(#vlm-token-leak).
            tags=[INTERNAL_LLM_TAG],
            extra_body={
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
    # 교정 대상은 **벽 region 만** — 창/공간 region 을 벽으로 바꾸는 계약 밖 교정을
    # 원천 차단한다(#vlm-wall-only).
    valid_ids = {
        str(r.get("region_id"))
        for r in regions
        if isinstance(r, dict) and str(r.get("class_name") or "") in _WALL_LABELS
    }
    window_ids = {
        str(r.get("region_id"))
        for r in regions
        if isinstance(r, dict) and str(r.get("class_name") or "") == "window"
    }
    supplement = _normalize_supplement(
        data,
        model=model_str.split(":", 1)[1],
        valid_ids=valid_ids,
        window_ids=window_ids,
    )
    log.info(
        "vlm_interpret_completed",
        notes=len(supplement["notes"]),
        reclassifications=len(supplement["reclassifications"]),
        region_assessments=len(supplement["region_assessments"]),
        confidence=supplement["confidence"],
        is_floorplan=supplement["is_floorplan"],
    )
    return supplement
