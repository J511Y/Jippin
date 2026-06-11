"""faqs 모델 메타데이터 sanity (CMP-DIRECT)."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY

from src.models import FAQ_CATEGORIES, Base, Faq


def test_faq_table_is_registered() -> None:
    assert "faqs" in Base.metadata.tables


def test_faq_columns_and_defaults_are_sealed() -> None:
    table = Faq.__table__
    # id 는 identity 정수 — 상세 URL(/faq/{faqId})용 식별자.
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.identity is not None
    # categories 는 슬러그 배열(다중 카테고리).
    assert isinstance(table.c.categories.type, ARRAY)
    assert isinstance(table.c.categories.type.item_type, Text)
    assert isinstance(table.c.question.type, Text)
    assert isinstance(table.c.answer.type, Text)
    assert isinstance(table.c.sort_order.type, Integer)
    assert isinstance(table.c.is_published.type, Boolean)
    # 공개 콘텐츠라 필수 컬럼은 not null, 노출 기본값은 true.
    assert table.c.categories.nullable is False
    assert table.c.answer.nullable is False
    assert table.c.is_published.nullable is False
    assert table.c.is_published.server_default is not None


def test_faq_categories_check_constraint_matches_allowed_slugs() -> None:
    check_constraints = {
        c.name: str(c.sqltext)
        for c in Faq.__table__.constraints
        if isinstance(c, CheckConstraint)
    }
    sqltext = check_constraints["ck_faqs_categories_allowed"]
    for slug in FAQ_CATEGORIES:
        assert f"'{slug}'" in sqltext
    # 빈 배열 차단(<@ 는 빈 배열에 true 라 길이 검사를 병행한다).
    assert "array_length(categories, 1) >= 1" in sqltext
