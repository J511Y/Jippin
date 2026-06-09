"""이메일/비밀번호 회원가입·인증 관련 Pydantic 계약 (CMP-DIRECT).

비밀번호는 Supabase Auth(auth.users)가 단독 관리하며 우리 DB 에는 저장하지 않는다
(AGENTS §4.7 #3). 본 계약은 입력 검증과 응답 형태만 정의한다. 비밀번호 정책은 Supabase
콘솔 설정과 정합한다: 최소 6자, 영문+숫자 각각 1자 이상.

휴대폰 정규화/검증은 ``schemas.leads.normalize_korean_phone`` SSOT 를 재사용한다.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .leads import normalize_korean_phone

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 72  # bcrypt 입력 상한.

_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")
# 가벼운 이메일 형식 검증(email-validator 의존성 회피). 최종 정합은 Supabase Auth 가 한다.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_format(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_RE.match(normalized) or len(normalized) > 254:
        raise ValueError("이메일 형식이 올바르지 않습니다.")
    return normalized


def validate_password_policy(value: str) -> str:
    """Supabase 콘솔 정책과 정합한 비밀번호 검증(최소 6자, 영문+숫자)."""

    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 최대 {MAX_PASSWORD_LENGTH}자까지 가능합니다.")
    if not _HAS_LETTER.search(value) or not _HAS_DIGIT.search(value):
        raise ValueError("비밀번호는 영문과 숫자를 모두 포함해야 합니다.")
    return value


class PhoneSendCodeRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)

    @field_validator("phone")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_korean_phone(value)


class PhoneSendCodeResponse(BaseModel):
    expires_in_seconds: int


class PhoneVerifyRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    code: str = Field(min_length=4, max_length=8)

    @field_validator("phone")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_korean_phone(value)

    @field_validator("code")
    @classmethod
    def _digits_only(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped.isdigit():
            raise ValueError("인증번호는 숫자만 입력해 주세요.")
        return stripped


class PhoneVerifyResponse(BaseModel):
    phone_token: str


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    phone_token: str = Field(min_length=1, max_length=256)
    # 이용약관·개인정보처리방침 명시적 동의. **필수 필드**(default 없음) — 생략 시 422 로 막혀
    # 동의 없이 가입/consent 기록이 생기지 않는다. Literal[True] 로 False/생략을 모두 거부한다.
    agreed_to_terms: Literal[True]

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return validate_email_format(value)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        return normalize_korean_phone(value)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password_policy(value)


class SignupResponse(BaseModel):
    user_id: str
    email: str


class FindEmailRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    phone_token: str = Field(min_length=1, max_length=256)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        return normalize_korean_phone(value)


class FoundEmail(BaseModel):
    email_masked: str
    created_at: str


class FindEmailResponse(BaseModel):
    emails: list[FoundEmail]


class ResetPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=1, max_length=40)
    phone_token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return validate_email_format(value)

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        return normalize_korean_phone(value)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password_policy(value)


class ResetPasswordResponse(BaseModel):
    ok: bool = True


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password_policy(value)


class ChangePasswordResponse(BaseModel):
    ok: bool = True


class ClaimAnonymousLeadsRequest(BaseModel):
    anonymous_access_token: str = Field(min_length=1, max_length=4096)


class ClaimAnonymousLeadsResponse(BaseModel):
    moved: int = 0


class DeleteAccountResponse(BaseModel):
    ok: bool = True
