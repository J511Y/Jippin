"""quizzes 모델 메타데이터 sanity (우리집 체크 대기 화면 퀴즈)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY

from src.models import QUIZ_CATEGORIES, Base, Quiz


def test_quiz_table_is_registered() -> None:
    assert "quizzes" in Base.metadata.tables


def test_quiz_columns_and_defaults_are_sealed() -> None:
    table = Quiz.__table__
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.identity is not None
    assert isinstance(table.c.categories.type, ARRAY)
    assert isinstance(table.c.categories.type.item_type, Text)
    assert isinstance(table.c.question.type, Text)
    # 객관식 일반형 — 선택지 배열 + 0-base 정답 인덱스 + 마크다운 해설.
    assert isinstance(table.c.choices.type, ARRAY)
    assert isinstance(table.c.choices.type.item_type, Text)
    assert isinstance(table.c.answer_index.type, SmallInteger)
    assert isinstance(table.c.explanation.type, Text)
    assert isinstance(table.c.sort_order.type, Integer)
    assert isinstance(table.c.is_published.type, Boolean)
    # 공개 콘텐츠라 필수 컬럼은 not null, 노출 기본값은 true.
    assert table.c.categories.nullable is False
    assert table.c.choices.nullable is False
    assert table.c.answer_index.nullable is False
    assert table.c.explanation.nullable is False
    assert table.c.is_published.nullable is False
    assert table.c.is_published.server_default is not None


def test_quiz_check_constraints_match_migration() -> None:
    check_constraints = {
        c.name: str(c.sqltext)
        for c in Quiz.__table__.constraints
        if isinstance(c, CheckConstraint)
    }

    categories_sql = check_constraints["ck_quizzes_categories_allowed"]
    for slug in QUIZ_CATEGORIES:
        assert f"'{slug}'" in categories_sql
    assert "cardinality(categories) >= 1" in categories_sql

    # 선택지 2~5개(2=O/X, 3~5=객관식) + 정답 인덱스는 선택지 범위 안(0-base).
    assert "cardinality(choices) between 2 and 5" in check_constraints[
        "ck_quizzes_choices_range"
    ]
    answer_sql = check_constraints["ck_quizzes_answer_index_valid"]
    assert "answer_index >= 0" in answer_sql
    assert "answer_index < cardinality(choices)" in answer_sql


def test_quiz_categories_reuse_faq_slugs() -> None:
    from src.models import FAQ_CATEGORIES

    assert QUIZ_CATEGORIES == FAQ_CATEGORIES
