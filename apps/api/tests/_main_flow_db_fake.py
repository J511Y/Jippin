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
    "_db_advance_session_status",
    "_db_select_session",
    "_db_list_sessions",
    "_db_clear_owner_sessions_expiry",
    "_db_set_session_verdict_if_inputs",
    "_db_clear_session_expiry",
    "_db_select_session_address",
    "_db_upsert_session_address",
    "_db_insert_floorplan_upload",
    "_db_insert_floorplan_asset",
    "_db_select_selected_floorplan_asset",
    "_db_search_floorplan_catalog",
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
    "_db_list_chat_messages",
    "_db_update_session_fields",
    "_db_insert_agent_run",
    "_db_select_agent_run",
    "_db_select_active_agent_run",
    "_db_mark_agent_run_running",
    "_db_update_agent_run",
    "_db_cancel_agent_run",
    "_db_finalize_agent_run",
    "_db_claim_resumable_agent_run",
    "_db_append_pending_ui",
    "_db_take_pending_ui",
    "_db_set_run_analysis_inputs",
    "_db_get_run_analysis_inputs",
)

# agent_runs 의 활성(=세션당 1개 부분 유니크) 상태 집합.
_ACTIVE_RUN_STATUSES: frozenset[str] = frozenset(
    {"pending", "running", "awaiting_input", "interrupted"}
)


