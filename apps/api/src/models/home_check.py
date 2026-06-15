"""우리집 체크(home-check) ORM 모델 — 집합건축물대장 전유부+표제부 조회.

DDL 정본은 ``supabase/migrations/..._0014_home_checks.sql`` 다(Alembic 은 historical
only — ``apps/api/README.md`` §4.1). 본 모델은 런타임 ORM INSERT/SELECT 용이며 SQL
마이그레이션의 컬럼/제약/인덱스와 1:1 로 맞춘다. 결정 정본은
``docs/adr/0008-home-check-building-register.md``.

보관 원칙(ADR-0008 §2.3):

- 발급 PDF(``resOriGinalData``)를 SoT 원본으로 Supabase Storage(``home-check-docs``)에
  보관하고(``HomeCheckDocument`` 가 포인터), DB 에는 판정·표시용 최소 필드만 둔다.
- 소유자/설계자 등 PII(``resOwnerList``/``resLicenseClassList``)·주민번호·세움터
  password 는 구조화 저장하지 않는다 — 원본 PDF 로만 확인.
- ``consultation_leads`` 와 동일하게 PII 테이블이므로 RLS client grant 없이 백엔드
  풀 role 로만 접근한다. ``user_id`` 는 nullable + ``ON DELETE SET NULL`` (이력 보존).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, CreatedAtMixin, TimestampMixin


class HomeCheck(TimestampMixin, Base):
    """우리집 체크 조회 잡 한 건 + 판정 + PII-free 요약."""

    __tablename__ = "home_checks"
    # 제약 ``name`` 은 테이블 접두사를 포함하지 않는다 — naming convention 이
    # ``ck_home_checks_<name>`` 으로 만든다(0014 SQL 과 정합).
    __table_args__ = (
        sa.CheckConstraint(
            "status in ('pending', 'querying', 'needs_input', 'completed', 'failed')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "signal is null or signal in ('violation', 'caution', 'normal')",
            name="signal_allowed",
        ),
        sa.CheckConstraint(
            "signal is null or status = 'completed'",
            name="signal_requires_completed",
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
    is_anonymous: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    # 잡 상태 / 종합 판정
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    signal: Mapped[str | None] = mapped_column(sa.Text)

    # 조회 주소 (도로명주소 팝업 입력 + 정규화)
    road_addr: Mapped[str | None] = mapped_column(sa.Text)
    jibun_addr: Mapped[str | None] = mapped_column(sa.Text)
    addr_dong: Mapped[str | None] = mapped_column(sa.Text)
    addr_ho: Mapped[str | None] = mapped_column(sa.Text)

    # 건축물 식별자 (전유부 / 표제부)
    comm_unique_no: Mapped[str | None] = mapped_column(sa.Text)
    heading_comm_unique_no: Mapped[str | None] = mapped_column(sa.Text)
    res_doc_no: Mapped[str | None] = mapped_column(sa.Text)
    heading_res_doc_no: Mapped[str | None] = mapped_column(sa.Text)
    res_issue_date: Mapped[date | None] = mapped_column(sa.Date)

    # 위반 표시 (전유부 + 표제부 병행)
    exclusive_violation: Mapped[bool | None] = mapped_column(sa.Boolean)
    heading_violation: Mapped[bool | None] = mapped_column(sa.Boolean)
    violation: Mapped[bool | None] = mapped_column(sa.Boolean)

    # 전유부 요약 (전유부분 resType="0")
    exclusive_area_m2: Mapped[float | None] = mapped_column(sa.Numeric)
    exclusive_use_type: Mapped[str | None] = mapped_column(sa.Text)
    exclusive_structure: Mapped[str | None] = mapped_column(sa.Text)
    exclusive_floor: Mapped[str | None] = mapped_column(sa.Text)

    # 표제부 요약 (건물 단위)
    building_main_use: Mapped[str | None] = mapped_column(sa.Text)
    building_floors: Mapped[str | None] = mapped_column(sa.Text)
    building_approval_date: Mapped[date | None] = mapped_column(sa.Date)
    building_permit_date: Mapped[date | None] = mapped_column(sa.Date)

    # 가변 데이터 (PII 미포함)
    change_list: Mapped[list] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    price_list: Mapped[list] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    heading_detail: Mapped[dict] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    result_fields: Mapped[dict] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    # 상담 인입 연결
    consultation_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("consultation_leads.id", ondelete="SET NULL"),
    )

    # 운영
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    queried_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class HomeCheckDocument(CreatedAtMixin, Base):
    """발급 PDF(전유부/표제부) Storage object 포인터 — 바이너리는 home-check-docs 버킷."""

    __tablename__ = "home_check_documents"
    __table_args__ = (
        sa.CheckConstraint(
            "kind in ('exclusive_part', 'building_heading')",
            name="kind_allowed",
        ),
        sa.UniqueConstraint("home_check_id", "kind"),
        sa.UniqueConstraint("bucket", "object_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    home_check_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("home_checks.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    bucket: Mapped[str] = mapped_column(sa.Text, nullable=False)
    object_path: Mapped[str] = mapped_column(sa.Text, nullable=False)
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger)


sa.Index(None, HomeCheck.user_id, HomeCheck.created_at.desc())
sa.Index(None, HomeCheck.status, HomeCheck.created_at.desc())
sa.Index(
    None,
    HomeCheck.comm_unique_no,
    postgresql_where=HomeCheck.comm_unique_no.isnot(None),
)
sa.Index(
    None,
    HomeCheck.consultation_lead_id,
    postgresql_where=HomeCheck.consultation_lead_id.isnot(None),
)

sa.Index(None, HomeCheckDocument.home_check_id)
