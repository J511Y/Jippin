from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sealed APP_ENV enum; DB branch selection comes from environment URLs.
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

    # 상담 리드(consultation leads) — CMP-DIRECT.
    # 도로명주소 API 승인키(business.juso.go.kr). 미설정 시 주소 검색 endpoint 가 503.
    juso_confm_key: str | None = Field(default=None)
    juso_api_url: str = Field(
        default="https://business.juso.go.kr/addrlink/addrLinkApi.do"
    )
    # 평면도 첨부 Supabase Storage 버킷명 (migration 0009 와 정합).
    lead_floorplan_bucket: str = Field(default="lead-floorplans")

    # CMP-609 Phase A skeleton 라우터 (sessions/floorplans/chat) 의 운영 노출 가드.
    # `services.main_flow` 는 in-memory 저장소이므로 컨테이너 재시작/멀티 worker
    # 환경에서 세션이 유실된다. CMP-608 Phase A migration + DB-backed repository
    # 가 들어오기 전에는 본 플래그를 끄고 운영 API surface 에서 라우터를 빼야 한다.
    # 테스트/로컬 dev 만 명시적으로 활성화한다.
    phase_a_skeleton_enabled: bool = Field(default=False)

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
    # Derivation primitives (CMP-DIRECT). Most per-environment URLs are pure
    # functions of {Supabase project ref, public web origin}; instead of hand-
    # filling each one per environment, set these two and let _derive_from_
    # primitives() fill the rest. Any explicit env value still wins (escape
    # hatch) — derivation only fills fields the operator did not provide.
    #   - supabase_ref      -> supabase_jwks_url, supabase_jwt_issuer
    #   - public_web_origin -> frontend_auth_{success,failure,terms}_url, cors
    # NB: DATABASE_*_URL is intentionally NOT derived — it carries a secret
    # password and the pooler shard host is not a pure function of the ref.
    supabase_ref: str | None = Field(default=None)
    public_web_origin: str | None = Field(default=None)

    frontend_auth_success_url: str = Field(default="http://localhost:3000/auth/success")
    frontend_auth_failure_url: str = Field(default="http://localhost:3000/auth/failure")
    frontend_auth_terms_url: str = Field(default="http://localhost:3000/auth/terms")

    auth_jwt_secret: str | None = Field(default=None)
    auth_jwt_alg: str = Field(default="HS256")
    auth_session_ttl_days: int = Field(default=14)
    auth_cookie_name: str = Field(default="jippin_session")
    auth_cookie_domain: str | None = Field(default=None)
    auth_cookie_secure: bool | None = Field(default=None)

    supabase_jwt_issuer: str | None = Field(default=None)
    supabase_jwks_url: str | None = Field(default=None)
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

    @field_validator("supabase_jwks_url", "supabase_jwt_issuer", mode="before")
    @classmethod
    def _blank_supabase_url_is_none(cls, v: object) -> object:
        # A `.env` copied from `.env.example` carries `SUPABASE_JWKS_URL=` (empty
        # string), which pydantic would otherwise treat as a provided value and
        # block derivation from SUPABASE_REF. Normalize blank -> unset.
        if v == "":
            return None
        return v

    @field_validator("public_web_origin", mode="before")
    @classmethod
    def _validate_public_web_origin(cls, v: object) -> object:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("PUBLIC_WEB_ORIGIN must be a string.")
        origin = v.rstrip("/")
        parsed = urlparse(origin)
        # Derived into cors_allow_origins, which Starlette compares against the
        # browser Origin header by exact string (scheme + host[:port], never a
        # path). Reject any path/query/fragment so a base-URL form like
        # https://dev.jippin.ai/app can't silently produce a CORS entry that
        # blocks every real browser call.
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PUBLIC_WEB_ORIGIN must be a bare origin (scheme + host[:port]) "
                "with no path/query/fragment, e.g. https://dev.jippin.ai."
            )
        return origin

    @model_validator(mode="after")
    def _derive_from_primitives(self) -> "Settings":
        """Fill per-environment URLs from {supabase_ref, public_web_origin}.

        Only fields the operator did NOT pass explicitly are derived — an env
        value always wins. This collapses the secrets surface to the irreducible
        inputs while keeping every field individually overridable (12-factor
        escape hatch).

        Supabase URLs derive whenever they are falsy (None / blank), so the
        documented "leave blank and set SUPABASE_REF" path works even when a
        copied `.env` provides them as empty strings. Fields with concrete
        defaults (frontend URLs, CORS) use ``model_fields_set`` so their
        defaults are not mistaken for an explicit override.
        """
        provided = self.model_fields_set
        if self.supabase_ref:
            base = f"https://{self.supabase_ref}.supabase.co/auth/v1"
            if not self.supabase_jwks_url:
                self.supabase_jwks_url = f"{base}/.well-known/jwks.json"
            if not self.supabase_jwt_issuer:
                self.supabase_jwt_issuer = base
        if self.public_web_origin:
            origin = self.public_web_origin
            if "frontend_auth_success_url" not in provided:
                self.frontend_auth_success_url = f"{origin}/auth/success"
            if "frontend_auth_failure_url" not in provided:
                self.frontend_auth_failure_url = f"{origin}/auth/failure"
            if "frontend_auth_terms_url" not in provided:
                self.frontend_auth_terms_url = f"{origin}/auth/terms"
            if "cors_allow_origins" not in provided:
                self.cors_allow_origins = [origin]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
