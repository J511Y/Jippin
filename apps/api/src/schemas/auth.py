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


class SupabaseSessionBridgeRequest(BaseModel):
    anonymous_user_id: uuid.UUID | None = Field(
        default=None,
        description="Client-stored localStorage.jippin_anonymous_user_id value.",
    )
    requested_provider: Literal["google", "kakao", "naver"] | None = Field(
        default=None,
        description="Provider selected by the signed web OAuth flow context.",
    )


class SupabaseSessionBridgeResponse(BaseModel):
    signup_complete: bool
    missing_required_terms: list[str]
    redirect_url: str | None = None


class SupabaseAccountLinkResponse(BaseModel):
    ok: bool = True


class SupabaseAccountLinkRequest(BaseModel):
    requested_provider: Literal["google", "kakao", "naver"]


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
