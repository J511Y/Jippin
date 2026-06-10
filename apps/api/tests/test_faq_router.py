"""자주묻는질문(FAQ) 라우터 테스트 (CMP-DIRECT).

DB 는 TEST_MODE 에서 미접속이므로 ``services.faq.list_published_faqs`` 를 monkeypatch 해
실제 SELECT 없이 라우터/직렬화/공개 접근(인증 불요) 경로를 검증한다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import create_app

from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_list_faqs_is_public_and_returns_items(monkeypatch) -> None:
    rows = [
        {
            "id": uuid.uuid4(),
            "category": "cost",
            "question": "사전검토 비용은 얼마인가요?",
            "answer": "**AI 사전검토는 무료**입니다. [시작하기](/sessions/new)",
            "sort_order": 1,
        },
        {
            "id": uuid.uuid4(),
            "category": "prereview",
            "question": "사전검토는 시간이 얼마나 걸리나요?",
            "answer": "로그인 없이 약 1분이면 됩니다.",
            "sort_order": 1,
        },
    ]

    async def fake_list():
        return rows

    monkeypatch.setattr("src.services.faq.list_published_faqs", fake_list)

    client = TestClient(create_app())
    with client:
        # 인증 헤더 없이 접근 — 공개 콘텐츠.
        response = client.get("/faqs")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    first = body["items"][0]
    assert first["category"] == "cost"
    assert first["question"] == "사전검토 비용은 얼마인가요?"
    # 마크다운 텍스트가 그대로 보존된다(렌더링은 프론트 책임).
    assert "[시작하기](/sessions/new)" in first["answer"]


def test_list_faqs_empty_returns_empty_list(monkeypatch) -> None:
    async def fake_list():
        return []

    monkeypatch.setattr("src.services.faq.list_published_faqs", fake_list)

    client = TestClient(create_app())
    with client:
        response = client.get("/faqs")

    assert response.status_code == 200
    assert response.json() == {"items": []}
