"""주소 → 총괄PK·표제부PK 해석(_find_building) — 지번 우선 검색(#jibun-first).

세움터 ES 숫자 토큰은 부분일치라('897' 질의가 '89-7' 필지를 1위로 올린다) 점수 1위를 믿지
않고 필지·도로명 **정확 일치** 후보만 쓰는지, 같은 필지에 레코드가 여럿이면 동이 맞는 쪽을
고르는지, 지번이 없거나 빗나가면 도로명 검색으로 폴백하는지를 검증한다.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.flow import (
    FlowError,
    SeumteoFlow,
    _jibun_parcel_prefix,
    _parcel_key,
    _road_key,
)
from src.models import BuildingRegisterRequest

_SEARCH = "https://search.eais.go.kr"


def _mst(pk: str, jibun: str | None, road: str | None) -> dict:
    return {
        "_id": pk,
        "_source": {
            "mgmUpperBldrgstPk": pk,
            "jibunAddr": jibun,
            "roadAddr": road,
            "untClsfCd": "1020",
        },
    }


class _EsRouter:
    """bldrgstmst/bldrgsttitle 만 응답하는 가짜 ES — 질의 필드별 결과와 PK별 동 목록을 준다."""

    def __init__(
        self,
        *,
        jibun_hits: list[dict] | None = None,
        road_hits: list[dict] | None = None,
        titles: dict[str, list[str]] | None = None,
    ) -> None:
        self.jibun_hits = jibun_hits or []
        self.road_hits = road_hits or []
        self.titles = titles or {}
        self.mst_queries: list[tuple[str, list[str]]] = []
        self.title_pks: list[str] = []

    async def __call__(self, _page, url: str, body: dict) -> dict:
        if url.endswith("/bldrgstmst/_search"):
            mm = body["query"]["multi_match"]
            self.mst_queries.append((mm["query"], mm["fields"]))
            hits = self.jibun_hits if mm["fields"] == ["jibunAddr"] else self.road_hits
            return {"hits": {"hits": hits}}
        if url.endswith("/bldrgsttitle/_search"):
            pk = body["query"]["bool"]["filter"][0]["term"]["mgmUpperBldrgstPk"]
            self.title_pks.append(pk)
            dongs = self.titles.get(pk, [])
            return {
                "hits": {
                    "hits": [
                        {"_id": f"{pk}-T{i}", "_source": {"dongNm": d}}
                        for i, d in enumerate(dongs)
                    ]
                }
            }
        raise AssertionError(f"unexpected url: {url}")


def _flow(router: _EsRouter) -> SeumteoFlow:
    flow = object.__new__(SeumteoFlow)
    flow._s = SimpleNamespace(
        eais_base_url="https://www.eais.go.kr", eais_search_base_url=_SEARCH
    )
    flow._post = router
    return flow


def _req(
    *, road: str, jibun: str | None, dong: str = "104동", ho: str = "504호"
) -> BuildingRegisterRequest:
    return BuildingRegisterRequest(
        road_addr=road, jibun_addr=jibun, dong=dong, ho=ho, register_kind="exclusive"
    )


_ROAD = "서울특별시 영등포구 여의대방로43나길 25"
_ROAD_ES = "서울특별시 영등포구 여의대방로43나길 25(신길동,삼환아파트)"
_JIBUN = "서울특별시 영등포구 신길동 897-1 삼환아파트"


class ParcelHelpersTest(unittest.TestCase):
    def test_parcel_prefix_drops_building_name(self) -> None:
        self.assertEqual(
            _jibun_parcel_prefix(_JIBUN), "서울특별시 영등포구 신길동 897-1"
        )

    def test_parcel_prefix_keeps_san_and_strips_beonji(self) -> None:
        self.assertEqual(
            _jibun_parcel_prefix("서울특별시 종로구 사직동 산 1-1"),
            "서울특별시 종로구 사직동 산 1-1",
        )
        self.assertEqual(
            _jibun_parcel_prefix("경기도 용인시 기흥구 중동 1105번지 (어떤빌딩)"),
            "경기도 용인시 기흥구 중동 1105",
        )
        self.assertEqual(_parcel_key("… 사직동 산 1-1"), _parcel_key("… 사직동 산1-1"))

    def test_parcel_prefix_ignores_digits_inside_dong_name(self) -> None:
        # '종로1가'·'효자동3가' 는 번지가 아니다 — 그 뒤 독립 번지 토큰까지 잘라야 한다.
        self.assertEqual(
            _jibun_parcel_prefix("서울특별시 종로구 종로1가 1 교보빌딩"),
            "서울특별시 종로구 종로1가 1",
        )

    def test_parcel_prefix_empty_without_parcel_number(self) -> None:
        self.assertEqual(_jibun_parcel_prefix("강원특별자치도 춘천시 퇴계동"), "")
        self.assertEqual(_jibun_parcel_prefix(None), "")

    def test_road_key_drops_reference_suffix(self) -> None:
        self.assertEqual(_road_key(_ROAD_ES), _road_key(_ROAD))


class FindBuildingTest(unittest.IsolatedAsyncioTestCase):
    async def test_jibun_first_picks_exact_parcel_not_top_score(self) -> None:
        # ES 는 '897-1' 질의에도 부분일치로 '89-7' 을 1위에 올릴 수 있다 — 정확 필지만 채택.
        router = _EsRouter(
            jibun_hits=[
                _mst("WRONG", "서울특별시 영등포구 신길동 89-7", None),
                _mst("RIGHT", _JIBUN, _ROAD_ES),
            ],
            titles={"WRONG": ["104동"], "RIGHT": ["104동"]},
        )
        src, title_pk, _ = await _flow(router)._find_building(
            None, _req(road=_ROAD, jibun=_JIBUN)
        )

        self.assertEqual(src["mgmUpperBldrgstPk"], "RIGHT")
        self.assertEqual(title_pk, "RIGHT-T0")
        # 지번 검색은 건물명을 뗀 필지까지만, jibunAddr 필드만으로 — 도로명 검색은 하지 않는다.
        self.assertEqual(
            router.mst_queries, [("서울특별시 영등포구 신길동 897-1", ["jibunAddr"])]
        )
        self.assertEqual(router.title_pks, ["RIGHT"])

    async def test_same_parcel_records_pick_the_one_with_matching_dong(self) -> None:
        # 같은 필지에 동 목록이 없는 필지 단위 레코드와 단지 레코드가 공존(실측: 개포동 12).
        router = _EsRouter(
            jibun_hits=[
                _mst("PARCEL", "서울특별시 영등포구 신길동 897-1 삼환아파트", _ROAD_ES),
                _mst("COMPLEX", _JIBUN, _ROAD_ES),
            ],
            titles={"PARCEL": [], "COMPLEX": ["103동", "104동"]},
        )
        src, title_pk, _ = await _flow(router)._find_building(
            None, _req(road=_ROAD, jibun=_JIBUN)
        )

        self.assertEqual(src["mgmUpperBldrgstPk"], "COMPLEX")
        self.assertEqual(title_pk, "COMPLEX-T1")

    async def test_multiple_dong_matches_prefer_same_road(self) -> None:
        router = _EsRouter(
            jibun_hits=[
                _mst(
                    "OTHER", _JIBUN, "서울특별시 영등포구 여의대방로43나길 27(신길동)"
                ),
                _mst("MINE", _JIBUN, _ROAD_ES),
            ],
            titles={"OTHER": ["104동"], "MINE": ["104동"]},
        )
        src, _, _ = await _flow(router)._find_building(
            None, _req(road=_ROAD, jibun=_JIBUN)
        )

        self.assertEqual(src["mgmUpperBldrgstPk"], "MINE")

    async def test_falls_back_to_road_when_jibun_has_no_exact_parcel(self) -> None:
        router = _EsRouter(
            jibun_hits=[_mst("NEAR", "서울특별시 영등포구 신길동 897-10", None)],
            road_hits=[_mst("ROAD", _JIBUN, _ROAD_ES)],
            titles={"ROAD": ["104동"]},
        )
        src, _, _ = await _flow(router)._find_building(
            None, _req(road=_ROAD, jibun=_JIBUN)
        )

        self.assertEqual(src["mgmUpperBldrgstPk"], "ROAD")
        self.assertEqual(
            [fields for _, fields in router.mst_queries],
            [["jibunAddr"], ["jibunAddr", "roadAddr^3"]],
        )
        self.assertNotIn("NEAR", router.title_pks)

    async def test_without_jibun_road_exact_match_beats_top_score(self) -> None:
        router = _EsRouter(
            road_hits=[
                _mst(
                    "TOP",
                    "서울특별시 영등포구 신길동 1 다른아파트",
                    "서울특별시 영등포구 여의대방로43나길 251(신길동)",
                ),
                _mst("EXACT", _JIBUN, _ROAD_ES),
            ],
            titles={"TOP": ["104동"], "EXACT": ["104동"]},
        )
        src, _, _ = await _flow(router)._find_building(
            None, _req(road=_ROAD, jibun=None)
        )

        self.assertEqual(src["mgmUpperBldrgstPk"], "EXACT")
        self.assertEqual(router.mst_queries, [(_ROAD, ["jibunAddr", "roadAddr^3"])])

    async def test_inexact_road_fallback_tries_only_the_top_hit(self) -> None:
        # 정확 일치가 없을 때 2위 이하까지 동 매칭으로 넓히면, 같은 '104동'을 가진 남의 단지를
        # 발급할 수 있다 — 종전처럼 1위만 본다.
        router = _EsRouter(
            road_hits=[
                _mst(
                    "TOP",
                    "서울특별시 영등포구 신길동 2",
                    "서울특별시 영등포구 다른로 1",
                ),
                _mst(
                    "SECOND",
                    "서울특별시 영등포구 신길동 3",
                    "서울특별시 영등포구 다른로 2",
                ),
            ],
            # 동이 하나뿐이면 _match_dong 이 그 동을 쓰므로, 1위는 동이 둘인 단지로 둔다.
            titles={"TOP": ["101동", "102동"], "SECOND": ["104동"]},
        )
        with self.assertRaisesRegex(FlowError, "동을 찾지 못했"):
            await _flow(router)._find_building(None, _req(road=_ROAD, jibun=None))
        self.assertEqual(router.title_pks, ["TOP"])

    async def test_no_hits_is_not_found(self) -> None:
        router = _EsRouter()
        with self.assertRaisesRegex(FlowError, "건축물대장을 찾지 못했"):
            await _flow(router)._find_building(None, _req(road=_ROAD, jibun=_JIBUN))


if __name__ == "__main__":
    unittest.main()
