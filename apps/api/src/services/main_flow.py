"""Phase A 메인 흐름 (사전검토 세션/주소/도면/채팅) DB-backed 서비스.

CMP-609 skeleton 의 in-memory 저장소를 실 Phase A 테이블
(``sessions`` / ``session_addresses`` / ``floorplan_uploads`` /
``floorplan_candidates`` / ``chat_messages`` / ``chat_tool_calls``,
``supabase/migrations/20260604073000_0008_main_feature_phase_a.sql``) 로
영속화한 구현이다 (CMP-608 상당). DB write 는 ``services.leads`` 와 동일하게
``get_engine().begin()`` 경로를 쓴다.

구조:

- public 서비스 함수 (``create_session`` 등) 는 ownership/검증 로직을 담당하고,
  실제 SQL 은 ``_db_*`` seam 함수가 트랜잭션 단위로 소유한다. 테스트는
  ``test_leads_router`` 가 ``_insert_lead`` 를 monkeypatch 하는 패턴 그대로
  ``_db_*`` seam 을 stateful fake 로 대체한다 (``tests/_main_flow_db_fake.py``).
- 각 seam 의 반환 dict 는 Pydantic ``from_attributes=True`` response 모델이
  그대로 읽을 수 있도록 컬럼 이름 (``metadata`` 포함) 을 키로 쓴다.

비고:

- ``sessions.user_id`` 는 Supabase ``auth.users.id`` 다. 익명/비익명 모두
  자기 자신의 row 만 본다. 타인 세션은 404 (열거 누수 방지).
- DB row 에는 ``is_anonymous_owner`` 컬럼이 없다 — 익명 owner 여부는
  ``expires_at IS NOT NULL`` 로 표현된다 (익명 TTL 정책, board round-3 #1).
- migration 0008 의 client guard trigger 들은 ``current_role = 'authenticated'``
  에만 적용된다. 본 서비스는 backend 역할로 접속하므로 service-controlled
  컬럼 (status/expires_at/last_activity_at 등) 을 직접 관리한다.
- ``floorplan_candidates`` 는 ``(session_id, lookup_revision, floorplan_id)``
  와 ``(session_id, lookup_revision, rank)`` 이 unique 다. 같은 revision 안에
  중복 저장이 들어오면 409 로 막는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..models import (
    AgentRun,
    ChatMessage,
    ChatToolCall,
    FloorplanAsset,
    FloorplanCandidate,
    FloorplanUpload,
    Session,
    SessionAddress,
)

_SESSIONS = Session.__table__
_SESSION_ADDRESSES = SessionAddress.__table__
_FLOORPLAN_UPLOADS = FloorplanUpload.__table__
_FLOORPLAN_ASSETS = FloorplanAsset.__table__
_FLOORPLAN_CANDIDATES = FloorplanCandidate.__table__
_CHAT_MESSAGES = ChatMessage.__table__
_CHAT_TOOL_CALLS = ChatToolCall.__table__
_AGENT_RUNS = AgentRun.__table__

# completion_decision 처럼 None 자체가 유효한 값(결정 해제)인 필드의 "미지정"을
# 구분하기 위한 sentinel — set_session_decision 참조.
_UNSET: Any = object()


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found(message: str, code: str = "NOT_FOUND") -> ZippinException:
    return ZippinException(message, code=code, http_status=404)


def _conflict(message: str, code: str) -> ZippinException:
    return ZippinException(message, code=code, http_status=409)


def _unprocessable(message: str, code: str) -> ZippinException:
    return ZippinException(message, code=code, http_status=422)


def _touch_session_stmt(session_id: uuid.UUID) -> sa.Update:
    """세션 활동 timestamp 갱신 statement.

    updated_at trigger 는 authenticated role 전용이라 backend write 경로에서는
    서비스가 직접 ``updated_at`` 을 관리한다.
    """

    return (
        sa.update(_SESSIONS)
        .where(_SESSIONS.c.id == session_id)
        .values(last_activity_at=sa.func.now(), updated_at=sa.func.now())
    )


# ---------------------------------------------------------------------------
# DB seams — 각 함수가 트랜잭션 1개를 소유한다. 테스트 monkeypatch 지점
# (``tests/_main_flow_db_fake.py`` 가 같은 시그니처로 대체).
# ---------------------------------------------------------------------------


async def _db_insert_session(values: dict[str, Any]) -> dict[str, Any]:
    """`sessions` INSERT. id/created_at 등 server default 는 RETURNING 으로 회수."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(_SESSIONS).values(**values).returning(*_SESSIONS.c)
            )
        ).one()
    return dict(row._mapping)


