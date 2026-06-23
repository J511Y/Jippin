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


async def set_completion_decision_impl(
    *,
    session_id: uuid.UUID,
    completion_decision: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """FLOW_GUARD 결정을 세션에 기록한다(ASK_MORE/REQUEST_OVERLAY_REVIEW/...)."""

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
    return _ok(
        completion_decision=row.get("completion_decision"),
        status=row.get("status"),
        reason=reason,
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

    # 판정이 의존하는 입력 지문 결정.
    #  - 에이전트 경로(run_context 있음): judgment_values 를 만든 분석(segment) 시작 시점
    #    지문이 정본이다. 첫 분석에서 기록되고 resume 시 런너가 내구 버퍼에서 복원한다.
    #    지문이 없으면(분석을 안 했거나 복원 실패) **현재 세션 입력으로 폴백하지 않고
    #    fail-closed** — stale 판정이 새 입력에 report-ready 로 붙는 걸 막는다
    #    (#analysis-input-fingerprint).
    #  - 비-에이전트 경로(run_context 없음: 직접 호출/테스트): resume 개념이 없으므로
    #    현재 스냅샷 기준으로 영속한다.
    fingerprint = (
        getattr(run_context, "analysis_inputs", None)
        if run_context is not None
        else None
    )
    if run_context is None:
        inputs = await main_flow.get_session_inputs(session_id)
        persist = True
    else:
        inputs = fingerprint
        persist = fingerprint is not None
    try:
        verdict = rule_engine.evaluate_judgment_values(judgment_values)
    except rule_engine.RuleInputError as exc:
        return _err("RULE_INPUT_INVALID", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _safe_error(exc, "RULE_EVAL_FAILED", tool="evaluate_rules")
    result = verdict.to_contract_dict(evaluated_at=datetime.now(UTC))
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
