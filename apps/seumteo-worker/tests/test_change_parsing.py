"""변동사항 파서 회귀 — 실발급 PDF 텍스트(pypdf 추출) 기반.

fixture 는 실제 발급 건(집합건축물대장, 2026-07-14 발급)의 pypdf ``extract_text()``
출력을 개인 성명만 가명 치환해 고정한 것이다. 줄바꿈(셀 폭 절단) 위치까지 실측 그대로 —
이 구조가 파서 입력의 정의다. 회귀 대상(세션 903c0c36 실측 결함):
  * 같은 행이 오프셋만 다른 절단본으로 중복 추출
  * "-이하여백-"(빈칸 필러)·"사용승인일"(서식 라벨)이 변동 이력으로 승격
  * 공동주택가격/인허가 시기 등 이웃 표의 날짜 행 오인
  * 설계자·감리자 성명(PII)이 사유에 유입
"""

from __future__ import annotations

import unittest

from src.flow import (
    _dedupe_changes,
    _is_meaningful_reason,
    _parse_changes,
    _parse_changes_pdf,
    _scan_change_lines,
)

# 전유부(갑) 2쪽 — 변동사항 1행 + 공용부분/공동주택가격 표(날짜 행 잡음원).
EXCLUSIVE_PAGE2 = """(2쪽 중 제2쪽)
297㎜×210㎜[백상지 (80g/㎡)]
변동사항
그 밖의 기재사항
변동일 변동내용 및 원인 변동일 변동내용 및 원인
2011.5.20. 주택재건축과-10582(2011.5.13)호 의거 2011.3.
9. 이전고시되어 신규작성(신축)
- 이하여백 -
공 용 부 분 공동주택(아파트) 가 격 (단위 : 원)
구분 층별 ※구조 용도 면적(㎡) 기 준 일 공동주택(아파트) 가격
*「부동산 가격공시에 관한 법률」제 18조에 따른 공동주택가격만 표시됩니다.
부 1~2층 철근콘크리트구조 문고,노인정,보육시설,주민공동시설 0.43
주 각층 철근콘크리트구조 계단,전실,벽체,발코니초과 23.44
부 1층 철근콘크리트구조 경비실 0.01
부 2층 철근콘크리트구조 관리사무소 0.06
- 이하여백 -
2026.1.1. 858,000,000
2025.1.1. 666,000,000
2024.1.1. 579,000,000
건물ID 2220111260004354 고유번호 1174010600-3-06300000 명칭 둔촌 푸르지오 아파트
107동"""

# 표제부(갑) 2쪽 — 변동사항 3행이 인허가 시기(허가일/착공일/사용승인일)·설계자 성명 표와
# 뒤섞여 추출되는 실측 레이아웃.
HEADING_PAGE2 = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제3호서식] (2쪽 중 제2쪽)
※ 표시 항목은 총괄표제부가 있는 경우에는 적지 않을 수 있습니다.
건축물 구조 현황
내진설계 적용 여부 내진능력
변동사항
변동일 변동내용 및 원인 변동일 변동내용 및 원인
건축물 관리 현황
인허가 시기
허가일
착공일
사용승인일
2
구분 성명 또는 명칭 면허(등록)번호
건축주
설계자
공사감리자
공사시공자
(현장관리인)
2019.5.28. 국토교통부 건축정책과-281 (2018.1.11.)호에 의거 건
축물대장 내진설계 여부 기재
2026.5.21. 공동주택과-14300호(2026.05.21.)에 의거 403호
거실과 발코니 사이 비내력벽 철거(창호포함) 및 발코니 확장(6
.84㎡), 침실1과 발코니 사이 비내력벽 철거(창호포함) 및
발코니 확장(4.23㎡), 세대간 경량칸막이 구조로 대피공간 설
치 예외, 방화판 및 자동화재감지기 설치【행위허가】
2011.5.20. 주택재건축과-10582(2011.5.13)호 의거 2011.3.
대지위치 서울특별시 강동구 둔촌동 명칭
둔촌 푸르지오 아파트 107동
호수/가구수/세대수
0호/0가구/60세대
길동진흥아파트주택재건
축정비사업조합 244171-0******
김가명
(주)디엔에이엔지니어링종합
건축사사무소
이가명
(주)삼우종합건축사사무소
박가명 (주)대우건설
2005.5.16.
2007.7.16.
2010.3.12.
※주차장
구분 옥내 옥외 인근 면제
그 밖의 기재사항"""

# 표제부(을) 변동사항 쪽 — 날짜 줄 위에 앞 쪽에서 넘어온 고아 연속줄이 먼저 온다.
HEADING_PAGE4 = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제4호의2서식] <개정 2023. 8. 1.>
297㎜×210㎜[백상지(80g/㎡)]
9.이전고시되어 신규작성(신축)
2011.5.20. 발코니 확장(재건축과-14232(2010.12.28)호 의거 103호,
주택재건축과-662(2011.1.12)호 의거 203호,
주택재건축과-662(2011.1.12)호 의거 203호,
재건축과-14232(2010.12.28)호 의거 204호, 재건축과-5484(2010.5.18)호
의거 701호, 재건축과-5350(2010.5.14)호 의거 702호,
재건축과-8168(2010.7.23)호 의거 801호, 재건축과-6612(2010.6.17)호
의거 1104호, 재건축과-6753(2010.6.21)호 의거 1301호,
재건축과-6334(2010.6.10)호 의거 1403호)
- 이하여백 -
변동사항
변동일 변동내용 및 원인 변동일 변동내용 및 원인
집합건축물대장(표제부, 을) 변동사항 (1쪽 중 제1쪽)
건물ID 2120111260000163 고유번호 1174010600-3-06300000 명칭
둔촌 푸르지오 아파트 107동"""