async def _db_select_session(session_id: uuid.UUID) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(sa.select(_SESSIONS).where(_SESSIONS.c.id == session_id))
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_clear_session_expiry(session_id: uuid.UUID) -> dict[str, Any]:
    """익명 owner 세션의 permanent 승격 — ``expires_at`` 해제 (board P2-5)."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_SESSIONS)
                .where(_SESSIONS.c.id == session_id)
                .values(expires_at=None, updated_at=sa.func.now())
                .returning(*_SESSIONS.c)
            )
        ).one()
    return dict(row._mapping)


async def _db_select_session_address(
    session_id: uuid.UUID,
) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_SESSION_ADDRESSES).where(
                    _SESSION_ADDRESSES.c.session_id == session_id
                )
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_upsert_session_address(
    address_values: dict[str, Any], *, session_id: uuid.UUID
) -> dict[str, Any]:
    """`session_addresses` upsert + 세션 pointer/status 전이 (단일 트랜잭션).

    ``session_addresses.session_id`` 가 unique 이므로 ``ON CONFLICT`` 로
    1 session = 1 address 를 보장한다. conflict 경로에서는 id/created_at/
    normalized_at 을 보존한다 (set 절에 포함하지 않음). migration 0008 의
    ``trg_sessions_reference_scope`` 가 ``sessions.address_id`` 의 동일-세션
    참조를 검증하므로 address row 를 먼저 쓰고 session 을 갱신한다.
    """

    insert_stmt = pg_insert(_SESSION_ADDRESSES).values(**address_values)
    update_set = {
        key: insert_stmt.excluded[key]
        for key in address_values
        if key not in ("session_id", "user_id")
    }
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                insert_stmt.on_conflict_do_update(
                    index_elements=[_SESSION_ADDRESSES.c.session_id],
                    set_=update_set,
                ).returning(*_SESSION_ADDRESSES.c)
            )
        ).one()
        await conn.execute(
            sa.update(_SESSIONS)
            .where(_SESSIONS.c.id == session_id)
            .values(
                address_id=row._mapping["id"],
                # draft 에서만 address_ready 로 전이 — 이후 단계 status 는
                # 주소 재입력으로 되돌리지 않는다 (in-memory 구현과 동일).
                status=sa.case(
                    (_SESSIONS.c.status == "draft", "address_ready"),
                    else_=_SESSIONS.c.status,
                ),
                last_activity_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )
    return dict(row._mapping)


async def _db_insert_floorplan_upload(
    values: dict[str, Any], *, session_id: uuid.UUID
) -> dict[str, Any]:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(_FLOORPLAN_UPLOADS)
                .values(**values)
                .returning(*_FLOORPLAN_UPLOADS.c)
            )
        ).one()
        await conn.execute(_touch_session_stmt(session_id))
    return dict(row._mapping)


async def _db_select_candidate_revision_keys(
    session_id: uuid.UUID, lookup_revision: int
) -> tuple[set[uuid.UUID], set[int]]:
    """같은 revision 에 이미 저장된 (floorplan_id, rank) 집합 — 사전 충돌 검사용."""

    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(
                    _FLOORPLAN_CANDIDATES.c.floorplan_id,
                    _FLOORPLAN_CANDIDATES.c.rank,
                ).where(
                    _FLOORPLAN_CANDIDATES.c.session_id == session_id,
                    _FLOORPLAN_CANDIDATES.c.lookup_revision == lookup_revision,
                )
            )
        ).all()
    floorplan_ids = {row.floorplan_id for row in rows if row.floorplan_id is not None}
    ranks = {row.rank for row in rows}
    return floorplan_ids, ranks


async def _db_insert_floorplan_candidates(
    rows: list[dict[str, Any]], *, session_id: uuid.UUID
) -> list[dict[str, Any]]:
    """후보 batch INSERT — 단일 트랜잭션이라 partial-save 가 남지 않는다.

    사전 검사를 통과해도 동시 호출이 같은 unique key 를 먼저 점유할 수 있다 —
    DB unique constraint 위반은 같은 409 (REVISION_CONFLICT) 로 매핑하고
    트랜잭션 전체가 롤백된다.
    """

    saved: list[dict[str, Any]] = []
    try:
        async with get_engine().begin() as conn:
            for values in rows:
                row = (
                    await conn.execute(
                        sa.insert(_FLOORPLAN_CANDIDATES)
                        .values(**values)
                        .returning(*_FLOORPLAN_CANDIDATES.c)
                    )
                ).one()
                saved.append(dict(row._mapping))
            await conn.execute(_touch_session_stmt(session_id))
    except IntegrityError as exc:
        raise _conflict(
            "Candidate already exists for this revision.",
            code="FLOORPLAN_CANDIDATE_REVISION_CONFLICT",
        ) from exc
    return saved


async def _db_insert_chat_message(
    values: dict[str, Any], *, session_id: uuid.UUID
) -> dict[str, Any]:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(_CHAT_MESSAGES).values(**values).returning(*_CHAT_MESSAGES.c)
            )
        ).one()
        await conn.execute(_touch_session_stmt(session_id))
    return dict(row._mapping)


async def _db_select_chat_message(
    message_id: uuid.UUID,
) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_CHAT_MESSAGES).where(_CHAT_MESSAGES.c.id == message_id)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_select_chat_tool_call(
    tool_call_id: uuid.UUID,
) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_CHAT_TOOL_CALLS).where(_CHAT_TOOL_CALLS.c.id == tool_call_id)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_insert_chat_tool_call(
    values: dict[str, Any], *, session_id: uuid.UUID
) -> dict[str, Any]:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(_CHAT_TOOL_CALLS)
                .values(**values)
                .returning(*_CHAT_TOOL_CALLS.c)
            )
        ).one()
        await conn.execute(_touch_session_stmt(session_id))
    return dict(row._mapping)


async def _db_complete_chat_tool_call(
    tool_call_id: uuid.UUID,
    values: dict[str, Any],
    *,
    session_id: uuid.UUID,
) -> dict[str, Any] | None:
    """tool call 완료 UPDATE — ``status='started'`` guard 로 이중 완료를 차단.

    동시 완료 race 에서 진 쪽은 row 를 얻지 못하고 None 을 받는다 (호출자가
    409 로 매핑).
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_CHAT_TOOL_CALLS)
                .where(
                    _CHAT_TOOL_CALLS.c.id == tool_call_id,
                    _CHAT_TOOL_CALLS.c.status == "started",
                )
                .values(completed_at=sa.func.now(), **values)
                .returning(*_CHAT_TOOL_CALLS.c)
            )
        ).one_or_none()
        if row is None:
            return None
        await conn.execute(_touch_session_stmt(session_id))
    return dict(row._mapping)


# ---------------------------------------------------------------------------
# agent projection seams (CMP-DIRECT) — 에이전트 런타임이 astream 이벤트를
# chat_messages / chat_tool_calls 로 투영할 때의 lc_* idempotency 조회 + 세션
# 결정 전이 + agent_runs 라이프사이클. 모두 internal/runtime-only.
# ---------------------------------------------------------------------------


