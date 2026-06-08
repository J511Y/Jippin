from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator
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

    # 이메일/비밀번호 회원가입 — Supabase Auth GoTrue admin API 호출용 (CMP-DIRECT).
    # 비밀번호는 auth.users 가 단독 관리한다(우리 테이블에 password 컬럼 없음 — AGENTS §4.7 #3).
    # admin base 는 supabase_jwt_issuer(=https://<ref>.supabase.co/auth/v1)에서 파생한다.
    supabase_url: str | None = Field(default=None)
    supabase_service_role_key: str | None = Field(default=None)
    # 회원가입 비밀번호 정책 (Supabase 콘솔 설정과 정합: 최소 6자, 영문+숫자).
    signup_min_password_length: int = Field(default=6)

    # SOLAPI 문자 인증 (CMP-DIRECT). 발신번호는 SOLAPI 콘솔에 사전 등록된 번호여야 한다.
    solapi_api_key: str | None = Field(default=None)
    solapi_api_secret: str | None = Field(default=None)
    solapi_sender_phone: str | None = Field(default=None)
    solapi_api_url: str = Field(default="https://api.solapi.com")

    # 휴대폰 OTP — Redis 저장. OAuth state store 와 같은 Redis 를 공유한다.
    phone_otp_code_length: int = Field(default=6)
    phone_otp_ttl_seconds: int = Field(default=180)
    # 인증 성공 후 가입/찾기/재설정 단계에서 쓰는 단기 검증 토큰의 수명.
    phone_otp_token_ttl_seconds: int = Field(default=600)
    phone_otp_max_attempts: int = Field(default=5)
    phone_otp_resend_cooldown_seconds: int = Field(default=30)
    phone_otp_daily_send_limit: int = Field(default=10)
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
