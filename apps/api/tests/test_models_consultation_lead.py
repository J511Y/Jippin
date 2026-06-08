"""consultation_leads 모델 메타데이터 sanity (CMP-DIRECT)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint

from src.models import Base, ConsultationLead, ConsultationLeadAttachment


def test_lead_tables_are_registered() -> None:
    assert {
        "consultation_leads",
        "consultation_lead_attachments",
    }.issubset(Base.metadata.tables)


def test_lead_user_id_is_nullable_set_null() -> None:
    col = ConsultationLead.__table__.c.user_id
    fk = next(iter(col.foreign_keys))
    # 리드는 익명 user cleanup 후에도 보존돼야 한다 → SET NULL + nullable.
    assert col.nullable is True
    assert fk.target_fullname == "auth.users.id"
    assert fk.ondelete == "SET NULL"


def test_lead_full_form_check_constraint_exists() -> None:
    names = {
        c.name
        for c in ConsultationLead.__table__.constraints
        if isinstance(c, CheckConstraint)
    }
    assert "ck_consultation_leads_full_form_required" in names
    assert "ck_consultation_leads_source_form_allowed" in names


def test_attachment_cascades_from_lead() -> None:
    col = ConsultationLeadAttachment.__table__.c.lead_id
    fk = next(iter(col.foreign_keys))
    assert fk.target_fullname == "consultation_leads.id"
    assert fk.ondelete == "CASCADE"
