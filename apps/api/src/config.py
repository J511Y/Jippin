from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sealed APP_ENV ↔ Neon branch mapping (CMP-538 / AGENTS.md §4.4).
# Any other value is treated as a human error signal and blocks boot.
ALLOWED_APP_ENVS: frozenset[str] = frozenset(
    {"development", "test", "staging", "production"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    request_id_header: str = Field(default="x-request-id")
    api_port: int = Field(default=8000)
    api_version: str = Field(default="0.1.0")

    database_url: str | None = Field(default=None)
    database_pool_url: str | None = Field(default=None)

    test_mode: bool = Field(default=False)
    anon_session_ttl_days: int = Field(default=30)
    redis_url: str = Field(default="redis://redis:6379/0")

    oauth_state_redis_url: str | None = Field(default=None)
    auth_oauth_state_ttl_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices(
            "AUTH_OAUTH_STATE_TTL_SECONDS",
            "OAUTH_STATE_TTL_SECONDS",
        ),
    )
    kakao_rest_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("KAKAO_REST_API_KEY", "OAUTH_KAKAO_CLIENT_ID"),
    )
    kakao_client_secret: str | None = Field(default=None)
    kakao_redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("KAKAO_REDIRECT_URI", "OAUTH_KAKAO_REDIRECT_URI"),
    )
    google_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_OAUTH_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_ID"
        ),
    )
    google_oauth_client_secret: str | None = Field(default=None)
    google_oauth_redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_OAUTH_REDIRECT_URI", "OAUTH_GOOGLE_REDIRECT_URI"
        ),
    )
    naver_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NAVER_OAUTH_CLIENT_ID", "OAUTH_NAVER_CLIENT_ID"),
    )
    naver_oauth_client_secret: str | None = Field(default=None)
    naver_oauth_redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NAVER_OAUTH_REDIRECT_URI", "OAUTH_NAVER_REDIRECT_URI"
        ),
    )
    frontend_auth_success_url: str = Field(default="http://localhost:3000/auth/success")
    frontend_auth_failure_url: str = Field(default="http://localhost:3000/auth/failure")
    frontend_auth_terms_url: str = Field(default="http://localhost:3000/auth/terms")

    auth_jwt_secret: str | None = Field(default=None)
    auth_jwt_alg: str = Field(default="HS256")
    auth_session_ttl_days: int = Field(default=14)
    auth_cookie_name: str = Field(default="jippin_session")
    auth_cookie_domain: str | None = Field(default=None)
    auth_cookie_secure: bool | None = Field(default=None)
    supabase_jwt_secret: str | None = Field(default=None)
    supabase_jwt_audience: str = Field(default="authenticated")
    kakao_sync_required_term_tags: list[str] = Field(
        default_factory=lambda: ["service_terms", "privacy_policy"]
    )

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("app_env", mode="before")
    @classmethod
    def _validate_app_env(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError(
                f"APP_ENV must be a string, got {type(v).__name__}. "
                f"Allowed: {sorted(ALLOWED_APP_ENVS)}."
            )
        normalized = v.strip().lower()
        if normalized not in ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV={v!r} is not one of {sorted(ALLOWED_APP_ENVS)}. "
                "See AGENTS.md §4.4 and docs/runbooks/neon-branches.md."
            )
        return normalized

    @field_validator("auth_oauth_state_ttl_seconds")
    @classmethod
    def _validate_oauth_state_ttl(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("AUTH_OAUTH_STATE_TTL_SECONDS must be positive.")
        return v

    @field_validator(
        "frontend_auth_success_url",
        "frontend_auth_failure_url",
        "frontend_auth_terms_url",
    )
    @classmethod
    def _validate_frontend_auth_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Frontend auth URLs must be absolute http(s) URLs.")
        return v

    @field_validator("auth_session_ttl_days")
    @classmethod
    def _validate_auth_session_ttl_days(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("AUTH_SESSION_TTL_DAYS must be positive.")
        return v

    @field_validator("auth_cookie_domain", "auth_cookie_secure", mode="before")
    @classmethod
    def _empty_cookie_settings_are_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("kakao_sync_required_term_tags", mode="before")
    @classmethod
    def _parse_kakao_sync_required_term_tags(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
