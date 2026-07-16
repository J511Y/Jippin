"""확장 신고 ↔ 변동사항 LLM 대조 판정(home_check_extension) 단위 테스트.

LLM 호출은 fake ``invoke`` 로 주입해 네트워크 없이 검증한다. 실제 판정 지능(모델)이 아니라
**프롬프트 조립·응답 파싱·verdict 정규화·규칙3 단락·degrade** 계약을 검증한다. few-shot
프롬프트가 4개 정본 규칙을 담고 있는지는 build_messages 로 확인한다.
"""

from __future__ import annotations

import json

import pytest

from src.services.home_check_extension import (
    ExtensionJudgment,
    build_messages,
    judge_extension,
    parse_judgment,
)


class _Resp:
    """langchain ainvoke 반환(.content) 흉내."""

    def __init__(self, content):
        self.content = content


def _fake_invoke(payload):
    """messages 를 무시하고 고정 응답을 돌려주는 invoke 팩토리."""

    async def _invoke(messages):
        return _Resp(payload)

    return _invoke


def _echo_last_user_invoke():
    """마지막 user 메시지(실입력)를 그대로 되돌려 프롬프트 조립을 관찰하는 invoke."""

    async def _invoke(messages):
        return _Resp(messages[-1]["content"])

    return _invoke


class _Settings:
    agent_model = "openai:gpt-5.4-mini"
    openai_api_key = None  # _build_invoke 는 쓰지 않는다(invoke 주입).
    openai_store_logs = False
    extension_judge_timeout_seconds = 5.0


# ---------------------------------------------------------------------------
# 프롬프트 조립 — few-shot 이 4개 정본 규칙을 담는가.
# ---------------------------------------------------------------------------
def test_build_messages_has_system_and_fewshot():
    msgs = build_messages("거실", [{"date": "2015.03.02", "reason": "신규작성(신축)"}])
    assert msgs[0]["role"] == "system"
    assert "위반건축물" in msgs[0]["content"]
    # few-shot user/assistant 쌍이 있고, assistant 예시는 유효 JSON verdict 를 담는다.
    assistants = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert len(assistants) >= 4
    verdicts = {json.loads(a)["verdict"] for a in assistants}
    assert {"legal", "violation", "uncertain"} <= verdicts
    # 마지막은 실제 입력.
    assert msgs[-1]["role"] == "user"
    assert "거실" in msgs[-1]["content"]
    assert "신규작성(신축)" in msgs[-1]["content"]


def test_build_messages_change_history_variants():
    # dict(reason) / ChangeEntry 유사 객체 / 문자열 모두 관용해야 한다.
    class _CE:
        date = "2010.12.17"
        reason = "행위허가 사용검사 처리 〈발코니 확장/거실/5.344㎡〉"

    msgs = build_messages("거실", [_CE(), "소유권 이전", {"reason": "신규작성"}])
    last = msgs[-1]["content"]
    assert "발코니 확장/거실" in last
    assert "소유권 이전" in last


def test_build_messages_empty_change_history():
    msgs = build_messages("거실", [])
    assert "(변동사항 없음)" in msgs[-1]["content"]


# ---------------------------------------------------------------------------
# 응답 파싱 — 코드펜스/무효 verdict/부분필드.
# ---------------------------------------------------------------------------
def test_parse_judgment_plain_json():
    j = parse_judgment(
        '{"verdict":"violation","reason":"거실 미등재","reported_areas":["거실"],'
        '"matched_areas":[],"unrecorded_areas":["거실"]}'
    )
    assert isinstance(j, ExtensionJudgment)
    assert j.verdict == "violation"
    assert j.unrecorded_areas == ["거실"]


def test_parse_judgment_codefence_and_prose():
    text = '설명\n```json\n{"verdict":"legal","reason":"ok"}\n```\n끝'
    j = parse_judgment(text)
    assert j is not None and j.verdict == "legal"
    assert j.reason == "ok"


def test_parse_judgment_langchain_blocks():
    blocks = [{"type": "text", "text": '{"verdict":"uncertain","reason":"모호"}'}]
    j = parse_judgment(blocks)
    assert j is not None and j.verdict == "uncertain"


