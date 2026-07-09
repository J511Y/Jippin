"""우리집 체크 — 사용자 신고 확장 vs 대장 변동사항 LLM 대조 판정.

'우리집 체크'의 핵심 목적: 아파트를 거래하는 매수자·중개인이 신고한 '확장·개조된 공간'이
건축물대장 **변동사항**(resChangeList)에 등재돼 있는지 대조하는 것이다. 신고했는데 대장에
대응 기재가 없으면 **사용신고 없이 확장한 미등재(위반건축물) 소지**다 — 갑지의 공식
'위반건축물'(노란딱지) 표시와는 **별개 축**의 판정이다.

판정은 rule-base 가 아니라 **LLM few-shot** 이다(운영자 지시). 부위 명칭의 동의어·부분일치·
모호성(거실=거실, 안방≈침실, 베란다=발코니, "발코니 확장 〈…거실…〉" 등)을 사람처럼 대조해야
하기 때문이다. 판정 규칙(운영자 정본 예시):

  1) 사용자가 확장을 신고했으나 변동사항에 관련 기재가 **없음**              → violation(위반건축물)
  2) 사용자가 확장을 신고했고 변동사항에 관련 기재가 **있음**              → legal(적법)
  3) 사용자가 '확장된 부분 **없음**'이라고 함                              → legal(무조건 적법)
  4) 사용자가 '침실+거실'을 신고했으나 변동사항엔 '거실'만 기재            → violation(누락 부위 존재)

그 외 예상 케이스는 few-shot 예시에 준해 LLM 이 합리적으로 판단한다. **주의**: 기재가
'행위허가'까지만 있고 '사용검사'가 없더라도, 부위가 변동사항에 **기재되어 있으면** 규칙상
'기재됨'(legal)으로 본다 — 사용검사 완결 여부는 이 판정의 기준이 아니다(운영자 확정).

실패(미설정/타임아웃/파싱오류)는 raise 하지 않고 verdict='uncertain'(확인필요)으로 degrade
한다 — LLM 대조는 보조 축이며, 공식 위반표시·신호는 home_check._judge 가 별도로 판정한다.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..logging import get_logger

if TYPE_CHECKING:
    from ..config import Settings

log = get_logger("zippin.home_check.extension")

Verdict = str  # "violation" | "legal" | "uncertain"

_VERDICTS = frozenset({"violation", "legal", "uncertain"})


@dataclass(frozen=True)
class ExtensionJudgment:
    """확장 신고 ↔ 변동사항 대조 판정 결과(PII-free)."""

    verdict: Verdict
    reason: str
    reported_areas: list[str] = field(default_factory=list)
    matched_areas: list[str] = field(default_factory=list)
    unrecorded_areas: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 프롬프트 (few-shot). vlm.py 와 동일한 JSON-only 규약.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "당신은 대한민국 건축물대장 '변동사항'과, 매수자·중개인이 신고한 확장·개조 부위를 "
    "대조하는 검토 분석가입니다.\n"
    "목적: 신고된 확장·개조가 대장 변동사항에 등재되어 있는지 대조해, 신고했지만 대장에 "
    "기재되지 않은 '미신고(미등재) 확장'을 찾아냅니다. 이는 사용신고 없이 확장한 위반건축물 "
    "소지입니다.\n\n"
    "입력:\n"
    "- [신고한 확장 부위]: 사용자가 확장·개조했다고 신고한 공간(자연어).\n"
    "- [건축물대장 변동사항]: 대장에 기재된 변동 항목들. 각 항목은 날짜와 변동내용 문자열이며, "
    "'행위허가'/'사용검사'/'사용승인'/'신규작성' 등과 확장 부위·면적(예: '발코니 확장/거실/"
    "5.344㎡')이 포함될 수 있습니다.\n\n"
    "판정(verdict):\n"
    "- \"violation\": 신고한 확장 부위 중, 변동사항에 대응 기재가 전혀 없는 부위가 하나라도 "
    "있으면.\n"
    "- \"legal\": 신고한 모든 확장 부위가 변동사항에 대응 기재가 있으면. (사용자가 '확장 없음'"
    "이라고 신고한 경우도 legal.)\n"
    "- \"uncertain\": 신고 부위가 특정되지 않거나 변동내용이 불명확해 대조를 단정할 수 없을 때.\n\n"
    "대조 원칙:\n"
    "- 부위 명칭은 동의어·유사어를 사람처럼 대응시킨다: 거실=거실, 안방≈침실, 베란다=발코니, "
    "다용도실≈보조주방 등. 확신이 서지 않으면 매칭하지 않는다.\n"
    "- '발코니(베란다) 확장'은 거실·침실 등 인접 실을 넓히는 대표적 확장 유형이다. 변동사항의 "
    "'발코니 확장 〈…거실…〉'은 거실 확장 신고와 대응한다.\n"
    "- 기재가 '행위허가'까지만 있고 '사용검사'가 없더라도, 부위가 변동사항에 기재되어 있으면 "
    "'기재됨'(matched)으로 본다. 사용검사 완결 여부는 판정 기준이 아니다.\n"
    "- 부분 일치: 신고 부위 중 일부만 기재돼 있으면(예: 신고=거실+침실, 대장=거실만) 누락 부위"
    "(침실)를 unrecorded_areas 에 넣고 verdict=violation.\n"
    "- 변동사항이 비어 있는데 확장을 신고했다면 전부 미등재 → violation.\n\n"
    "출력은 JSON 만(설명 텍스트·코드펜스 금지):\n"
    '{"verdict":"violation|legal|uncertain","reason":"한국어 한두 문장 근거",'
    '"reported_areas":[신고 부위],"matched_areas":[기재 확인된 부위],'
    '"unrecorded_areas":[신고했으나 미기재된 부위]}\n'
    "reason 은 '대장 변동사항 기준'임을 명확히 하고 단정 표현을 피한다."
)

# few-shot 예시(user 입력 → assistant JSON). 4개 정본 규칙 + 동의어/행위허가-only + uncertain.
_FEWSHOT: list[tuple[str, str]] = [
    (
        "[신고한 확장 부위]\n거실 확장\n\n"
        "[건축물대장 변동사항]\n"
        "1. 2004.11.18 · 사용승인되어 신규작성(신축)\n"
        "2. 2010.12.17 · 건축과-25011호에 의거 행위허가 사용검사 처리 〈발코니 확장/거실/5.344㎡〉",
        '{"verdict":"legal","reason":"신고한 \'거실\' 확장이 2010.12.17 변동사항(발코니 확장/거실 '
        '5.344㎡)에 등재되어 있어 대장 기재와 일치합니다.","reported_areas":["거실"],'
        '"matched_areas":["거실"],"unrecorded_areas":[]}',
    ),
    (
        "[신고한 확장 부위]\n거실 확장\n\n"
        "[건축물대장 변동사항]\n"
        "1. 2015.03.02 · 사용승인되어 신규작성(신축)",
        '{"verdict":"violation","reason":"신고한 \'거실\' 확장에 대응하는 기재가 대장 변동사항에 '
        '없습니다. 사용신고 없이 확장한 미등재(위반건축물) 소지가 있습니다.","reported_areas":["거실"],'
        '"matched_areas":[],"unrecorded_areas":["거실"]}',
    ),
    (
        "[신고한 확장 부위]\n거실과 침실 확장\n\n"
        "[건축물대장 변동사항]\n"
        "1. 2004.11.18 · 신규작성(신축)\n"
        "2. 2010.12.17 · 행위허가 사용검사 처리 〈발코니 확장/거실/5.344㎡〉",
        '{"verdict":"violation","reason":"신고한 \'거실\'은 2010.12.17 변동사항에 등재돼 있으나 '
        "'침실' 확장은 대장 변동사항에서 확인되지 않습니다. 침실 부분은 미등재(위반건축물) 소지가 "
        '있습니다.","reported_areas":["거실","침실"],"matched_areas":["거실"],'
        '"unrecorded_areas":["침실"]}',
    ),
    (
        "[신고한 확장 부위]\n베란다(발코니) 확장, 침실2\n\n"
        "[건축물대장 변동사항]\n"
        "1. 2004.11.18 · 신규작성(신축)\n"
        "2. 2025.08.11 · 주택과-27774호에 의거 행위허가 〈발코니확장/침실2/3.89㎡〉",
        '{"verdict":"legal","reason":"신고한 발코니(=베란다)·침실2 확장이 2025.08.11 변동사항'
        "(발코니확장/침실2 3.89㎡)에 등재되어 있어 대장 기재와 일치합니다. 행위허가 단계까지 "
        '기재된 상태입니다.","reported_areas":["발코니","침실2"],"matched_areas":["발코니","침실2"],'
        '"unrecorded_areas":[]}',
    ),
    (
        "[신고한 확장 부위]\n확장은 했는데 어디인지는 잘 모르겠어요\n\n"
        "[건축물대장 변동사항]\n"
        "1. 2004.11.18 · 신규작성(신축)",
        '{"verdict":"uncertain","reason":"확장을 신고했으나 부위가 특정되지 않아 대장 변동사항과 '
        "정밀 대조가 어렵습니다. 변동사항에 확장 관련 기재가 없어 추가 확인이 필요합니다.\","
        '"reported_areas":[],"matched_areas":[],"unrecorded_areas":[]}',
    ),
]


# ---------------------------------------------------------------------------
# 순수 헬퍼 (I/O 없음 — 단위 테스트 대상).
# ---------------------------------------------------------------------------
def _change_lines(change_history: list[Any]) -> str:
    """변동사항 항목 배열을 번호 매긴 텍스트로. dict/ChangeEntry/문자열 모두 관용."""

    lines: list[str] = []
    for idx, item in enumerate(change_history or [], start=1):
        date = None
        reason = None
        if isinstance(item, dict):
            date = item.get("date") or item.get("resChangeDate")
            reason = item.get("reason") or item.get("resChangeReason")
        else:  # ChangeEntry 등 속성 접근
            date = getattr(item, "date", None)
            reason = getattr(item, "reason", None)
            if reason is None and isinstance(item, str):
                reason = item
        reason = (str(reason).strip() if reason is not None else "")
        if not reason:
            continue
        prefix = f"{idx}. "
        lines.append(f"{prefix}{date} · {reason}" if date else f"{prefix}{reason}")
    return "\n".join(lines) if lines else "(변동사항 없음)"


def _format_user(reported_areas: str, change_history: list[Any]) -> str:
    return (
        f"[신고한 확장 부위]\n{reported_areas.strip()}\n\n"
        f"[건축물대장 변동사항]\n{_change_lines(change_history)}"
    )


def build_messages(reported_areas: str, change_history: list[Any]) -> list[dict[str, str]]:
    """system + few-shot + 실제 입력으로 LLM 메시지 배열을 만든다(순수)."""

    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for user_ex, assistant_ex in _FEWSHOT:
        messages.append({"role": "user", "content": user_ex})
        messages.append({"role": "assistant", "content": assistant_ex})
    messages.append({"role": "user", "content": _format_user(reported_areas, change_history)})
    return messages


def _parse_json(text: Any) -> dict[str, Any] | None:
    """vlm.py 와 동일한 관용 JSON 파서(코드펜스/전후 잡텍스트 허용)."""

    if isinstance(text, list):  # langchain content blocks
        text = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in text
        )
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
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


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out[:20]


def parse_judgment(text: Any) -> ExtensionJudgment | None:
    """LLM 응답 텍스트 → ExtensionJudgment. 파싱 실패/무효 verdict 는 None(호출측이 degrade)."""

    data = _parse_json(text)
    if data is None:
        return None
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in _VERDICTS:
        return None
    reported = _str_list(data.get("reported_areas"))
    matched = _str_list(data.get("matched_areas"))
    unrecorded = _str_list(data.get("unrecorded_areas"))
    reason = str(data.get("reason") or "").strip()[:400]
    # 방어적 정합: violation 인데 미기재 부위가 비었으면 사유만으로도 표시되게 둔다(강제 X).
    return ExtensionJudgment(
        verdict=verdict,
        reason=reason or _default_reason(verdict),
        reported_areas=reported,
        matched_areas=matched,
        unrecorded_areas=unrecorded,
    )


def _default_reason(verdict: Verdict) -> str:
    return {
        "violation": "신고한 확장 부위가 대장 변동사항에서 확인되지 않습니다(추가 확인 필요).",
        "legal": "신고한 확장 부위가 대장 변동사항에 등재되어 있습니다.",
        "uncertain": "대장 변동사항과의 대조 결과가 명확하지 않아 추가 확인이 필요합니다.",
    }.get(verdict, "추가 확인이 필요합니다.")


_UNCERTAIN_FALLBACK = ExtensionJudgment(
    verdict="uncertain",
    reason=(
        "신고하신 확장 내용을 대장 변동사항과 자동으로 대조하지 못했습니다. "
        "변동사항 타임라인을 직접 확인해 주세요."
    ),
)

_NO_EXTENSION = ExtensionJudgment(
    verdict="legal",
    reason="확장·개조된 부분이 없다고 확인하셔서 대장 변동사항 대조가 불필요합니다.",
)


# ---------------------------------------------------------------------------
# 판정 진입점 (I/O). invoke 를 주입하면 LLM 없이 테스트 가능.
# ---------------------------------------------------------------------------
InvokeFn = Callable[[list[dict[str, str]]], Awaitable[Any]]


async def judge_extension(
    *,
    reported_extension: bool | None,
    extended_areas: str | None,
    change_history: list[Any],
    settings: "Settings",
    invoke: InvokeFn | None = None,
) -> ExtensionJudgment | None:
    """확장 신고 ↔ 변동사항 대조 판정.

    - ``reported_extension`` None: 사용자가 확장 질문에 답하지 않음 → None(리포트에 확장판정 미포함).
    - False: '확장 없음' 신고 → 무조건 legal(규칙 3, LLM 미호출).
    - True: LLM few-shot 대조. 실패는 uncertain 으로 degrade.
    """

    if reported_extension is None:
        return None
    if reported_extension is False:
        return _NO_EXTENSION

    areas = (extended_areas or "").strip() or "부위 미상(사용자가 확장은 있다고 함)"
    messages = build_messages(areas, change_history)

    try:
        if invoke is None:
            invoke = _build_invoke(settings)
        resp = await asyncio.wait_for(
            invoke(messages),
            timeout=float(getattr(settings, "extension_judge_timeout_seconds", 20.0)),
        )
    except Exception as exc:  # noqa: BLE001 — 미설정/타임아웃/SDK 모두 degrade
        log.info("extension_judge_degraded", error_type=type(exc).__name__)
        return _UNCERTAIN_FALLBACK

    content = getattr(resp, "content", resp)
    judgment = parse_judgment(content)
    if judgment is None:
        log.info("extension_judge_unparsable")
        return _UNCERTAIN_FALLBACK
    log.info(
        "extension_judge_completed",
        verdict=judgment.verdict,
        reported=len(judgment.reported_areas),
        unrecorded=len(judgment.unrecorded_areas),
    )
    return judgment


def _build_invoke(settings: "Settings") -> InvokeFn:
    """settings.agent_model(openai:*) 로 ChatOpenAI ainvoke 를 만든다(vlm.py 규약).

    키·모델 미설정이면 RuntimeError 를 던져 judge_extension 이 uncertain 으로 degrade 한다.
    """

    model_str = getattr(settings, "agent_model", None)
    api_key = getattr(settings, "openai_api_key", None)
    if not isinstance(model_str, str) or not model_str.startswith("openai:") or not api_key:
        raise RuntimeError("extension_judge: OpenAI 모델/키 미설정")

    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=model_str.split(":", 1)[1],
        api_key=api_key,
        max_retries=1,
        temperature=0,
        store=getattr(settings, "openai_store_logs", False),
        model_kwargs={"metadata": {"app": "jippin-home-check-extension"}},
    )

    async def _invoke(messages: list[dict[str, str]]) -> Any:
        return await model.ainvoke(messages)

    return _invoke