async def _db_select_chat_message_by_lc_id(
    session_id: uuid.UUID, lc_message_id: str
) -> dict[str, Any] | None:
    """같은 세션에서 ``metadata->>'lc_message_id'`` 로 기존 투영 메시지 조회."""

    # Table.c 는 컬럼 *이름*("metadata")으로 키된다 — ORM 속성명(metadata_)이 아니다.
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_CHAT_MESSAGES).where(
                    _CHAT_MESSAGES.c.session_id == session_id,
                    _CHAT_MESSAGES.c["metadata"]["lc_message_id"].astext
                    == lc_message_id,
                )
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_select_chat_tool_call_by_lc_id(
    session_id: uuid.UUID, lc_tool_call_id: str
) -> dict[str, Any] | None:
    """같은 세션에서 ``metadata->>'lc_tool_call_id'`` 로 기존 투영 툴콜 조회."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_CHAT_TOOL_CALLS).where(
                    _CHAT_TOOL_CALLS.c.session_id == session_id,
                    _CHAT_TOOL_CALLS.c["metadata"]["lc_tool_call_id"].astext
                    == lc_tool_call_id,
                )
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_update_session_fields(
    session_id: uuid.UUID, values: dict[str, Any]
) -> dict[str, Any] | None:
    """세션 service-controlled 필드(status/completion_decision) UPDATE.

    migration 0008 의 reference-scope trigger 가 항상(role 무관) 적용되므로
    분석 단계로의 전이는 주소/도면 선택 선행을 요구한다 — 위반 시 DB 가 raise 하고
    런너가 런을 failed 로 마감한다.
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_SESSIONS)
                .where(_SESSIONS.c.id == session_id)
                .values(
                    last_activity_at=sa.func.now(),
                    updated_at=sa.func.now(),
                    **values,
                )
                .returning(*_SESSIONS.c)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_insert_agent_run(values: dict[str, Any]) -> dict[str, Any] | None:
    """`agent_runs` INSERT(멱등). 같은 ``id`` 가 이미 있으면 ON CONFLICT DO NOTHING 으로
    None 을 반환한다 — 라우터가 헤더 노출 전에 만든 placeholder 나 이른 ``/interrupt``
    가 만든 취소 row 위로 generator 가 다시 create 해도 충돌하지 않게(#early-interrupt-
    race). 활성 런 1개 부분 유니크 위반(IntegrityError)은 호출자(``create_agent_run``)가
    409 로 매핑한다 — seam 이 fake 로 교체돼도 매핑이 유지되도록 public 함수에 둔다.
    """

    stmt = (
        pg_insert(_AGENT_RUNS)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(*_AGENT_RUNS.c)
    )
    async with get_engine().begin() as conn:
        row = (await conn.execute(stmt)).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_select_agent_run(run_id: uuid.UUID) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(sa.select(_AGENT_RUNS).where(_AGENT_RUNS.c.id == run_id))
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_update_agent_run(
    run_id: uuid.UUID, values: dict[str, Any]
) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_AGENT_RUNS)
                .where(_AGENT_RUNS.c.id == run_id)
                .values(updated_at=sa.func.now(), **values)
                .returning(*_AGENT_RUNS.c)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


_ACTIVE_RUN_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "awaiting_input",
    "interrupted",
)


async def _db_select_active_agent_run(
    session_id: uuid.UUID,
) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_AGENT_RUNS)
                .where(
                    _AGENT_RUNS.c.session_id == session_id,
                    _AGENT_RUNS.c.status.in_(_ACTIVE_RUN_STATUSES),
                )
                .order_by(_AGENT_RUNS.c.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_mark_agent_run_running(
    run_id: uuid.UUID,
) -> dict[str, Any] | None:
    """pending → running 조건부 전이(+started_at). 아니면 None."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_AGENT_RUNS)
                .where(
                    _AGENT_RUNS.c.id == run_id,
                    _AGENT_RUNS.c.status == "pending",
                )
                .values(
                    status="running",
                    started_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
                .returning(*_AGENT_RUNS.c)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_cancel_agent_run(run_id: uuid.UUID) -> dict[str, Any] | None:
    """비-terminal 런만 원자적으로 cancelled 로 전이.

    status read 이후 런이 자연 종료되는 race 에서, 무조건 UPDATE 가 terminal
    succeeded/failed 를 cancelled 로 덮어쓰는 것을 막는다 — 조건부라 no-op 이면 None.
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_AGENT_RUNS)
                .where(
                    _AGENT_RUNS.c.id == run_id,
                    _AGENT_RUNS.c.status.not_in(["succeeded", "failed", "cancelled"]),
                )
                .values(
                    status="cancelled",
                    finished_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
                .returning(*_AGENT_RUNS.c)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_finalize_agent_run(
    run_id: uuid.UUID, status: str
) -> dict[str, Any] | None:
    """비-terminal 런만 주어진 terminal status 로 마감(+finished_at). 조건부.

    finalize read 이후 마감 write 직전에 /interrupt 가 cancelled 로 바꾼 race 에서,
    무조건 write 가 그 cancelled 를 succeeded/failed 로 덮어쓰는 것을 막는다 —
    no-op 이면 None(호출자가 실제 terminal 을 다시 읽는다).
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_AGENT_RUNS)
                .where(
                    _AGENT_RUNS.c.id == run_id,
                    _AGENT_RUNS.c.status.not_in(["succeeded", "failed", "cancelled"]),
                )
                .values(
                    status=status,
                    finished_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
                .returning(*_AGENT_RUNS.c)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def _db_claim_resumable_agent_run(
    run_id: uuid.UUID,
) -> dict[str, Any] | None:
    """resumable(awaiting_input/interrupted) 런을 원자적으로 running 으로 전이.

    조건부 UPDATE 라 동시 resume(두 탭/재시도/더블서브밋) 중 단 하나만 성공한다 —
    진 쪽은 None 을 받아 409 로 매핑된다. 같은 row 라 활성-런 유니크는 못 막는다.
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.update(_AGENT_RUNS)
                .where(
                    _AGENT_RUNS.c.id == run_id,
                    _AGENT_RUNS.c.status.in_(["awaiting_input", "interrupted"]),
                )
                .values(
                    status="running",
                    started_at=sa.func.now(),
                    updated_at=sa.func.now(),
                    # 이전 마감의 stale terminal 메타를 지운다 — running 인데 finished_at
                    # 이 남아 lifecycle 소비자가 "이미 끝남"으로 오해하지 않게.
                    finished_at=None,
                    error_code=None,
                    error_message=None,
                )
                .returning(*_AGENT_RUNS.c)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


# ---------------------------------------------------------------------------
# ownership helpers
# ---------------------------------------------------------------------------


async def _resolve_owner_session(
    session_id: uuid.UUID,
    *,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
) -> dict[str, Any]:
    """Owner-gated session lookup + identity-link conversion side effect.

    타인 세션 또는 부재 세션은 동일하게 404 (열거 누수 방지).

    Supabase ``linkIdentity()`` 는 같은 ``auth.users.id`` 를 permanent user 로
    승격한다. DB 에는 ``is_anonymous_owner`` 컬럼이 없으므로 "익명 owner" 는
    ``expires_at IS NOT NULL`` 로 판별한다 — 같은 owner UUID 가 non-anonymous
    token 으로 다시 접근하면 ``expires_at`` 을 해제해 가입 완료 사용자의
    사전검토 artifact 가 익명 TTL cleanup 으로 삭제되지 않게 한다 (board P2-5).
    """

    row = await _db_select_session(session_id)
    if row is None or row["user_id"] != owner_user_id:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")
    if not owner_is_anonymous and row["expires_at"] is not None:
        row = await _db_clear_session_expiry(session_id)
    return row


# ---------------------------------------------------------------------------
# sessions / session_addresses
# ---------------------------------------------------------------------------


async def create_session(
    *,
    user_id: uuid.UUID,
    is_anonymous_owner: bool,
    judgment_schema_version: str | None,
) -> dict[str, Any]:
    """`sessions` row 생성. 익명 owner 도 허용된다.

    익명 owner 가 만든 사전검토 세션은 retention 정책 (``ANON_SESSION_TTL_DAYS``)
    에 따라 ``expires_at`` 가 설정된다. permanent user 는 별도 expiry policy 가
    있을 때까지 ``expires_at = None`` 으로 둔다. cleanup cron 은 Phase D 에서
    이 컬럼을 기준으로 만료 익명 세션을 정리한다.
    """

    settings = get_settings()
    expires_at: datetime | None = None
    if is_anonymous_owner:
        expires_at = _now() + timedelta(days=settings.anon_session_ttl_days)
    return await _db_insert_session(
        {
            "user_id": user_id,
            "judgment_schema_version": judgment_schema_version,
            "expires_at": expires_at,
        }
    )


async def get_owned_session(
    session_id: uuid.UUID,
    *,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """Owner 가 본인인 session row 만 반환. 아니면 404 (열거 누수 방지).

    같은 user_id 가 non-anonymous token 으로 다시 GET 하면 anon-conversion
    side-effect 가 한 번 발생한다 (``_resolve_owner_session`` 참조).
    """

    return await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )


async def _db_list_sessions(
    owner_user_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(_SESSIONS)
                .where(
                    _SESSIONS.c.user_id == owner_user_id,
                    _SESSIONS.c.status != "deleted",
                )
                .order_by(_SESSIONS.c.last_activity_at.desc())
                .limit(limit)
            )
        ).all()
    return [dict(r._mapping) for r in rows]


