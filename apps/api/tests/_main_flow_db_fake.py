"""Stateful in-memory fake for the ``main_flow`` DB seams (CMP-DIRECT).

TEST_MODE 에서는 실 DB 에 접속하지 않는다 — ``test_leads_router`` 가
``services.leads._insert_lead`` seam 을 monkeypatch 하는 패턴의 확장으로,
``services.main_flow`` 의 모든 ``_db_*`` seam 을 같은 시그니처의 stateful
fake 로 대체한다. service 레이어의 ownership/검증/merge 로직과 라우터 경로는
실 코드 그대로 실행되고, SQL 트랜잭션 부분만 dict 저장소로 바뀐다.

fake 는 migration 0008 의 server default (status='draft', judgment_schema='{}',
created_at/updated_at/last_activity_at=now()) 와 unique(session_addresses.
session_id) upsert semantics 를 흉내낸다. 반환 dict 는 항상 복사본이다 —
RETURNING 결과가 저장소 live reference 를 노출하지 않는 실 DB 와 같게.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.services import main_flow

# main_flow 의 seam 이 이름 변경/추가되면 monkeypatch 가 즉시 실패하도록
# 명시적 목록을 유지한다 (drift 가드).
_SEAM_NAMES: tuple[str, ...] = (
    "_db_insert_session",
    "_db_select_session",
    "_db_clear_session_expiry",
    "_db_select_session_address",
    "_db_upsert_session_address",
    "_db_insert_floorplan_upload",
    "_db_select_candidate_revision_keys",
    "_db_insert_floorplan_candidates",
    "_db_insert_chat_message",
    "_db_select_chat_message",
    "_db_select_chat_tool_call",
    "_db_insert_chat_tool_call",
    "_db_complete_chat_tool_call",
    # agent projection / runs (CMP-DIRECT)
    "_db_select_chat_message_by_lc_id",
    "_db_select_chat_tool_call_by_lc_id",
    "_db_update_session_fields",
    "_db_insert_agent_run",
    "_db_select_agent_run",
    "_db_update_agent_run",
    "_db_claim_resumable_agent_run",
)

# agent_runs 의 활성(=세션당 1개 부분 유니크) 상태 집합.
_ACTIVE_RUN_STATUSES: frozenset[str] = frozenset(
    {"pending", "running", "awaiting_input", "interrupted"}
)


def _fake_integrity_error(message: str) -> IntegrityError:
    return IntegrityError(message, None, Exception(message))


def _now() -> datetime:
    return datetime.now(UTC)


class FakeMainFlowDb:
    """Phase A 테이블의 dict 저장소 — seam 함수와 1:1 메서드."""

    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, dict[str, Any]] = {}
        self.session_addresses: dict[uuid.UUID, dict[str, Any]] = {}
        self.floorplan_uploads: dict[uuid.UUID, dict[str, Any]] = {}
        # (session_id, lookup_revision, floorplan_id) -> row
        self.floorplan_candidates: dict[
            tuple[uuid.UUID, int, uuid.UUID | None], dict[str, Any]
        ] = {}
        self.chat_messages: dict[uuid.UUID, dict[str, Any]] = {}
        self.chat_tool_calls: dict[uuid.UUID, dict[str, Any]] = {}
        self.agent_runs: dict[uuid.UUID, dict[str, Any]] = {}

    # -- helpers ---------------------------------------------------------

    def _touch_session(self, session_id: uuid.UUID) -> None:
        row = self.sessions[session_id]
        now = _now()
        row["last_activity_at"] = now
        row["updated_at"] = now

    # -- sessions --------------------------------------------------------

    async def _db_insert_session(self, values: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "user_id": values["user_id"],
            "status": "draft",
            "address_id": None,
            "selected_floorplan_id": None,
            "selected_floorplan_upload_id": None,
            "selected_floorplan_asset_id": None,
            "judgment_schema": {},
            "judgment_schema_version": values.get("judgment_schema_version"),
            "completion_decision": None,
            "last_activity_at": now,
            "expires_at": values.get("expires_at"),
            "created_at": now,
            "updated_at": now,
        }
        self.sessions[row["id"]] = row
        return dict(row)

    async def _db_select_session(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.sessions.get(session_id)
        return dict(row) if row is not None else None

    async def _db_clear_session_expiry(self, session_id: uuid.UUID) -> dict[str, Any]:
        row = self.sessions[session_id]
        row["expires_at"] = None
        row["updated_at"] = _now()
        return dict(row)

    # -- session_addresses -------------------------------------------------

    async def _db_select_session_address(
        self, session_id: uuid.UUID
    ) -> dict[str, Any] | None:
        for row in self.session_addresses.values():
            if row["session_id"] == session_id:
                return dict(row)
        return None

    async def _db_upsert_session_address(
        self, address_values: dict[str, Any], *, session_id: uuid.UUID
    ) -> dict[str, Any]:
        existing = next(
            (
                row
                for row in self.session_addresses.values()
                if row["session_id"] == session_id
            ),
            None,
        )
        if existing is None:
            row: dict[str, Any] = {
                "id": uuid.uuid4(),
                "normalized_at": None,
                "created_at": _now(),
                **address_values,
            }
            self.session_addresses[row["id"]] = row
        else:
            # ON CONFLICT (session_id) DO UPDATE — id/created_at/normalized_at
            # 은 보존된다 (set 절 밖).
            existing.update(
                {
                    key: value
                    for key, value in address_values.items()
                    if key not in ("session_id", "user_id")
                }
            )
            row = existing

        session = self.sessions[session_id]
        session["address_id"] = row["id"]
        if session["status"] == "draft":
            session["status"] = "address_ready"
        self._touch_session(session_id)
        return dict(row)

    # -- floorplan_uploads -------------------------------------------------

    async def _db_insert_floorplan_upload(
        self, values: dict[str, Any], *, session_id: uuid.UUID
    ) -> dict[str, Any]:
        now = _now()
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "original_asset_id": None,
            "status": "uploaded",
            "created_at": now,
            "updated_at": now,
            **values,
        }
        self.floorplan_uploads[row["id"]] = row
        self._touch_session(session_id)
        return dict(row)

    # -- floorplan_candidates ----------------------------------------------

    async def _db_select_candidate_revision_keys(
        self, session_id: uuid.UUID, lookup_revision: int
    ) -> tuple[set[uuid.UUID], set[int]]:
        floorplan_ids: set[uuid.UUID] = set()
        ranks: set[int] = set()
        for (sid, rev, fp_id), row in self.floorplan_candidates.items():
            if sid == session_id and rev == lookup_revision:
                if fp_id is not None:
                    floorplan_ids.add(fp_id)
                ranks.add(row["rank"])
        return floorplan_ids, ranks

    async def _db_insert_floorplan_candidates(
        self, rows: list[dict[str, Any]], *, session_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        now = _now()
        saved: list[dict[str, Any]] = []
        for values in rows:
            row: dict[str, Any] = {
                "id": uuid.uuid4(),
                "selected_at": None,
                "rejected_at": None,
                "created_at": now,
                **values,
            }
            key = (row["session_id"], row["lookup_revision"], row["floorplan_id"])
            self.floorplan_candidates[key] = row
            saved.append(dict(row))
        self._touch_session(session_id)
        return saved

    # -- chat_messages -------------------------------------------------------

    async def _db_insert_chat_message(
        self, values: dict[str, Any], *, session_id: uuid.UUID
    ) -> dict[str, Any]:
        # 부분 유니크(session_id, metadata->>'lc_message_id') 백스톱 — resume race.
        lc_id = (values.get("metadata") or {}).get("lc_message_id")
        if lc_id is not None and any(
            r["session_id"] == values["session_id"]
            and (r.get("metadata") or {}).get("lc_message_id") == lc_id
            for r in self.chat_messages.values()
        ):
            raise _fake_integrity_error("duplicate lc_message_id")
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "created_at": _now(),
            **values,
        }
        self.chat_messages[row["id"]] = row
        self._touch_session(session_id)
        return dict(row)

    async def _db_select_chat_message(
        self, message_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = self.chat_messages.get(message_id)
        return dict(row) if row is not None else None

    async def _db_select_chat_message_by_lc_id(
        self, session_id: uuid.UUID, lc_message_id: str
    ) -> dict[str, Any] | None:
        for row in self.chat_messages.values():
            if (
                row["session_id"] == session_id
                and (row.get("metadata") or {}).get("lc_message_id") == lc_message_id
            ):
                return dict(row)
        return None

    # -- chat_tool_calls -----------------------------------------------------

    async def _db_select_chat_tool_call(
        self, tool_call_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = self.chat_tool_calls.get(tool_call_id)
        return dict(row) if row is not None else None

    async def _db_select_chat_tool_call_by_lc_id(
        self, session_id: uuid.UUID, lc_tool_call_id: str
    ) -> dict[str, Any] | None:
        for row in self.chat_tool_calls.values():
            if (
                row["session_id"] == session_id
                and (row.get("metadata") or {}).get("lc_tool_call_id")
                == lc_tool_call_id
            ):
                return dict(row)
        return None

    async def _db_insert_chat_tool_call(
        self, values: dict[str, Any], *, session_id: uuid.UUID
    ) -> dict[str, Any]:
        # 부분 유니크(session_id, metadata->>'lc_tool_call_id') 백스톱 — resume race.
        lc_id = (values.get("metadata") or {}).get("lc_tool_call_id")
        if lc_id is not None and any(
            r["session_id"] == values["session_id"]
            and (r.get("metadata") or {}).get("lc_tool_call_id") == lc_id
            for r in self.chat_tool_calls.values()
        ):
            raise _fake_integrity_error("duplicate lc_tool_call_id")
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "output": None,
            "output_summary": None,
            "error_code": None,
            "error_message": None,
            "duration_ms": None,
            "started_at": _now(),
            "completed_at": None,
            **values,
        }
        self.chat_tool_calls[row["id"]] = row
        self._touch_session(session_id)
        return dict(row)

    async def _db_complete_chat_tool_call(
        self,
        tool_call_id: uuid.UUID,
        values: dict[str, Any],
        *,
        session_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        row = self.chat_tool_calls.get(tool_call_id)
        # UPDATE ... WHERE id = :id AND status = 'started' 와 동일 semantics.
        if row is None or row["status"] != "started":
            return None
        row.update(values)
        row["completed_at"] = _now()
        self._touch_session(session_id)
        return dict(row)

    # -- sessions (service-field update) ------------------------------------

    async def _db_update_session_fields(
        self, session_id: uuid.UUID, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = self.sessions.get(session_id)
        if row is None:
            return None
        row.update(values)
        self._touch_session(session_id)
        return dict(row)

    # -- agent_runs ----------------------------------------------------------

    async def _db_insert_agent_run(self, values: dict[str, Any]) -> dict[str, Any]:
        # 세션당 활성 런 1개 부분 유니크 백스톱.
        if any(
            r["session_id"] == values["session_id"]
            and r["status"] in _ACTIVE_RUN_STATUSES
            for r in self.agent_runs.values()
        ):
            raise _fake_integrity_error("agent run already active for session")
        now = _now()
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "status": "pending",
            "current_step": None,
            "langsmith_run_id": None,
            "langsmith_run_url": None,
            "error_code": None,
            "error_message": None,
            "input_summary": {},
            "started_at": None,
            "finished_at": None,
            "created_at": now,
            "updated_at": now,
            **values,
        }
        self.agent_runs[row["id"]] = row
        return dict(row)

    async def _db_select_agent_run(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.agent_runs.get(run_id)
        return dict(row) if row is not None else None

    async def _db_update_agent_run(
        self, run_id: uuid.UUID, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        row = self.agent_runs.get(run_id)
        if row is None:
            return None
        row.update(values)
        row["updated_at"] = _now()
        return dict(row)

    async def _db_claim_resumable_agent_run(
        self, run_id: uuid.UUID
    ) -> dict[str, Any] | None:
        # 조건부 UPDATE: status IN (awaiting_input, interrupted) → running.
        row = self.agent_runs.get(run_id)
        if row is None or row["status"] not in {"awaiting_input", "interrupted"}:
            return None
        row["status"] = "running"
        row["started_at"] = _now()
        row["updated_at"] = _now()
        return dict(row)


def install_main_flow_fake(monkeypatch) -> FakeMainFlowDb:
    """``main_flow`` 의 모든 ``_db_*`` seam 을 fake 로 대체하고 fake 를 반환."""

    fake = FakeMainFlowDb()
    for name in _SEAM_NAMES:
        # raising=True (default) — main_flow 쪽 seam 이름이 바뀌면 즉시 실패.
        monkeypatch.setattr(main_flow, name, getattr(fake, name))
    return fake
