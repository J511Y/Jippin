"""대장 상세(전유부 층/구조/용도/면적, 표제부 주용도/층수/인허가 일자) PDF 파서 회귀.

fixture 는 실발급 PDF 의 pypdf ``extract_text()`` 출력을 개인 성명·주민번호·소유자
주소만 가명 치환해 고정한 것(줄 구조 실측 그대로). 회귀 대상:
  * 내부 JSON(R04/R01)이 못 주는 층/구조/용도·층수·인허가 일자가 비어
    리포트 '대장 상세'가 전유면적만 남던 결함
  * 소유자현황(성명·주소·주민번호) PII 가 상세 필드에 유입되지 않을 것
  * 인허가 일자(라벨과 값이 떨어져 추출됨)의 오매핑 방지 가드
"""

from __future__ import annotations

import unittest

from src.flow import _parse_exclusive_detail_pdf, _parse_heading_detail_pdf
from src.flow import _pdf_page_texts  # noqa: F401 — 파서가 쓰는 헬퍼(임포트 회귀 가드)
from src import flow

# 전유부(갑) 1쪽 — 소유자현황(가명) + 전유부분/공용부분 표가 한 쪽에 섞인 실측 레이아웃.
EXCLUSIVE_PAGE1 = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제5호서식] <개정 2023. 8. 1.>
※ 경계벽이 없는 구분점포의 경우에는 전유부분 구조란에 경계벽이 없음을 기재합니다.
297㎜×210㎜[백상지 (80g/㎡)]
홍가명
서울특별시 어느구 어딘가 1-1 1/1
2011.5.4.
700101-2****** 소유권보존
※ 이 건축물대장은 현소유자만 표시한 것입니다.
- 이하여백 -
부 지2 철근콘크리트구조 기계,전기실 0.85
부 지1~2 철근콘크리트구조 지하주차장 34.617
주 15층 철근콘크리트구조 아파트 59.98
- 이하여백 -
이 등(초)본은 건축물대장의 원본 내용과 틀림없음을 증명합니다.
발급일자 : 2026년 7월 14일
집합건축물대장(전유부, 갑)
 (2쪽 중 제1쪽)
건물ID 2220111260004354 고유번호 1174010600-3-06300000 명칭 둔촌 푸르지오 아파트
107동
전 유 부 분 소 유 자 현 황
구분 층별 ※구조 용도 면적(㎡)
공 용 부 분
구분 층별 구조 용도 면적(㎡)"""

# 표제부(갑) 1쪽 — 주구조/주용도/층수 값줄 + 건축물 현황 표.
HEADING_PAGE1 = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제3호서식] <개정 2023. 8. 1.>
집합건축물대장(표제부, 갑)
건축물 현황 건축물 현황
구분 층별 구조 용도 면적(㎡) 구분 층별 구조 용도 면적(㎡)
주7 1층 철근콘크리트구조 아파트 342
주7 2층 철근콘크리트구조 아파트 332.56
건물ID 2120111260000163 고유번호 1174010600-3-06300000 명칭
둔촌 푸르지오 아파트 107동
※대지면적
㎡
연면적
㎡
※지역 ※지구 ※구역
0 5,019.14 제3종일반주거지역 제1종지구단위계획구역
건축면적
㎡
용적률 산정용 연면적
㎡
주구조 주용도 층수
393.7 5,019.14 철근콘크리트구조 아파트 지하: 층, 지상: 16층
※건폐율
%
※용적률
%
높이
m
지붕 부속건축물 동
0 0 45.3 (철근)콘크리트 ㎡"""

# 표제부(갑) 2쪽 — 인허가 시기(라벨과 값이 떨어짐, 값은 날짜 단독 줄 연속 3개, 성명 가명).
HEADING_PAGE2 = """■ 건축물대장의 기재 및 관리 등에 관한 규칙 [별지 제3호서식] (2쪽 중 제2쪽)
건축물 구조 현황
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
2011.5.20. 주택재건축과-10582(2011.5.13)호 의거 2011.3.
대지위치 서울특별시 강동구 둔촌동 명칭
김가명
(주)가명종합건축사사무소
2005.5.16.
2007.7.16.
2010.3.12.
※주차장
구분 옥내 옥외 인근 면제
그 밖의 기재사항"""


