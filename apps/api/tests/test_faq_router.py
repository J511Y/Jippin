"""자주묻는질문(FAQ) 라우터 테스트 (CMP-DIRECT).

DB 는 TEST_MODE 에서 미접속이므로 ``services.faq`` 의 조회 함수를 monkeypatch 해
실제 SELECT 없이 라우터/직렬화/공개 접근(인증 불요) 경로를 검증한다.
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


def test_list_faqs_is_public_and_returns_items(monkeypatch) -> None:
    rows = [
        {
            "id": 1,
            "categories": ["cost", "act_permit", "use_inspection"],
            "question": "업무 대행 비용은 어떻게 되나요?",
            "answer": "**AI 사전검토는 무료**입니다. [시작하기](/sessions/new)",
            "sort_order": 1,
        },
        {
            "id": 2,
            "categories": ["prereview"],
            "question": "사전검토는 시간이 얼마나 걸리나요?",
            "answer": "로그인 없이 약 1분이면 됩니다.",
            "sort_order": 2,
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
    # id 는 identity 정수(상세 URL /faq/{faqId} 용), categories 는 슬러그 배열.
    assert first["id"] == 1
    assert first["categories"] == ["cost", "act_permit", "use_inspection"]
    assert first["question"] == "업무 대행 비용은 어떻게 되나요?"
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


def test_get_faq_returns_single_item(monkeypatch) -> None:
    row = {
        "id": 7,
        "categories": ["fireproofing"],
        "question": "방화판이랑 방화유리, 뭘 선택해야 하나요?",
        "answer": "| 구분 | 방화판 | 방화유리 |\n|---|---|---|",
        "sort_order": 7,
    }

    captured: list[int] = []

    async def fake_get(faq_id: int):
        captured.append(faq_id)
        return row

    monkeypatch.setattr("src.services.faq.get_published_faq", fake_get)

    client = TestClient(create_app())
    with client:
        response = client.get("/faqs/7")

    assert response.status_code == 200
    assert captured == [7]
    body = response.json()
    assert body["id"] == 7
    assert body["categories"] == ["fireproofing"]
    # 마크다운 표가 그대로 보존된다.
    assert body["answer"].startswith("| 구분 |")


def test_get_faq_missing_or_unpublished_is_404(monkeypatch) -> None:
    async def fake_get(faq_id: int):
        return None

    monkeypatch.setattr("src.services.faq.get_published_faq", fake_get)

    client = TestClient(create_app())
    with client:
        response = client.get("/faqs/999")

    assert response.status_code == 404
    # 전역 핸들러가 detail 을 error.message 봉투로 옮긴다 — 웹(`lib/faq.ts`)이 이
    # 메시지로 부재 404 와 라우트-미스 404 를 구분하므로 계약을 고정한다.
    assert response.json()["error"]["message"] == "FAQ not found"


def test_get_faq_non_int_id_is_422() -> None:
    client = TestClient(create_app())
    with client:
        # 정수가 아닌 id 는 검증 단계에서 거부된다(서비스 미호출).
        response = client.get("/faqs/abc")

    assert response.status_code == 422
