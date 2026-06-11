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

# 만 14세 이상 자기확인(개인정보보호법) — 생년월일은 수집하지 않고 체크박스 attestation 만
# terms_consents 에 timestamp 와 함께 남긴다(감사 추적). 라우터가 False/누락을 400 으로
# 거부하므로 본 모듈에 도달한 가입은 항상 동의 상태다.
AGE_OVER_14_TERM_ID = "age_over_14"
# 광고성 정보(SMS 등) 수신 동의 — 선택(정보통신망법 §50). 기존 약관 화면의 term_id 관례
# (`marketing`, tests/test_auth_secondary_endpoints.py)를 재사용한다.
MARKETING_TERM_ID = "marketing"


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(len(local) - 1, 1)
    else:
        masked_local = local[:2] + "*" * (len(local) - 2)
    return f"{masked_local}@{domain}"


async def create_signup_profile(
    *, user_id: uuid.UUID, display_name: str, marketing_agreed: bool = False
) -> None:
    """이메일 가입자의 public.users 프로필과 내부 약관 동의를 기록한다.

    필수 약관(`service_terms`/`privacy_policy`)과 만 14세 이상 확인(`age_over_14`)은
    항상 기록하고, 광고성 정보 수신(`marketing`)은 동의한 경우에만 기록한다 —
    terms_consents 는 동의 사실(agreed_at)만 저장하므로 미동의는 row 를 남기지 않는다.
    """

    settings = get_settings()
    consent_term_ids = list(
        dict.fromkeys([*_required_term_ids(settings), AGE_OVER_14_TERM_ID])
    )
    if marketing_agreed:
        consent_term_ids.append(MARKETING_TERM_ID)
    async with get_engine().begin() as conn:
        await conn.execute(
            pg_insert(User)
            .values(id=user_id, display_name=display_name, status="active")
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={"display_name": display_name, "updated_at": sa.func.now()},
            )
        )
        if consent_term_ids:
            consent_rows = [
                {
                    "user_id": user_id,
                    "term_id": term_id,
                    "version": INTERNAL_TERMS_VERSION,
                    "source": INTERNAL_TERMS_SOURCE,
                    "agreed_at": sa.func.now(),
                    "updated_at": sa.func.now(),
                }
                for term_id in consent_term_ids
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
