"""faqs 모델 메타데이터 sanity (CMP-DIRECT)."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, Text

from src.models import FAQ_CATEGORIES, Base, Faq


def test_faq_table_is_registered() -> None:
    assert "faqs" in Base.metadata.tables


def test_faq_columns_and_defaults_are_sealed() -> None:
    table = Faq.__table__
    assert isinstance(table.c.category.type, Text)
    assert isinstance(table.c.question.type, Text)
    assert isinstance(table.c.answer.type, Text)
    assert isinstance(table.c.sort_order.type, Integer)
    assert isinstance(table.c.is_published.type, Boolean)
    # 공개 콘텐츠라 필수 컬럼은 not null, 노출 기본값은 true.
    assert table.c.category.nullable is False
    assert table.c.answer.nullable is False
    assert table.c.is_published.nullable is False
    assert table.c.is_published.server_default is not None


def test_faq_category_check_constraint_matches_allowed_slugs() -> None:
    check_constraints = {
        c.name: str(c.sqltext)
        for c in Faq.__table__.constraints
        if isinstance(c, CheckConstraint)
    }
    sqltext = check_constraints["ck_faqs_category_allowed"]
    for slug in FAQ_CATEGORIES:
        assert f"'{slug}'" in sqltext
