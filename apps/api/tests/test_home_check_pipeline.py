"""우리집 체크 파이프라인 회귀 — 세움터 워커 출력 → 클라이언트 매핑 → 판정/요약.

세움터 워커가 내보내는 결과(dict)를 SeumteoBuildingRegisterClient 의 매퍼로 CODEF 결과
dataclass 로 바꾼 뒤, home_check 의 판정(_judge)·요약(_summarize_*)이 올바른 신호등을 내는지
검증한다. 세움터 실주소 6종 정찰(삼환/기흥더샵/노원·송파 빌라/해운대 오피스텔/대구)로 확인한
출력 형태를 반영한다 — 특히 현 워커는 owned 에 면적만 채우므로 구조/용도/층은 비고, 그래도
신호(정상/주의/위반)는 정확해야 한다.
"""

from __future__ import annotations

from src.services.codef.types import BuildingHeadingResult, ExclusivePartResult
from src.services.home_check import (
    _exclusive_core_missing,
    _judge,
    _merge_change_history,
    _summarize_exclusive,
    _summarize_heading,
)
from src.services.seumteo.client import _to_exclusive, _to_heading

# 기흥더샵 102동 901호(실측 형태) — 현 워커 owned=면적만.
_EXCL_NORMAL = {
    "ok": True,
    "register_kind": "exclusive",
    "comm_unique_no": "11161100306459",
    "road_addr": "경기도 용인시 기흥구 구갈로 71-18",
    "addr_dong": "102동",
    "addr_ho": "901호",
    "violation_status": None,
    "owned": [{"resType": "0", "resArea": "116.384"}],
    "change_list": [],
    "price_list": [],
    "original_pdf_base64": "JVBERi0x",
}
_HEAD_NORMAL = {
    "ok": True,
    "register_kind": "heading",
    "comm_unique_no": "11161100306460",
    "violation_status": None,
    "detail_list": [{"resType": "주용도", "resContents": "공동주택(아파트)"}],
    "change_list": [],
    "building_status_list": [],
    "original_pdf_base64": "JVBERi0x",
}


def _judge_result(worker_excl: dict, worker_head: dict | None):
    excl = _to_exclusive(worker_excl)
    head = _to_heading(worker_head) if worker_head is not None else None
    ev, hv, viol, signal, caution = _judge(excl, head)
    return excl, head, signal, viol, caution


def test_mapping_produces_codef_dataclasses():
    excl = _to_exclusive(_EXCL_NORMAL)
    head = _to_heading(_HEAD_NORMAL)
    assert isinstance(excl, ExclusivePartResult)
    assert isinstance(head, BuildingHeadingResult)
    assert excl.violation_status is None
    assert excl.owned == [{"resType": "0", "resArea": "116.384"}]
    assert head.detail_list[0]["resContents"] == "공동주택(아파트)"


def test_normal_signal():
    _e, _h, signal, viol, caution = _judge_result(_EXCL_NORMAL, _HEAD_NORMAL)
    assert signal == "normal"
    assert viol is False
    assert caution == []


def test_exclusive_violation_signal():
    excl = {**_EXCL_NORMAL, "violation_status": "위반건축물"}
    _e, _h, signal, viol, _c = _judge_result(excl, _HEAD_NORMAL)
    assert signal == "violation"
    assert viol is True


def test_heading_violation_signal():
    # 표제부(건물 전체) 위반표시 — 전유부는 정상이어도 종합 위반.
    head = {**_HEAD_NORMAL, "violation_status": "위반건축물"}
    _e, _h, signal, viol, _c = _judge_result(_EXCL_NORMAL, head)
    assert signal == "violation"
    assert viol is True


def test_heading_missing_is_caution():
    _e, _h, signal, viol, caution = _judge_result(_EXCL_NORMAL, None)
    assert signal == "caution"
    assert viol is False
    assert any("표제부" in c for c in caution)


def test_exclusive_core_missing_is_caution():
    excl = {**_EXCL_NORMAL, "owned": []}
    e, _h, signal, _v, caution = _judge_result(excl, _HEAD_NORMAL)
    assert signal == "caution"
    assert _exclusive_core_missing(e) is True
    assert any("전유부" in c for c in caution)


def test_summary_sparse_but_area_present():
    # 현 워커 형태: 면적만 있고 구조/용도/층은 None(리포트/무료API 미보강 시). 신호는 정상.
    excl = _to_exclusive(_EXCL_NORMAL)
    summary = _summarize_exclusive(excl)
    assert summary.area_m2 == 116.384
    assert summary.use_type is None
    assert summary.structure is None
    assert summary.floor is None
    # 면적이 있으므로 core_missing 아님 → 정상 신호 유지.
    assert _exclusive_core_missing(excl) is False