class ScanChangeLinesTest(unittest.TestCase):
    def test_exclusive_page_yields_single_joined_row(self) -> None:
        rows = _scan_change_lines(EXCLUSIVE_PAGE2.splitlines())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resChangeDate"], "2011-05-20")
        # 셀 폭 줄바꿈("…2011.3." + "9. 이전고시…")은 공백 없이 이어 붙는다.
        self.assertEqual(
            rows[0]["resChangeReason"],
            "주택재건축과-10582(2011.5.13)호 의거 2011.3.9. 이전고시되어 신규작성(신축)",
        )

    def test_price_table_date_rows_are_not_changes(self) -> None:
        rows = _scan_change_lines(EXCLUSIVE_PAGE2.splitlines())

        for row in rows:
            self.assertNotIn("858,000,000", row["resChangeReason"])
            self.assertNotEqual(row["resChangeDate"], "2026-01-01")

    def test_heading_page_extracts_three_rows_without_pii(self) -> None:
        rows = _scan_change_lines(HEADING_PAGE2.splitlines())

        self.assertEqual(
            [r["resChangeDate"] for r in rows],
            ["2019-05-28", "2026-05-21", "2011-05-20"],
        )
        self.assertEqual(
            rows[0]["resChangeReason"],
            "국토교통부 건축정책과-281 (2018.1.11.)호에 의거 건축물대장 내진설계 여부 기재",
        )
        # 403호 행위허가 행 — 부위(거실/침실)·면적(6.84/4.23㎡)이 원문 그대로 보존된다.
        self.assertIn("403호", rows[1]["resChangeReason"])
        self.assertIn("발코니 확장(6.84㎡)", rows[1]["resChangeReason"])
        self.assertIn("발코니 확장(4.23㎡)", rows[1]["resChangeReason"])
        self.assertIn("【행위허가】", rows[1]["resChangeReason"])
        # 인허가 시기(허가일 2005.5.16 등) 날짜 단독 줄은 변동 행이 아니다.
        self.assertNotIn("2005-05-16", [r["resChangeDate"] for r in rows])
        # 설계자·감리자·시공자 성명(PII)은 어떤 사유에도 유입되지 않는다.
        joined = " ".join(r["resChangeReason"] for r in rows)
        for name in ("김가명", "이가명", "박가명"):
            self.assertNotIn(name, joined)

    def test_eul_page_captures_full_unit_list(self) -> None:
        rows = _scan_change_lines(HEADING_PAGE4.splitlines())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resChangeDate"], "2011-05-20")
        reason = rows[0]["resChangeReason"]
        self.assertTrue(reason.startswith("발코니 확장(재건축과-14232"))
        # 확장 등재 세대 목록이 절단 없이 보존된다 — 판정 LLM 이 세대(호) 대조에 쓴다.
        self.assertIn("103호", reason)
        self.assertIn("1403호)", reason)
        self.assertNotIn("이하여백", reason)


