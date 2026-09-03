"""우리집 체크 플로우 도메인 도구 impl — langchain 없이 테스트 가능한 순수 async.

각 impl 은 세션 컨텍스트(session_id/owner_user_id)와 런 컨텍스트(UI 버퍼)를 명시적
인자로 받는다. langchain ``@tool`` 래핑은 ``build_tools()`` 가 closure 로 바인딩한다.

도구는 실제 서비스(services.leads 주소검색, services.home_check CODEF 건축물대장,
services.rule_engine 룰 평가, services.main_flow 세션/도면)에 연결된다. 어떤 도구도
uncaught raise 하지 않고 {ok, error_code} 구조화 결과를 돌려 에이전트가 degrade 한다.
"""

from __future__ import annotations

import asyncio
import copy
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from ...errors import ZippinException
from ...logging import get_logger
from ...services import home_check, leads, main_flow, report_content, rule_engine

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
    # HOLD_OR_HANDOFF 는 여기서 handoff 로 올리지 않는다 — 상담 카드만 띄운 단계라
    # 실제 전환이 아니다. handoff 전이는 사용자가 폼을 실제 제출해 리드가 생성될 때
    # (create_lead, reason='consultation_submitted')에만 일어난다. 이로써 퍼널의 handoff
    # 가 카드 노출이 아닌 실제 상담 신청만 집계한다(리뷰 지적).
    _decision_status = {
        "REQUEST_OVERLAY_REVIEW": "awaiting_overlay",
        "PROCEED_RULE": "ready_for_rule",
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


# 에이전트 컨텍스트 보호 — 변동/행위허가 이력은 최근 것부터 이 개수만 넘긴다.
_REGISTER_HISTORY_LIMIT = 20

# 대장 변동일 파싱 — 신 워커는 "2009-03-17"(zero-pad ISO), 구 워커는 "2011.5.20" 등
# 무패딩·비 ISO 표기가 섞여 있어 문자열 정렬이 시간순이 아니다.
_CHANGE_DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})")


def _change_date_key(value: Any) -> tuple[int, int, int]:
    """변동일 문자열 → (연, 월, 일) 정렬 키. 파싱 불가는 (0,0,0)=가장 오래된 것."""

    match = _CHANGE_DATE_RE.search(str(value or ""))
    if match is None:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


# 대장 변동 이력의 잡 상태 → 에이전트 안내 문구(내부 용어 노출 금지).
# needs_input: 추가 인증(two-way) 입력 UI 는 '우리집 체크' 화면에만 있고 이 대화(A2UI)
# 엔 없다 — 존재하지 않는 화면을 안내하지 말고, 대장 없이 검토를 이어가되 원하면
# 우리집 체크 메뉴에서 같은 주소로 조회해 인증을 이어갈 수 있다고 안내한다.
_REGISTER_STATUS_SUMMARY: dict[str, str] = {
    "querying": "건축물대장 조회가 아직 진행 중입니다. 잠시 후 다시 확인하세요.",
    "needs_input": (
        "건축물대장 조회에 추가 본인 인증이 필요해 이 대화에서는 결과를 받을 수 "
        "없습니다. 대장 확인 없이 검토를 계속 진행하고, 사용자에게는 '우리집 체크' "
        "메뉴에서 같은 주소로 조회하면 인증을 이어가 위반 여부를 확인할 수 있다고 "
        "안내하세요. 이 조회를 다시 폴링하지 마세요."
    ),
    "failed": "건축물대장 조회가 실패했습니다. 대장 없이 검토를 이어가세요.",
}


def _norm_addr_part(value: Any, suffix: str) -> str:
    """동/호 표기 정규화 — "101동"/"101" 혼재를 같은 값으로 비교한다."""

    text = str(value or "").strip()
    return text[: -len(suffix)] if suffix and text.endswith(suffix) else text