def test_summary_rich_when_report_parsed():
    # CLIP 텍스트 파싱(또는 무료 API)이 구조/용도/층·변동을 채운 경우.
    excl = _to_exclusive(
        {
            **_EXCL_NORMAL,
            "owned": [
                {
                    "resType": "0",
                    "resArea": "116.384",
                    "resUseType": "공동주택",
                    "resStructure": "철근콘크리트구조",
                    "resFloor": "9층",
                }
            ],
            "change_list": [
                {"resChangeDate": "2015.03.02", "resChangeReason": "신규작성(신축)"}
            ],
        }
    )
    head = _to_heading(
        {
            **_HEAD_NORMAL,
            "detail_list": [
                {"resType": "주용도", "resContents": "공동주택(아파트)"},
                {"resType": "층수", "resContents": "지하2층/지상20층"},
                {"resType": "사용승인일", "resContents": "2015-03-02"},
            ],
        }
    )
    es = _summarize_exclusive(excl)
    assert (es.use_type, es.structure, es.floor) == (
        "공동주택",
        "철근콘크리트구조",
        "9층",
    )
    hs = _summarize_heading(head)
    assert hs.main_use == "공동주택(아파트)"
    assert hs.floors == "지하2층/지상20층"
    assert hs.approval_date == "2015-03-02"
    changes = _merge_change_history(excl, head)
    assert changes[0].reason == "신규작성(신축)"
    assert changes[0].source == "exclusive"


def test_present_change_history_cleans_legacy_garbage():
    # 세션 903c0c36 실측: 구 워커(CLIP 창 채굴)가 저장한 change_list 그대로.
    # 읽기 시점 정화가 절단 중복을 붕괴하고 필러/라벨 행을 걷어내야 한다(DB 원본 불변).
    from src.services.home_check import _present_change_history

    stored = [
        {
            "date": None,
            "reason": "9.이전고시되어신규작성(신축)표 이하여백-,-이하여백-,",
            "source": "exclusive",
        },
        {
            "date": None,
            "reason": ".이전고시되어신규작성(신축)표 이하여백-,-이하여백-,",
            "source": "exclusive",
        },
        {
            "date": "2011.5.20",
            "reason": "9.이전고시되어신규작성(신축) 발코니확장(",
            "source": "heading",
        },
        {
            "date": "2011.5.20",
            "reason": ".이전고시되어신규작성(신축) 발코니확장(재건축과-",
            "source": "heading",
        },
        {
            "date": "2011.5.2",
            "reason": "판및자동화재감지기설치【행위허가】표",
            "source": "heading",
        },
        {
            "date": None,
            "reason": "사용승인일,사용승인일, 사용승인일 ,,",
            "source": "heading",
        },
        {
            "date": None,
            "reason": "사용승인일,사용승인일, 사용승인일 ,, 0,",
            "source": "heading",
        },
        {"date": None, "reason": ", 사용승인일 ,,", "source": "heading"},
    ]

    cleaned = _present_change_history(stored)

    reasons = [e["reason"] for e in cleaned]
    # 필러(이하여백)·라벨(사용승인일) 행 제거 + 절단 중복 붕괴 → 8행이 3행으로.
    assert len(cleaned) == 3
    assert all("이하여백" not in r and "사용승인일" not in r for r in reasons)
    # 절단본 쌍은 더 긴 사유로 붕괴되고, 절단 잔재(후행 '-')는 정리된다.
    assert "이전고시되어신규작성(신축) 발코니확장(재건축과" in reasons
    assert "이전고시되어신규작성(신축)표" in reasons


def test_present_change_history_keeps_clean_rows_intact():
    # 새 워커(PDF 파싱) 출력 형태는 그대로 통과한다.
    from src.services.home_check import _present_change_history

    stored = [
        {
            "date": "2026-05-21",
            "reason": "공동주택과-14300호(2026.05.21.)에 의거 403호거실과 발코니 사이 비내력벽 철거(창호포함) 및 발코니 확장(6.84㎡) 【행위허가】",
            "source": "heading",
        },
        {
            "date": "2011-05-20",
            "reason": "주택재건축과-10582(2011.5.13)호 의거 2011.3.9. 이전고시되어 신규작성(신축)",
            "source": "exclusive",
        },
    ]

    assert _present_change_history(stored) == stored