class DedupeChangesTest(unittest.TestCase):
    def test_same_row_truncations_collapse_to_longest(self) -> None:
        rows = [
            {"resChangeDate": None, "resChangeReason": "이전고시되어신규작성(신축)"},
            {
                "resChangeDate": "2011-05-20",
                "resChangeReason": "이전고시되어신규작성(신축) 발코니확장(재건축과",
            },
            {
                "resChangeDate": "2011-05-20",
                "resChangeReason": "이전고시되어신규작성(신축) 발코니확장",
            },
        ]

        out = _dedupe_changes(rows)

        self.assertEqual(len(out), 1)
        self.assertEqual(
            out[0]["resChangeReason"], "이전고시되어신규작성(신축) 발코니확장(재건축과"
        )
        self.assertEqual(out[0]["resChangeDate"], "2011-05-20")

    def test_distinct_document_numbers_do_not_collapse(self) -> None:
        # 상용구("…과-N호 의거")가 같아도 문서번호가 다르면 별개 변동이다.
        rows = [
            {
                "resChangeDate": "2011-05-20",
                "resChangeReason": "주택재건축과-10582(2011.5.13)호 의거 신규작성",
            },
            {
                "resChangeDate": "2011-05-20",
                "resChangeReason": "발코니 확장(주택재건축과-662(2011.1.12)호 의거 203호)",
            },
        ]

        self.assertEqual(len(_dedupe_changes(rows)), 2)

    def test_different_dates_never_collapse(self) -> None:
        rows = [
            {"resChangeDate": "2019-05-28", "resChangeReason": "내진설계 여부 기재"},
            {"resChangeDate": "2020-03-02", "resChangeReason": "내진설계 여부 기재"},
        ]

        self.assertEqual(len(_dedupe_changes(rows)), 2)


class MeaningfulReasonTest(unittest.TestCase):
    def test_form_labels_and_fillers_are_rejected(self) -> None:
        for garbage in (
            "사용승인일,사용승인일, 사용승인일 ,,",
            ", 사용승인일 ,,",
            "-이하여백-,-이하여백-,",
            "858,000,000",
            "",
        ):
            self.assertFalse(_is_meaningful_reason(garbage), garbage)

    def test_short_change_keywords_survive(self) -> None:
        for keep in ("증축", "말소", "발코니 확장(4.23㎡)", "신규작성(신축)"):
            self.assertTrue(_is_meaningful_reason(keep), keep)


class ClipFallbackTest(unittest.TestCase):
    def test_window_truncations_are_cleaned_and_collapsed(self) -> None:
        # 세션 903c0c36 실측 결함의 압축 텍스트 재현: 같은 행이 창 오프셋만 다르게 잡히고
        # 필러(이하여백)·라벨(사용승인일)이 섞인다.
        compact = (
            "변동사항그밖의기재사항변동일변동내용및원인"
            "2011.5.20.주택재건축과-10582(2011.5.13)호의거2011.3.9."
            "이전고시되어신규작성(신축)-이하여백--이하여백-"
            "사용승인일,사용승인일,사용승인일,,"
        )

        rows = _parse_changes(compact)

        self.assertTrue(rows)
        reasons = [r["resChangeReason"] for r in rows]
        for reason in reasons:
            self.assertTrue(_is_meaningful_reason(reason), reason)
            self.assertNotIn("이하여백", reason)
            self.assertNotIn("사용승인일", reason)
        # 신규작성/신축 창 절단본은 한 행으로 붕괴된다.
        self.assertEqual(len([r for r in reasons if "신규작성" in r or "신축" in r]), 1)

    def test_empty_text_yields_no_rows(self) -> None:
        self.assertEqual(_parse_changes(""), [])


class ParseChangesPdfTest(unittest.TestCase):
    def test_missing_or_broken_pdf_falls_back(self) -> None:
        self.assertIsNone(_parse_changes_pdf(None))
        self.assertIsNone(_parse_changes_pdf(""))
        self.assertIsNone(_parse_changes_pdf("bm90LWEtcGRm"))  # "not-a-pdf"
