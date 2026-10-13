"""위반표시 재확인 회귀 — 변동사항의 '표시 → 해제' 이력만으로 위반 판정하지 않는다.

fixture 는 실제 발급 건(집합건축물대장 표제부, 2026-10-13 발급)의 pypdf ``extract_text()``
출력 중 변동사항 쪽이다(개인 PII 없음 — 법인명·문서번호만). 오탐 사례: CLIP 전문에
"위반건축물"이 있다는 이유만으로 2015년에 해제된 위반표시를 현재 위반으로 안내했다.
silent-normal(실제 위반 → 정상 오안내)이 더 위험하므로 해제가 증명될 때만 끈다.
"""

from __future__ import annotations

import unittest

from src.flow import _parse_changes_pdf, _resolve_violation

# 표제부(을) 변동사항 쪽 — 위반표시(2015.2.10.) 후 해제(2015.7.16.). '�' 는 PDF 의
# 미매핑 글리프(실측 그대로).
HEADING_CHANGES_RELEASED = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제4호의2서식] <개정 2023. 8. 1.>
297㎜×210㎜[백상지(80�/㎡)]
부속 일련번호 : `` → `4`, 주/부속 일련번호 : `` → `4`, 주/부속 일련번호 : ``
→ `4`, 주/부속 일련번호 : `` → `4`, 주/부속 일련번호 : `1` → `4`) 직권변경
2015.2.10. 수원시 주택과-4385(2015.02.09.)호에 따라 위반건축물 표시�144동
101호 공용테라스 약9.3㎡ 무단증축�
2015.7.16. 수원시 주택과-22000(2015.07.15.)호 위반건축물 표시 해제 통보에 의거
2015.02.10.자 "위반표시 해제" 정리
- 이하여백 -
변동사항
변동일 변동내용 및 원인 변동일 변동내용 및 원인
집합건축물대장(표제부, 을) 변동사항 (1쪽 중 제1쪽)
건물ID 2120041860012558 고유번호 4111513800-3-07060000 명칭 꽃뫼버들마을 진흥아파트144동 호수/가구수/세대수0호/0가구/108세대
대지위치 경기도 수원시 팔달구 화서동 지번 706 도로명주소 경기도 수원시 팔달구 화산로 57 (화서동)"""

# 해제 행이 없는 변형(현재 위반).
HEADING_CHANGES_ACTIVE = HEADING_CHANGES_RELEASED.replace(
    """2015.7.16. 수원시 주택과-22000(2015.07.15.)호 위반건축물 표시 해제 통보에 의거
2015.02.10.자 "위반표시 해제" 정리
""",
    "",
)

# 갑지 상단 표시란에 현재 위반표시가 실린 쪽(이력 밖 출현).
HEADING_PAGE1_MARKED = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제3호서식] <개정 2023. 8. 1.>
위반건축물
집합건축물대장(표제부, 갑)
건물ID 2120041860012558 고유번호 4111513800-3-07060000"""

HEADING_PAGE1_PLAIN = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제3호서식] <개정 2023. 8. 1.>
집합건축물대장(표제부, 갑)
건물ID 2120041860012558 고유번호 4111513800-3-07060000"""


def _resolve(pages: list[str], clip_violation: bool = True) -> tuple[bool, str | None]:
    return _resolve_violation(clip_violation, pages, _parse_changes_pdf(pages))


class ResolveViolationTest(unittest.TestCase):
    def test_released_history_only_is_not_violation(self) -> None:
        pages = [HEADING_PAGE1_PLAIN, HEADING_CHANGES_RELEASED]
        self.assertEqual(_resolve(pages), (False, "history_released"))

    def test_parser_captures_both_history_rows(self) -> None:
        rows = _parse_changes_pdf([HEADING_CHANGES_RELEASED]) or []
        dates = [r["resChangeDate"] for r in rows]
        self.assertIn("2015-02-10", dates)
        self.assertIn("2015-07-16", dates)

    def test_unreleased_history_stays_violation(self) -> None:
        pages = [HEADING_PAGE1_PLAIN, HEADING_CHANGES_ACTIVE]
        self.assertEqual(_resolve(pages), (True, None))

    def test_mark_outside_history_stays_violation(self) -> None:
        # 해제 이력이 있어도 갑지 표시란에 현재 위반표시가 있으면 위반(재지정 등).
        pages = [HEADING_PAGE1_MARKED, HEADING_CHANGES_RELEASED]
        self.assertEqual(_resolve(pages), (True, None))

    def test_more_marks_than_releases_stays_violation(self) -> None:
        extra = HEADING_CHANGES_RELEASED.replace(
            "- 이하여백 -",
            "2016.3.2. 수원시 주택과-1(2016.03.01.)호에 따라 위반건축물 표시 202호 무단증축\n"
            "- 이하여백 -",
        )
        self.assertEqual(_resolve([HEADING_PAGE1_PLAIN, extra]), (True, None))

    def test_no_pdf_keeps_clip_verdict(self) -> None:
        self.assertEqual(_resolve_violation(True, None, None), (True, None))
        pages = [HEADING_CHANGES_RELEASED]
        # PDF 변동사항 파싱이 없으면(CLIP 폴백) 재확인하지 않는다.
        self.assertEqual(_resolve_violation(True, pages, None), (True, None))

    def test_mark_missing_from_pdf_text_keeps_clip_verdict(self) -> None:
        # CLIP 은 봤는데 PDF 텍스트 레이어에 없음(이미지 표시 등) → 현재 위반 유지.
        self.assertEqual(_resolve([HEADING_PAGE1_PLAIN]), (True, None))

    def test_clip_negative_is_untouched(self) -> None:
        pages = [HEADING_PAGE1_MARKED, HEADING_CHANGES_ACTIVE]
        self.assertEqual(_resolve(pages, clip_violation=False), (False, None))


if __name__ == "__main__":
    unittest.main()