class _FakeDbError(Exception):
    """psycopg 의 .sqlstate 를 흉내내는 orig — 호출자가 유니크/FK 위반을 구분."""

    def __init__(self, message: str, sqlstate: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def _fake_integrity_error(message: str, sqlstate: str = "23505") -> IntegrityError:
    # 기본 23505(unique_violation) — 활성 런/lc-id 부분 유니크 위반 재현용.
    return IntegrityError(message, None, _FakeDbError(message, sqlstate))


def _now() -> datetime:
    return datetime.now(UTC)


class FakeMainFlowDb:
    """Phase A 테이블의 dict 저장소 — seam 함수와 1:1 메서드."""

    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, dict[str, Any]] = {}
        self.session_addresses: dict[uuid.UUID, dict[str, Any]] = {}
        self.floorplan_uploads: dict[uuid.UUID, dict[str, Any]] = {}
        self.floorplan_assets: dict[uuid.UUID, dict[str, Any]] = {}
        # 내부 보유 도면 카탈로그(floorplans). 기본 비어 있음(미큐레이션).
        self.floorplans: dict[uuid.UUID, dict[str, Any]] = {}
        # (session_id, lookup_revision, floorplan_id) -> row
        self.floorplan_candidates: dict[
            tuple[uuid.UUID, int, uuid.UUID | None], dict[str, Any]
        ] = {}
        self.chat_messages: dict[uuid.UUID, dict[str, Any]] = {}
        self.chat_tool_calls: dict[uuid.UUID, dict[str, Any]] = {}
        self.agent_runs: dict[uuid.UUID, dict[str, Any]] = {}
        # sessions.status forward-only 전이 이력 (append-only). 각 항목:
        # {session_id, from_status, to_status, reason, run_id, occurred_at}.
        self.session_status_events: list[dict[str, Any]] = []

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
            "rule_eval_result": None,
            "rule_evaluated_at": None,
            "last_activity_at": now,
            "expires_at": values.get("expires_at"),
            "created_at": now,
            "updated_at": now,
        }
        self.sessions[row["id"]] = row
        self.session_status_events.append(
            {
                "session_id": row["id"],
                "from_status": None,
                "to_status": "draft",
                "reason": "session_created",
                "run_id": None,
                "occurred_at": now,
            }
        )
        return dict(row)

    async def _db_advance_session_status(
        self,
        session_id: uuid.UUID,
        target: str,
        *,
        reason: str | None,
        run_id: uuid.UUID | None,
    ) -> dict[str, Any] | None:
        """마일스톤 이벤트(단계별 1회) + forward-only status(real seam 미러).

        reference-scope 트리거는 미적용. status 가 이미 더 높아도 마일스톤 이벤트는
        단계별 1회 기록하고(중복 방지), status 는 더 높을 때만 전진한다.
        """

        rank = {name: i for i, name in enumerate(main_flow.STATUS_ORDER)}
        row = self.sessions.get(session_id)
        if row is None or row["status"] in ("expired", "deleted"):
            return None
        from_status = row["status"]
        already = any(
            e["session_id"] == session_id and e["to_status"] == target
            for e in self.session_status_events
        )
        if not already:
            self.session_status_events.append(
                {
                    "session_id": session_id,
                    "from_status": from_status,
                    "to_status": target,
                    "reason": reason,
                    "run_id": run_id,
                    "occurred_at": _now(),
                }
            )
        if rank.get(from_status, -1) >= rank[target]:
            return None
        row["status"] = target
        self._touch_session(session_id)
        return dict(row)

    async def _db_select_session(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.sessions.get(session_id)
        return dict(row) if row is not None else None

    async def _db_clear_owner_sessions_expiry(self, owner_user_id: uuid.UUID) -> None:
        for row in self.sessions.values():
            if row["user_id"] == owner_user_id and row.get("expires_at") is not None:
                row["expires_at"] = None
                row["updated_at"] = _now()

    async def _db_list_sessions(
        self, owner_user_id: uuid.UUID, limit: int
    ) -> list[dict[str, Any]]:
        rows = [
            r
            for r in self.sessions.values()
            if r["user_id"] == owner_user_id and r.get("status") != "deleted"
        ]
        rows.sort(key=lambda r: r["last_activity_at"], reverse=True)
        return [dict(r) for r in rows[:limit]]

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
        # migration 0016 trg_session_addresses_invalidate_verdict 미러: INSERT(새 주소)는
        # 항상, UPDATE 는 식별 주소 필드가 실제로 바뀔 때만 verdict 를 무효화한다. 같은
        # 주소 재확인(no-op upsert)은 리포트를 떨어뜨리지 않는다(#address-noop-update).
        _ADDRESS_FIELDS = (
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
        if existing is None:
            row: dict[str, Any] = {
                "id": uuid.uuid4(),
                "normalized_at": None,
                "created_at": _now(),
                **address_values,
            }
            self.session_addresses[row["id"]] = row
            address_changed = True
        else:
            # ON CONFLICT (session_id) DO UPDATE — id/created_at/normalized_at
            # 은 보존된다 (set 절 밖).
            merged = {
                key: value
                for key, value in address_values.items()
                if key not in ("session_id", "user_id")
            }
            address_changed = any(
                existing.get(f) != merged.get(f, existing.get(f))
                for f in _ADDRESS_FIELDS
            )
            existing.update(merged)
            row = existing

        session = self.sessions[session_id]
        session["address_id"] = row["id"]
        # status(draft→address_ready) 전이는 public upsert_session_address 가
        # advance_session_status 로 처리한다(real seam 미러) — 여기선 포인터만.
        if address_changed:
            session["rule_eval_result"] = None
            session["rule_evaluated_at"] = None
            session["completion_decision"] = None
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

    # -- floorplan_assets --------------------------------------------------

    async def _db_insert_floorplan_asset(
        self, values: dict[str, Any]
    ) -> dict[str, Any]:
        now = _now()
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "floorplan_id": None,
            "floorplan_upload_id": None,
            "session_id": None,
            "owner_user_id": None,
            "sha256_hex": None,
            "width_px": None,
            "height_px": None,
            "page_count": None,
            "scan_status": "pending",
            "created_at": now,
            "updated_at": now,
            **values,
        }
        self.floorplan_assets[row["id"]] = row
        return dict(row)

    async def _db_select_selected_floorplan_asset(
        self, session_id: uuid.UUID
    ) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        asset_id = session.get("selected_floorplan_asset_id")
        if asset_id is None:
            return None
        row = self.floorplan_assets.get(asset_id)
        return dict(row) if row is not None else None

    async def _db_search_floorplan_catalog(
        self, *, apartment_name: str, building_dong: str | None, limit: int
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in self.floorplans.values():
            if r.get("visibility") != "public_catalog":
                continue
            if r.get("quality_status") != "verified":
                continue
            if apartment_name.lower() not in (r.get("apartment_name") or "").lower():
                continue
            if building_dong and r.get("building_dong") != building_dong:
                continue
            out.append(dict(r))
        return out[:limit]

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

    async def _db_list_chat_messages(
        self, session_id: uuid.UUID, limit: int
    ) -> list[dict[str, Any]]:
        rows = [
            r
            for r in self.chat_messages.values()
            if r["session_id"] == session_id and r.get("role") in ("user", "assistant")
        ]
        rows.sort(key=lambda r: r.get("created_at"))
        return [dict(r) for r in rows[:limit]]

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
        # migration 0016 trg_sessions_invalidate_verdict 미러: 입력 포인터가 바뀌면
        # 영속된 verdict 를 무효화한다(#verdict-input-consistency).
        pointer_keys = (
            "address_id",
            "selected_floorplan_id",
            "selected_floorplan_upload_id",
            "selected_floorplan_asset_id",
        )
        pointer_changed = any(
            k in values and values[k] != row.get(k) for k in pointer_keys
        )
        row.update(values)
        if pointer_changed:
            row["rule_eval_result"] = None
            row["rule_evaluated_at"] = None
            row["completion_decision"] = None
        self._touch_session(session_id)
        return dict(row)

    async def _db_set_session_verdict_if_inputs(
        self,
        session_id: uuid.UUID,
        values: dict[str, Any],
        expected_asset_id: Any,
        expected_address_id: Any,
    ) -> dict[str, Any] | None:
        row = self.sessions.get(session_id)
        if row is None:
            return None
        # _UNSET 인 입력은 검사 생략(main_flow._UNSET 미러).
        if (
            expected_asset_id is not main_flow._UNSET
            and row.get("selected_floorplan_asset_id") != expected_asset_id
        ):
            return None
        if (
            expected_address_id is not main_flow._UNSET
            and row.get("address_id") != expected_address_id
        ):
            return None
        row.update(values)
        row["updated_at"] = _now()
        return dict(row)

    # -- agent_runs ----------------------------------------------------------

    async def _db_insert_agent_run(
        self, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        # ON CONFLICT (id) DO NOTHING — 같은 id 가 이미 있으면 None(멱등 재생성).
        run_id = values.get("id")
        if run_id is not None and run_id in self.agent_runs:
            return None
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
            "pending_ui": [],
            "pending_judgment_snapshot": None,
            "analysis_inputs": None,
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

    async def _db_select_active_agent_run(
        self, session_id: uuid.UUID
    ) -> dict[str, Any] | None:
        rows = [
            row
            for row in self.agent_runs.values()
            if row["session_id"] == session_id and row["status"] in _ACTIVE_RUN_STATUSES
        ]
        if not rows:
            return None
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return dict(rows[0])

    async def _db_mark_agent_run_running(
        self, run_id: uuid.UUID
    ) -> dict[str, Any] | None:
        # 조건부: status == 'pending' → running.
        row = self.agent_runs.get(run_id)
        if row is None or row["status"] != "pending":
            return None
        row["status"] = "running"
        row["started_at"] = _now()
        row["updated_at"] = _now()
        return dict(row)

    async def _db_cancel_agent_run(self, run_id: uuid.UUID) -> dict[str, Any] | None:
        # 조건부: status NOT IN terminal → cancelled.
        row = self.agent_runs.get(run_id)
        if row is None or row["status"] in {"succeeded", "failed", "cancelled"}:
            return None
        row["status"] = "cancelled"
        row["finished_at"] = _now()
        row["updated_at"] = _now()
        return dict(row)

    async def _db_finalize_agent_run(
        self, run_id: uuid.UUID, status: str
    ) -> dict[str, Any] | None:
        # 조건부: status NOT IN terminal → 주어진 terminal status.
        row = self.agent_runs.get(run_id)
        if row is None or row["status"] in {"succeeded", "failed", "cancelled"}:
            return None
        row["status"] = status
        row["finished_at"] = _now()
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
        row["finished_at"] = None
        row["error_code"] = None
        row["error_message"] = None
        return dict(row)

    async def _db_append_pending_ui(
        self,
        run_id: uuid.UUID,
        components: list[dict[str, Any]],
        snapshot: dict[str, Any] | None,
    ) -> None:
        row = self.agent_runs.get(run_id)
        if row is None:
            return
        row["pending_ui"] = list(row.get("pending_ui") or []) + list(components or [])
        if snapshot is not None:
            row["pending_judgment_snapshot"] = snapshot
        row["updated_at"] = _now()

    async def _db_take_pending_ui(
        self, run_id: uuid.UUID
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        row = self.agent_runs.get(run_id)
        if row is None:
            return [], None
        ui = list(row.get("pending_ui") or [])
        snap = row.get("pending_judgment_snapshot")
        row["pending_ui"] = []
        row["pending_judgment_snapshot"] = None
        row["updated_at"] = _now()
        return ui, snap

    async def _db_set_run_analysis_inputs(
        self, run_id: uuid.UUID, payload: dict[str, Any]
    ) -> None:
        row = self.agent_runs.get(run_id)
        if row is None:
            return
        row["analysis_inputs"] = dict(payload)
        row["updated_at"] = _now()

    async def _db_get_run_analysis_inputs(
        self, run_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = self.agent_runs.get(run_id)
        if row is None:
            return None
        payload = row.get("analysis_inputs")
        return dict(payload) if payload is not None else None


def install_main_flow_fake(monkeypatch) -> FakeMainFlowDb:
    """``main_flow`` 의 모든 ``_db_*`` seam 을 fake 로 대체하고 fake 를 반환."""

    fake = FakeMainFlowDb()
    for name in _SEAM_NAMES:
        # raising=True (default) — main_flow 쪽 seam 이름이 바뀌면 즉시 실패.
        monkeypatch.setattr(main_flow, name, getattr(fake, name))
    return fake
