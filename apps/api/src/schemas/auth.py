from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AnonymousUserCreateRequest(BaseModel):
    existing_anonymous_user_id: str | None = Field(
        default=None,
        description="Client-stored localStorage.jippin_anonymous_user_id value.",
    )


class AnonymousUserCreateResponse(BaseModel):
    anonymous_user_id: uuid.UUID
    reused: bool
