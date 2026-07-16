"""대기 화면 퀴즈 라우터 테스트 (우리집 체크).

DB 는 TEST_MODE 에서 미접속이므로 ``services.quiz`` 의 조회 함수를 monkeypatch 해
실제 SELECT 없이 라우터/직렬화/공개 접근(인증 불요) 경로를 검증한다(faq 테스트 미러).
"""

from __future__ import annotations

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


def test_list_quizzes_is_public_and_returns_items(monkeypatch) -> None:
    rows = [
        {
            "id": 1,
            "categories": ["glossary"],
            "question": "내력벽은 건물의 하중을 지지하는 벽이라 함부로 철거하면 안 된다.",
            "choices": ["O", "X"],
            "answer_index": 0,
            "explanation": "내력벽은 **구조 벽**입니다.",
            "sort_order": 1,
        },
        {
            "id": 16,
            "categories": ["fireproofing"],
            "question": "확장 발코니에 설치하는 방화판·방화유리의 최소 높이는?",
            "choices": ["60cm 이상", "90cm 이상", "120cm 이상"],
            "answer_index": 1,
            "explanation": "기준은 **바닥판 두께 포함 90cm 이상**입니다.",
            "sort_order": 16,
        },
    ]

    async def fake_list():
        return rows

    monkeypatch.setattr("src.services.quiz.list_published_quizzes", fake_list)

    client = TestClient(create_app())
    with client:
        # 인증 헤더 없이 접근 — 공개 콘텐츠.
        response = client.get("/quizzes")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    ox, mc = body["items"]
    # O/X 문항은 choices=['O','X'] 특수 케이스, answer_index 는 0-base 정수.
    assert ox["choices"] == ["O", "X"]
    assert ox["answer_index"] == 0
    # 객관식 문항 — 선택지 3개 + 마크다운 해설이 그대로 보존된다(렌더링은 프론트 책임).
    assert len(mc["choices"]) == 3
    assert mc["answer_index"] == 1
    assert "**바닥판 두께 포함 90cm 이상**" in mc["explanation"]


def test_list_quizzes_empty_returns_empty_list(monkeypatch) -> None:
    async def fake_list():
        return []

    monkeypatch.setattr("src.services.quiz.list_published_quizzes", fake_list)

    client = TestClient(create_app())
    with client:
        response = client.get("/quizzes")

    assert response.status_code == 200
    assert response.json() == {"items": []}
