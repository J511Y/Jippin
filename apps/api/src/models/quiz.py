"""대기 화면 퀴즈 ORM 모델 (우리집 체크).

DDL 정본은 ``supabase/migrations/..._0023_quizzes.sql`` 다 (Alembic 은 historical
only — faqs 0011 과 동일 정책). 본 모델은 런타임 ORM SELECT 용이며 SQL 마이그레이션의
컬럼/제약/인덱스와 1:1 로 맞춘다.

정책 비고 (faqs 미러):

- 퀴즈는 공개 콘텐츠다(PII 아님). 공개 읽기는 ``GET /quizzes`` 백엔드 경로를 통하며,
  백엔드는 권한 role 로 접속해 RLS 를 우회 SELECT 한다.
- **객관식 일반형**: ``choices``(2~5개) + ``answer_index``(0-base). O/X 문항은
  ``choices=['O','X']`` 인 특수 케이스 — 운영자가 선택지 배열만으로 두 형식을 편집한다.
- ``explanation`` 은 마크다운(정답 공개 후 해설). 렌더링은 프론트 책임.
- ``categories`` 는 FAQ 와 동일한 영문 슬러그 배열. 한국어 라벨은 프론트가 소유한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin
from src.models.faq import FAQ_CATEGORIES

# 퀴즈 카테고리 = FAQ 슬러그 재사용(콘텐츠 도메인이 동일 — 리모델링/건축 규정).
QUIZ_CATEGORIES: tuple[str, ...] = FAQ_CATEGORIES


class Quiz(TimestampMixin, Base):
    """대기 화면 퀴즈 한 건. 공개 노출(`is_published`) + 카테고리/정렬 메타 포함."""

    __tablename__ = "quizzes"
    # 제약 name 은 naming convention 이 ``ck_quizzes_<name>`` 으로 만든다(0023 과 정합).
    __table_args__ = (
        sa.CheckConstraint(
            "categories <@ array["
            "'cost', 'prereview', 'glossary', 'act_permit', "
            "'resident_consent', 'fireproofing', 'use_inspection'"
            "]::text[] and cardinality(categories) >= 1",
            name="categories_allowed",
        ),
        sa.CheckConstraint(
            "cardinality(choices) between 2 and 5",
            name="choices_range",
        ),
        sa.CheckConstraint(
            "answer_index >= 0 and answer_index < cardinality(choices)",
            name="answer_index_valid",
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
    # 선택지 2~5개. ['O','X'] 는 O/X 문항(프론트가 배열을 보고 렌더 분기).
    choices: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        nullable=False,
    )
    answer_index: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    # 마크다운 해설(정답 공개 후 표시).
    explanation: Mapped[str] = mapped_column(sa.Text, nullable=False)
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
# 셔플·카테고리 필터는 프론트가 전체 목록을 받아 클라이언트에서 처리한다.
sa.Index(
    "ix_quizzes_published_sort_order",
    Quiz.sort_order,
    postgresql_where=Quiz.is_published.is_(True),
)
