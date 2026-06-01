from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_head_is_auth_identities_revision() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "0007_auth_identities"


def test_auth_skeleton_revision_is_ordered_after_request_logs() -> None:
    path = Path("migrations/versions/20260529_1200_0005_auth_skeleton.py")
    spec = importlib.util.spec_from_file_location("auth_skeleton_revision", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0005_auth_skeleton"
    assert module.down_revision == "0004_request_logs"


def test_terms_consent_unique_key_revision_is_ordered_after_auth_skeleton() -> None:
    path = Path("migrations/versions/20260529_1330_0006_terms_consent_unique_key.py")
    spec = importlib.util.spec_from_file_location("terms_consent_unique_key", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0006_terms_consent_unique_key"
    assert module.down_revision == "0005_auth_skeleton"


def test_auth_identities_revision_is_ordered_after_terms_consent_unique_key() -> None:
    path = Path("migrations/versions/20260601_1200_0007_auth_identities.py")
    spec = importlib.util.spec_from_file_location("auth_identities_revision", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0007_auth_identities"
    assert module.down_revision == "0006_terms_consent_unique_key"
