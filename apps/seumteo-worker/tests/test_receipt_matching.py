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

    # ------------------------------------------------------------------
    # 동/호 접미 관용(#recp-unit-suffix) — 2026-09-03 삼부아파트 실패 회귀.
    # ES dongNm '101'(접미 없음)·hoNm '1001호' 건물은 신청내역 주소가 '… 101 1001호' 라
    # 옛 '(dong+"동") in addr' 검사가 접수행을 못 찾아 upstream 오류로 끝났다.
    # ------------------------------------------------------------------
    def _use_sambu(self, **overrides: object) -> None:
        self.req = BuildingRegisterRequest(
            road_addr="서울특별시 강남구 봉은사로111길 26",
            dong="101",
            ho="1001",
            register_kind="exclusive",
        )
        self.targets = {
            "bld_nm": None,
            "jibun_addr": "서울특별시 강남구 삼성동 99-13 삼부아파트",
            "loc": {"mnnm": "0099", "slno": "0013"},
            "es_dong_nm": "101",
            "es_ho_nm": "1001호",
            **overrides,
        }

    def _history(self, *rows: dict) -> None:
        self.flow._post = AsyncMock(
            return_value={
                "IssueReadHistList": list(rows),
                "caisMessage": {"resultCode": "S00000"},
            }
        )

    async def test_accepts_dong_without_suffix_in_es_and_history(self) -> None:
        """실측 회귀(삼부아파트): dongNm '101'·hoNm '1001호' → '… 삼부아파트 101 1001호' 매칭."""

        self._use_sambu()
        self._history(
            _row(
                "20263230000I317500",
                "20260903142230",
                address="서울특별시 강남구 삼성동 99-13 삼부아파트 101 1001호",
            )
        )

        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263230000I317500")

    async def test_rejects_other_dong_and_ho_when_suffix_absent(self) -> None:
        """접미가 없어도 다른 동(1101)·다른 호(1002)·붙은 숫자(11001)는 경계로 걸러낸다."""

        self._use_sambu(es_ho_nm="1001")
        self._history(
            _row(
                "20263230000I317501",
                "20260903142231",
                address="서울특별시 강남구 삼성동 99-13 삼부아파트 1101 1001",
            ),
            _row(
                "20263230000I317502",
                "20260903142232",
                address="서울특별시 강남구 삼성동 99-13 삼부아파트 101 1002",
            ),
            _row(
                "20263230000I317503",
                "20260903142233",
                address="서울특별시 강남구 삼성동 99-13 삼부아파트 101 11001",
            ),
        )

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

    async def test_accepts_prefixed_dong_and_ho_forms(self) -> None:
        """'제101동 제1001호'/'101동1001호' 처럼 접두·접미·공백이 달라도 같은 세대로 본다."""

        self._use_sambu(es_dong_nm="101동")
        for address in (
            "서울특별시 강남구 삼성동 99-13 삼부아파트 제101동 제1001호",
            "서울특별시 강남구 삼성동 99-13 삼부아파트 101동1001호",
        ):
            with self.subTest(address=address):
                self._history(
                    _row("20263230000I317504", "20260903142234", address=address)
                )

                result = await self.flow._find_recp_no(
                    _Page(), self.req, self.targets, set()
                )

                self.assertEqual(result["pbsvcRecpNo"], "20263230000I317504")

    async def test_accepts_unnamed_dong_marker(self) -> None:
        """실측 회귀(더써밋타워): dongNm '동명칭없음' 은 접미가 없어도 그 자체로 동 토큰이다."""

        self.req = BuildingRegisterRequest(
            road_addr="서울특별시 동작구 장승배기로 174",
            dong="더써밋타워",
            ho="2313",
            register_kind="exclusive",
        )
        self.targets = {
            "bld_nm": "더써밋타워",
            "jibun_addr": "서울특별시 동작구 노량진동 54-4 더써밋타워",
            "loc": {"mnnm": "0054", "slno": "0004"},
            "es_dong_nm": "동명칭없음",
            "es_ho_nm": "2313호",
        }
        self._history(
            _row(
                "20263230000I317505",
                "20260903142235",
                address="서울특별시 동작구 노량진동 54-4 더써밋타워 동명칭없음 2313호",
            )
        )

        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263230000I317505")

    async def test_accepts_echoed_cart_address_without_identifiers(self) -> None:
        """담기 때 보낸 locDetlAddr 가 그대로 돌아오면 건물명·지번 식별자 없이도 확정한다."""

        self._use_sambu(
            jibun_addr=None,
            loc={},
            _locDetlAddr="서울특별시 강남구 삼성동 99-13 삼부아파트 101 1001호",
        )
        self._history(
            _row(
                "20263230000I317506",
                "20260903142236",
                address="서울특별시 강남구 삼성동 99-13 삼부아파트 101  1001호",
            )
        )

        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263230000I317506")

    async def test_rejects_dong_token_hidden_in_parcel_number(self) -> None:
        """동 '1' 은 지번 본번 '종로1가 1' 이 아니라 건물 식별자 뒤 구간에서만 찾는다."""

        self.req = BuildingRegisterRequest(
            road_addr="서울특별시 종로구 종로 1",
            dong="1",
            ho="2001",
            register_kind="exclusive",
        )
        self.targets = {
            "bld_nm": "검색단지명",
            "jibun_addr": "서울특별시 종로구 종로1가 1 검색단지명",
            "loc": {"mnnm": "0001", "slno": ""},
            "es_dong_nm": "1",
            "es_ho_nm": "2001",
        }
        self._history(
            _row(
                "20261100000G209111",
                "20260903142237",
                address="서울특별시 종로구 종로1가 1 검색단지명 105동 2001",
            )
        )

        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

    async def test_echo_match_keeps_unit_boundaries(self) -> None:
        """echo 비교는 공백을 지우지 않는다 — '101 1001호' 와 '1011001호' 는 다른 세대다(Codex P2)."""

        self._use_sambu(
            _locDetlAddr="서울특별시 강남구 삼성동 99-13 삼부아파트 101 1001호",
        )
        collided = _row(
            "20263230000I317507",
            "20260903142238",
            address="서울특별시 강남구 삼성동 99-13 삼부아파트 1011001호",
        )
        mine = _row(
            "20263230000I317508",
            "20260903142237",
            address="서울특별시 강남구 삼성동 99-13 삼부아파트 101 1001호",
        )

        self._history(collided)
        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self._history(collided, mine)
        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263230000I317508")

    async def test_nonnumeric_unit_token_requires_boundary(self) -> None:
        """'OF-304-1' 은 'OF-304-10' 에 걸리지 않는다 — 비숫자 토큰도 영숫자·하이픈 경계(Codex P2)."""

        self._use_sambu(es_ho_nm="OF-304-1")
        longer = _row(
            "20263230000I317509",
            "20260903142240",
            address="서울특별시 강남구 삼성동 99-13 삼부아파트 101 OF-304-10",
        )
        mine = _row(
            "20263230000I317510",
            "20260903142239",
            address="서울특별시 강남구 삼성동 99-13 삼부아파트 101 OF-304-1",
        )

        self._history(longer)
        with self.assertRaisesRegex(FlowError, "신청한 발급 건"):
            await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self._history(longer, mine)
        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263230000I317510")

    async def test_short_building_name_inside_dong_token_does_not_hide_units(
        self,
    ) -> None:
        """건물명 'A' 가 동 'A동' 안에서 잡혀도 지번 식별자 뒤 구간에서 동→호를 찾는다(Codex P2)."""

        self._use_sambu(
            bld_nm="A",
            jibun_addr="서울특별시 강남구 삼성동 99-13 다른표기",
            es_dong_nm="A동",
        )
        self._history(
            _row(
                "20263230000I317511",
                "20260903142241",
                address="서울특별시 강남구 삼성동 99-13 다른표기 A동 1001호",
            )
        )

        result = await self.flow._find_recp_no(_Page(), self.req, self.targets, set())

        self.assertEqual(result["pbsvcRecpNo"], "20263230000I317511")

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
