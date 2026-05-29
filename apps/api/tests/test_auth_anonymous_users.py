from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.services import auth as auth_service
from src.services.auth import AnonymousUserResult, parse_existing_anonymous_user_id


def test_post_anonymous_users_creates_new_uuid(monkeypatch):
    created_id = uuid.uuid4()

    async def fake_create_or_reuse(existing_anonymous_user_id: str | None):
        assert existing_anonymous_user_id is None
        return AnonymousUserResult(anonymous_user_id=created_id, reused=False)

    monkeypatch.setattr(
        "src.routers.auth.create_or_reuse_anonymous_user",
        fake_create_or_reuse,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/anonymous-users",
            json={"existing_anonymous_user_id": None},
        )

    assert response.status_code == 200
    assert response.json() == {
        "anonymous_user_id": str(created_id),
        "reused": False,
    }


def test_post_anonymous_users_reuses_existing_uuid(monkeypatch):
    existing_id = uuid.uuid4()

    async def fake_create_or_reuse(existing_anonymous_user_id: str | None):
        assert existing_anonymous_user_id == str(existing_id)
        return AnonymousUserResult(anonymous_user_id=existing_id, reused=True)

    monkeypatch.setattr(
        "src.routers.auth.create_or_reuse_anonymous_user",
        fake_create_or_reuse,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/anonymous-users",
            json={"existing_anonymous_user_id": str(existing_id)},
        )

    assert response.status_code == 200
    assert response.json() == {
        "anonymous_user_id": str(existing_id),
        "reused": True,
    }


def test_post_anonymous_users_invalid_uuid_is_not_validation_error(monkeypatch):
    created_id = uuid.uuid4()

    async def fake_create_or_reuse(existing_anonymous_user_id: str | None):
        assert existing_anonymous_user_id == "not-a-uuid"
        return AnonymousUserResult(anonymous_user_id=created_id, reused=False)

    monkeypatch.setattr(
        "src.routers.auth.create_or_reuse_anonymous_user",
        fake_create_or_reuse,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/anonymous-users",
            json={"existing_anonymous_user_id": "not-a-uuid"},
        )

    assert response.status_code == 200
    assert response.json()["anonymous_user_id"] == str(created_id)
    assert response.json()["reused"] is False


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
async def test_create_or_reuse_anonymous_user_touches_last_seen_on_active_reuse(
    monkeypatch,
):
    existing_id = uuid.uuid4()
    inserted_id = uuid.uuid4()
    conn = _FakeConnection(selected_id=existing_id, inserted_id=inserted_id)
    monkeypatch.setattr(auth_service, "get_engine", lambda: _FakeEngine(conn))

    result = await auth_service.create_or_reuse_anonymous_user(str(existing_id))

    assert result == AnonymousUserResult(anonymous_user_id=existing_id, reused=True)
    assert len(conn.statements) == 2
    assert conn.statements[0].startswith("SELECT")
    assert "last_seen_at" in conn.statements[0]
    assert conn.statements[1].startswith("UPDATE")
    assert "last_seen_at" in conn.statements[1]


@pytest.mark.asyncio
async def test_create_or_reuse_anonymous_user_inserts_when_existing_is_converted(
    monkeypatch,
):
    existing_id = uuid.uuid4()
    inserted_id = uuid.uuid4()
    conn = _FakeConnection(selected_id=None, inserted_id=inserted_id)
    monkeypatch.setattr(auth_service, "get_engine", lambda: _FakeEngine(conn))

    result = await auth_service.create_or_reuse_anonymous_user(str(existing_id))

    assert result == AnonymousUserResult(anonymous_user_id=inserted_id, reused=False)
    assert len(conn.statements) == 2
    assert conn.statements[0].startswith("SELECT")
    assert conn.statements[1].startswith("INSERT")


@pytest.mark.asyncio
async def test_create_or_reuse_anonymous_user_inserts_when_existing_is_stale(
    monkeypatch,
):
    existing_id = uuid.uuid4()
    inserted_id = uuid.uuid4()
    conn = _FakeConnection(selected_id=None, inserted_id=inserted_id)
    monkeypatch.setattr(auth_service, "get_engine", lambda: _FakeEngine(conn))

    result = await auth_service.create_or_reuse_anonymous_user(str(existing_id))

    assert result == AnonymousUserResult(anonymous_user_id=inserted_id, reused=False)
    assert len(conn.statements) == 2
    assert conn.statements[0].startswith("SELECT")
    assert "last_seen_at" in conn.statements[0]
    assert conn.statements[1].startswith("INSERT")


@pytest.mark.asyncio
async def test_create_or_reuse_anonymous_user_inserts_for_invalid_uuid(monkeypatch):
    inserted_id = uuid.uuid4()
    conn = _FakeConnection(selected_id=None, inserted_id=inserted_id)
    monkeypatch.setattr(auth_service, "get_engine", lambda: _FakeEngine(conn))

    result = await auth_service.create_or_reuse_anonymous_user("not-a-uuid")

    assert result == AnonymousUserResult(anonymous_user_id=inserted_id, reused=False)
    assert len(conn.statements) == 1
    assert conn.statements[0].startswith("INSERT")
