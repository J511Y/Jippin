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


def test_empty_hosts_env_does_not_break_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #empty-list-env: 콤마 리스트 필드는 NoDecode 로 JSON 디코딩을 건너뛰므로
    # `HOSTS=` 빈 문자열에서도 settings 생성이 깨지지 않고 [] 가 된다.
    monkeypatch.setenv("HF_SEGMENTATION_ALLOWED_IMAGE_HOSTS", "")
    settings = Settings()
    assert settings.hf_segmentation_allowed_image_hosts == []


def test_comma_hosts_env_parses_to_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_SEGMENTATION_ALLOWED_IMAGE_HOSTS", "a.example, b.example")
    settings = Settings()
    assert settings.hf_segmentation_allowed_image_hosts == ["a.example", "b.example"]


def test_comma_term_tags_env_parses_to_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 같은 NoDecode 경로 — 콤마 문자열이 JSON 으로 파싱되지 않는다.
    monkeypatch.setenv("KAKAO_SYNC_REQUIRED_TERM_TAGS", "service_terms,marketing")
    settings = Settings()
    assert settings.kakao_sync_required_term_tags == ["service_terms", "marketing"]


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


def test_blank_supabase_urls_still_derive_from_ref() -> None:
    # A `.env` copied from `.env.example` provides these as empty strings;
    # derivation must still fire (else auth reports AUTH_SESSION_CONFIG_MISSING).
    settings = Settings(
        supabase_ref="vrxdfratsckukzyxrlce",
        supabase_jwks_url="",
        supabase_jwt_issuer="",
    )
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


@pytest.mark.parametrize(
    "value",
    [
        "dev.jippin.ai",  # no scheme
        "ftp://x",  # wrong scheme
        "/relative",  # no host
        "not a url",
        "https://dev.jippin.ai/app",  # path — would corrupt derived CORS
        "https://dev.jippin.ai/auth/success",
        "https://dev.jippin.ai?foo=bar",  # query
        "https://dev.jippin.ai#frag",  # fragment
    ],
)
def test_invalid_public_web_origin_blocks_boot(value: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(public_web_origin=value)
    assert "PUBLIC_WEB_ORIGIN" in str(exc.value)


def test_public_web_origin_allows_port() -> None:
    settings = Settings(public_web_origin="http://localhost:3000")
    assert settings.cors_allow_origins == ["http://localhost:3000"]
    assert settings.frontend_auth_success_url == "http://localhost:3000/auth/success"


# --- 에이전트 활성화 fail-safe (CMP-DIRECT) ---------------------------------


def test_agent_enabled_does_not_require_phase_a() -> None:
    # agent 라우터가 phase_a 게이트에서 분리됐으므로 phase_a 없이 agent 만 켜도 settings
    # 생성이 깨지지 않는다(#stale-phase-prereq). 다른 필수(OPENAI 키 등)는 충족시킨다.
    settings = Settings(
        agent_enabled=True,
        phase_a_skeleton_enabled=False,
        openai_api_key="sk-test-not-a-real-key",
    )
    assert settings.agent_enabled is True
    assert settings.phase_a_skeleton_enabled is False


def test_agent_enabled_requires_openai_key() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            agent_enabled=True,
            phase_a_skeleton_enabled=True,
            openai_api_key=None,
        )
    assert "OPENAI_API_KEY" in str(exc.value)


def test_agent_enabled_rejects_pooler_url() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            agent_enabled=True,
            phase_a_skeleton_enabled=True,
            openai_api_key="test-openai-key",
            database_url="postgresql://host:6543/db",
        )
    assert ":6543" in str(exc.value)


def test_agent_enabled_boots_with_valid_config() -> None:
    settings = Settings(
        agent_enabled=True,
        phase_a_skeleton_enabled=True,
        openai_api_key="test-openai-key",
        database_url="postgresql://host:5432/db",
    )
    assert settings.agent_enabled is True