def _register_matches_session_address(
    row: dict[str, Any], address: dict[str, Any] | None
) -> bool:
    """대장 조회 잡이 실행된 주소(row)와 현재 세션 주소가 같은 세대인지 검사.

    조회가 백그라운드로 도는 사이 사용자가 세션 주소를 바꾸면, 완료된 row 는 **옛
    주소**의 결과다 — 이때 현재 주소로 지문을 찍어 영속하면 다른 건물의 위반/이력이
    새 주소 리포트에 귀속된다(#register-supplement-address-fingerprint). 도로명이 서로
    있으면 도로명으로, 그 외엔 동·호 표기로 대조한다.
    """

    if not isinstance(address, dict):
        return False
    row_road = str(row.get("road_addr") or "").strip()
    ses_road = str(address.get("road_address") or "").strip()
    if row_road and ses_road and row_road != ses_road:
        return False
    if _norm_addr_part(row.get("addr_dong"), "동") != _norm_addr_part(
        address.get("building_dong"), "동"
    ):
        return False
    return _norm_addr_part(row.get("addr_ho"), "호") == _norm_addr_part(
        address.get("unit_ho"), "호"
    )


async def get_building_register_impl(
    *,
    owner_user_id: uuid.UUID,
    home_check_id: str,
    session_id: uuid.UUID | None = None,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """시작해 둔 건축물대장 조회(home_check)의 **결과를 읽어 온다**(read-back).

    check_building_register 는 fire-and-forget 이라 위반 여부·변동/행위허가 이력이
    대화 컨텍스트로 돌아오지 않았다 — 대장에 "발코니 비내력벽 철거 행위허가" 같은
    이력이 있으면 사전검토 판단의 직접 근거가 되므로 이 도구로 조회해 반영한다.
    완료 결과의 핵심(위반 여부·행위허가 이력)은 세션 judgment_schema 의
    ``register_supplement`` 로도 영속한다 — 리포트(웹/PDF)는 rule_eval_result 만 보는
    구조라, 영속 없이는 대화에서 확인한 대장 사실이 리포트에 도달하지 못한다
    (#register-supplement-persist).
    """

    try:
        job_id = uuid.UUID(str(home_check_id))
    except ValueError:
        return _err("BUILDING_REGISTER_BAD_ID", "잘못된 건축물대장 조회 ID 입니다.")
    try:
        row = await home_check.get_home_check_row(
            home_check_id=job_id, user_id=owner_user_id
        )
    except Exception as exc:  # noqa: BLE001 - 구조화 에러로 degrade
        return _safe_error(
            exc, "BUILDING_REGISTER_FAILED", tool="get_building_register"
        )
    if row is None:
        return _err(
            "BUILDING_REGISTER_NOT_FOUND", "해당 건축물대장 조회를 찾을 수 없습니다."
        )

    status = str(row.get("status") or "querying")
    if status != "completed":
        return _ok(
            home_check_id=str(job_id),
            status=status,
            summary=_REGISTER_STATUS_SUMMARY.get(
                status, _REGISTER_STATUS_SUMMARY["querying"]
            ),
        )

    is_violation = bool(row.get("violation"))
    source_labels = {"exclusive": "전유부", "heading": "표제부"}
    history = [
        {
            "date": entry.get("date"),
            "reason": entry.get("reason"),
            "source": source_labels.get(str(entry.get("source")), "대장"),
        }
        for entry in home_check.present_change_history(row.get("change_list") or [])
    ]
    # 저장 순서는 전유부 전체 → 표제부 전체(날짜 무정렬)라 tail 절단이 최신을 보장하지
    # 않는다 — 날짜를 (연,월,일) 정수로 파싱해 시간순 정렬 후 최근 이력을 남긴다.
    # 구 워커 행은 zero-pad 없는 "2011.5.20" 형태라 문자열 정렬이 깨진다("2024.10.01"
    # < "2024.9.30"). 날짜 미상 행은 가장 오래된 것으로 취급한다.
    history.sort(key=lambda e: _change_date_key(e.get("date")))
    history = history[-_REGISTER_HISTORY_LIMIT:]
    permit_entries = [e for e in history if "행위허가" in str(e.get("reason") or "")]

    # 리포트 도달 경로(#register-supplement-persist): 웹/PDF 리포트 조립이 읽는 세션
    # 상태로 핵심만 영속한다. 실패는 도구 결과를 막지 않는다(best-effort).
    # **내용 기반** 주소 지문을 함께 저장한다 — session_addresses.id 는 upsert 가
    # 보존하는 안정 ID 라 주소 변경을 못 가른다. 이후 사용자가 주소를 바꾸면(다른
    # 건물) 리포트 조립이 지문 불일치로 이 supplement 를 무시해, 옛 주소 건물의
    # 위반/이력이 새 주소 리포트에 붙는 것을 막는다
    # (#register-supplement-address-fingerprint).
    if session_id is not None:
        try:
            current_address = await main_flow.get_session_address(session_id)
            # 조회 잡의 주소(row)와 현재 세션 주소가 다르면(조회 도중 주소 변경) 영속을
            # 건너뛴다 — 옛 건물 결과에 새 주소 지문이 찍히는 레이스 차단.
            if _register_matches_session_address(row, current_address):
                await main_flow.merge_judgment_schema(
                    session_id=session_id,
                    owner_user_id=owner_user_id,
                    owner_is_anonymous=owner_is_anonymous,
                    patch={
                        "register_supplement": {
                            "is_violation": is_violation,
                            "unit_floor": row.get("exclusive_floor"),
                            "permit_entries": permit_entries[-5:],
                            "address_fingerprint": report_content.address_fingerprint(
                                current_address
                            ),
                            "checked_at": datetime.now(UTC).isoformat(),
                        }
                    },
                )
            else:
                log.info(
                    "register_supplement_skipped_address_mismatch",
                    session_id=str(session_id),
                )
        except Exception:  # noqa: BLE001 - 영속 실패는 조회 결과 반환을 막지 않는다
            log.error("register_supplement_persist_failed", session_id=str(session_id))

    violation_txt = "위반건축물로 표시됨" if is_violation else "위반건축물 표시 없음"
    permit_txt = (
        f", 행위허가 이력 {len(permit_entries)}건(내용을 판단에 반영할 것)"
        if permit_entries
        else ""
    )
    return _ok(
        home_check_id=str(job_id),
        status=status,
        violation={
            "is_violation": is_violation,
            "exclusive": row.get("exclusive_violation"),
            "heading": row.get("heading_violation"),
        },
        building_floors=row.get("building_floors"),
        # 전유부 층 표기(예: "3층") — 세대 층수(floor_count) 확인의 근거로 쓸 수 있다.
        unit_floor=row.get("exclusive_floor"),
        change_history=history,
        summary=(
            f"건축물대장 조회 완료 — {violation_txt}, 변동 이력 "
            f"{len(history)}건{permit_txt}."
        ),
    )


def _derive_wall_type(judgment_schema: dict[str, Any]) -> str | None:
    """selected_walls + wall_objects 에서 철거 대상 벽 종류를 유도한다.

    사용자가 고른 벽 중 하나라도 내력벽 후보면 보수적으로 LOAD_BEARING(→DENY),
    전부 비내력벽 후보면 NON_LOAD_BEARING. 선택이 없거나 매핑 불가면 None(HOLD 가 묻는다).

    **VLM 영역별 의견과의 충돌**(#region-assessments, Codex P1): 세그멘테이션은 비내력
    후보라 해도 VLM 이 같은 벽을 내력 추정/판단 어려움으로 봤다면 두 근거가 갈린 것이다.
    이때 비내력으로 확정해 ALLOW/WARN 을 영속하면 안 되므로 None(→HOLD, 추가 확인)으로
    강등한다 — 세션 상태 블록이 에이전트에게 주는 '단정 금지' 안내와 룰 판정을 일치시킨다.
    """
    selected = judgment_schema.get("selected_walls")
    walls = judgment_schema.get("wall_objects")
    if not isinstance(selected, list) or not selected or not isinstance(walls, list):
        return None
    by_id = {w.get("id"): w.get("wall_type") for w in walls if isinstance(w, dict)}
    ids = [s for s in selected if isinstance(s, str)]
    types = [by_id.get(s) for s in ids]
    if any(t == "LOAD_BEARING" for t in types):
        return "LOAD_BEARING"
    if types and all(t == "NON_LOAD_BEARING" for t in types):
        opinions = _region_assessments_by_id(judgment_schema)
        if any(opinions.get(rid) in ("LOAD_BEARING", "UNCERTAIN") for rid in ids):
            return None
        return "NON_LOAD_BEARING"
    return None


def _region_assessments_by_id(judgment_schema: dict[str, Any]) -> dict[str, str]:
    """vlm_supplement.region_assessments → {region_id: assessment}."""

    supplement = judgment_schema.get("vlm_supplement")
    items = (
        supplement.get("region_assessments") if isinstance(supplement, dict) else None
    )
    if not isinstance(items, list):
        return {}
    return {
        a["region_id"]: str(a.get("assessment") or "")
        for a in items
        if isinstance(a, dict) and isinstance(a.get("region_id"), str)
    }


def _nonempty_list(judgment_schema: dict[str, Any], key: str) -> bool:
    value = judgment_schema.get(key)
    return isinstance(value, list) and len(value) > 0


def _has_analyzed_selection(judgment_schema: dict[str, Any]) -> bool:
    """분석 객체와 사용자 선택이 **둘 다** 있으면 True (벽 또는 창호 축 중 하나라도).

    cross-turn 영속(리포트 발행)의 전제다 — 이게 있어야 '실제 도면 분석 + 사용자 선택'에
    근거한 판정이다. 없으면(segment 안 돈 턴에서 모델이 wall_type 만 들고 온 경우 등)
    분석 없는 판정이 리포트로 발행되지 않게 막는다(#require-analyzed-selection).
    창호-only 세션(경계 창호 철거 검토)도 window_objects+selected_windows 로 인정한다."""

    walls_ok = _nonempty_list(judgment_schema, "wall_objects") and _nonempty_list(
        judgment_schema, "selected_walls"
    )
    windows_ok = _nonempty_list(judgment_schema, "window_objects") and _nonempty_list(
        judgment_schema, "selected_windows"
    )
    return walls_ok or windows_ok


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


def _vlm_window_boundary(judgment_schema: dict[str, Any]) -> str | None:
    """선택 창호의 VLM 경계 판정(region_assessments)에서 window_demolition_boundary 를
    유도한다(#region-assessments → 룰 자동 보강).

    - 선택 창호 중 하나라도 EXTERIOR 면 EXTERIOR(보수적 — 그 창은 철거 불가, DENY).
    - 전부 BALCONY_BOUNDARY 면 BALCONY_BOUNDARY(발코니 확장 경로).
    - 그 외(UNCERTAIN/평가 없음 포함)면 None — 룰엔진이 HOLD 로 재확인을 요구하고,
      에이전트는 확정되지 않은 창에 대해서만 사용자에게 묻는다.
    - VLM 전체 신뢰도가 **유효한 숫자로 문턱 이상**일 때만 승격한다 — 저신뢰는 물론
      신뢰도가 누락/비정상(None)이어도 None 으로 두어, 측정되지 않은 추측이 HOLD 를
      우회해 확정 판정/오거부가 되지 않게(#low-conf-gate, Codex P1).
    """

    from .vlm import has_trusted_confidence

    selected = judgment_schema.get("selected_windows")
    if not isinstance(selected, list) or not selected:
        return None
    supplement = judgment_schema.get("vlm_supplement")
    if not has_trusted_confidence(supplement if isinstance(supplement, dict) else None):
        return None
    by_id = _region_assessments_by_id(judgment_schema)
    if not by_id:
        return None
    verdicts = [by_id.get(rid) for rid in selected if isinstance(rid, str)]
    if any(v == "EXTERIOR" for v in verdicts):
        return "EXTERIOR"
    if verdicts and all(v == "BALCONY_BOUNDARY" for v in verdicts):
        return "BALCONY_BOUNDARY"
    return None


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
    # 평가가 근거로 삼는 선택 스냅숏 — verdict 영속을 이 스냅숏 조건부로 만든다
    # (#verdict-selection-fingerprint). 평가와 영속 사이에 재분석 프루닝/사용자
    # 재선택으로 저장 선택이 바뀌면 set_session_verdict 가 쓰지 않아, 무효화된 선택
    # 기준 판정이 report-ready 로 붙지 않는다.
    snapshot_walls = (
        js.get("selected_walls") if isinstance(js.get("selected_walls"), list) else []
    )
    snapshot_windows = (
        js.get("selected_windows")
        if isinstance(js.get("selected_windows"), list)
        else []
    )
    # 철거 대상 벽 종류는 **사용자가 도면에서 고른 벽(selected_walls)이 정본**이다 — 모델이
    # judgment_values 로 wall_type 을 넘겨도 선택에서 유도한 값으로 덮어쓴다(모델이 선택과
    # 다른 wall_type 을 우겨 내력벽을 비내력벽으로 잘못 판정/영속하는 걸 막는다,
    # #wall-type-from-selection). 선택이 없을 때만 모델 제공값을 그대로 둔다.
    wall_selected = _nonempty_list(js, "selected_walls")
    window_selected = _nonempty_list(js, "selected_windows")
    derived = _derive_wall_type(js)
    if derived:
        clean_values["wall_type"] = derived
    elif wall_selected or window_selected:
        # 선택이 있는데 유도 실패면 **모델 제공 wall_type 도 버린다** — 두 경우 모두
        # 모델이 넘긴 값이 선택과 무관하거나 근거 없는 단정이기 때문이다.
        #  - 벽 선택 + 유도 불가(구조 불확실 벽 UNKNOWN 포함/매핑 불가): 모델이
        #    NON_LOAD_BEARING 을 우겨 넣으면 룰엔진이 불확실 벽을 확정 비내력으로
        #    판정·영속해 HOLD(확인 필요)를 우회한다(#wall-unknown-hold).
        #  - 창호-only 세션(#window-only-target): 벽 선택이 없어 유도 근거가 없는데
        #    모델 wall_type=LOAD_BEARING 이 남으면 _evaluate_wall 이 창호 경로보다
        #    먼저 돌아 내력벽 철거로 오판·DENY 한다.
        clean_values.pop("wall_type", None)
    # 철거 검토 대상(벽/창호)은 **오버레이 선택이 정본**이다 — 모델 제공값과 무관하게
    # selected_walls/selected_windows 존재 여부로 덮어쓴다(#window-only-target). 창호만
    # 고른 세션은 룰엔진이 벽 종류 미상 HOLD 를 건너뛰고 창호 경계(R-WINDOW-01)를 본다.
    for target_key, selected in (
        ("wall_demolition_target", wall_selected),
        ("window_demolition_target", window_selected),
    ):
        if selected:
            clean_values[target_key] = True
        else:
            clean_values.pop(target_key, None)
    hinted = _apply_vlm_hints(clean_values, js, accepted)
    # 창호 경계는 **LLM 전달값 > VLM 영역 판정 > 미확인(HOLD)** — LLM 이 사용자 답으로
    # 정정한 값이 있으면 그것을 존중하고, 없을 때만 VLM 판정으로 채운다.
    if (
        window_selected
        and clean_values.get("window_demolition_boundary") is None
        and "window_demolition_boundary" in accepted
    ):
        boundary = _vlm_window_boundary(js)
        if boundary is not None:
            clean_values["window_demolition_boundary"] = boundary
            hinted.append("window_demolition_boundary")
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
            expected_selected_walls=snapshot_walls,
            expected_selected_windows=snapshot_windows,
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


async def _card_asset_stamp(
    *,
    run_context: "RunContext | None",
    session_id: uuid.UUID | None,
) -> tuple[bool, str | None]:
    """카드에 스탬프할 asset id 를 정한다 — ``(ok, asset_id)``.

    **이 턴 분석이 실제로 본 asset**(RunContext.analysis_inputs 지문)을 우선한다:
    분석 결과가 카드 방출의 원인이므로, 방출 직전에 다른 탭이 도면을 교체해도 카드는
    원인이 된 asset 을 가리켜야 한다(#floorplan-request-prior-asset 의 지문 우선).
    지문이 없으면(이 턴에 분석 없음 — 사용자가 재업로드만 요청 등) 현재 선택 asset 을
    조회한다. ok=False 면 조회 실패 — 호출자는 스탬프를 생략한다(보수적 폴백).
    """

    inputs = getattr(run_context, "analysis_inputs", None) if run_context else None
    if inputs is not None:
        return True, (str(inputs[0]) if inputs[0] is not None else None)
    if session_id is None:
        return False, None
    try:
        live = await main_flow.get_session_inputs(session_id)
    except Exception:  # noqa: BLE001 - 스탬프 실패가 카드 방출을 막으면 안 된다
        return False, None
    if live is None:
        return False, None
    return True, (str(live[0]) if live[0] is not None else None)


async def emit_floorplan_request_impl(
    *,
    run_context: "RunContext",
    run_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """다음 답변에 **도면 업로드 카드(FloorplanRequest)** 를 첨부한다.

    평면도가 아직 첨부되지 않았을 때는 물론, **다른 도면으로 재업로드가 필요할 때**
    (분석 결과 벽·창호 후보 0 등)도 호출된다. 본문에 업로드 방법을 텍스트로
    설명하는 대신 이 도구를 호출하면 프론트가 실제 업로드 컨트롤을 보여 준다. 미리 만든
    json-render 스펙을 emit_ui_component 버퍼에 넣을 뿐이라 LLM 이 스펙을 구성할 필요가 없다.

    카드엔 발행 원인이 된 asset(이 턴 분석 지문, 없으면 현재 선택)을 ``prior_asset_id``
    로 스탬프한다 — 프론트 카드는 "세션에 도면이 하나라도 있으면 첨부 완료"가 아니라
    "이 카드 발행 **이후** 새 asset 이 붙었는가"로 완료를 판정해, 재업로드 요청 카드가
    뜨자마자 '받았어요'로 잠기는 문제를 막는다(#floorplan-request-prior-asset). 조회
    실패 시엔 스탬프를 생략한다(구 카드와 같은 보수적 동작으로 폴백).
    """

    props: dict[str, Any] = {}
    if isinstance(reason, str) and reason.strip():
        props["reason"] = reason.strip()
    ok, asset_id = await _card_asset_stamp(
        run_context=run_context, session_id=session_id
    )
    if ok:
        props["prior_asset_id"] = asset_id
    spec = {
        "root": "fp",
        "elements": {"fp": {"type": "FloorplanRequest", "props": props}},
    }
    return await emit_ui_component_impl(
        run_context=run_context, run_id=run_id, components=[spec]
    )


#: judgment_schema.wall_objects.wall_type → 오버레이 class_name (재구성 폴백용 역매핑).
_OVERLAY_CLASS_BY_WALL_TYPE: dict[str, str] = {
    "NON_LOAD_BEARING": "wall_nonbearing",
    "LOAD_BEARING": "wall_reinforced_concrete",
    "UNKNOWN": "wall_other",
}


def _overlay_component_asset(
    component: Any,
) -> tuple[str | None, dict[str, Any]] | None:
    """json-render 스펙에서 FloorplanOverlay 카드의 (asset_id, props) 를 읽는다."""

    if not isinstance(component, dict):
        return None
    root = component.get("root")
    elements = component.get("elements")
    if not isinstance(root, str) or not isinstance(elements, dict):
        return None
    element = elements.get(root)
    if not isinstance(element, dict) or element.get("type") != "FloorplanOverlay":
        return None
    props = element.get("props")
    if not isinstance(props, dict):
        return None
    asset_id = props.get("asset_id")
    return (asset_id if isinstance(asset_id, str) else None), props


def _rebuild_overlay_regions(judgment_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """영속된 판단객체(wall/window_objects)로 오버레이 region 을 재구성한다(폴백).

    분석 시점의 카드가 chat_messages 에 남아 있지 않을 때만 쓴다 — coords(MaskCoord[])
    를 평탄 polygon 으로 되돌리고 wall_type 을 오버레이 어휘로 역매핑한다. 세그멘테이션
    원본의 score/bbox 는 없으므로 최소 필드만 싣는다.
    """

    regions: list[dict[str, Any]] = []

    def _polygon(obj: dict[str, Any]) -> list[float]:
        flat: list[float] = []
        for pt in obj.get("coords") or []:
            if isinstance(pt, dict) and isinstance(pt.get("x"), (int, float)):
                if isinstance(pt.get("y"), (int, float)):
                    flat.extend((float(pt["x"]), float(pt["y"])))
        return flat

    walls = judgment_schema.get("wall_objects")
    if isinstance(walls, list):
        for w in walls:
            if not isinstance(w, dict) or not isinstance(w.get("id"), str):
                continue
            cls = _OVERLAY_CLASS_BY_WALL_TYPE.get(str(w.get("wall_type")))
            poly = _polygon(w)
            if cls and len(poly) >= 6:
                regions.append(
                    {"region_id": w["id"], "class_name": cls, "polygon": poly}
                )
    windows = judgment_schema.get("window_objects")
    if isinstance(windows, list):
        for win in windows:
            if not isinstance(win, dict) or not isinstance(win.get("id"), str):
                continue
            poly = _polygon(win)
            if len(poly) >= 6:
                regions.append(
                    {"region_id": win["id"], "class_name": "window", "polygon": poly}
                )
    return regions


#: 오버레이에서 사용자가 고를 수 있는 클래스(FloorplanOverlayCard.selectableRegions 와 정합).
_OVERLAY_SELECTABLE_CLASSES: frozenset[str] = frozenset(
    {"wall_nonbearing", "wall_other", "wall_unknown", "window"}
)


def _selectable_signature(
    regions: list[Any],
) -> dict[str, tuple[str, tuple[float, ...]]]:
    """선택 가능 region 의 **완전한 표현**(id → (정규화 클래스, 폴리곤)) — 재사용 카드가
    현재 판단객체와 기하·분류까지 같은지 대조한다(Codex P2). 미확정 벽은 카드 payload 에서
    ``wall_unknown`` 으로 통일되므로(#deploy-skew) ``wall_other`` 와 같은 클래스로 본다."""

    out: dict[str, tuple[str, tuple[float, ...]]] = {}
    for r in regions:
        if not isinstance(r, dict) or not isinstance(r.get("region_id"), str):
            continue
        cls = r.get("class_name")
        if cls not in _OVERLAY_SELECTABLE_CLASSES:
            continue
        poly = r.get("polygon") or []
        if not all(isinstance(v, (int, float)) for v in poly):
            continue
        norm_cls = "wall_other" if cls == "wall_unknown" else str(cls)
        out[r["region_id"]] = (norm_cls, tuple(round(float(v), 2) for v in poly))
    return out


def _overlay_card_matches_judgment(
    spec: dict[str, Any], judgment_schema: dict[str, Any]
) -> bool:
    """카드의 선택 가능 region(id·클래스·폴리곤)이 현재 판단객체와 완전히 같은가."""

    found = _overlay_component_asset(spec)
    if found is None:
        return False
    _asset, props = found
    return _selectable_signature(
        list(props.get("regions") or [])
    ) == _selectable_signature(_rebuild_overlay_regions(judgment_schema))


#: 결과 카드에 스탬프할 선택 지문 — 정의는 main_flow(리드 제출 재검증과 공유,
#: #judgment-selection-stamp). 웹 `selectionKeyOf` 와 형식이 같아야 한다.
selection_key = main_flow.judgment_selection_key


async def show_floorplan_overlay_impl(
    *,
    run_context: "RunContext",
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
    reason: str | None = None,
) -> dict[str, Any]:
    """현재 도면의 **오버레이 카드를 다시 띄운다**(#overlay-reshow).

    분석 후 대화가 이어진 뒤 사용자가 다른 벽/창호를 추가로 검토하고 싶어 하거나, 에이전트가
    "도면에서 골라 달라"고 요청해야 할 때 호출한다 — 카드 없이 말로만 고르라고 하면 사용자가
    무엇을 해야 할지 모른다(세션 32a62ac9 의 '날개벽' 사례). 재분석은 하지 않는다: 분석
    시점에 방출된 카드(chat_messages.ui_components)를 현재 선택 asset 기준으로 찾아 그대로
    재방출하고, 없으면 영속된 판단객체로 재구성한다. 프론트 카드는 저장된 선택을 복원하고
    재선택·재제출을 허용하므로, 제출되면 서버가 selected_walls 를 갱신하고 옛 verdict 를
    무효화한다(기존 흐름 재사용).
    """

    asset = await main_flow.get_selected_floorplan_asset(
        session_id=session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    if asset is None:
        return _err(
            "OVERLAY_NO_FLOORPLAN",
            "아직 첨부된 도면이 없습니다. emit_floorplan_request 로 도면을 먼저 받으세요.",
        )
    asset_id = str(asset["id"])
    try:
        js = await main_flow.get_session_judgment_schema(session_id)
    except Exception:  # noqa: BLE001 - 조회 실패는 '분석 없음'과 같이 다룬다
        js = {}
    walls = js.get("wall_objects")
    windows = js.get("window_objects")
    analyzed = isinstance(walls, list) or isinstance(windows, list)
    # 선택 가능 = 내력벽이 아닌 벽 + 창호(프론트 selectableRegions 와 정합, Codex P2) —
    # 내력벽만 잡힌 도면은 카드에 제출 버튼이 없어 '다시 고르기'를 이어갈 수 없다.
    selectable = any(
        isinstance(w, dict) and w.get("wall_type") != "LOAD_BEARING"
        for w in (walls or [])
    ) or bool(windows)
    if not analyzed or not selectable:
        return _err(
            "OVERLAY_NO_ANALYSIS",
            "이 도면의 분석 결과가 없거나 고를 수 있는 벽·창호가 없습니다. "
            "segment_floorplan 으로 먼저 분석하세요.",
        )

    spec: dict[str, Any] | None = None
    try:
        messages = await main_flow.list_session_chat_messages(
            session_id=session_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
        )
    except Exception:  # noqa: BLE001 - 이력 조회 실패는 재구성 폴백으로
        messages = []
    for row in reversed(messages):
        if row.get("role") != "assistant":
            continue
        for component in row.get("ui_components") or []:
            found = _overlay_component_asset(component)
            if found is None:
                continue
            found_asset, _props = found
            if found_asset == asset_id:
                spec = copy.deepcopy(component)
                break
        if spec is not None:
            break

    # 재사용 카드 검증(Codex P2): 같은 asset 이 재분석됐는데 그 카드가 투영되지 못한
    # 경우(영속 성공 후 런 실패 등) 옛 카드는 현재 판단객체와 다른 기하/분류/id 를 담을
    # 수 있다. 선택 가능 region 의 id·클래스·폴리곤이 현재 판단객체와 완전히 같을 때만
    # 재사용하고, 아니면 버리고 재구성한다.
    if spec is not None and not _overlay_card_matches_judgment(spec, js):
        log.info(
            "overlay_reshow_card_mismatch",
            session_id=str(session_id),
            asset_id=asset_id,
        )
        spec = None

    source = "message"
    if spec is None:
        from .segmentation import build_overlay_spec

        regions = _rebuild_overlay_regions(js)
        if not regions:
            return _err(
                "OVERLAY_NO_ANALYSIS",
                "이 도면의 분석 결과로는 오버레이를 다시 그릴 수 없습니다. "
                "segment_floorplan 으로 다시 분석하세요.",
            )
        image: dict[str, Any] = {}
        if isinstance(asset.get("width_px"), int) and isinstance(
            asset.get("height_px"), int
        ):
            image = {"width": asset["width_px"], "height": asset["height_px"]}
        spec = build_overlay_spec(asset_id=asset_id, image=image, regions=regions)
        source = "rebuilt"

    root = spec.get("root")
    props = spec["elements"][root]["props"]
    if isinstance(reason, str) and reason.strip():
        props["reason"] = reason.strip()
    else:
        props["reason"] = "추가로 철거를 검토할 벽이나 창호를 골라 다시 제출해 주세요."
    await emit_ui_component_impl(
        run_context=run_context, run_id=run_id, components=[spec]
    )
    log.info(
        "overlay_reshown",
        session_id=str(session_id),
        asset_id=asset_id,
        source=source,
    )
    return _ok(
        overlay_emitted=True,
        summary=(
            "도면 오버레이 카드를 다시 띄웠어요. 본문에는 무엇을 고르면 되는지 짧은 안내 "
            "한 문장만 두세요."
        ),
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
    # 이 결과가 유래한 도면 asset 스탬프 — 도면이 **교체**되면 프론트가 이 카드를
    # '이전 도면 기준 결과'로 표시하고 상담 CTA 를 막아, A 도면의 결론에 B 도면이
    # 붙어 나가는 상담 인입을 차단한다(#judgment-asset-stamp).
    ok, stamp = await _card_asset_stamp(run_context=run_context, session_id=session_id)
    if ok and stamp is not None:
        props["asset_id"] = stamp
    # 선택 지문 스탬프 — 같은 도면에서 벽/창호를 **다시 골라** 옛 verdict 가 무효화돼도
    # 옛 결과 카드가 현재처럼 보이며 상담 CTA 를 열지 않게 한다(#judgment-selection-stamp).
    # 지문엔 verdict 리비전도 들어간다 — 같은 선택으로 재분석·재평가돼도 옛 카드가
    # 통과하지 않게(main_flow.judgment_selection_key 참고).
    try:
        stamped = await main_flow.get_session_selection_key(session_id)
        if stamped is not None:
            props["selection_key"] = stamped
    except Exception:  # noqa: BLE001 - 지문 조회 실패는 카드 방출을 막지 않는다(구 카드 동작)
        pass
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
