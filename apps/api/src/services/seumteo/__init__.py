"""세움터 직결 클라이언트 (CODEF 대체, ADR-0009).

CODEF 클라이언트와 **동일 인터페이스**(``CodefBuildingRegisterClient`` 시그니처 + codef.types
결과 dataclass)를 유지한 채, 내부는 Flycast 사설망의 세움터 워커(apps/seumteo-worker)를
HTTP 호출한다. 따라서 ``home_check.py`` 는 무변경으로 동작한다.

결과 dataclass·예외는 기존 정본(``..codef.types``)을 그대로 재사용한다 — home_check 및
테스트가 의존하는 계약을 흔들지 않기 위함.
"""

from ..codef.types import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefAuthError,
    CodefError,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    CodefUpstreamError,
    ExclusivePartResult,
)
from .client import SeumteoBuildingRegisterClient

__all__ = [
    "SeumteoBuildingRegisterClient",
    "BuildingHeadingResult",
    "BuildingRegisterQuery",
    "ExclusivePartResult",
    "CodefError",
    "CodefAuthError",
    "CodefNotFound",
    "CodefInvalidInput",
    "CodefUpstreamError",
    "CodefNeedsUserInput",
]