def _fake_pages(monkey_pages):
    """_pdf_page_texts 를 fixture 페이지로 대체하는 헬퍼(디코드 경로 우회)."""

    def fake(pdf_b64):
        return monkey_pages if pdf_b64 else None

    return fake


class ExclusiveDetailTest(unittest.TestCase):
    def test_extracts_unit_row_matching_area_hint(self) -> None:
        original = flow._pdf_page_texts
        flow._pdf_page_texts = _fake_pages([EXCLUSIVE_PAGE1])
        try:
            detail = _parse_exclusive_detail_pdf("stub", area_hint="59.98")
        finally:
            flow._pdf_page_texts = original

        self.assertEqual(
            detail,
            {
                "resArea": "59.98",
                "resFloor": "15층",
                "resStructure": "철근콘크리트구조",
                "resUseType": "아파트",
            },
        )

    def test_falls_back_to_ju_row_without_area_hint(self) -> None:
        original = flow._pdf_page_texts
        flow._pdf_page_texts = _fake_pages([EXCLUSIVE_PAGE1])
        try:
            detail = _parse_exclusive_detail_pdf("stub", area_hint=None)
        finally:
            flow._pdf_page_texts = original

        # 공용부분 '부' 행(지하주차장 등)이 아니라 전유 '주' 행을 고른다.
        self.assertIsNotNone(detail)
        self.assertEqual(detail["resUseType"], "아파트")
        self.assertEqual(detail["resFloor"], "15층")

    def test_owner_pii_never_leaks_into_fields(self) -> None:
        original = flow._pdf_page_texts
        flow._pdf_page_texts = _fake_pages([EXCLUSIVE_PAGE1])
        try:
            detail = _parse_exclusive_detail_pdf("stub", area_hint="59.98")
        finally:
            flow._pdf_page_texts = original

        joined = " ".join(str(v) for v in (detail or {}).values())
        for pii in ("홍가명", "700101", "어느구 어딘가"):
            self.assertNotIn(pii, joined)

    def test_missing_pdf_returns_none(self) -> None:
        self.assertIsNone(_parse_exclusive_detail_pdf(None))
        self.assertIsNone(_parse_exclusive_detail_pdf(""))


class HeadingDetailTest(unittest.TestCase):
    def test_extracts_use_structure_floors_and_permit_dates(self) -> None:
        original = flow._pdf_page_texts
        flow._pdf_page_texts = _fake_pages([HEADING_PAGE1, HEADING_PAGE2])
        try:
            detail = _parse_heading_detail_pdf("stub")
        finally:
            flow._pdf_page_texts = original

        self.assertEqual(
            detail,
            {
                "주구조": "철근콘크리트구조",
                "주용도": "아파트",
                "층수": "지상 16층",  # 지하 칸이 빈 서식 — 지상만.
                "허가일": "2005-05-16",
                "착공일": "2007-07-16",
                "사용승인일": "2010-03-12",
            },
        )

    def test_ambiguous_date_runs_leave_permit_dates_empty(self) -> None:
        # 날짜 단독 줄 묶음이 3개가 아니면(사용승인 전 건물 등) 오매핑 대신 생략한다.
        page = HEADING_PAGE2.replace("2010.3.12.\n", "")
        original = flow._pdf_page_texts
        flow._pdf_page_texts = _fake_pages([HEADING_PAGE1, page])
        try:
            detail = _parse_heading_detail_pdf("stub")
        finally:
            flow._pdf_page_texts = original

        self.assertNotIn("사용승인일", detail)
        self.assertNotIn("허가일", detail)

    def test_dates_are_iso_normalized_for_api_parse_date(self) -> None:
        # api _parse_date 는 숫자 8자리만 받는다 — "2010.3.12."(7자리)는 탈락하므로
        # 워커가 zero-pad ISO 로 내보내는 것이 계약이다.
        original = flow._pdf_page_texts
        flow._pdf_page_texts = _fake_pages([HEADING_PAGE1, HEADING_PAGE2])
        try:
            detail = _parse_heading_detail_pdf("stub")
        finally:
            flow._pdf_page_texts = original

        for label in ("허가일", "착공일", "사용승인일"):
            digits = "".join(ch for ch in detail[label] if ch.isdigit())
            self.assertEqual(len(digits), 8, detail[label])
