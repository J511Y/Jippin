"""Phase A 메인 흐름 (사전검토 세션/주소/도면/채팅) skeleton 서비스.

이 모듈은 의도적으로 **in-memory** 저장소를 사용한다. Phase A DB migration
([CMP-608]) 가 아직 들어오지 않았기 때문에 실 ``sessions`` /
``session_addresses`` / ``floorplan_uploads`` / ``floorplan_candidates`` /
``chat_messages`` / ``chat_tool_calls`` row 에 INSERT 할 수 없다. 본 skeleton
의 책임은:

1. 라우터 + 스키마 + 서비스 인터페이스를 미리 고정해 후속 이슈가 internal
   refactor 없이 DB-backed repository 만 갈아끼우도록 한다.
2. ownership/auth/legacy-endpoint 회귀 테스트가 지금 통과하도록 한다.

각 함수의 반환 dict 는 Pydantic ``from_attributes=True`` response 모델에
그대로 들어가도록 Phase A 컬럼 이름과 정확히 맞춘다. DB-backed repository 가
들어오면 dict → ORM row 로 swap 가능한 shape 다.

비고:

- ``sessions.user_id`` 는 Supabase ``auth.users.id`` 다. 익명/비익명 모두
  자기 자신의 row 만 본다. ``[[paperclip-shared-tree]]`` 와 무관.
- ``floorplan_candidates`` 는 ``(session_id, lookup_revision, floorplan_id)``
  와 ``(session_id, lookup_revision, rank)`` 이 unique 다. 같은 revision 안에
  중복 저장이 들어오면 409 로 막는다.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..config import get_settings
from ..errors import ZippinException


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _PhaseAStore:
    """단순 in-process 저장소. 실 repository 로 교체될 때까지의 placeholder."""

    sessions: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    session_addresses: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    floorplan_uploads: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    # (session_id, lookup_revision, floorplan_id) -> row
    floorplan_candidates: dict[tuple[uuid.UUID, int, uuid.UUID], dict[str, Any]] = (
        field(default_factory=dict)
    )
    chat_messages: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    chat_tool_calls: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


_store = _PhaseAStore()


def _reset_for_tests() -> None:
    """테스트 격리용. 운영 코드 경로에서는 호출하지 않는다."""

    with _store.lock:
        _store.sessions.clear()
        _store.session_addresses.clear()
        _store.floorplan_uploads.clear()
        _store.floorplan_candidates.clear()
        _store.chat_messages.clear()
        _store.chat_tool_calls.clear()


def _not_found(message: str, code: str = "NOT_FOUND") -> ZippinException:
    return ZippinException(message, code=code, http_status=404)


def _conflict(message: str, code: str) -> ZippinException:
    return ZippinException(message, code=code, http_status=409)


# ---------------------------------------------------------------------------
# sessions / session_addresses
# ---------------------------------------------------------------------------


def create_session(
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
    now = _now()
    session_id = uuid.uuid4()
    expires_at: datetime | None = None
    if is_anonymous_owner:
        expires_at = now + timedelta(days=settings.anon_session_ttl_days)
    row: dict[str, Any] = {
        "id": session_id,
        "user_id": user_id,
        "is_anonymous_owner": is_anonymous_owner,
        "status": "draft",
        "address_id": None,
        "selected_floorplan_id": None,
        "selected_floorplan_upload_id": None,
        "selected_floorplan_asset_id": None,
        "judgment_schema": {},
        "judgment_schema_version": judgment_schema_version,
        "completion_decision": None,
        "last_activity_at": now,
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
    }
    with _store.lock:
        _store.sessions[session_id] = row
    return dict(row)


def get_owned_session(
    session_id: uuid.UUID, *, owner_user_id: uuid.UUID
) -> dict[str, Any]:
    """Owner 가 본인인 session row 만 반환. 아니면 404 (열거 누수 방지)."""

    with _store.lock:
        row = _store.sessions.get(session_id)
        if row is None or row["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")
        return dict(row)


def upsert_session_address(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """`session_addresses` row 를 upsert 한다 (1 session = 1 address)."""

    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None or session["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        address_id = session["address_id"] or uuid.uuid4()
        row: dict[str, Any] = {
            "id": address_id,
            "session_id": session_id,
            "user_id": owner_user_id,
            "road_address": payload.get("road_address"),
            "jibun_address": payload.get("jibun_address"),
            "apartment_name": payload.get("apartment_name"),
            "building_dong": payload.get("building_dong"),
            "unit_ho": payload.get("unit_ho"),
            "floor_no": payload.get("floor_no"),
            "exclusive_area_m2": _decimal(payload.get("exclusive_area_m2")),
            "size_type": payload.get("size_type"),
            "building_identity": dict(payload.get("building_identity") or {}),
            "address_provider": payload.get("address_provider"),
            "normalized_at": None,
            "created_at": (
                _store.session_addresses[address_id]["created_at"]
                if address_id in _store.session_addresses
                else now
            ),
        }
        _store.session_addresses[address_id] = row
        session["address_id"] = address_id
        if session["status"] == "draft":
            session["status"] = "address_ready"
        session["last_activity_at"] = now
        session["updated_at"] = now
        return dict(row)


# ---------------------------------------------------------------------------
# floorplan_uploads / floorplan_candidates
# ---------------------------------------------------------------------------


def create_floorplan_upload(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None or session["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        upload_id = uuid.uuid4()
        row: dict[str, Any] = {
            "id": upload_id,
            "session_id": session_id,
            "user_id": owner_user_id,
            "original_asset_id": None,
            "status": "uploaded",
            "file_name": payload.get("file_name"),
            "source_note": payload.get("source_note"),
            "upload_metadata": dict(payload.get("upload_metadata") or {}),
            "created_at": now,
            "updated_at": now,
        }
        _store.floorplan_uploads[upload_id] = row
        session["last_activity_at"] = now
        session["updated_at"] = now
        return dict(row)


def save_floorplan_candidate_snapshot(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    lookup_revision: int,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """후보 snapshot 저장.

    같은 ``(session_id, lookup_revision, floorplan_id)`` 또는 ``(..., rank)`` 가
    중복되면 409. 다른 ``lookup_revision`` 끼리는 독립이다.

    ``_store`` 가 in-memory dict 라도 batch 절반만 들어간 partial-save 상태를
    남기면 후속 재시도가 ``REVISION_CONFLICT`` 로 막혀 복구 불가능해진다.
    그래서 (1) 모든 item 을 먼저 검증해 charged 된 row 를 만들고,
    (2) 한 번에 dict.update 로 commit 한다. DB-backed repo 로 교체될 때
    같은 (validate-then-insert) 패턴을 그대로 쓰면 된다.
    """

    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None or session["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        existing_ranks = {
            row["rank"]
            for (sid, rev, _fp), row in _store.floorplan_candidates.items()
            if sid == session_id and rev == lookup_revision
        }

        # Pass 1 — 모든 item 을 검증하고 staged row 를 만든다. 어떤 row 도
        # 아직 _store 에 들어가지 않는다.
        seen_ranks: set[int] = set()
        seen_floorplans: set[uuid.UUID] = set()
        staged: list[tuple[tuple[uuid.UUID, int, uuid.UUID], dict[str, Any]]] = []
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

            key = (session_id, lookup_revision, floorplan_id)
            if key in _store.floorplan_candidates:
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

            staged.append(
                (
                    key,
                    {
                        "id": uuid.uuid4(),
                        "session_id": session_id,
                        "lookup_revision": lookup_revision,
                        "floorplan_id": floorplan_id,
                        "rank": rank,
                        "confidence": _decimal(item["confidence"]),
                        "match_reasons": list(item.get("match_reasons") or []),
                        "lookup_input": dict(item.get("lookup_input") or {}),
                        "selected_at": None,
                        "rejected_at": None,
                        "created_at": now,
                    },
                )
            )

        # Pass 2 — 모든 검증이 끝났으므로 한 번에 commit. lock 안에서
        # 다른 caller 가 끼어들 수 없으니 부분 저장 위험 없음.
        rows: list[dict[str, Any]] = []
        for key, row in staged:
            _store.floorplan_candidates[key] = row
            rows.append(dict(row))

        session["last_activity_at"] = now
        session["updated_at"] = now
        rows.sort(key=lambda r: r["rank"])
        return rows


# ---------------------------------------------------------------------------
# chat_messages / chat_tool_calls
# ---------------------------------------------------------------------------


def append_chat_message(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """공개 endpoint 경로 — ``role='user'`` message 만 받는다.

    assistant / system / tool message 는 ``append_internal_chat_message`` 로만
    만든다. Pydantic schema 가 1차 차단하지만 service 단에서도 ``role`` 을
    무시하고 항상 user 로 기록한다 (depth-in-defense).
    """

    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None or session["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        message_id = uuid.uuid4()
        row: dict[str, Any] = {
            "id": message_id,
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
            "created_at": now,
        }
        _store.chat_messages[message_id] = row
        session["last_activity_at"] = now
        session["updated_at"] = now
        return dict(row)


def append_internal_chat_message(
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

    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        message_id = uuid.uuid4()
        row: dict[str, Any] = {
            "id": message_id,
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
            "created_at": now,
        }
        _store.chat_messages[message_id] = row
        session["last_activity_at"] = now
        session["updated_at"] = now
        return dict(row)


def start_chat_tool_call(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None or session["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        message_id = payload.get("message_id")
        if message_id is not None:
            message = _store.chat_messages.get(message_id)
            if message is None or message["session_id"] != session_id:
                raise _not_found(
                    "Referenced chat message not found in this session.",
                    code="CHAT_MESSAGE_NOT_FOUND",
                )

        parent_id = payload.get("parent_tool_call_id")
        if parent_id is not None:
            parent = _store.chat_tool_calls.get(parent_id)
            if parent is None or parent["session_id"] != session_id:
                raise _not_found(
                    "Parent tool call not found in this session.",
                    code="CHAT_TOOL_CALL_PARENT_NOT_FOUND",
                )

        tool_call_id = uuid.uuid4()
        row: dict[str, Any] = {
            "id": tool_call_id,
            "session_id": session_id,
            "message_id": message_id,
            "parent_tool_call_id": parent_id,
            "user_id": owner_user_id,
            "tool_name": payload["tool_name"],
            "tool_kind": payload["tool_kind"],
            "status": "started",
            "input": dict(payload.get("input") or {}),
            "output": None,
            "output_summary": None,
            "error_code": None,
            "error_message": None,
            "duration_ms": None,
            "started_at": now,
            "completed_at": None,
            "metadata": dict(payload.get("metadata") or {}),
        }
        _store.chat_tool_calls[tool_call_id] = row
        session["last_activity_at"] = now
        session["updated_at"] = now
        return dict(row)


def complete_chat_tool_call(
    *,
    session_id: uuid.UUID,
    tool_call_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    now = _now()
    with _store.lock:
        session = _store.sessions.get(session_id)
        if session is None or session["user_id"] != owner_user_id:
            raise _not_found("Session not found.", code="SESSION_NOT_FOUND")

        row = _store.chat_tool_calls.get(tool_call_id)
        if row is None or row["session_id"] != session_id:
            raise _not_found("Tool call not found.", code="CHAT_TOOL_CALL_NOT_FOUND")
        if row["status"] != "started":
            raise _conflict(
                "Tool call already completed.",
                code="CHAT_TOOL_CALL_ALREADY_COMPLETED",
            )

        new_status = payload["status"]
        # DB 비고: tool output 이 UI 로 렌더링되지 않아도 `output` 또는
        # `output_summary` 로 저장 가능해야 한다. 둘 다 None 이어도 허용.
        row["status"] = new_status
        row["output"] = (
            dict(payload["output"]) if payload.get("output") is not None else None
        )
        row["output_summary"] = payload.get("output_summary")
        row["error_code"] = payload.get("error_code")
        row["error_message"] = payload.get("error_message")
        row["duration_ms"] = payload.get("duration_ms")
        row["completed_at"] = now
        session["last_activity_at"] = now
        session["updated_at"] = now
        return dict(row)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
