from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.flow import FlowError, SeumteoFlow
from src.models import BuildingRegisterRequest


class _Page:
    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


def _row(
    receipt: str,
    created_at: str,
    *,
    address: str = "대구광역시 달서구 유천동 488 유천동 포스코 더샵아파트 105동 2001",
) -> dict:
    return {
        "mgmNo": f"mgm-{receipt}",
        "locDetlAddr": address,
        "progStateCd": "91",
        "pbsvcRecpNo": receipt,
        "regstrKindCd": "4",
        "issueReadGbCd": "0",
        "bldrgstGbCd": "1",
        "firstCrtnDt": created_at,
        "recpDate": "2026-07-13",
        "realProcessDateStr": "20260713",
    }


class ReceiptMatchingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.flow = object.__new__(SeumteoFlow)
        self.flow._s = SimpleNamespace(eais_base_url="https://www.eais.go.kr")
        self.req = BuildingRegisterRequest(
            road_addr="대구광역시 달서구 달서대로 67",
            dong="105동",
            ho="2001호",
            register_kind="exclusive",
        )
        self.targets = {
            "bld_nm": "유천동 포스코 더샵아파트",
            "jibun_addr": "대구광역시 달서구 유천동 488 유천동 포스코 더샵아파트",
            "loc": {"mnnm": "0488"},
            "es_dong_nm": "105동",
            "es_ho_nm": "2001",
        }

    async def test_accepts_new_history_row_when_submit_candidate_differs(self) -> None:
        """실측 회귀: 완료 행은 있는데 S01/D02 후보 번호가 달라도 새 행을 선택한다."""

        old = _row("20263470000G209084", "20260713103941")
        new = _row("20263470000G209088", "20260713104427")
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [new, old],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        result = await self.flow._find_recp_no(
            _Page(),
            self.req,
            self.targets,
            {"20263470000G209084"},
            submitted_recp="untrusted-response-value",
        )

        self.assertEqual(result["pbsvcRecpNo"], "20263470000G209088")
        self.assertEqual(result["appDate"], "20260713")

    async def test_accepts_history_when_building_name_variant_has_same_jibun(
        self,
    ) -> None:
        """실측 회귀: 검색 bldNm과 이력 주소의 법정동 접두어 표기가 다를 수 있다."""

        self.targets["bld_nm"] = "유천포스코더샵아파트"
        history = _row("20263470000G209107", "20260713105108")
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [history],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263470000G209107")

    async def test_rejects_name_variant_when_strong_jibun_does_not_match(self) -> None:
        """동·호가 같아도 다른 단지의 이력은 지번 식별자로 차단한다."""

        self.targets["bld_nm"] = "유천포스코더샵아파트"
        other_building = _row(
            "20263470000G209108",
            "20260713105208",
            address="대구광역시 달서구 유천동 489 다른아파트 105동 2001",
        )
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [other_building],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

    async def test_rejects_name_variant_when_parcel_number_only_has_prefix(
        self,
    ) -> None:
        """488과 4880은 다른 필지이므로 부분 문자열 매칭을 허용하지 않는다."""

        self.targets["bld_nm"] = "유천포스코더샵아파트"
        prefixed_parcel = _row(
            "20263470000G209109",
            "20260713105308",
            address="대구광역시 달서구 유천동 4880 다른아파트 105동 2001",
        )
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [prefixed_parcel],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

    async def test_rejects_when_main_lot_number_appears_in_legal_dong_name(
        self,
    ) -> None:
        """종로1가의 '1'이 아니라 공백 뒤 실제 지번 1을 기준으로 비교한다."""

        self.targets.update(
            {
                "bld_nm": "검색단지명",
                "jibun_addr": "서울특별시 종로구 종로1가 1 검색단지명",
                "loc": {"mnnm": "0001", "slno": ""},
            }
        )
        other_parcel = _row(
            "20261100000G209110",
            "20260713105408",
            address="서울특별시 종로구 종로1가 2 다른단지 105동 2001",
        )
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [other_parcel],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

    async def test_never_reuses_receipt_present_before_submission(self) -> None:
        old = _row("20263470000G209084", "20260713103941")
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [old],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(
                _Page(),
                self.req,
                self.targets,
                {"20263470000G209084"},
                submitted_recp="20263470000G209084",
            )

    async def test_submit_candidate_breaks_tie_between_two_new_rows(self) -> None:
        first = _row("20263470000G209088", "20260713104427")
        second = _row("20263470000G209107", "20260713105108")
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [second, first],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        result = await self.flow._find_recp_no(
            _Page(),
            self.req,
            self.targets,
            set(),
            submitted_recp="2026-347-0000G209107",
        )

        self.assertEqual(result["pbsvcRecpNo"], "20263470000G209107")

    async def test_snapshot_normalizes_existing_receipt_numbers(self) -> None:
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": [
                    {"pbsvcRecpNo": "2026-347-0000g209088"},
                    {"pbsvcRecpNo": ""},
                ],
                "caisMessage": {"resultCode": "S00000"},
            }
        )

        result = await self.flow._receipt_snapshot(_Page())

        self.assertEqual(result, {"20263470000G209088"})


if __name__ == "__main__":
    unittest.main()
