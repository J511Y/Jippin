"""APP_ENV sealed enum validation (CMP-538/CMP-574).

Mapping sealed by AGENTS.md §4.4 and src/config.py::ALLOWED_APP_ENVS.
Any value outside the sealed set must block boot via pydantic ValidationError.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import ALLOWED_APP_ENVS, Settings


@pytest.mark.parametrize("value", ["development", "test", "staging", "production"])
def test_allowed_app_envs_boot(value: str) -> None:
    settings = Settings(app_env=value)
    assert settings.app_env == value


def test_app_env_is_lowercased_and_trimmed() -> None:
    settings = Settings(app_env="  Production  ")
    assert settings.app_env == "production"


@pytest.mark.parametrize(
    "value",
    ["foobar", "prod", "dev", "qa", "staging-2", "", "PRODUCTION!"],
)
def test_invalid_app_env_blocks_boot(value: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(app_env=value)
    msg = str(exc.value)
    assert "APP_ENV" in msg
    assert "not one of" in msg


def test_app_env_non_string_blocks_boot() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(app_env=123)  # type: ignore[arg-type]
    assert "APP_ENV" in str(exc.value)


def test_allowed_set_is_exactly_the_sealed_four() -> None:
    # Guards against silent expansion of the sealed mapping.
    assert ALLOWED_APP_ENVS == frozenset(
        {"development", "test", "staging", "production"}
    )


def test_anonymous_session_ttl_defaults_to_env_example_value() -> None:
    settings = Settings()
    assert settings.anon_session_ttl_days == 30


# --- Derivation from primitives (CMP-DIRECT) ---------------------------------
# {supabase_ref, public_web_origin} expand into the per-environment URLs so the
# operator only sets the two primitives. Explicit env values still win.


def test_supabase_ref_derives_jwks_and_issuer() -> None:
    settings = Settings(supabase_ref="vrxdfratsckukzyxrlce")
    assert (
        settings.supabase_jwks_url
        == "https://vrxdfratsckukzyxrlce.supabase.co/auth/v1/.well-known/jwks.json"
    )
    assert (
        settings.supabase_jwt_issuer
        == "https://vrxdfratsckukzyxrlce.supabase.co/auth/v1"
    )


def test_explicit_supabase_urls_win_over_ref() -> None:
    settings = Settings(
        supabase_ref="vrxdfratsckukzyxrlce",
        supabase_jwks_url="https://override.example/jwks.json",
        supabase_jwt_issuer="https://override.example/auth/v1",
    )
    assert settings.supabase_jwks_url == "https://override.example/jwks.json"
    assert settings.supabase_jwt_issuer == "https://override.example/auth/v1"


def test_no_supabase_ref_leaves_urls_unset() -> None:
    settings = Settings()
    assert settings.supabase_jwks_url is None
    assert settings.supabase_jwt_issuer is None


def test_public_web_origin_derives_frontend_urls_and_cors() -> None:
    settings = Settings(public_web_origin="https://dev.jippin.ai")
    assert settings.frontend_auth_success_url == "https://dev.jippin.ai/auth/success"
    assert settings.frontend_auth_failure_url == "https://dev.jippin.ai/auth/failure"
    assert settings.frontend_auth_terms_url == "https://dev.jippin.ai/auth/terms"
    assert settings.cors_allow_origins == ["https://dev.jippin.ai"]


def test_public_web_origin_trailing_slash_is_normalized() -> None:
    settings = Settings(public_web_origin="https://dev.jippin.ai/")
    assert settings.frontend_auth_success_url == "https://dev.jippin.ai/auth/success"


def test_explicit_frontend_url_wins_over_origin() -> None:
    settings = Settings(
        public_web_origin="https://dev.jippin.ai",
        frontend_auth_success_url="https://custom.example/done",
    )
    assert settings.frontend_auth_success_url == "https://custom.example/done"
    # untouched siblings still derive from the origin
    assert settings.frontend_auth_failure_url == "https://dev.jippin.ai/auth/failure"


def test_no_origin_keeps_localhost_defaults_and_wildcard_cors() -> None:
    settings = Settings()
    assert settings.frontend_auth_success_url == "http://localhost:3000/auth/success"
    assert settings.cors_allow_origins == ["*"]


@pytest.mark.parametrize("value", ["dev.jippin.ai", "ftp://x", "/relative", "not a url"])
def test_invalid_public_web_origin_blocks_boot(value: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(public_web_origin=value)
    assert "PUBLIC_WEB_ORIGIN" in str(exc.value)