def test_parse_judgment_invalid_verdict_is_none():
    assert parse_judgment('{"verdict":"maybe","reason":"?"}') is None
    assert parse_judgment("not json") is None
    assert parse_judgment('{"reason":"no verdict"}') is None


def test_parse_judgment_missing_reason_gets_default():
    j = parse_judgment('{"verdict":"violation"}')
    assert j is not None and j.reason  # 기본 사유 채움


def test_parse_judgment_reconciles_unrecorded_to_violation():
    # 모델 자기모순(verdict=legal/uncertain 인데 미기재 부위 있음) → violation 으로 승격.
    for v in ("legal", "uncertain"):
        j = parse_judgment(
            '{"verdict":"' + v + '","reason":"x","unrecorded_areas":["침실"]}'
        )
        assert j is not None and j.verdict == "violation", v
        assert j.unrecorded_areas == ["침실"]


# ---------------------------------------------------------------------------
# judge_extension — 규칙3 단락, degrade, 정상 경로.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reported_none_returns_none():
    # 사용자가 확장 질문에 답하지 않음 → 리포트에 확장판정 미포함.
    out = await judge_extension(
        reported_extension=None,
        extended_areas=None,
        change_history=[],
        settings=_Settings(),
        invoke=_fake_invoke("should-not-be-called"),
    )
    assert out is None


@pytest.mark.asyncio
async def test_reported_false_is_legal_without_llm():
    # 규칙 3: '확장 없음' → 무조건 legal, LLM 미호출.
    called = {"n": 0}

    async def _invoke(messages):
        called["n"] += 1
        return _Resp('{"verdict":"violation","reason":"x"}')

    out = await judge_extension(
        reported_extension=False,
        extended_areas=None,
        change_history=[{"reason": "신규작성"}],
        settings=_Settings(),
        invoke=_invoke,
    )
    assert out is not None and out.verdict == "legal"
    assert called["n"] == 0  # LLM 호출 안 함


@pytest.mark.asyncio
async def test_reported_true_uses_llm_verdict():
    out = await judge_extension(
        reported_extension=True,
        extended_areas="거실, 침실",
        change_history=[
            {"date": "2010.12.17", "reason": "행위허가 사용검사 〈발코니 확장/거실〉"}
        ],
        settings=_Settings(),
        invoke=_fake_invoke(
            '{"verdict":"violation","reason":"침실 미등재","reported_areas":["거실","침실"],'
            '"matched_areas":["거실"],"unrecorded_areas":["침실"]}'
        ),
    )
    assert out is not None
    assert out.verdict == "violation"
    assert out.matched_areas == ["거실"]
    assert out.unrecorded_areas == ["침실"]


@pytest.mark.asyncio
async def test_llm_failure_degrades_to_uncertain():
    async def _boom(messages):
        raise RuntimeError("timeout")

    out = await judge_extension(
        reported_extension=True,
        extended_areas="거실",
        change_history=[],
        settings=_Settings(),
        invoke=_boom,
    )
    assert out is not None and out.verdict == "uncertain"


@pytest.mark.asyncio
async def test_llm_unparsable_degrades_to_uncertain():
    out = await judge_extension(
        reported_extension=True,
        extended_areas="거실",
        change_history=[],
        settings=_Settings(),
        invoke=_fake_invoke("완전히 이상한 응답 no json"),
    )
    assert out is not None and out.verdict == "uncertain"


@pytest.mark.asyncio
async def test_empty_areas_still_calls_llm_with_placeholder():
    # reported=True 인데 부위 미상 → 플레이스홀더로 LLM 대조(uncertain 유도 가능).
    out = await judge_extension(
        reported_extension=True,
        extended_areas="   ",
        change_history=[{"reason": "신규작성"}],
        settings=_Settings(),
        invoke=_echo_last_user_invoke(),
    )
    # echo invoke 는 user 텍스트를 content 로 돌려주므로 파싱 실패 → uncertain degrade.
    assert out is not None and out.verdict == "uncertain"
