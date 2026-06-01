"""SQLAlchemy 2.0 declarative base for Jippin API (CMP-537).

엔티티 모델은 후속 모듈 이슈(AUTH/INPUT/MASK/AI/RULE/REPORT 등)에서 정의한다.
본 파일은 Alembic autogenerate diff 가 안정적으로 동작하도록 다음 두 가지만 보장한다:

1. 모든 ORM 모델이 상속하는 단일 `Base = DeclarativeBase` 를 노출한다.
2. `MetaData` 의 naming convention 을 고정해 인덱스/제약 이름이 환경 간 결정적이 되도록 한다.
   - 이것이 없으면 Alembic 이 SQLAlchemy 의 익명 제약 이름을 매번 새 이름으로 인식해
     의미 없는 diff (drop/create) 를 만든다.

후속 이슈에서 모델을 추가할 때는 본 파일에서 `from .users import User` 식으로 import 만
추가해 `Base.metadata` 가 autogenerate 시점에 알 수 있게 한다.
"""

from __future__ import annotations

from .base import (
    NAMING_CONVENTION,
    AuditMixin,
    Base,
    CreatedAtMixin,
    CreatedByMixin,
    TimestampMixin,
    utc_now,
)
from .auth import (  # noqa: E402
    AUTH_IDENTITY_PROVIDER_VALUES,
    EXTERNAL_SSO_PROVIDER_VALUES,
    AnonymousUser,
    AuthIdentity,
    ExternalSsoAccount,
    TermsConsent,
    User,
    external_sso_provider_enum,
)

from .request_log import RequestLog  # noqa: E402

__all__ = [
    "AUTH_IDENTITY_PROVIDER_VALUES",
    "AnonymousUser",
    "AuditMixin",
    "AuthIdentity",
    "Base",
    "CreatedAtMixin",
    "CreatedByMixin",
    "EXTERNAL_SSO_PROVIDER_VALUES",
    "ExternalSsoAccount",
    "NAMING_CONVENTION",
    "RequestLog",
    "TermsConsent",
    "TimestampMixin",
    "User",
    "external_sso_provider_enum",
    "utc_now",
]
