from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.services import auth as auth_service
from src.services.auth import parse_existing_anonymous_user_id
from src.errors import ZippinException


def test_post_anonymous_users_returns_410_after_supabase_cutover():
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/anonymous-users",
            json={"existing_anonymous_user_id": None},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"


@pytest.mark.parametrize("value", [None, "", "not-a-uuid"])
def test_parse_existing_anonymous_user_id_returns_none_for_invalid_input(value):
    assert parse_existing_anonymous_user_id(value) is None


def test_parse_existing_anonymous_user_id_accepts_uuid_string():
    existing_id = uuid.uuid4()
    assert parse_existing_anonymous_user_id(str(existing_id)) == existing_id


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _FakeBegin(self.conn)


class _FakeConnection:
    def __init__(self, *, selected_id, inserted_id):
        self.selected_id = selected_id
        self.inserted_id = inserted_id
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        statement_text = self.statements[-1]
        if statement_text.startswith("SELECT"):
            return _FakeResult(self.selected_id)
        if statement_text.startswith("INSERT"):
            return _FakeResult(self.inserted_id)
        if statement_text.startswith("UPDATE"):
            return _FakeResult(None)
        raise AssertionError(f"Unexpected SQL statement: {statement_text}")


@pytest.mark.asyncio
async def test_create_or_reuse_anonymous_user_is_removed_after_supabase_cutover():
    with pytest.raises(ZippinException) as exc_info:
        await auth_service.create_or_reuse_anonymous_user(str(uuid.uuid4()))

    assert exc_info.value.code == "AUTH_LEGACY_FLOW_REMOVED"
    assert exc_info.value.http_status == 410
