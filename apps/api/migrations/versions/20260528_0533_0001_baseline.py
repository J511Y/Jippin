"""0001_baseline

revision: 0001_baseline / down: None

빈 베이스라인 리비전 (CMP-537). 실제 엔티티 모델은 후속 모듈 이슈에서 정의한다.
이 리비전이 적용되면 `alembic_version` 테이블만 생성되고 DB 스키마는 비어 있는 상태가 된다.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
