"""Phase A round-3 schema/DB alignment regression tests (CMP-609).

board round-3 리뷰 4건이 코드와 정합되어 있는지 직접 검증한다. PR #68 이
이미 merge 된 상태에서 후속 ``feat/api-phase-a-schema-fixes`` PR 로 들어가는
변경의 기본 가드.

1. ``SessionResponse`` 는 DB row 에 존재하지 않는 ``is_anonymous_owner`` 를
   더 이상 노출하지 않는다. ``from_attributes=True`` 가 ORM-like 객체에서
   해당 속성을 읽으려 시도하지 않는다.
2. ``ChatMessageResponse`` / ``ChatToolCallResponse`` 의 ``metadata`` 필드는
   SQLAlchemy ``metadata_`` 매핑과 dict-shape 둘 다 받는다.
3. ``FloorplanCandidateResponse.floorplan_id`` 는 nullable 이다 — catalog row
   삭제 후에도 snapshot 으로 응답 가능해야 한다.
4. ``FloorplanCandidateItemInput`` 는 ``floorplan_snapshot`` 을 필수로 받는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.schemas.chat import ChatMessageResponse, ChatToolCallResponse
from src.schemas.floorplans import (
    FloorplanCandidateItemInput,
    FloorplanCandidateResponse,
)
from src.schemas.sessions import SessionResponse


def _session_row(**overrides):
    base = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "status": "draft",
        "address_id": None,
        "selected_floorplan_id": None,
        "selected_floorplan_upload_id": None,
        "selected_floorplan_asset_id": None,
        "judgment_schema": {},
        "judgment_schema_version": None,
        "completion_decision": None,
        "last_activity_at": datetime.now(UTC),
        "expires_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


def test_session_response_omits_is_anonymous_owner_field():
    """board round-3 #1: response shape 에서 ``is_anonymous_owner`` 가 사라졌다.

    DB ``sessions`` row 와 from_attributes 정합. Supabase truth (``auth.users.is_anonymous``)
    는 client 가 자기 토큰에서 얻고, 서버 응답은 DB 컬럼만 노출한다.
    """

    assert "is_anonymous_owner" not in SessionResponse.model_fields


def test_session_response_validates_orm_like_object_without_extra_attr():
    """ORM-like 객체에 ``is_anonymous_owner`` 가 없어도 검증이 통과한다.

    Skeleton 의 in-memory dict (``is_anonymous_owner`` 키 포함) 도, DB-backed
    ORM row (해당 속성 없음) 도 같은 response 모델로 직렬화 가능해야 한다.
    """

    ns = SimpleNamespace(**_session_row())
    response = SessionResponse.model_validate(ns)
    dumped = response.model_dump(mode="json")
    assert "is_anonymous_owner" not in dumped
    assert dumped["status"] == "draft"


def test_chat_message_response_reads_metadata_underscore_alias():
    """board round-3 #2: SQLAlchemy ``metadata_`` 컬럼 매핑을 받아 ``metadata`` 로 낸다.

    ORM-like 객체에 ``metadata_`` 속성만 있어도 ``ChatMessageResponse`` 가
    검증을 통과하고 JSON 출력은 ``metadata`` 키를 사용한다.
    """

    row = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="user",
        content="hello",
        content_redacted=False,
        ui_components=[],
        judgment_snapshot=None,
        metadata_={"source": "user"},
        created_at=datetime.now(UTC),
    )
    response = ChatMessageResponse.model_validate(row)
    dumped = response.model_dump(mode="json")
    assert dumped["metadata"] == {"source": "user"}
    assert "metadata_" not in dumped


def test_chat_message_response_still_accepts_plain_metadata_key():
    """Skeleton in-memory dict (``metadata`` 키) 와도 호환된다."""

    row = {
        "id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "role": "user",
        "content": "hello",
        "content_redacted": False,
        "ui_components": [],
        "judgment_snapshot": None,
        "metadata": {"client": "web"},
        "created_at": datetime.now(UTC),
    }
    response = ChatMessageResponse.model_validate(row)
    assert response.metadata == {"client": "web"}


def test_chat_tool_call_response_reads_metadata_underscore_alias():
    """``ChatToolCallResponse`` 도 같은 alias 규칙을 따른다."""

    row = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        message_id=None,
        parent_tool_call_id=None,
        user_id=uuid.uuid4(),
        tool_name="search_floorplan_catalog",
        tool_kind="retrieval",
        status="started",
        input={"apartment_name": "예시아파트"},
        output=None,
        output_summary=None,
        error_code=None,
        error_message=None,
        duration_ms=None,
        started_at=datetime.now(UTC),
        completed_at=None,
        metadata_={"trace_id": "abc"},
    )
    response = ChatToolCallResponse.model_validate(row)
    dumped = response.model_dump(mode="json")
    assert dumped["metadata"] == {"trace_id": "abc"}


def test_floorplan_candidate_response_accepts_null_floorplan_id():
    """board round-3 #3: catalog row 삭제 후에도 후보 snapshot 응답이 가능.

    DB ``floorplan_candidates.floorplan_id`` 는 nullable 이며
    ``ON DELETE SET NULL`` 이다. 응답 모델도 None 을 받아야 한다.
    """

    row = {
        "id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "lookup_revision": 1,
        "floorplan_id": None,
        "rank": 1,
        "confidence": Decimal("0.91"),
        "match_reasons": ["apartment_name+size_type"],
        "lookup_input": {"apartment_name": "예시아파트"},
        "floorplan_snapshot": {
            "display_label": "84A 표준 평면",
            "size_type": "84A",
        },
        "selected_at": None,
        "rejected_at": None,
        "created_at": datetime.now(UTC),
    }
    response = FloorplanCandidateResponse.model_validate(row)
    dumped = response.model_dump(mode="json")
    assert dumped["floorplan_id"] is None
    assert dumped["floorplan_snapshot"]["display_label"] == "84A 표준 평면"


def test_floorplan_candidate_item_input_requires_non_empty_snapshot():
    """board round-3 #4: ``floorplan_snapshot`` 필수, 빈 dict 거절."""

    with pytest.raises(ValidationError):
        FloorplanCandidateItemInput.model_validate(
            {
                "floorplan_id": uuid.uuid4(),
                "rank": 1,
                "confidence": "0.9",
                "floorplan_snapshot": {},
            }
        )

    # 누락된 경우에도 거절된다.
    with pytest.raises(ValidationError):
        FloorplanCandidateItemInput.model_validate(
            {
                "floorplan_id": uuid.uuid4(),
                "rank": 1,
                "confidence": "0.9",
            }
        )

    # 비어 있지 않은 snapshot 이 있으면 통과.
    item = FloorplanCandidateItemInput.model_validate(
        {
            "floorplan_id": uuid.uuid4(),
            "rank": 1,
            "confidence": "0.9",
            "floorplan_snapshot": {"display_label": "84A"},
        }
    )
    assert item.floorplan_snapshot == {"display_label": "84A"}
