"""우리집 체크 플로우 도메인 도구 impl — langchain 없이 테스트 가능한 순수 async.

각 impl 은 세션 컨텍스트(session_id/owner_user_id)와 런 컨텍스트(UI 버퍼)를 명시적
인자로 받는다. langchain ``@tool`` 래핑은 ``build_tools()`` 가 closure 로 바인딩한다.

도구는 실제 서비스(services.leads 주소검색, services.home_check CODEF 건축물대장,
services.rule_engine 룰 평가, services.main_flow 세션/도면)에 연결된다. 어떤 도구도
uncaught raise 하지 않고 {ok, error_code} 구조화 결과를 돌려 에이전트가 degrade 한다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from ...errors import ZippinException
from ...logging import get_logger
from ...services import home_check, leads, main_flow, rule_engine

log = get_logger("zippin.agent.tools.domain")

SCHEMA_VERSION = "1.0.0"

# 비-도메인 예외에 노출하는 안정적 사용자 메시지(원본 str(exc) 는 SQL 파라미터·업스트림
# URL·주소 PII 를 담을 수 있어 tool 결과로 반환/영속하지 않는다).
_SAFE_TOOL_ERROR_MESSAGE = (
    "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
)


def _ok(**fields: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "ok": True, **fields}


def _err(error_code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error_code": error_code,
        "message": message,
    }


def _safe_error(exc: Exception, fallback_code: str, *, tool: str) -> dict[str, Any]:
    """예외를 구조화 tool 에러로 변환하되 message 를 정제한다.

    ZippinException(도메인 에러)의 message 는 통제된 사용자 문구라 그대로 노출하지만,
    그 외 예외의 ``str(exc)`` 는 PII/내부 정보를 담을 수 있어 안정적 문구만 반환하고
    원본은 redacted 로그에만 남긴다(runner 가 message 를 output_summary 로 승격해
    영속하므로, #sanitize-tool-message).
    """

    if isinstance(exc, ZippinException):
        return _err(getattr(exc, "code", None) or fallback_code, exc.message)
    # raw 메시지·트레이스백(주소·SQL·URL 가능)은 redaction 안 된 로그에 남기지 않는다 —
    # 안정적 코드/타입만(#no-raw-exc-log).
    log.error(
        "agent_tool_failed",
        tool=tool,
        error_code=fallback_code,
        error_type=type(exc).__name__,
    )
    return _err(fallback_code, _SAFE_TOOL_ERROR_MESSAGE)


async def confirm_address_impl(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
    road_address: str | None = None,
    jibun_address: str | None = None,
    apartment_name: str | None = None,
    building_dong: str | None = None,
    unit_ho: str | None = None,
    floor_no: int | None = None,
    exclusive_area_m2: float | None = None,
) -> dict[str, Any]:
    """세션 주소를 확정/갱신한다(부분 upsert). 충분하면 status 가 address_ready 로 전이."""

    payload = {
        key: value
        for key, value in {
            "road_address": road_address,
            "jibun_address": jibun_address,
            "apartment_name": apartment_name,
            "building_dong": building_dong,
            "unit_ho": unit_ho,
            "floor_no": floor_no,
            "exclusive_area_m2": exclusive_area_m2,
        }.items()
        if value is not None
    }
    # 도로명/지번이 없어도 아파트명(+동/호)만으로 주소를 확정할 수 있게 building_identity 를
    # 구성한다 — 과거엔 "야탑 장미마을 802동 1406호"처럼 도로명 없는 입력이
    # INSUFFICIENT_ADDRESS_DATA 로 거절돼 **아파트명조차 저장 못 해** 보유 도면 검색·세션
    # 주소 컨텍스트가 막혔다(#address-apt-identity). road/jibun 이 이미 있으면 손대지 않는다.
    if not road_address and not jibun_address and apartment_name:
        identity = {
            key: value
            for key, value in {
                "apartment_name": apartment_name,
                "building_dong": building_dong,
                "unit_ho": unit_ho,
            }.items()
            if value
        }
        if identity:
            payload["building_identity"] = identity
    try:
        row = await main_flow.upsert_session_address(
            session_id=session_id,
            owner_user_id=owner_user_id,
            payload=payload,
            owner_is_anonymous=owner_is_anonymous,
        )
    except Exception as exc:  # noqa: BLE001 - 구조화 에러로 변환(에이전트 degrade)
        return _safe_error(exc, "ADDRESS_UPSERT_FAILED", tool="confirm_address")
    return _ok(
        address={
            "road_address": row.get("road_address"),
            "jibun_address": row.get("jibun_address"),
            "apartment_name": row.get("apartment_name"),
            "building_dong": row.get("building_dong"),
            "unit_ho": row.get("unit_ho"),
        },
        summary="주소가 확정되었습니다.",
    )


def build_consultation_handoff_spec(
    *, reason: str | None, prefill_address: str | None, session_id: uuid.UUID
) -> dict[str, Any]:
    """상담 인입 카드(ConsultationHandoff) json-render spec — 서버 구성(LLM 미관여).

    사전검토가 리포트까지 가지 못하고 상담 전환이 필요할 때(HOLD_OR_HANDOFF) 띄운다.
    카드는 안내 문구(reason)와 함께 상담 폼을 보여 주고, 확정된 주소를 prefill 한다.
    """

    props: dict[str, Any] = {"from_session": str(session_id)}
    if isinstance(reason, str) and reason.strip():
        props["reason"] = reason.strip()
    if isinstance(prefill_address, str) and prefill_address.strip():
        props["prefill_address"] = prefill_address.strip()
    return {
        "root": "ch",
        "elements": {"ch": {"type": "ConsultationHandoff", "props": props}},
    }


async def set_completion_decision_impl(
    *,
    session_id: uuid.UUID,
    completion_decision: str,
    reason: str | None = None,
    run_context: "RunContext | None" = None,
    run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """FLOW_GUARD 결정을 세션에 기록한다(ASK_MORE/REQUEST_OVERLAY_REVIEW/...).

    HOLD_OR_HANDOFF(사전검토가 리포트까지 못 가고 상담 전환이 필요한 모든 실패 지점 —
    도면 없음/분석 실패/판단값 수집 실패/저신뢰 등)면 **상담 인입 카드를 결정적으로
    방출**한다. LLM 이 별도 도구를 부르지 않아도 어떤 handoff 경로든 상담 폼이 뜨도록
    여기서 보장한다(best-effort — 카드 방출 실패는 결정 기록을 막지 않는다).
    """

    allowed = {"ASK_MORE", "REQUEST_OVERLAY_REVIEW", "PROCEED_RULE", "HOLD_OR_HANDOFF"}
    if completion_decision not in allowed:
        return _err(
            "INVALID_COMPLETION_DECISION",
            f"completion_decision 는 {sorted(allowed)} 중 하나여야 합니다.",
        )
    try:
        row = await main_flow.set_session_decision(
            session_id=session_id, completion_decision=completion_decision
        )
    except Exception as exc:  # noqa: BLE001
        return _safe_error(exc, "SET_DECISION_FAILED", tool="set_completion_decision")

    # FLOW_GUARD 결정에 따라 세션 status 를 전진(forward-only, best-effort).
    _decision_status = {
        "REQUEST_OVERLAY_REVIEW": "awaiting_overlay",
        "PROCEED_RULE": "ready_for_rule",
        "HOLD_OR_HANDOFF": "handoff",
    }.get(completion_decision)
    if _decision_status is not None:
        await main_flow.advance_session_status(
            session_id=session_id,
            target=_decision_status,
            reason=f"decision:{completion_decision}",
        )

    handoff_emitted = False
    if (
        completion_decision == "HOLD_OR_HANDOFF"
        and run_context is not None
        and run_id is not None
    ):
        prefill_address: str | None = None
        try:
            # 도로명/지번이 없으면 아파트명+동+호로 폴백한다 — prefill 이 비어 상담 리드
            # 주소가 공란이 되던 문제 방지(#address-apt-identity, 0019).
            prefill_address = leads.session_address_display(
                await main_flow.get_session_address(session_id)
            )
        except Exception:  # noqa: BLE001 - 주소 조회 실패는 prefill 없이 진행
            prefill_address = None
        spec = build_consultation_handoff_spec(
            reason=reason, prefill_address=prefill_address, session_id=session_id
        )
        try:
            await emit_ui_component_impl(
                run_context=run_context, run_id=run_id, components=[spec]
            )
            handoff_emitted = True
            log.info("consultation_handoff_emitted", session_id=str(session_id))
        except Exception:  # noqa: BLE001 - 카드 방출 실패는 결정 기록을 막지 않는다
            log.warning("consultation_handoff_emit_failed", session_id=str(session_id))

    return _ok(
        completion_decision=row.get("completion_decision"),
        status=row.get("status"),
        reason=reason,
        handoff_emitted=handoff_emitted,
    )


async def search_address_impl(*, keyword: str) -> dict[str, Any]:
    """도로명주소 API(juso)로 주소 후보를 검색한다(services.leads.search_addresses)."""

    try:
        result = await leads.search_addresses(keyword=keyword)
    except Exception as exc:  # noqa: BLE001 - 구조화 에러로 degrade
        return _safe_error(exc, "ADDRESS_SEARCH_FAILED", tool="search_address")
    items = result.get("items", [])
    return _ok(
        total_count=result.get("total_count", len(items)),
        items=items[:10],
        summary=f"주소 후보 {len(items)}건을 찾았습니다.",
    )


async def lookup_floorplan_candidates_impl(*, session_id: uuid.UUID) -> dict[str, Any]:
    """INPUT-lookupFloorplanCandidates — 확정 주소(아파트명)로 내부 보유 도면 카탈로그를
    검색한다(기능명세서 §2.2, 플로우: 주소→보유 도면 확인→없으면 업로드).

    후보가 있으면(count>0) 사용자가 고르게 하고, 없으면(count==0) 직접 업로드를 요청한다.
    카탈로그가 미큐레이션이면 보통 0건이라 업로드로 흐른다.
    """

    try:
        addr = await main_flow.get_session_address(session_id)
    except Exception as exc:  # noqa: BLE001 - 구조화 에러로 degrade
        return _safe_error(
            exc, "FLOORPLAN_LOOKUP_FAILED", tool="lookup_floorplan_candidates"
        )
    apartment = addr.get("apartment_name") if isinstance(addr, dict) else None
    dong = addr.get("building_dong") if isinstance(addr, dict) else None
    if not apartment:
        return _ok(
            candidates=[],
            count=0,
            summary="아직 아파트명이 확정되지 않아 보유 도면을 찾지 못했어요.",
        )
    try:
        rows = await main_flow.search_floorplan_catalog(
            apartment_name=apartment, building_dong=dong, limit=10
        )
    except Exception as exc:  # noqa: BLE001
        return _safe_error(
            exc, "FLOORPLAN_LOOKUP_FAILED", tool="lookup_floorplan_candidates"
        )
    candidates = [
        {
            "floorplan_id": str(r.get("id")),
            "apartment_name": r.get("apartment_name"),
            "building_dong": r.get("building_dong"),
            "size_type": r.get("size_type"),
            "exclusive_area_m2": (
                float(r["exclusive_area_m2"])
                if r.get("exclusive_area_m2") is not None
                else None
            ),
        }
        for r in rows
    ]
    return _ok(
        candidates=candidates,
        count=len(candidates),
        summary=(
            f"내부 보유 도면 {len(candidates)}건을 찾았어요."
            if candidates
            else "내부 보유 도면이 없어 직접 올려주셔야 해요."
        ),
    )


# run_home_check 백그라운드 태스크 강참조(GC 방지). 라우터의 BackgroundTasks 와 동일한
# "응답 후 처리" 패턴을 에이전트 런타임에서 재현한다.
_home_check_tasks: set[Any] = set()


async def check_building_register_impl(
    *,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
    road_addr: str,
    dong: str,
    ho: str,
    jibun_addr: str | None = None,
) -> dict[str, Any]:
    """CODEF 집합건축물대장(전유부+표제부) 조회를 시작한다.

    CODEF 스크래핑은 느리고(최대 ~300s) 추가 인증(two-way)이 필요할 수 있어, 잡을
    만들고 처리는 **백그라운드**(``run_home_check``, 자체적으로 terminal 상태 마감)로
    돌린다 — 인라인 await 가 런 취소/타임아웃에 의해 끊겨 잡이 querying 으로 멈추는
    것을 피한다(#89). 결과는 ``GET /home-check/{id}`` 로 폴링하고, 추가 인증 재개는
    ``/home-check/{id}/continue`` 가 담당한다.
    """

    try:
        # 같은 입력으로 이미 진행 중인 잡이 있으면 재사용한다(tool replay 시 중복 CODEF
        # 작업/잡 방지, #codef-idempotent). 새 백그라운드 run 도 띄우지 않는다.
        existing = await home_check.find_reusable_home_check(
            user_id=owner_user_id, road_addr=road_addr, dong=dong, ho=ho
        )
        if existing is not None:
            return _ok(
                home_check_id=str(existing["id"]),
                status=existing["status"],
                summary="이미 진행 중인 건축물대장 조회를 이어서 보여드릴게요.",
            )
        job = await home_check.create_home_check(
            user_id=owner_user_id,
            is_anonymous=owner_is_anonymous,
            road_addr=road_addr,
            jibun_addr=jibun_addr,
            dong=dong,
            ho=ho,
        )
    except Exception as exc:  # noqa: BLE001 - 구조화 에러로 degrade
        return _safe_error(
            exc, "BUILDING_REGISTER_FAILED", tool="check_building_register"
        )

    task = asyncio.ensure_future(
        home_check.run_home_check(
            job["id"],
            road_addr=road_addr,
            jibun_addr=jibun_addr,
            dong=dong,
            ho=ho,
        )
    )
    _home_check_tasks.add(task)
    task.add_done_callback(_home_check_tasks.discard)

    return _ok(
        home_check_id=str(job["id"]),
        status="querying",
        summary="건축물대장 조회를 시작했어요. 잠시 후 결과를 확인할 수 있습니다.",
    )


def _derive_wall_type(judgment_schema: dict[str, Any]) -> str | None:
    """selected_walls + wall_objects 에서 철거 대상 벽 종류를 유도한다.

    사용자가 고른 벽 중 하나라도 내력벽 후보면 보수적으로 LOAD_BEARING(→DENY),
    전부 비내력벽 후보면 NON_LOAD_BEARING. 선택이 없거나 매핑 불가면 None(HOLD 가 묻는다).
    """
    selected = judgment_schema.get("selected_walls")
    walls = judgment_schema.get("wall_objects")
    if not isinstance(selected, list) or not selected or not isinstance(walls, list):
        return None
    by_id = {w.get("id"): w.get("wall_type") for w in walls if isinstance(w, dict)}
    types = [by_id.get(s) for s in selected if isinstance(s, str)]
    if any(t == "LOAD_BEARING" for t in types):
        return "LOAD_BEARING"
    if types and all(t == "NON_LOAD_BEARING" for t in types):
        return "NON_LOAD_BEARING"
    return None


def _has_analyzed_selection(judgment_schema: dict[str, Any]) -> bool:
    """분석된 벽 객체(wall_objects)와 사용자 선택(selected_walls)이 **둘 다** 있으면 True.

    cross-turn 영속(리포트 발행)의 전제다 — 이게 있어야 '실제 도면 분석 + 사용자 선택'에
    근거한 판정이다. 없으면(segment 안 돈 턴에서 모델이 wall_type 만 들고 온 경우 등)
    분석 없는 판정이 리포트로 발행되지 않게 막는다(#require-analyzed-selection)."""

    walls = judgment_schema.get("wall_objects")
    selected = judgment_schema.get("selected_walls")
    return (
        isinstance(walls, list)
        and len(walls) > 0
        and isinstance(selected, list)
        and len(selected) > 0
    )


def _apply_vlm_hints(
    clean_values: dict[str, Any],
    judgment_schema: dict[str, Any],
    accepted: set[str],
) -> list[str]:
    """LLM 이 안 넘긴 룰 입력을 VLM 이 도면에서 읽은 힌트로 채운다(P1-3 스코핑).

    우선순위: **LLM 제공값 > VLM 힌트 > (룰엔진 보수적 가정)**. VLM 힌트(vlm_supplement.
    judgment_hints, vlm.py 산출)는 계약 JudgmentValues 어휘라 그대로 병합한다. 힌트가
    None(도면에서 못 읽음)이면 채우지 않아 룰엔진 v2 의 '미확인 → 보수적 가정 + caveat'
    경로로 흐른다. 채운 필드 목록을 반환한다(로그/추적용)."""

    supplement = judgment_schema.get("vlm_supplement")
    hints = supplement.get("judgment_hints") if isinstance(supplement, dict) else None
    if not isinstance(hints, dict):
        return []
    filled: list[str] = []
    for key, value in hints.items():
        if key in accepted and value is not None and clean_values.get(key) is None:
            clean_values[key] = value
            filled.append(key)
    return filled


async def evaluate_rules_impl(
    *,
    session_id: uuid.UUID,
    judgment_values: dict[str, Any],
    run_context: "RunContext | None" = None,
) -> dict[str, Any]:
    """리모델링 룰 엔진 평가(rule-eval-result 계약) + 세션에 판정 영속.

    evaluated_at 은 직렬화 시점(지금)에 주입한다. 성공한 판정은 ``set_session_verdict``
    로 세션에 기록해 독립 리포트(GET /sessions/{id}/report)의 정본이 되게 한다 —
    영속 실패는 판정 자체를 막지 않고(best-effort) 로그만 남긴다.
    """

    # 입력 정제 — 계약 밖 key 는 hard-fail(RuleInputError → "평가 실패") 대신 조용히
    # 드롭한다(LLM 이 여분 key 를 넘겨 평가가 통째로 깨지는 걸 막는다). 드롭은 로그로 남긴다.
    accepted = set(rule_engine.JUDGMENT_VALUE_FIELDS) | set(rule_engine.CONTEXT_FIELDS)
    src = judgment_values if isinstance(judgment_values, dict) else {}
    clean_values = {k: v for k, v in src.items() if k in accepted}
    dropped = sorted(set(src) - accepted)
    if dropped:
        log.info("rule_eval_dropped_keys", session_id=str(session_id), dropped=dropped)
    # 분석 결과(judgment_schema)에서 자동 보강: wall_type(사용자 선택) + 안전 변수(VLM 힌트).
    # LLM 이 안 넘긴 값을 도면 분석으로 채워, 사용자에게 같은 걸 다시 묻지 않게 한다.
    try:
        js = await main_flow.get_session_judgment_schema(session_id)
    except Exception:  # noqa: BLE001 - 조회 실패는 무시(룰엔진이 미확인으로 처리)
        js = {}
    # 철거 대상 벽 종류는 **사용자가 도면에서 고른 벽(selected_walls)이 정본**이다 — 모델이
    # judgment_values 로 wall_type 을 넘겨도 선택에서 유도한 값으로 덮어쓴다(모델이 선택과
    # 다른 wall_type 을 우겨 내력벽을 비내력벽으로 잘못 판정/영속하는 걸 막는다,
    # #wall-type-from-selection). 선택이 없을 때만 모델 제공값을 그대로 둔다.
    derived = _derive_wall_type(js)
    if derived:
        clean_values["wall_type"] = derived
    hinted = _apply_vlm_hints(clean_values, js, accepted)
    if hinted:
        log.info(
            "rule_eval_vlm_hints_applied", session_id=str(session_id), fields=hinted
        )

    # 판정 영속의 freshness 기준(입력 지문) 결정.
    #  - 비-에이전트 직접 호출(run_context 없음: 테스트/내부 호출)은 호출자가 명시한
    #    입력 그대로 영속한다.
    #  - 에이전트 + 같은 런에서 분석(segment)이 돌아 지문이 있으면: 그 지문 기준으로
    #    조건부 영속해 분석 도중 도면/주소가 바뀐 stale 판정을 막는다(#analysis-input-fingerprint).
    #  - 에이전트 cross-turn(분석이 이전 턴이라 이 런엔 지문 없음)은 **실제 분석
    #    (wall_objects)+선택(selected_walls)이 있을 때만** 영속한다 — segment 안 돈 턴에서
    #    모델이 wall_type 만 들고 와 분석 없는 판정을 리포트로 발행하는 걸 막는다
    #    (#require-analyzed-selection). 정상 멀티턴(이전 턴 분석+선택)에선 영속돼 리포트가
    #    준비된다(#report-cross-turn).
    fingerprint = (
        getattr(run_context, "analysis_inputs", None)
        if run_context is not None
        else None
    )
    if run_context is None:
        inputs = await main_flow.get_session_inputs(session_id)
        persist = True
    elif fingerprint is not None:
        inputs = fingerprint
        persist = True
    else:
        inputs = await main_flow.get_session_inputs(session_id)
        persist = _has_analyzed_selection(js)
        if not persist:
            log.info("session_verdict_skipped_no_analysis", session_id=str(session_id))

    try:
        verdict = rule_engine.evaluate_judgment_values(clean_values)
    except rule_engine.RuleInputError as exc:
        return _err("RULE_INPUT_INVALID", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _safe_error(exc, "RULE_EVAL_FAILED", tool="evaluate_rules")
    result = verdict.to_contract_dict(evaluated_at=datetime.now(UTC))
    # 룰엔진이 실제로 돌았고 어떤 판정을 냈는지 로그로 남긴다 — "LLM 판단인지 룰 판정인지"
    # 추적 가능하게(#rule-trace). 입력 PII 는 키 이름만 남긴다.
    log.info(
        "rule_eval_completed",
        session_id=str(session_id),
        verdict=result.get("verdict"),
        permit_required=result.get("permit_required"),
        input_keys=sorted(clean_values.keys()),
        wall_type=clean_values.get("wall_type"),
        persisted=persist,
    )
    if not persist:
        # 분석 지문이 없어 freshness 를 증명할 수 없다 — 판정은 사용자에게 보여 주되
        # 리포트엔 영속하지 않는다(에이전트가 분석 후 재평가하도록).
        log.info("session_verdict_skipped_no_fingerprint", session_id=str(session_id))
        return _ok(result=result, summary=f"룰 평가 결과: {result.get('verdict')}")
    expected_asset, expected_address = inputs if inputs is not None else (None, None)
    try:
        persisted = await main_flow.set_session_verdict(
            session_id=session_id,
            rule_eval_result=result,
            expected_asset_id=expected_asset,
            expected_address_id=expected_address,
        )
        if persisted is None:
            # 평가 도중 입력이 바뀜 — 판정은 사용자에게 보여 주되 리포트엔 영속하지
            # 않는다(에이전트가 새 입력으로 재평가하도록).
            log.info(
                "session_verdict_skipped_inputs_changed", session_id=str(session_id)
            )
    except Exception:  # noqa: BLE001 - 리포트 영속 실패는 판정 응답을 막지 않는다
        log.error("session_verdict_persist_failed", session_id=str(session_id))
    return _ok(result=result, summary=f"룰 평가 결과: {result.get('verdict')}")


async def emit_ui_component_impl(
    *,
    run_context: "RunContext",
    run_id: uuid.UUID,
    components: list[dict[str, Any]],
    judgment_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """다음 assistant 메시지에 첨부할 A2UI payload 를 버퍼링한다.

    실제 첨부는 런너가 최종 assistant 메시지를 투영할 때 drain 한다(자유 텍스트
    파싱 대신 명시적 도구 채널을 쓴다 — 코드베이스 규칙).

    버퍼는 두 곳에 쌓는다: 같은 스트림 빠른 경로용 in-memory ``run_context`` 와,
    SSE 가 끊겨 resume 로 이어질 때(도구는 이미 체크포인트돼 재실행되지 않음)도 살아남는
    런 단위 **내구 버퍼**(agent_runs.pending_ui). drain 은 메모리를 우선하고, 비었으면
    내구 버퍼에서 가져온다(#a2ui-durable). 한 턴에 여러 번 호출되면 **누적**한다(#multi-emit).
    """

    run_context.pending_ui_components.extend(components or [])
    if judgment_snapshot is not None:
        run_context.pending_judgment_snapshot = dict(judgment_snapshot)
    await main_flow.append_pending_ui(
        run_id=run_id, components=components or [], snapshot=judgment_snapshot
    )
    return _ok(buffered=len(run_context.pending_ui_components))


async def emit_floorplan_request_impl(
    *,
    run_context: "RunContext",
    run_id: uuid.UUID,
    reason: str | None = None,
) -> dict[str, Any]:
    """다음 답변에 **도면 업로드 카드(FloorplanRequest)** 를 첨부한다.

    평면도가 필요한데 아직 첨부되지 않았을 때 호출한다. 본문에 업로드 방법을 텍스트로
    설명하는 대신 이 도구를 호출하면 프론트가 실제 업로드 컨트롤을 보여 준다. 미리 만든
    json-render 스펙을 emit_ui_component 버퍼에 넣을 뿐이라 LLM 이 스펙을 구성할 필요가 없다.
    """

    props: dict[str, Any] = {}
    if isinstance(reason, str) and reason.strip():
        props["reason"] = reason.strip()
    spec = {
        "root": "fp",
        "elements": {"fp": {"type": "FloorplanRequest", "props": props}},
    }
    return await emit_ui_component_impl(
        run_context=run_context, run_id=run_id, components=[spec]
    )


async def emit_address_candidates_impl(
    *,
    run_context: "RunContext",
    run_id: uuid.UUID,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """주소 후보 선택 카드(AddressCandidates)를 다음 답변에 첨부한다.

    각 후보: {id, road_address, jibun_address?, building_name?}. LLM 은 후보 목록만
    넘기면 되고, json-render 스펙은 서버가 만든다(LLM 스펙 구성 오류 차단).
    """

    spec = {
        "root": "addr",
        "elements": {
            "addr": {
                "type": "AddressCandidates",
                "props": {"candidates": candidates or []},
            }
        },
    }
    return await emit_ui_component_impl(
        run_context=run_context, run_id=run_id, components=[spec]
    )


# 룰엔진 verdict(rule-eval-result) → JudgmentSummary 카드 decision 매핑. 룰 판정이 있으면
# 이게 정본이다(SDD §4.8: 법적 판단은 결정성 RULE 엔진이 소유, LLM 이 발명하지 않음).
_RULE_VERDICT_TO_DECISION: dict[str, str] = {
    "ALLOW": "possible",
    "WARN": "conditional",
    "DENY": "not_possible",
    "HOLD": "needs_expert",
}


async def emit_judgment_summary_impl(
    *,
    run_context: "RunContext",
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    decision: str,
    title: str,
    summary: str,
    risks: list[str] | None = None,
) -> dict[str, Any]:
    """최종 판단 요약 카드(JudgmentSummary)를 다음 답변에 첨부한다.

    decision: possible|conditional|not_possible|needs_expert. **최종 판정은 룰엔진
    (evaluate_rules)의 verdict 가 정본**이어야 한다(SDD §4.8). 세션에 영속된 rule_eval_result
    가 있으면 그 verdict 를 decision 의 정본으로 쓰고(LLM 인자보다 우선), 카드에 rule_backed=
    true 를 실어 '룰엔진 검증됨'을 표시한다. 없으면(=evaluate_rules 미실행) **LLM 단독 판정**
    이므로 warning 로그 + rule_backed=false 로 명시해 추적/표시 가능하게 한다.
    """

    rule_verdict: str | None = None
    try:
        rev = await main_flow.get_session_verdict(session_id)
        v = rev.get("verdict") if isinstance(rev, dict) else None
        rule_verdict = str(v) if isinstance(v, str) else None
    except Exception:  # noqa: BLE001 - 판정 조회 실패는 카드 방출을 막지 않는다
        rule_verdict = None

    rule_backed = rule_verdict is not None
    decision_used = str(decision)
    if rule_backed:
        mapped = _RULE_VERDICT_TO_DECISION.get(rule_verdict or "")
        if mapped:
            decision_used = mapped
        log.info(
            "judgment_summary_emitted",
            session_id=str(session_id),
            llm_decision=str(decision),
            rule_verdict=rule_verdict,
            decision_used=decision_used,
            rule_backed=True,
        )
    else:
        log.warning(
            "judgment_summary_llm_only",
            session_id=str(session_id),
            llm_decision=str(decision),
            note="evaluate_rules 미실행 — 룰엔진 backing 없는 LLM 단독 판정",
        )

    props: dict[str, Any] = {
        "decision": decision_used,
        "title": str(title),
        "summary": str(summary),
        "rule_backed": rule_backed,
        "session_id": str(session_id),
    }
    if risks:
        props["risks"] = [str(r) for r in risks]
    # 판정 카드 하단 상담 CTA(빠른 상담폼)에서 현장 주소를 prefill 할 수 있게 확정 주소를 싣는다.
    # 도로명/지번이 없으면 아파트명+동+호로 폴백한다(0019).
    try:
        prefill = leads.session_address_display(
            await main_flow.get_session_address(session_id)
        )
        if prefill:
            props["prefill_address"] = prefill
    except Exception:  # noqa: BLE001 - 주소 조회 실패는 카드 방출을 막지 않는다
        pass
    spec = {
        "root": "j",
        "elements": {"j": {"type": "JudgmentSummary", "props": props}},
    }
    return await emit_ui_component_impl(
        run_context=run_context, run_id=run_id, components=[spec]
    )


class RunContext:
    """런 1회 동안 도구↔런너가 공유하는 가변 상태(UI 버퍼 + 분석 입력 지문)."""

    def __init__(self) -> None:
        self.pending_ui_components: list[dict[str, Any]] = []
        self.pending_judgment_snapshot: dict[str, Any] | None = None
        # 분석을 시작한 시점의 세션 입력 지문 (selected_floorplan_asset_id, address_id).
        # 첫 분석 도구(segment_floorplan)가 기록하고, evaluate_rules 가 verdict 영속을
        # 이 지문 기준 조건부로 만들어, 분석 도중 입력이 바뀌면 stale 판정을 막는다
        # (#analysis-input-fingerprint). 미설정이면 evaluate 시점 스냅샷으로 폴백.
        self.analysis_inputs: tuple[Any, Any] | None = None

    def drain_ui(self) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        ui = self.pending_ui_components
        snapshot = self.pending_judgment_snapshot
        self.pending_ui_components = []
        self.pending_judgment_snapshot = None
        return ui, snapshot
