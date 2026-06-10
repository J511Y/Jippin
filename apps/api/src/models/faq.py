"""자주묻는질문(FAQ) ORM 모델 (CMP-DIRECT).

DDL 정본은 ``supabase/migrations/..._0010_faqs.sql`` 다 (Alembic 은 historical
only — ``apps/api/README.md`` §4.1, 0008/0009 와 동일 정책). 본 모델은 런타임 ORM
SELECT 용이며 SQL 마이그레이션의 컬럼/제약/인덱스와 1:1 로 맞춘다.

정책 비고:

- FAQ 는 공개 콘텐츠다(PII 아님). 공개 읽기는 ``GET /faqs`` 백엔드 경로를 통하며,
  백엔드는 권한 role 로 접속해 RLS 를 우회 SELECT 한다(기존 도메인 테이블과 동일).
- ``answer`` 는 마크다운 텍스트를 보관한다(링크·이미지·목록 등 마크업 포함 가능).
  렌더링은 프론트(`/faq`)에서 처리한다.
- ``category`` 는 안정적인 영문 슬러그로 보관하고, 한국어 라벨/정렬은 프론트가
  소유한다(콘텐츠를 코드에 묶지 않기 위함). Phase 3 관리자 편집에서 드롭다운으로
  노출한다.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin

# 허용 카테고리 슬러그 — 한국어 라벨은 프론트(`lib/faq.ts`)가 매핑한다.
# 비용 / 사전검토 / 용어 / 행위허가 / 입주민 동의 / 방화·시공 / 사용검사.
FAQ_CATEGORIES: tuple[str, ...] = (
    "cost",
    "prereview",
    "glossary",
    "act_permit",
    "resident_consent",
    "fireproofing",
    "use_inspection",
)


class Faq(TimestampMixin, Base):
    """자주묻는질문 한 건. 공개 노출(`is_published`) + 카테고리/정렬 메타 포함."""

    __tablename__ = "faqs"
    # 제약 ``name`` 은 테이블 접두사를 포함하지 않는다 — naming convention
    # ``ck_%(table_name)s_%(constraint_name)s`` 가 ``ck_faqs_<name>`` 으로 만든다.
    __table_args__ = (
        sa.CheckConstraint(
            "category in ("
            "'cost', 'prereview', 'glossary', 'act_permit', "
            "'resident_consent', 'fireproofing', 'use_inspection'"
            ")",
            name="category_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    category: Mapped[str] = mapped_column(sa.Text, nullable=False)
    question: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # 마크다운 텍스트(링크/이미지/목록 등).
    answer: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    is_published: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("true"),
    )


# 공개 목록 조회용 인덱스 — 노출 행을 카테고리/정렬 순으로 읽는 단일 경로.
sa.Index(
    "ix_faqs_published_category_sort_order",
    Faq.category,
    Faq.sort_order,
    postgresql_where=Faq.is_published.is_(True),
)
