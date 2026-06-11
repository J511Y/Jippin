"""법령 규칙 카탈로그 (RULE 모듈, CMP-DIRECT).

국토교통부 고시 「발코니 등의 구조변경절차 및 설치기준」(제2018-775호)을
판단 규칙으로 구조화한 카탈로그다 (FR-RULE-001, 기능명세서 §2.8 RULE-001).

설계 원칙 (소프트웨어설계문서 §4.8):

- 규칙 카탈로그는 **코드가 정본**이다. DB(`rule_sets` 예정 테이블)의 JSON
  definition 은 버전·법령 검증일·임계 파라미터만 운반하며, 분기 로직 자체는
  코드 배포로만 바뀐다. 이렇게 해야 동일 입력 결정성 100%(NFR-QUAL-002)와
  룰 변경 시 회귀 테스트(NFR-MAINT-001)가 함께 보장된다.
- `Ruleset.from_definition()` 은 미래의 `rule_sets.definition`(JSONB) row 를
  그대로 받을 수 있는 모양이다. 현재 스키마에는 `rule_sets` 테이블이 아직
  없으므로 (supabase/migrations 기준) DB 조회 코드는 두지 않고, 호출 측이
  definition dict 를 넘기는 순수 로더만 제공한다.
- 평가 경로에는 시계·난수·네트워크가 없다. `verified_on` 은 룰셋 메타데이터
  (FR-RULE-007 법령 검증일)일 뿐 평가 입력이 아니다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

#: 기본(베이스라인) 룰셋 버전. 룰 분기 변경 시 반드시 함께 올린다 (FR-RULE-007).
BASELINE_RULESET_VERSION = "2018-775.v1"

#: 적용 법령 표기 (RULE-001).
BASELINE_LAW_REFERENCE = (
    "국토교통부 고시 제2018-775호 발코니 등의 구조변경절차 및 설치기준"
)


class RulesetDefinitionError(ValueError):
    """`rule_sets` definition JSON 이 스키마에 맞지 않을 때."""


@dataclass(frozen=True, slots=True)
class LegalBasis:
    """판단 근거 1건 — 조문 매핑 (FR-RULE-006: 결론 카드마다 근거 1개 이상)."""

    rule_id: str
    source: str
    section: str
    summary: str
    link: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "source": self.source,
            "section": self.section,
            "summary": self.summary,
            "link": self.link,
        }


@dataclass(frozen=True, slots=True)
class RulesetParameters:
    """규칙 임계값 파라미터 — `rule_sets.definition.parameters` 로 오버라이드 가능.

    분기 구조는 코드 정본이지만, 임계 수치는 법령 개정 시 룰셋 갱신으로
    바뀔 수 있어 데이터로 분리한다 (NFR-MAINT-001 룰셋 핫스왑).
    """

    # 기능명세서 §2.8 자동 예외: "1층 세대: 화재감지기만 설치".
    first_floor_exception_max_floor: int = 1
    # 기능명세서 §2.8 자동 예외: "계단실 2개소 이상: 방화문 설치 제외".
    staircase_exception_min_count: int = 2
    # 건축법 시행령 제46조④ — 아파트 4층 이상 세대 발코니 확장 시 대피공간 확보.
    evacuation_space_min_floor: int = 4
    # 고시 제2018-775호 제5조 — 아래층 화재 확산 방지 시설(방화판·방화유리창)은
    # 아래층 세대가 존재하는 2층 이상 세대에 적용. 1층 세대는 예외(§2.8).
    fire_spread_guard_min_floor: int = 2


@dataclass(frozen=True, slots=True)
class Ruleset:
    """버전 관리되는 룰셋 1건 (FR-RULE-001/007)."""

    version: str
    law_reference: str
    # 현행 법령 검증일 (FR-RULE-007). 평가 입력이 아닌 표기용 메타데이터다.
    verified_on: str
    parameters: RulesetParameters = field(default_factory=RulesetParameters)

    @classmethod
    def from_definition(cls, definition: Mapping[str, object]) -> "Ruleset":
        """미래 `rule_sets.definition`(JSONB) dict 로부터 룰셋을 로드한다.

        알 수 없는 파라미터 key 는 무시하지 않고 거절한다 — 오타로 인해
        의도한 임계값 변경이 조용히 누락되는 사고를 막기 위함 (보수 분기).
        """

        version = definition.get("version")
        if not isinstance(version, str) or not version.strip():
            raise RulesetDefinitionError(
                "definition.version 은 비어 있지 않은 문자열이어야 합니다."
            )
        law_reference = definition.get("law_reference")
        if not isinstance(law_reference, str) or not law_reference.strip():
            raise RulesetDefinitionError(
                "definition.law_reference 는 비어 있지 않은 문자열이어야 합니다."
            )
        verified_on = definition.get("verified_on")
        if not isinstance(verified_on, str) or not verified_on.strip():
            raise RulesetDefinitionError(
                "definition.verified_on (법령 검증일, FR-RULE-007) 이 필요합니다."
            )

        raw_params = definition.get("parameters") or {}
        if not isinstance(raw_params, Mapping):
            raise RulesetDefinitionError("definition.parameters 는 object 여야 합니다.")
        allowed = {
            "first_floor_exception_max_floor",
            "staircase_exception_min_count",
            "evacuation_space_min_floor",
            "fire_spread_guard_min_floor",
        }
        unknown = sorted(set(raw_params) - allowed)
        if unknown:
            raise RulesetDefinitionError(
                f"definition.parameters 에 알 수 없는 key 가 있습니다: {unknown}"
            )
        kwargs: dict[str, int] = {}
        for key in sorted(allowed & set(raw_params)):
            value = raw_params[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RulesetDefinitionError(
                    f"definition.parameters.{key} 는 0 이상의 정수여야 합니다."
                )
            kwargs[key] = value

        return cls(
            version=version,
            law_reference=law_reference,
            verified_on=verified_on,
            parameters=RulesetParameters(**kwargs),
        )

    def to_definition(self) -> dict[str, object]:
        """`rule_sets.definition` JSONB 에 그대로 저장 가능한 dict."""

        return {
            "version": self.version,
            "law_reference": self.law_reference,
            "verified_on": self.verified_on,
            "parameters": {
                "first_floor_exception_max_floor": (
                    self.parameters.first_floor_exception_max_floor
                ),
                "staircase_exception_min_count": (
                    self.parameters.staircase_exception_min_count
                ),
                "evacuation_space_min_floor": self.parameters.evacuation_space_min_floor,
                "fire_spread_guard_min_floor": self.parameters.fire_spread_guard_min_floor,
            },
        }


#: 베이스라인 룰셋 — 스펙에서 도출한 in-code 기본값.
#: verified_on 은 본 카탈로그를 명세서와 대조한 날짜다 (평가에 사용되지 않음).
BASELINE_RULESET = Ruleset(
    version=BASELINE_RULESET_VERSION,
    law_reference=BASELINE_LAW_REFERENCE,
    verified_on="2026-06-11",
)


# ---------------------------------------------------------------------------
# 법령 근거 카탈로그 (FR-RULE-006 — 조문 매핑)
# ---------------------------------------------------------------------------
# rule_id 네이밍: R-<영역>-<번호>. 영역 = WALL(벽체) / FIRE(방화시설) /
# EVAC(대피공간) / ZONE(방화구획) / PERMIT(행위허가 절차).

LEGAL_WALL_LOAD_BEARING_PROHIBITED = LegalBasis(
    rule_id="R-WALL-01",
    source="공동주택관리법",
    section="제35조 및 동법 시행령 제35조 별표 3",
    summary=(
        "내력벽의 철거·변경은 행위허가 대상이며 구조 안전 확인 없이는 "
        "허용되지 않습니다. 사전검토 단계에서는 진행이 어렵다고 안내합니다."
    ),
    link="https://www.law.go.kr/법령/공동주택관리법",
)

LEGAL_WALL_NON_LOAD_BEARING = LegalBasis(
    rule_id="R-WALL-02",
    source="공동주택관리법 시행령",
    section="제35조 별표 3 (비내력벽 철거)",
    summary=(
        "세대 내부 비내력벽 철거는 관할 행정기관의 행위허가(또는 신고) 절차를 "
        "거쳐 진행할 수 있습니다."
    ),
    link="https://www.law.go.kr/법령/공동주택관리법시행령",
)

LEGAL_FIRE_DETECTOR = LegalBasis(
    rule_id="R-FIRE-01",
    source=BASELINE_LAW_REFERENCE,
    section="제6조 (화재감지기 설치)",
    summary="확장되는 발코니 부분에는 화재감지기를 설치해야 합니다.",
    link="https://www.law.go.kr/행정규칙/발코니등의구조변경절차및설치기준",
)

LEGAL_FIRE_SPREAD_GUARD = LegalBasis(
    rule_id="R-FIRE-02",
    source=BASELINE_LAW_REFERENCE,
    section="제5조 (방화판 또는 방화유리창의 설치)",
    summary=(
        "아래층 세대에서 발생한 화재의 확산을 막기 위해 발코니 창호 부위에 "
        "방화판 또는 방화유리창을 설치해야 합니다."
    ),
    link="https://www.law.go.kr/행정규칙/발코니등의구조변경절차및설치기준",
)

LEGAL_FIRE_SPRINKLER_EXCEPTION = LegalBasis(
    rule_id="R-FIRE-03",
    source=BASELINE_LAW_REFERENCE,
    section="제5조 제1항·제6조 (스프링클러 살수범위 예외)",
    summary=(
        "발코니가 스프링클러 살수범위에 포함되는 경우 방화판·방화유리창과 "
        "화재감지기 설치 의무가 제외됩니다."
    ),
    link="https://www.law.go.kr/행정규칙/발코니등의구조변경절차및설치기준",
)

LEGAL_FIRE_DOOR = LegalBasis(
    rule_id="R-FIRE-04",
    source="건축법 시행령",
    section="제46조 제4항 (대피공간 출입구 방화문)",
    summary="대피공간을 두는 경우 그 출입구에는 방화문을 설치해야 합니다.",
    link="https://www.law.go.kr/법령/건축법시행령",
)

LEGAL_FIRE_DOOR_STAIRCASE_EXCEPTION = LegalBasis(
    rule_id="R-FIRE-05",
    source="건축법 시행령",
    section="제46조 제4항 단서 (직통계단 2개소 이상 예외)",
    summary=(
        "각 세대에서 이용 가능한 직통계단(계단실)이 2개소 이상이면 방화문 "
        "설치 의무가 제외됩니다."
    ),
    link="https://www.law.go.kr/법령/건축법시행령",
)

LEGAL_FIRST_FLOOR_EXCEPTION = LegalBasis(
    rule_id="R-FIRE-06",
    source=BASELINE_LAW_REFERENCE,
    section="제5조·제6조 (1층 세대 예외)",
    summary=(
        "1층 세대는 아래층 화재 확산·대피 경로 제약이 없어 화재감지기만 "
        "설치 대상이 됩니다 (방화판·방화문 제외)."
    ),
    link="https://www.law.go.kr/행정규칙/발코니등의구조변경절차및설치기준",
)

LEGAL_EVACUATION_SPACE = LegalBasis(
    rule_id="R-EVAC-01",
    source="건축법 시행령",
    section="제46조 제4항 (아파트 4층 이상 대피공간)",
    summary=(
        "4층 이상 세대의 발코니를 확장하는 경우 대피공간 또는 경량칸막이 "
        "등 대체 대피 경로를 확보해야 합니다."
    ),
    link="https://www.law.go.kr/법령/건축법시행령",
)

LEGAL_FIRE_ZONE_REVIEW = LegalBasis(
    rule_id="R-ZONE-01",
    source="건축법",
    section="제49조 및 건축물의 피난·방화구조 등의 기준에 관한 규칙 제14조",
    summary=(
        "철거 대상 부위가 방화구획에 포함되는 경우 구획 성능 유지 여부를 "
        "별도로 검토해야 하며, 자동 판단 범위를 벗어납니다."
    ),
    link="https://www.law.go.kr/법령/건축법",
)

LEGAL_PERMIT_PROCEDURE = LegalBasis(
    rule_id="R-PERMIT-01",
    source="공동주택관리법",
    section="제35조 (행위허가 등)",
    summary=(
        "공동주택의 비내력벽 철거·발코니 구조변경은 관할 시·군·구의 "
        "행위허가 대상입니다. 신고 대상 여부는 지자체 기준에 따라 달라질 수 "
        "있습니다."
    ),
    link="https://www.law.go.kr/법령/공동주택관리법",
)

#: 카탈로그 전체 — 근거 출력 순서를 고정하기 위한 정렬 기준 (결정론 보장).
LEGAL_BASIS_CATALOG: tuple[LegalBasis, ...] = (
    LEGAL_WALL_LOAD_BEARING_PROHIBITED,
    LEGAL_WALL_NON_LOAD_BEARING,
    LEGAL_FIRE_DETECTOR,
    LEGAL_FIRE_SPREAD_GUARD,
    LEGAL_FIRE_SPRINKLER_EXCEPTION,
    LEGAL_FIRE_DOOR,
    LEGAL_FIRE_DOOR_STAIRCASE_EXCEPTION,
    LEGAL_FIRST_FLOOR_EXCEPTION,
    LEGAL_EVACUATION_SPACE,
    LEGAL_FIRE_ZONE_REVIEW,
    LEGAL_PERMIT_PROCEDURE,
)

_CATALOG_ORDER: dict[str, int] = {
    basis.rule_id: index for index, basis in enumerate(LEGAL_BASIS_CATALOG)
}


def sort_legal_basis(
    items: set[LegalBasis] | list[LegalBasis],
) -> tuple[LegalBasis, ...]:
    """근거 목록을 카탈로그 등재 순서로 고정 정렬한다 (NFR-QUAL-002)."""

    return tuple(sorted(items, key=lambda basis: _CATALOG_ORDER[basis.rule_id]))
