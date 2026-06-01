from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AnonymousUserCreateRequest(BaseModel):
    existing_anonymous_user_id: str | None = Field(
        default=None,
        description="Client-stored localStorage.jippin_anonymous_user_id value.",
    )


class AnonymousUserCreateResponse(BaseModel):
    anonymous_user_id: uuid.UUID
    reused: bool


class OAuthStartResponse(BaseModel):
    authorization_url: str


class AuthUserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    profile_image_url: str | None
    role: str


class AuthMeResponse(BaseModel):
    user: AuthUserResponse
    providers: list[str]
    signup_complete: bool
    missing_required_terms: list[str]


class AuthLogoutResponse(BaseModel):
    ok: bool = True


class TermsConsentInput(BaseModel):
    term_id: str | int
    agreed: bool

    @field_validator("term_id")
    @classmethod
    def _normalize_term_id(cls, value: str | int) -> str:
        return str(value)


class TermsAcceptRequest(BaseModel):
    consents: list[TermsConsentInput] = Field(default_factory=list)


class TermsAcceptResponse(BaseModel):
    signup_complete: bool
    missing_required_terms: list[str]
    claimed_anonymous_user: bool = False


class KakaoSyncAuditRequest(BaseModel):
    """Payload from `apps/web/lib/kakao-sync-audit.ts` (CMP-581 round-13).

    `linked_provider` 은 web 어댑터의 `normalizeProviderForBackend` 가 SDK id
    (`'kakao' | 'custom:kakao'`) 를 backend enum (`'kakao'` 단일) 로 normalize
    한 결과만 받는다. Phase 1 stub 은 schema 검증 + Bearer 헤더 존재 확인까지만
    수행하고 actual `terms_consents` upsert 는 Backend/Auth 트랙이 담당.
    """

    supabase_user_id: str = Field(..., min_length=1)
    linked_provider: Literal["kakao"] = "kakao"
    provider_access_token: str | None = None
    provider_refresh_token: str | None = None


class KakaoSyncAuditResponse(BaseModel):
    """Phase 1 stub response. `stubbed: true` 가 callsite 에 audit 완료가
    아직 placeholder 임을 명시 — Backend/Auth 트랙이 ship 완료하면 false 로 전환."""

    accepted: bool = True
    stubbed: bool = True
    detail: str = (
        "Phase 1 stub — payload schema 검증과 Bearer 헤더 존재 확인까지만 수행."
        " Backend/Auth 트랙이 terms_consents(source='kakao_sync') upsert 와 Kakao "
        "OpenAPI 검증 로직을 ship 한 뒤 stubbed=false 로 전환."
    )
