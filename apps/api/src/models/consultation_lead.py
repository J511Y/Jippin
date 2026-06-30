"""상담 리드(consultation leads) ORM 모델 (CMP-DIRECT).

DDL 정본은 ``supabase/migrations/..._0009_consultation_leads.sql`` 다 (Alembic 은
historical only — ``apps/api/README.md`` §4.1). 본 모델은 런타임 ORM INSERT/SELECT
용이며 SQL 마이그레이션의 컬럼/제약/인덱스와 1:1 로 맞춘다.

정책 비고:

- 비회원(Supabase Anonymous Sign-In)도 리드를 생성할 수 있다 — ADR-0004 §5.3 #11 /
  AGENTS §4.7 의 conversion-only 봉인을 사용자 결정으로 override 한 결과다.
- ``user_id`` 는 nullable + ``ON DELETE SET NULL`` 이다. 리드는 영업 자산이므로 익명
  user 가 TTL cleanup 으로 삭제돼도 보존돼야 하기 때문에, 기존 도메인 테이블의
  ``ON DELETE CASCADE`` 와 의도적으로 다르다.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, CreatedAtMixin, TimestampMixin


class ConsultationLead(TimestampMixin, Base):
    """상담 신청 리드 한 건. main_page 간소화 폼 / lead_page 전체 폼 공용."""

    __tablename__ = "consultation_leads"
    # 제약 ``name`` 은 테이블 접두사를 포함하지 않는다 — naming convention
    # ``ck_%(table_name)s_%(constraint_name)s`` 가 접두사를 붙여
    # ``ck_consultation_leads_<name>`` 으로 만든다(0009 SQL 과 정합, 63자 한도 회피).
    __table_args__ = (
        sa.CheckConstraint(
            "source_form in ('main_page', 'lead_page')",
            name="source_form_allowed",
        ),
        sa.CheckConstraint(
            "applicant_kind in ('individual', 'company')",
            name="applicant_kind_allowed",
        ),
        sa.CheckConstraint(
            "ownership_status is null "
            "or ownership_status in ('in_transaction', 'owner')",
            name="ownership_status_allowed",
        ),
        sa.CheckConstraint(
            "inflow_source is null or inflow_source in "
            "('naver_search', 'blog', 'acquaintance', 'cafe', 'etc')",
            name="inflow_source_allowed",
        ),
        sa.CheckConstraint(
            "status in ('new', 'contacted', 'in_progress', 'closed', 'spam')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "construction_start_date is null "
            "or construction_end_date is null "
            "or construction_end_date >= construction_start_date",
            name="construction_period_order",
        ),
        sa.CheckConstraint(
            "source_form <> 'lead_page' or ("
            "road_addr_part1 is not null "
            "and road_addr_detail is not null "
            "and expansion_location is not null "
            "and ownership_status is not null)",
            name="full_form_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="SET NULL"),
    )
    # 사전검토(precheck_session) 인입이면 원천 세션 id — 관리자 세션↔상담 교차 참조용.
    # nullable + ON DELETE SET NULL(0019): 리드는 영업 자산이라 세션 정리 후에도 보존한다.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="SET NULL"),
    )
    is_anonymous: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    source_form: Mapped[str] = mapped_column(sa.Text, nullable=False)
    applicant_kind: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'individual'"),
    )
    applicant_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    applicant_phone: Mapped[str] = mapped_column(sa.Text, nullable=False)
    road_addr_part1: Mapped[str | None] = mapped_column(sa.Text)
    road_addr_part2: Mapped[str | None] = mapped_column(sa.Text)
    road_addr_detail: Mapped[str | None] = mapped_column(sa.Text)
    expansion_location: Mapped[str | None] = mapped_column(sa.Text)
    ownership_status: Mapped[str | None] = mapped_column(sa.Text)
    construction_start_date: Mapped[date | None] = mapped_column(sa.Date)
    construction_end_date: Mapped[date | None] = mapped_column(sa.Date)
    inflow_source: Mapped[str | None] = mapped_column(sa.Text)
    message: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'new'"),
    )


class ConsultationLeadAttachment(CreatedAtMixin, Base):
    """리드 첨부(평면도 등) — Supabase Storage object metadata 만 보관."""

    __tablename__ = "consultation_lead_attachments"
    __table_args__ = (
        sa.CheckConstraint(
            "byte_size is null or byte_size >= 0",
            name="byte_size_nonnegative",
        ),
        sa.UniqueConstraint("bucket", "object_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("consultation_leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    bucket: Mapped[str] = mapped_column(sa.Text, nullable=False)
    object_path: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_name: Mapped[str | None] = mapped_column(sa.Text)
    content_type: Mapped[str | None] = mapped_column(sa.Text)
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger)


sa.Index(None, ConsultationLead.status, ConsultationLead.created_at.desc())
sa.Index(None, ConsultationLead.user_id, ConsultationLead.created_at.desc())
sa.Index("ix_consultation_leads_session_id", ConsultationLead.session_id)
sa.Index(None, ConsultationLead.applicant_phone)
sa.Index("ix_consultation_leads_created_at", ConsultationLead.created_at.desc())

sa.Index(None, ConsultationLeadAttachment.lead_id)
