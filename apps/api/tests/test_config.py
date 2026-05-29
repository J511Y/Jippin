"""APP_ENV ↔ Neon branch mapping validation (CMP-538).

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
