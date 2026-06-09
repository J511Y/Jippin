"""이메일 회원가입 후처리 — public.users 프로필 + 내부 약관 동의 기록 (CMP-DIRECT).

비밀번호/이메일/휴대폰은 Supabase Auth(auth.users)가 보관하고, 본 모듈은 앱 프로필
(``public.users``)과 필수 약관 동의(``terms_consents``, source='internal_signup')만
기록한다. 회원가입은 내부 약관 동의 화면을 거치므로(AGENTS §4.7 #6) 동의를 가입 시점에
baseline 으로 남긴다.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import get_engine
from ..models import TermsConsent, User
from .auth import (
    INTERNAL_TERMS_SOURCE,
    INTERNAL_TERMS_VERSION,
    _required_term_ids,
)


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(len(local) - 1, 1)
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


async def create_signup_profile(*, user_id: uuid.UUID, display_name: str) -> None:
    """이메일 가입자의 public.users 프로필과 내부 약관 동의를 기록한다."""

    settings = get_settings()
    required_terms = _required_term_ids(settings)
    async with get_engine().begin() as conn:
        await conn.execute(
            pg_insert(User)
            .values(id=user_id, display_name=display_name, status="active")
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={"display_name": display_name, "updated_at": sa.func.now()},
            )
        )
        if required_terms:
            consent_rows = [
                {
                    "user_id": user_id,
                    "term_id": term_id,
                    "version": INTERNAL_TERMS_VERSION,
                    "source": INTERNAL_TERMS_SOURCE,
                    "agreed_at": sa.func.now(),
                    "updated_at": sa.func.now(),
                }
                for term_id in required_terms
            ]
            await conn.execute(
                pg_insert(TermsConsent)
                .values(consent_rows)
                .on_conflict_do_nothing(
                    index_elements=[
                        TermsConsent.user_id,
                        TermsConsent.term_id,
                        TermsConsent.version,
                    ],
                )
            )
