"""CODEF 세움터 집합건축물대장 전유부+표제부 인하우스 클라이언트 (ADR-0008).

공개 인터페이스는 ``types`` 의 dataclass/예외 전체 + ``CodefBuildingRegisterClient``.
Round2 의 home-check 오케스트레이터는 이 패키지에서만 import 한다.
"""

from __future__ import annotations

from .building_register import CodefBuildingRegisterClient
from .types import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefAuthError,
    CodefCircuitOpen,
    CodefError,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    CodefUpstreamError,
    ExclusivePartResult,
)

__all__ = [
    "BuildingHeadingResult",
    "BuildingRegisterQuery",
    "CodefAuthError",
    "CodefBuildingRegisterClient",
    "CodefCircuitOpen",
    "CodefError",
    "CodefInvalidInput",
    "CodefNeedsUserInput",
    "CodefNotFound",
    "CodefUpstreamError",
    "ExclusivePartResult",
]
