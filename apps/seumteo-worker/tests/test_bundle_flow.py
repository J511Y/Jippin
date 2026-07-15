"""통합 잡(_run_bundle_on_page) 오케스트레이션 — 카트 2건·단일 신청·종류별 접수 매칭.

발급/추출(_issue_and_extract)은 모킹하고, 그 앞 단계(공유 해석 → 카트 → 신청 → 접수
매칭)의 계약을 검증한다: C01 이 종류별로 2회, S01 은 두 건을 실은 1회, 격리는 상대
종류의 카트 행을 지우지 않고, 접수번호는 regstrKindCd 로 종류별 매칭된다.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.flow import FlowError, SeumteoFlow
from src.models import (
    BuildingRegisterBundleRequest,
    BuildingRegisterError,
    BuildingRegisterResult,
)

_ADDR = "대구광역시 달서구 유천동 488 유천동 포스코 더샵아파트"


class _Page:
    async def goto(self, _url: str, wait_until: str | None = None) -> None:
        return None

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


def _hist_row(receipt: str, kind: str, *, ho: str = "") -> dict:
    address = f"{_ADDR} 105동" + (f" {ho}" if ho else "")
    return {
        "mgmNo": f"mgm-{receipt}-{kind}",
        "locDetlAddr": address,
        "progStateCd": "91",
        "pbsvcRecpNo": receipt,
        "regstrKindCd": kind,
        "issueReadGbCd": "0",
        "bldrgstGbCd": "1",
        "firstCrtnDt": "20260714104427",
        "recpDate": "2026-07-14",
        "realProcessDateStr": "20260714",
    }


class _Router:
    """URL 별 응답 라우터 — 호출 순서·본문을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.s01_fail_first = False
        self.fail_heading_resolve = False
        self._s01_calls = 0
        self._r05_calls = 0
        self._hist_calls = 0

    def _ok(self, extra: dict | None = None) -> dict:
        return {"caisMessage": {"resultCode": "S00000"}, **(extra or {})}

    async def __call__(self, _page, url: str, body: object) -> dict:
        self.calls.append((url, body))
        if "bldrgstmst/_search" in url:
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "mgmUpperBldrgstPk": "MST1",
                                "roadAddr": "대구광역시 달서구 달서대로 67",
                                "jibunAddr": _ADDR,
                                "untClsfCd": "1020",
                            }
                        }
                    ]
                }
            }
        if "bldrgsttitle/_search" in url:
            return {
                "hits": {"hits": [{"_id": "TITLE1", "_source": {"dongNm": "105동"}}]}
            }
        if "bldrgstexpos/_search" in url:
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "EXPOS1",
                            "_source": {"hoNm": "2001", "recapTitlePk": "RECAP1"},
                        }
                    ]
                }
            }
        if url.endswith("/bci/BCIAAA02R04"):
            return self._ok(
                {
                    "findExposList": [
                        {
                            "totArea": 84.9,
                            "dongNm": "105동",
                            "sigunguCd": "27290",
                            "bjdongCd": "10900",
                            "platGbCd": "0",
                            "mnnm": "0488",
                            "slno": "",
                            "bldNm": "유천동 포스코 더샵아파트",
                        }
                    ]
                }
            )
        if url.endswith("/bci/BCIAAA02R01"):
            if self.fail_heading_resolve:
                return {
                    "caisMessage": {
                        "resultCode": "E99999",
                        "resultMessage": "표제부 조회 오류",
                    }
                }
            return self._ok(
                {
                    "jibunAddr": [
                        {
                            "dongNm": "105동",
                            "mainPrposNm": "공동주택",
                            "sigunguCd": "27290",
                            "bjdongCd": "10900",
                            "platGbCd": "0",
                            "mnnm": "0488",
                            "slno": "",
                            "bldNm": "유천동 포스코 더샵아파트",
                        }
                    ]
                }
            )
        if url.endswith("/bci/BCIAAA02R05"):
            self._r05_calls += 1
            if self._r05_calls == 1:  # 담기 전 preclean — 이전 잡 잔재 1건.
                return self._ok(
                    {"findPbsvcResveDtls": [{"pbsvcResveDtlsSeqno": "OLD1"}]}
                )
            return self._ok(
                {
                    "findPbsvcResveDtls": [
                        {
                            "pbsvcResveDtlsSeqno": "CART-EX",
                            "bldrgstSeqno": "EXPOS1",
                            "locDongNm": "105동",
                            "locHoNm": "2001",
                            "firstCrtnDt": "20260714104000",
                        },
                        {
                            "pbsvcResveDtlsSeqno": "CART-HEAD",
                            "bldrgstSeqno": "TITLE1",
                            "locDongNm": "105동",
                            "locHoNm": "",
                            "firstCrtnDt": "20260714104001",
                        },
                        {
                            "pbsvcResveDtlsSeqno": "LEFTOVER",
                            "bldrgstSeqno": "OTHER",
                            "firstCrtnDt": "20260713000000",
                        },
                    ]
                }
            )
        if url.endswith("/bci/BCIAAA02D01"):
            return self._ok()
        if url.endswith("/bci/BCIAAA02C01"):
            return self._ok()
        if url.endswith("/awp/AWPACC01R03"):
            return {"resultData": {"results": [{"bizno": "123", "nm": "집핀"}]}}
        if url.endswith("/bci/BCIAZA02S01"):
            self._s01_calls += 1
            if self.s01_fail_first and self._s01_calls == 1:
                return {"caisMessage": {"resultCode": "E99999", "resultMessage": "오류"}}
            return self._ok({"pbsvcRecpNo": "SUBMIT-CAND"})
        if url.endswith("/bci/BCIAAA02D02"):
            return self._ok()
        if url.endswith("/bci/BCIAAA06R01"):
            self._hist_calls += 1
            if self._hist_calls == 1:  # 신청 전 스냅샷 — 새 행 없음.
                return self._ok({"IssueReadHistList": []})
            return self._ok(
                {
                    "IssueReadHistList": [
                        _hist_row("20263230000G100001", "4", ho="2001"),
                        _hist_row("20263230000G100002", "3"),
                    ]
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    def urls(self, suffix: str) -> list[tuple[str, object]]:
        return [(u, b) for (u, b) in self.calls if suffix in u]


def _make_flow(router: _Router) -> SeumteoFlow:
    flow = object.__new__(SeumteoFlow)
    flow._s = SimpleNamespace(
        eais_base_url="https://www.eais.go.kr",
        eais_search_base_url="https://search.eais.go.kr",
        seumteo_max_concurrency=1,
        seumteo_bundle_single_submit=True,
        bundle_deadline_ms=180_000,
        report_render_timeout_ms=45_000,
    )
    flow._appnt = None
    # AsyncMock(side_effect=인스턴스) 는 async __call__ 을 감지하지 못해 코루틴을
    # 반환값으로 이중 래핑한다 — 라우터를 직접 할당한다(_post 는 인스턴스 속성 호출).
    flow._post = router
    flow._get = AsyncMock(
        return_value={
            "ds_SessionRep": {
                "membNo": "M1",
                "membGbCd": "06",
                "sessionUserNm": "집핀",
            }
        }
    )
    return flow


def _result(kind: str) -> BuildingRegisterResult:
    return BuildingRegisterResult(register_kind=kind)


class BundleFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.router = _Router()
        self.flow = _make_flow(self.router)
        self.req = BuildingRegisterBundleRequest(
            road_addr="대구광역시 달서구 달서대로 67",
            dong="105동",
            ho="2001호",
            jibun_addr=_ADDR,
        )

    async def test_single_submit_carries_both_items(self) -> None:
        extract_calls: list[tuple[str, str]] = []

        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            extract_calls.append((req.register_kind, recp["pbsvcRecpNo"]))
            return _result(req.register_kind)

        self.flow._issue_and_extract = _fake_extract

        res = await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

        # C01 두 번 — 종류코드/PK 가 각각 전유(4/EXPOS1)·표제(3/TITLE1).
        c01 = self.router.urls("/bci/BCIAAA02C01")
        self.assertEqual(len(c01), 2)
        kinds = {(b["regstrKindCd"], b["bldrgstSeqno"]) for (_, b) in c01}
        self.assertEqual(kinds, {("4", "EXPOS1"), ("3", "TITLE1")})

        # S01 한 번 — 두 건 + 건수 2. D02 도 두 건 리스트.
        s01 = self.router.urls("/bci/BCIAZA02S01")
        self.assertEqual(len(s01), 1)
        body = s01[0][1]
        self.assertEqual(len(body["pbsvcResveDtls"]), 2)
        self.assertEqual(body["pbsvcRecpInfo"]["pbsvcResveDtlsCnt"], 2)
        d02 = self.router.urls("/bci/BCIAAA02D02")
        self.assertEqual(len(d02), 1)
        self.assertEqual(len(d02[0][1]), 2)

        # 격리 — 상대 종류 행은 삭제하지 않고 잔재(OLD1 preclean, LEFTOVER)만 D01.
        d01_seqs = {b["pbsvcResveDtlsSeqno"] for (_, b) in self.router.urls("D01")}
        self.assertEqual(d01_seqs, {"OLD1", "LEFTOVER"})

        # 접수 매칭 — 종류별 접수번호로 전유부 먼저 발급·추출.
        self.assertEqual(
            extract_calls,
            [
                ("exclusive", "20263230000G100001"),
                ("heading", "20263230000G100002"),
            ],
        )
        self.assertTrue(res.exclusive.ok)
        self.assertTrue(res.heading.ok)

    async def test_falls_back_to_sequential_submit_on_s01_error(self) -> None:
        self.router.s01_fail_first = True

        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            return _result(req.register_kind)

        self.flow._issue_and_extract = _fake_extract

        res = await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

        # 실패한 2건 S01 + 폴백 단건 S01 ×2 = 총 3회. D02 는 성공한 신청 뒤 2회.
        self.assertEqual(len(self.router.urls("/bci/BCIAZA02S01")), 3)
        self.assertEqual(len(self.router.urls("/bci/BCIAAA02D02")), 2)
        self.assertTrue(res.exclusive.ok)
        self.assertTrue(res.heading.ok)

    async def test_heading_failure_keeps_exclusive_result(self) -> None:
        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            if req.register_kind == "heading":
                raise FlowError("upstream", "표제부 리포트 실패")
            return _result(req.register_kind)

        self.flow._issue_and_extract = _fake_extract

        res = await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

        self.assertTrue(res.exclusive.ok)
        self.assertIsInstance(res.heading, BuildingRegisterError)
        self.assertEqual(res.heading.category, "upstream")

    async def test_exclusive_failure_propagates(self) -> None:
        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            raise FlowError("upstream", "전유부 리포트 실패")

        self.flow._issue_and_extract = _fake_extract

        with self.assertRaisesRegex(FlowError, "전유부 리포트 실패"):
            await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

    async def test_resolve_not_found_propagates_with_field(self) -> None:
        async def _empty_mst(_page, url, body):
            if "bldrgstmst/_search" in url:
                return {"hits": {"hits": []}}
            raise AssertionError(f"unexpected url after empty mst: {url}")

        self.flow._post = _empty_mst

        with self.assertRaisesRegex(FlowError, "찾지 못했"):
            await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

    async def test_heading_resolve_failure_keeps_exclusive_result(self) -> None:
        """표제부 해석(R01) 실패는 best-effort — 전유부만으로 단건 신청해 완주한다."""

        self.router.fail_heading_resolve = True
        extract_calls: list[str] = []

        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            extract_calls.append(req.register_kind)
            return _result(req.register_kind)

        self.flow._issue_and_extract = _fake_extract

        res = await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

        self.assertTrue(res.exclusive.ok)
        self.assertIsInstance(res.heading, BuildingRegisterError)
        # R01 cais 오류("...조회 오류")는 _check_cais 가 not_found 로 분류한다 —
        # 봉투는 원래 FlowError category 를 보존한다(호출측 caution 흡수는 동일).
        self.assertEqual(res.heading.category, "not_found")
        self.assertEqual(extract_calls, ["exclusive"])
        # 표제부가 빠졌으니 담기(C01)·신청(S01)도 전유부 1건만.
        self.assertEqual(len(self.router.urls("/bci/BCIAAA02C01")), 1)
        s01 = self.router.urls("/bci/BCIAZA02S01")
        self.assertEqual(len(s01), 1)
        self.assertEqual(s01[0][1]["pbsvcRecpInfo"]["pbsvcResveDtlsCnt"], 1)

    async def test_heading_extract_timeout_keeps_exclusive_result(self) -> None:
        """표제부 추출이 멈춰도 남은 예산 타임박스로 끊고 전유부 결과를 보존한다."""

        loop = asyncio.get_running_loop()
        # 표제부 몫 예산이 ~0.05s 만 남도록 데드라인을 당긴다(반환 예약 4s 제외).
        overall_deadline = loop.time() + (4000 / 1000) + 0.05

        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            if req.register_kind == "heading":
                await asyncio.sleep(5)  # 타임박스(0.05s)보다 훨씬 길게 — 중단돼야 한다.
            return _result(req.register_kind)

        self.flow._issue_and_extract = _fake_extract

        res = await self.flow._run_bundle_on_page(_Page(), self.req, overall_deadline)

        self.assertTrue(res.exclusive.ok)
        self.assertIsInstance(res.heading, BuildingRegisterError)
        self.assertIn("시간 내", res.heading.message)

    async def test_shared_receipt_number_matches_both_kinds(self) -> None:
        # 통합 신청이 하나의 pbsvcRecpNo 를 두 행에 공유해도 종류별 매칭이 성립해야 한다.
        original = self.router.__call__

        async def _shared_recp(_page, url, body):
            if url.endswith("/bci/BCIAAA06R01"):
                self.router._hist_calls += 1
                if self.router._hist_calls == 1:
                    return {
                        "caisMessage": {"resultCode": "S00000"},
                        "IssueReadHistList": [],
                    }
                return {
                    "caisMessage": {"resultCode": "S00000"},
                    "IssueReadHistList": [
                        _hist_row("20263230000G200001", "4", ho="2001"),
                        _hist_row("20263230000G200001", "3"),
                    ],
                }
            return await original(_page, url, body)

        self.flow._post = _shared_recp
        extract_calls: list[tuple[str, str, str]] = []

        async def _fake_extract(page, req, t, recp, *, pdf_deadline=None):
            extract_calls.append(
                (req.register_kind, recp["pbsvcRecpNo"], recp["mgmNo"])
            )
            return _result(req.register_kind)

        self.flow._issue_and_extract = _fake_extract

        res = await self.flow._run_bundle_on_page(
            _Page(), self.req, asyncio.get_running_loop().time() + 60.0
        )

        self.assertTrue(res.exclusive.ok)
        self.assertTrue(res.heading.ok)
        # 같은 접수번호라도 mgmNo(행 식별자)는 종류별로 달라 리포트가 구분된다.
        self.assertEqual(len(extract_calls), 2)
        self.assertNotEqual(extract_calls[0][2], extract_calls[1][2])


if __name__ == "__main__":
    unittest.main()
