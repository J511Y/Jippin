"""자주묻는질문(FAQ) ORM 모델 (CMP-DIRECT).

DDL 정본은 ``supabase/migrations/..._0011_faqs_v2.sql`` 다 (Alembic 은 historical
only — ``apps/api/README.md`` §4.1, 0008/0009 와 동일 정책). 본 모델은 런타임 ORM
SELECT 용이며 SQL 마이그레이션의 컬럼/제약/인덱스와 1:1 로 맞춘다.

정책 비고:

- FAQ 는 공개 콘텐츠다(PII 아님). 공개 읽기는 ``GET /faqs``·``GET /faqs/{faq_id}``
  백엔드 경로를 통하며, 백엔드는 권한 role 로 접속해 RLS 를 우회 SELECT 한다(기존
  도메인 테이블과 동일).
- ``id`` 는 identity 정수다 — 상세 페이지 URL(``/faq/{faqId}``)에 쓰는 사람이 읽을
  수 있는 식별자.
- ``answer`` 는 마크다운 텍스트를 보관한다(표·링크·인라인 HTML 일부 포함 가능).
  렌더링은 프론트(`/faq`, `/faq/[faqId]`)에서 처리한다.
- ``categories`` 는 안정적인 영문 슬러그 배열로 보관하고(한 질문이 여러 카테고리에
  속할 수 있다), 한국어 라벨/정렬은 프론트가 소유한다(콘텐츠를 코드에 묶지 않기
  위함). Phase 3 관리자 편집에서 드롭다운으로 노출한다.
"""

from __future__ import annotations

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
    """자주묻는질문 한 건. 공개 노출(`is_published`) + 카테고리 배열/정렬 메타 포함."""

    __tablename__ = "faqs"
    # 제약 ``name`` 은 테이블 접두사를 포함하지 않는다 — naming convention
    # ``ck_%(table_name)s_%(constraint_name)s`` 가 ``ck_faqs_<name>`` 으로 만든다.
    # ``<@`` 는 빈 배열에 true 이고 ``array_length('{}',1)`` 은 NULL(UNKNOWN → 통과)이라
    # cardinality 로 빈 배열을 차단한다(마이그레이션과 동일).
    __table_args__ = (
        sa.CheckConstraint(
            "categories <@ array["
            "'cost', 'prereview', 'glossary', 'act_permit', "
            "'resident_consent', 'fireproofing', 'use_inspection'"
            "]::text[] and cardinality(categories) >= 1",
            name="categories_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.Identity(always=True),
        primary_key=True,
    )
    categories: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # 마크다운 텍스트(표/링크/목록 등).
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


# 공개 목록 조회용 인덱스 — 노출 행을 전역 정렬(sort_order) 순으로 읽는 단일 경로.
# 카테고리 필터·검색·페이징은 프론트가 전체 목록을 받아 클라이언트에서 처리한다.
sa.Index(
    "ix_faqs_published_sort_order",
    Faq.sort_order,
    postgresql_where=Faq.is_published.is_(True),
)