async def list_owned_sessions(
    *,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """요청자 본인 소유 세션을 최신 활동순으로 반환(목록 화면용). deleted 제외.

    owner_user_id(Supabase sub)로 직접 필터링하므로 익명/permanent 모두 본인 것만
    본다. owner_is_anonymous 는 호출부 일관성을 위해 받되 필터에는 user_id 만 쓴다.
    """

    return await _db_list_sessions(owner_user_id, limit)


async def get_session_report(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """리포트용 세션+주소 번들을 반환. 판정이 없으면 404 REPORT_NOT_READY.

    리포트의 정본은 ``sessions.rule_eval_result`` 다(에이전트 evaluate_rules 가 영속).
    아직 없으면(대화 미완료) 가짜 판정을 내지 않고 미준비로 응답한다.
    """

    session = await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    if session.get("rule_eval_result") is None:
        raise _not_found("Report is not ready yet.", code="REPORT_NOT_READY")
    address = await _db_select_session_address(session_id)
    return {"session": session, "address": address}


# session_addresses 컬럼 — partial upsert 가 기존 값을 덮어쓰지 않도록 본 화이트리스트
# 안에 있는 key 만 payload 에서 받아 row 에 적용한다.
_ADDRESS_FIELDS: tuple[str, ...] = (
    "road_address",
    "jibun_address",
    "apartment_name",
    "building_dong",
    "unit_ho",
    "floor_no",
    "exclusive_area_m2",
    "size_type",
    "building_identity",
    "address_provider",
)


# Address sufficiency 기준 — `address_ready` 로 status 를 전이시키려면 본
# heuristic 을 통과해야 한다. road/jibun 주소 문자열 또는 의미 있는
# building_identity (PNU 등) 중 하나 이상이 있어야 한다.
def _address_is_sufficient(row: dict[str, Any]) -> bool:
    if (row.get("road_address") or "").strip():
        return True
    if (row.get("jibun_address") or "").strip():
        return True
    identity = row.get("building_identity") or {}
    return bool(identity)


async def upsert_session_address(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """`session_addresses` row 를 partial-upsert 한다 (1 session = 1 address).

    Router 는 ``model_dump(exclude_unset=True)`` 로 client 가 명시한 key 만
    payload 로 넘긴다. 본 함수는 기존 row 를 읽어 그 key 만 merge 해 누락
    필드를 보존한다 (board P2-1). road/jibun/building_identity 중 최소 한
    가지가 없으면 ``INSUFFICIENT_ADDRESS_DATA`` 로 거절하고 status 도 전이하지
    않는다 (board P2-2).
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )

    existing = await _db_select_session_address(session_id)
    if existing is not None:
        row: dict[str, Any] = dict(existing)
    else:
        row = {
            "road_address": None,
            "jibun_address": None,
            "apartment_name": None,
            "building_dong": None,
            "unit_ho": None,
            "floor_no": None,
            "exclusive_area_m2": None,
            "size_type": None,
            "building_identity": {},
            "address_provider": None,
        }

    # 명시된 field 만 덮어쓴다 — 나머지는 기존 값을 유지.
    for field in _ADDRESS_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if field == "exclusive_area_m2":
            row[field] = _decimal(value)
        elif field == "building_identity":
            # explicit None 으로 비우려는 의도가 없으므로 None 은 무시,
            # dict 만 받는다. 빈 dict 는 sufficiency 체크에서 자연 reject.
            if value is None:
                continue
            row[field] = dict(value)
        else:
            row[field] = value

    if not _address_is_sufficient(row):
        raise _unprocessable(
            (
                "Address payload must include road_address, jibun_address, "
                "or a non-empty building_identity."
            ),
            code="INSUFFICIENT_ADDRESS_DATA",
        )

    address_values: dict[str, Any] = {field: row[field] for field in _ADDRESS_FIELDS}
    address_values["session_id"] = session_id
    address_values["user_id"] = owner_user_id
    return await _db_upsert_session_address(address_values, session_id=session_id)


# ---------------------------------------------------------------------------
# floorplan_uploads / floorplan_candidates
# ---------------------------------------------------------------------------


async def create_floorplan_upload(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    return await _db_insert_floorplan_upload(
        {
            "session_id": session_id,
            "user_id": owner_user_id,
            "file_name": payload.get("file_name"),
            "source_note": payload.get("source_note"),
            "upload_metadata": dict(payload.get("upload_metadata") or {}),
        },
        session_id=session_id,
    )


async def _db_insert_floorplan_asset(values: dict[str, Any]) -> dict[str, Any]:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(_FLOORPLAN_ASSETS)
                .values(**values)
                .returning(*_FLOORPLAN_ASSETS.c)
            )
        ).one()
    return dict(row._mapping)


async def _db_select_selected_floorplan_asset(
    session_id: uuid.UUID,
) -> dict[str, Any] | None:
    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(_FLOORPLAN_ASSETS)
                .select_from(
                    _SESSIONS.join(
                        _FLOORPLAN_ASSETS,
                        _SESSIONS.c.selected_floorplan_asset_id
                        == _FLOORPLAN_ASSETS.c.id,
                    )
                )
                .where(_SESSIONS.c.id == session_id)
            )
        ).one_or_none()
    return dict(row._mapping) if row is not None else None


async def create_floorplan_asset(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """업로드된 도면 파일의 storage 메타데이터를 ``floorplan_assets`` 에 기록하고,
    세션의 ``selected_floorplan_asset_id`` 로 연결한다.

    실제 바이너리는 클라이언트가 presigned URL 로 Storage 에 직접 PUT 한 뒤이며,
    본 함수는 ``bucket``/``object_key`` 등 메타만 받는다(파일 자체는 저장하지 않음).
    세그멘테이션 도구가 이 asset 을 서명해 HF 엔드포인트로 보낸다.
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    asset = await _db_insert_floorplan_asset(
        {
            "session_id": session_id,
            "owner_user_id": owner_user_id,
            "kind": "original",
            "storage_provider": "s3",
            "bucket": payload["bucket"],
            "object_key": payload["object_key"],
            "content_type": payload["content_type"],
            "byte_size": payload["byte_size"],
            "sha256_hex": payload.get("sha256_hex"),
            # 사용자 업로드 원본은 검사 전이므로 pending — 세그멘테이션은 clean(또는
            # 설정상 허용)일 때만 분석한다(#scan-gate, schema plan §1534/§1588).
            "scan_status": "pending",
        }
    )
    # 세션을 이 asset 으로 연결한다. main_flow 는 비-authenticated 풀러로 쓰므로 0008
    # client-guard 트리거는 early-return 하고, 같은 세션 소속 asset 이라 reference-scope
    # 도 통과한다(상태 전이는 강제하지 않음 — 에이전트 플로우가 status 를 진행).
    await _db_update_session_fields(
        session_id, {"selected_floorplan_asset_id": asset["id"]}
    )
    return asset


async def get_selected_floorplan_asset(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any] | None:
    """세션에 선택된 도면 asset 을 반환(없으면 None). owner-gated."""

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    return await _db_select_selected_floorplan_asset(session_id)


async def set_session_verdict(
    *, session_id: uuid.UUID, rule_eval_result: dict[str, Any]
) -> dict[str, Any]:
    """룰 판정 결과(rule-eval-result)를 세션에 영속한다 — runtime-only.

    에이전트가 evaluate_rules 로 verdict 를 만든 직후 호출한다. 이 값이 채워지면
    GET /sessions/{id}/report 가 리포트를 제공한다(rule_eval_result IS NOT NULL =
    리포트 준비됨). owner 검증은 caller(런너)가 세션 컨텍스트로 이미 보장한다.
    """

    row = await _db_update_session_fields(
        session_id,
        {"rule_eval_result": dict(rule_eval_result), "rule_evaluated_at": _now()},
    )
    if row is None:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")
    return row


async def save_floorplan_candidate_snapshot(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    lookup_revision: int,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """후보 snapshot 저장 — **internal/runtime-only**.

    Public HTTP route 가 없다. 백엔드 검색/매칭 서비스 (Phase B agent runtime)
    가 직접 호출하며, owner_user_id 는 호출 측이 미리 검증한 session owner 다
    (board P2-3: client-writable 화면에서 후보 snapshot 을 받지 않는다).

    같은 ``(session_id, lookup_revision, floorplan_id)`` 또는 ``(..., rank)`` 가
    중복되면 409. 다른 ``lookup_revision`` 끼리는 독립이다.

    batch 절반만 들어간 partial-save 상태를 남기면 후속 재시도가
    ``REVISION_CONFLICT`` 로 막혀 복구 불가능해진다. 그래서 (1) 모든 item 을
    먼저 검증해 staged row 를 만들고, (2) 단일 트랜잭션으로 INSERT 한다 —
    DB unique constraint 위반 (동시 호출 race) 도 트랜잭션 전체 롤백 + 409 다.

    각 item 은 사용자가 본 후보 표시값을 영구 보존하기 위해
    ``floorplan_snapshot`` (비어 있지 않은 dict) 을 반드시 포함한다.
    ``floorplans`` catalog row 가 ``ON DELETE SET NULL`` 로 사라져도 후보 화면
    재현이 가능해야 한다 (board round-3 #4).
    """

    session = await _db_select_session(session_id)
    if session is None or session["user_id"] != owner_user_id:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

    existing_floorplans, existing_ranks = await _db_select_candidate_revision_keys(
        session_id, lookup_revision
    )

    # Pass 1 — 모든 item 을 검증하고 staged row 를 만든다. 어떤 row 도
    # 아직 INSERT 되지 않는다.
    seen_ranks: set[int] = set()
    seen_floorplans: set[uuid.UUID] = set()
    staged: list[dict[str, Any]] = []
    for item in items:
        floorplan_id = item["floorplan_id"]
        rank = item["rank"]
        if floorplan_id in seen_floorplans:
            raise _conflict(
                "Duplicate floorplan_id within candidate snapshot.",
                code="FLOORPLAN_CANDIDATE_DUPLICATE_FLOORPLAN",
            )
        if rank in seen_ranks:
            raise _conflict(
                "Duplicate rank within candidate snapshot.",
                code="FLOORPLAN_CANDIDATE_DUPLICATE_RANK",
            )
        seen_floorplans.add(floorplan_id)
        seen_ranks.add(rank)

        if floorplan_id in existing_floorplans:
            raise _conflict(
                "Candidate already exists for this revision.",
                code="FLOORPLAN_CANDIDATE_REVISION_CONFLICT",
            )
        # DB unique (session_id, lookup_revision, rank) — 다른 batch 에서
        # 이미 사용된 rank 가 같은 revision 안으로 다시 들어오면 reject.
        if rank in existing_ranks:
            raise _conflict(
                "Rank already used within this revision.",
                code="FLOORPLAN_CANDIDATE_REVISION_CONFLICT",
            )

        snapshot_raw = item.get("floorplan_snapshot")
        if not isinstance(snapshot_raw, dict) or not snapshot_raw:
            raise _unprocessable(
                (
                    "Candidate item must include a non-empty floorplan_snapshot "
                    "(display label, type, thumbnail metadata) so deleted "
                    "catalog rows do not erase user-visible history."
                ),
                code="FLOORPLAN_CANDIDATE_SNAPSHOT_REQUIRED",
            )

        staged.append(
            {
                "session_id": session_id,
                "lookup_revision": lookup_revision,
                "floorplan_id": floorplan_id,
                "rank": rank,
                "confidence": _decimal(item["confidence"]),
                "match_reasons": list(item.get("match_reasons") or []),
                "lookup_input": dict(item.get("lookup_input") or {}),
                "floorplan_snapshot": dict(snapshot_raw),
            }
        )

    # Pass 2 — 모든 검증이 끝났으므로 단일 트랜잭션으로 commit.
    rows = await _db_insert_floorplan_candidates(staged, session_id=session_id)
    rows.sort(key=lambda r: r["rank"])
    return rows


# ---------------------------------------------------------------------------
# chat_messages / chat_tool_calls
# ---------------------------------------------------------------------------


async def append_chat_message(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """공개 endpoint 경로 — ``role='user'`` message 만 받는다.

    assistant / system / tool message 는 ``append_internal_chat_message`` 로만
    만든다. Pydantic schema 가 1차 차단하지만 service 단에서도 ``role`` 을
    무시하고 항상 user 로 기록한다 (depth-in-defense).
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    return await _db_insert_chat_message(
        {
            "session_id": session_id,
            "user_id": owner_user_id,
            "role": "user",
            "content": payload["content"],
            # user-source content 는 외부 입력 — masking 정책은 별 이슈 (Phase A
            # PII redaction track) 이지만 기본값은 False 로 둔다.
            "content_redacted": False,
            "ui_components": [],
            "judgment_snapshot": None,
            "metadata": dict(payload.get("metadata") or {}),
        },
        session_id=session_id,
    )


async def append_internal_chat_message(
    *,
    session_id: uuid.UUID,
    role: str,
    content: str,
    ui_components: list[Any] | None = None,
    judgment_snapshot: dict[str, Any] | None = None,
    content_redacted: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Runtime/내부 서비스 전용 — HTTP 로 노출하지 않는다.

    agent runtime, FLOW_GUARD evaluator, rule engine 등이 만들어내는
    assistant/system/tool message 를 ``chat_messages`` 에 기록한다. 외부
    request 에서는 호출하지 않으며, 호출 권한은 caller (내부 서비스 / Phase B
    job runner) 가 관리한다. owner check 가 없는 이유는 caller 가 이미 session
    소유권을 검증한 상태에서 부르기 때문이다.
    """

    if role not in {"assistant", "system", "tool"}:
        raise ValueError(
            "append_internal_chat_message 는 assistant/system/tool 만 허용한다."
        )

    session = await _db_select_session(session_id)
    if session is None:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

    return await _db_insert_chat_message(
        {
            "session_id": session_id,
            # assistant/system/tool message 는 agent runtime 이 만든 것이라
            # user_id 는 null 이 맞다 (DB 설계 문서의 chat_messages 설명).
            "user_id": None,
            "role": role,
            "content": content,
            "content_redacted": bool(content_redacted),
            "ui_components": list(ui_components or []),
            "judgment_snapshot": judgment_snapshot,
            "metadata": dict(metadata or {}),
        },
        session_id=session_id,
    )


async def start_chat_tool_call(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """`chat_tool_calls` row 생성 — **internal/runtime-only**.

    Phase A 의 public 라우터는 본 함수를 호출하지 않는다 (board P2-4).
    agent runtime / rule engine / 내부 평가 서비스가 owner_user_id 를 직접
    명시해 호출한다. owner check 는 호출 측이 이미 마쳤지만 service 단에서도
    한 번 더 확인해 다른 owner 의 session 에 row 가 새지 않게 한다.
    """

    session = await _db_select_session(session_id)
    if session is None or session["user_id"] != owner_user_id:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

    message_id = payload.get("message_id")
    if message_id is not None:
        message = await _db_select_chat_message(message_id)
        if message is None or message["session_id"] != session_id:
            raise _not_found(
                "Referenced chat message not found in this session.",
                code="CHAT_MESSAGE_NOT_FOUND",
            )

    parent_id = payload.get("parent_tool_call_id")
    if parent_id is not None:
        parent = await _db_select_chat_tool_call(parent_id)
        if parent is None or parent["session_id"] != session_id:
            raise _not_found(
                "Parent tool call not found in this session.",
                code="CHAT_TOOL_CALL_PARENT_NOT_FOUND",
            )

    return await _db_insert_chat_tool_call(
        {
            "session_id": session_id,
            "message_id": message_id,
            "parent_tool_call_id": parent_id,
            "user_id": owner_user_id,
            "tool_name": payload["tool_name"],
            "tool_kind": payload["tool_kind"],
            "status": "started",
            "input": dict(payload.get("input") or {}),
            "metadata": dict(payload.get("metadata") or {}),
        },
        session_id=session_id,
    )


async def complete_chat_tool_call(
    *,
    session_id: uuid.UUID,
    tool_call_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """`chat_tool_calls` 라이프사이클 완료 — **internal/runtime-only**.

    public 라우터는 본 함수를 호출하지 않는다 (board P2-4). 외부 client 가
    임의 ``output`` / ``status`` 를 주입해 agent-internal 결과를 위조하는 것을
    막기 위함.
    """

    session = await _db_select_session(session_id)
    if session is None or session["user_id"] != owner_user_id:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

    row = await _db_select_chat_tool_call(tool_call_id)
    if row is None or row["session_id"] != session_id:
        raise _not_found("Tool call not found.", code="CHAT_TOOL_CALL_NOT_FOUND")
    if row["status"] != "started":
        raise _conflict(
            "Tool call already completed.",
            code="CHAT_TOOL_CALL_ALREADY_COMPLETED",
        )

    # DB 비고: tool output 이 UI 로 렌더링되지 않아도 `output` 또는
    # `output_summary` 로 저장 가능해야 한다. 둘 다 None 이어도 허용.
    updated = await _db_complete_chat_tool_call(
        tool_call_id,
        {
            "status": payload["status"],
            "output": (
                dict(payload["output"]) if payload.get("output") is not None else None
            ),
            "output_summary": payload.get("output_summary"),
            "error_code": payload.get("error_code"),
            "error_message": payload.get("error_message"),
            "duration_ms": payload.get("duration_ms"),
        },
        session_id=session_id,
    )
    if updated is None:
        # 사전 status 검사 이후 다른 트랜잭션이 먼저 완료한 race — 같은 409.
        raise _conflict(
            "Tool call already completed.",
            code="CHAT_TOOL_CALL_ALREADY_COMPLETED",
        )
    return updated


# ---------------------------------------------------------------------------
# agent projection / runs (internal/runtime-only) — CMP-DIRECT
# ---------------------------------------------------------------------------


async def find_chat_message_by_lc_id(
    *, session_id: uuid.UUID, lc_message_id: str
) -> dict[str, Any] | None:
    """투영 idempotency — 같은 LC 메시지가 이미 기록됐는지 확인(resume replay)."""

    return await _db_select_chat_message_by_lc_id(session_id, lc_message_id)


async def _db_list_chat_messages(
    session_id: uuid.UUID, limit: int
) -> list[dict[str, Any]]:
    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(_CHAT_MESSAGES)
                .where(
                    _CHAT_MESSAGES.c.session_id == session_id,
                    _CHAT_MESSAGES.c.role.in_(("user", "assistant")),
                )
                .order_by(_CHAT_MESSAGES.c.created_at.asc())
                .limit(limit)
            )
        ).all()
    return [dict(r._mapping) for r in rows]


async def list_session_chat_messages(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """소유 세션의 user/assistant 메시지를 시간순으로 반환(채팅 UI 마운트 복원용).

    런이 끝나면 resume 스트림이 없어 영속된 transcript 를 다시 흘릴 수 없으므로,
    프론트가 마운트 시 이 GET 으로 과거 메시지를 채운다(#load-history-on-mount).
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    return await _db_list_chat_messages(session_id, limit)


async def find_chat_tool_call_by_lc_id(
    *, session_id: uuid.UUID, lc_tool_call_id: str
) -> dict[str, Any] | None:
    """투영 idempotency — 같은 LC 툴콜이 이미 기록됐는지 확인(resume replay)."""

    return await _db_select_chat_tool_call_by_lc_id(session_id, lc_tool_call_id)


async def set_session_decision(
    *,
    session_id: uuid.UUID,
    status: str | None = None,
    completion_decision: Any = _UNSET,
) -> dict[str, Any]:
    """세션 상태 머신/FLOW_GUARD 결정 전이 — runtime-only.

    ``completion_decision`` 은 None 자체가 "결정 해제"라서 sentinel 로 미지정과
    구분한다. status 와 completion_decision 중 최소 하나는 줘야 한다.
    """

    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
    if completion_decision is not _UNSET:
        values["completion_decision"] = completion_decision
    if not values:
        raise ValueError(
            "set_session_decision 는 status 또는 completion_decision 을 요구한다."
        )

    row = await _db_update_session_fields(session_id, values)
    if row is None:
        raise _not_found("Session not found.", code="SESSION_NOT_FOUND")
    return row


async def create_agent_run(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    model: str,
    input_summary: dict[str, Any] | None = None,
    owner_is_anonymous: bool = False,
    run_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """`agent_runs` row 생성 — runtime-only. thread_id 는 session_id 와 동일.

    세션당 활성 런 1개(부분 유니크)라 동시 시작은 409 AGENT_RUN_ALREADY_ACTIVE.
    ``run_id`` 를 주면 그 id 로 insert 한다 — 라우터가 스트림 시작 전에 헤더로 노출한
    id 와 generator 안에서 만드는 row 를 일치시키기 위함이다(#pre-stream-orphan).
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    values: dict[str, Any] = {
        "session_id": session_id,
        "user_id": owner_user_id,
        "thread_id": session_id,
        "status": "pending",
        "model": model,
        "input_summary": dict(input_summary or {}),
    }
    if run_id is not None:
        values["id"] = run_id
    try:
        row = await _db_insert_agent_run(values)
    except IntegrityError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate == "23503":
            # _resolve_owner_session 성공 후 insert 커밋 전에 세션/유저가 삭제되면
            # 활성-런 유니크가 아니라 FK 위반(23503)이 난다 — 활성 런 복구 경로로
            # 보내지 말고 깔끔히 not-found 로 매핑한다(#unique-only-conflict).
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND") from exc
        if sqlstate not in (None, "23505"):
            # 활성 런 부분 유니크(23505) 외의 무결성 위반은 삼키지 않고 올린다.
            raise
        raise _conflict(
            "An agent run is already active for this session.",
            code="AGENT_RUN_ALREADY_ACTIVE",
        ) from exc
    if row is None:
        # id 충돌(ON CONFLICT DO NOTHING) — 라우터 placeholder 또는 이른 interrupt 의
        # 취소 row 가 같은 id 로 먼저 만들어졌다. 그 row 를 그대로 반환해 멱등 보장한다
        # (취소 row 면 이후 mark_agent_run_running 이 None 을 돌려 런이 멈춘다).
        if run_id is not None:
            existing = await _db_select_agent_run(run_id)
            if existing is not None:
                return existing
        raise _conflict(
            "An agent run is already active for this session.",
            code="AGENT_RUN_ALREADY_ACTIVE",
        )
    return row


async def get_active_agent_run(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any] | None:
    """세션의 활성(pending/running/awaiting_input/interrupted) 런을 반환(없으면 None).

    라우터가 새 런 시작 전에 빠른 409 판정을 하기 위한 owner-gated 읽기. 최종
    경합은 generator 의 insert 가 부분 유니크로 막는다.
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    return await _db_select_active_agent_run(session_id)


async def finalize_agent_run(
    *, run_id: uuid.UUID, status: str
) -> dict[str, Any] | None:
    """비-terminal 런만 terminal status 로 마감. 이미 terminal(동시 cancel 등)이면 None."""

    return await _db_finalize_agent_run(run_id, status)


async def mark_agent_run_running(*, run_id: uuid.UUID) -> dict[str, Any] | None:
    """pending 런만 running 으로 표시(+started_at). 이미 cancelled/terminal 이면 None.

    스트림 시작 전에 /interrupt 가 cancelled 로 바꾼 경우, 무조건 UPDATE 가 다시
    running 으로 되살리지 못하게 한다(#startup-overwrite). None 이면 런너가 중단한다.
    """

    return await _db_mark_agent_run_running(run_id)


async def get_agent_run(
    *,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """소유 세션의 런만 반환(아니면 404, 열거 누수 방지)."""

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    row = await _db_select_agent_run(run_id)
    if row is None or row["session_id"] != session_id:
        raise _not_found("Agent run not found.", code="AGENT_RUN_NOT_FOUND")
    return row


_AGENT_RUN_UPDATABLE: frozenset[str] = frozenset(
    {
        "status",
        "current_step",
        "langsmith_run_id",
        "langsmith_run_url",
        "error_code",
        "error_message",
        "started_at",
        "finished_at",
    }
)


async def update_agent_run(*, run_id: uuid.UUID, **fields: Any) -> dict[str, Any]:
    """런 라이프사이클 필드 UPDATE — runtime-only. 화이트리스트 밖 키는 거부."""

    values = {
        key: value for key, value in fields.items() if key in _AGENT_RUN_UPDATABLE
    }
    unknown = set(fields) - _AGENT_RUN_UPDATABLE
    if unknown:
        raise ValueError(f"update_agent_run: 허용되지 않은 필드 {sorted(unknown)}.")
    if not values:
        raise ValueError("update_agent_run 는 최소 한 개의 갱신 필드를 요구한다.")

    row = await _db_update_agent_run(run_id, values)
    if row is None:
        raise _not_found("Agent run not found.", code="AGENT_RUN_NOT_FOUND")
    return row


async def cancel_agent_run(
    *,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """런을 cancelled 로 전이(소유 세션만). 이미 terminal 이면 그 row 를 그대로 반환.

    조건부 UPDATE 라, interrupt 호출과 자연 종료가 겹쳐도 terminal 상태를 덮어쓰지
    않는다(idempotent).
    """

    try:
        current = await get_agent_run(
            session_id=session_id,
            run_id=run_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
        )
    except ZippinException as exc:
        if getattr(exc, "code", None) != "AGENT_RUN_NOT_FOUND":
            raise
        # run_id 는 헤더로 노출됐지만 start generator 가 아직 row 를 안 만든 창에서의
        # /interrupt — 취소 의도를 cancelled 톰스톤으로 남긴다. generator 의 멱등 create
        # (ON CONFLICT id DO NOTHING)가 이 row 를 받아 mark_running→None→done(cancelled)
        # 로 멈춘다. 톰스톤은 terminal 이라 active 부분유니크를 차지하지 않아 다음 send 를
        # 막지 않고, row 를 미리 만들지 않으므로 pre-stream orphan 도 없다(#early-interrupt).
        tombstone = await _db_insert_agent_run(
            {
                "id": run_id,
                "session_id": session_id,
                "user_id": owner_user_id,
                "thread_id": session_id,
                "status": "cancelled",
                "model": get_settings().agent_model,
                "finished_at": _now(),
            }
        )
        if tombstone is not None:
            return tombstone
        # 그새 generator 가 같은 id 로 만들었다(ON CONFLICT→None) — 정상 취소 경로로.
        current = await get_agent_run(
            session_id=session_id,
            run_id=run_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
        )
    row = await _db_cancel_agent_run(run_id)
    if row is None:
        # 이미 terminal(race) — 최신 row 를 다시 읽어 반환.
        refreshed = await _db_select_agent_run(run_id)
        return refreshed or current
    return row


async def claim_resumable_agent_run(
    *,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool = False,
) -> dict[str, Any]:
    """resume 시작 전 resumable 런을 원자적으로 점유한다(동시 resume race 방지).

    소유 세션의 런만(아니면 404). resumable 상태가 아니거나 이미 running 이면 409.
    """

    await _resolve_owner_session(
        session_id,
        owner_user_id=owner_user_id,
        owner_is_anonymous=owner_is_anonymous,
    )
    existing = await _db_select_agent_run(run_id)
    if existing is None or existing["session_id"] != session_id:
        raise _not_found("Agent run not found.", code="AGENT_RUN_NOT_FOUND")
    row = await _db_claim_resumable_agent_run(run_id)
    if row is None:
        raise _conflict(
            "Run is not resumable or already running.",
            code="AGENT_RUN_NOT_RESUMABLE",
        )
    return row


async def _db_append_pending_ui(
    run_id: uuid.UUID,
    components: list[dict[str, Any]],
    snapshot: dict[str, Any] | None,
) -> None:
    # read-modify-write(한 트랜잭션) — 한 런의 emit 은 그래프 실행상 순차라 안전.
    async with get_engine().begin() as conn:
        sel = (
            await conn.execute(
                sa.select(_AGENT_RUNS.c.pending_ui).where(_AGENT_RUNS.c.id == run_id)
            )
        ).one_or_none()
        if sel is None:
            return
        merged = list(sel.pending_ui or []) + list(components or [])
        values: dict[str, Any] = {"pending_ui": merged, "updated_at": sa.func.now()}
        if snapshot is not None:
            values["pending_judgment_snapshot"] = snapshot
        await conn.execute(
            sa.update(_AGENT_RUNS).where(_AGENT_RUNS.c.id == run_id).values(**values)
        )


async def _db_take_pending_ui(
    run_id: uuid.UUID,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    # read + clear(한 트랜잭션) — drain 후 비워 stale carry-over 를 막는다.
    async with get_engine().begin() as conn:
        sel = (
            await conn.execute(
                sa.select(
                    _AGENT_RUNS.c.pending_ui,
                    _AGENT_RUNS.c.pending_judgment_snapshot,
                ).where(_AGENT_RUNS.c.id == run_id)
            )
        ).one_or_none()
        if sel is None:
            return [], None
        await conn.execute(
            sa.update(_AGENT_RUNS)
            .where(_AGENT_RUNS.c.id == run_id)
            .values(
                pending_ui=[],
                pending_judgment_snapshot=None,
                updated_at=sa.func.now(),
            )
        )
    return list(sel.pending_ui or []), sel.pending_judgment_snapshot


async def append_pending_ui(
    *,
    run_id: uuid.UUID,
    components: list[dict[str, Any]],
    snapshot: dict[str, Any] | None = None,
) -> None:
    """A2UI 버퍼를 런에 내구적으로 누적한다(resume 생존용). runtime-only."""

    await _db_append_pending_ui(run_id, components, snapshot)


async def take_pending_ui(
    *, run_id: uuid.UUID
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """런의 내구 A2UI 버퍼를 읽고 비운다(메시지 투영 시 drain). runtime-only."""

    return await _db_take_pending_ui(run_id)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
