"""HF 세그멘테이션 도구 실패 분류 테스트 — CMP-DIRECT.

httpx MockTransport 로 미배포/404/503-콜드스타트/타임아웃/연결오류/200/5xx/4xx 를
재현하고, segment_floorplan_impl 이 raise 없이 구조화 결과 + 안정적 error_code 로
매핑하는지 검증한다. LLM 미사용.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import httpx

from src.agent.tools.segmentation import (
    segment_floorplan_impl,
    segment_session_floorplan,
)
from src.services import main_flow, storage

from . import _main_flow_db_fake as db_fake

_IMG = "https://storage.example/floorplan.png"


def _settings(**override: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "hf_segmentation_endpoint_url": "https://hf.example/seg",
        "hf_segmentation_token": "tok",
        "hf_segmentation_timeout_seconds": 5,
        "hf_segmentation_cold_start_max_retries": 0,
        "hf_segmentation_allowed_image_hosts": [],
        # 실제 기본값과 일치(엣지 검증된 pending 도면 분석 허용).
        "agent_allow_unscanned_floorplans": True,
    }
    base.update(override)
    return SimpleNamespace(**base)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_unset_endpoint_is_unavailable() -> None:
    res = await segment_floorplan_impl(
        image_url=_IMG, settings=_settings(hf_segmentation_endpoint_url=None)
    )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_404_is_unavailable() -> None:
    async with _client(lambda req: httpx.Response(404)) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_503_cold_start_timeout_when_no_retries() -> None:
    async with _client(lambda req: httpx.Response(503)) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_COLD_START_TIMEOUT"


async def test_read_timeout_is_timeout() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=req)

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_TIMEOUT"


async def test_connect_error_is_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=req)

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_500_is_upstream_error() -> None:
    async with _client(lambda req: httpx.Response(500)) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_UPSTREAM_ERROR"


async def test_422_is_bad_request() -> None:
    async with _client(lambda req: httpx.Response(422)) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_BAD_REQUEST"


async def test_200_parses_instances() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instances": [
                    {"label": "wall_other", "count": 3, "mean_confidence": 0.8},
                    {"label": "wall_reinforced_concrete", "count": 1},
                    {"label": "bogus", "count": 9},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    labels = {i["label"]: i["count"] for i in res["instances"]}
    assert labels == {"wall_other": 3, "wall_reinforced_concrete": 1}
    assert "비내력벽 후보 3" in res["summary"]


async def test_200_non_json_is_bad_response() -> None:
    async with _client(lambda req: httpx.Response(200, content=b"not json")) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_BAD_RESPONSE"


async def test_request_error_is_upstream() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset", request=req)

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_UPSTREAM_ERROR"


async def test_200_drops_out_of_range_confidence() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instances": [
                    {"label": "door", "count": 1, "mean_confidence": 1.4},
                    {"label": "window", "count": 1, "mean_confidence": 0.5},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    by_label = {i["label"]: i for i in res["instances"]}
    assert "mean_confidence" not in by_label["door"]  # 1.4 는 드롭
    assert by_label["window"]["mean_confidence"] == 0.5


async def test_200_preserves_mask_asset_id() -> None:
    mask_id = "11111111-1111-1111-1111-111111111111"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"instances": [], "mask_asset_id": mask_id})

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    assert res["mask_asset_id"] == mask_id


async def test_200_drops_non_uuid_mask_asset_id() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"instances": [], "mask_asset_id": "storage/key/not-a-uuid"}
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    assert res["mask_asset_id"] is None


async def test_200_drops_invalid_counts() -> None:
    # 음수·bool count 는 계약(count>=0) 위반이라 드롭한다.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "instances": [
                    {"label": "door", "count": -1},
                    {"label": "window", "count": True},
                    {"label": "wall_other", "count": 2},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    labels = {i["label"]: i["count"] for i in res["instances"]}
    assert labels == {"wall_other": 2}


async def test_rejects_unsafe_or_disallowed_image_url() -> None:
    # http/사설/localhost/메타데이터는 SSRF 가드로 차단. allowlist 밖 호스트도 차단.
    def boom(req: httpx.Request) -> httpx.Response:  # 호출되면 안 됨
        raise AssertionError("URL 검증 전에 endpoint 를 호출하면 안 된다")

    cases = [
        "http://storage.example/floorplan.png",  # https 아님
        "https://localhost/floorplan.png",  # localhost
        "https://169.254.169.254/latest/meta-data",  # 메타데이터
        "https://10.0.0.5/floorplan.png",  # 사설 IP
    ]
    for url in cases:
        async with _client(boom) as client:
            res = await segment_floorplan_impl(
                image_url=url, settings=_settings(), client=client
            )
        assert res["ok"] is False
        assert res["error_code"] == "SEGMENTATION_BAD_REQUEST"

    # allowlist 가 설정되면 그 호스트만 통과.
    async with _client(boom) as client:
        res = await segment_floorplan_impl(
            image_url="https://evil.example/x.png",
            settings=_settings(hf_segmentation_allowed_image_hosts=["storage.example"]),
            client=client,
        )
    assert res["error_code"] == "SEGMENTATION_BAD_REQUEST"


async def _session_with_asset(
    monkeypatch, *, scan_status: str = "clean"
) -> tuple[uuid.UUID, uuid.UUID]:
    fake = db_fake.install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    asset = await main_flow.create_floorplan_asset(
        session_id=session["id"],
        owner_user_id=owner,
        payload={
            "bucket": "session-floorplans",
            "object_key": f"{owner}/{session['id']}/x.png",
            "content_type": "image/png",
            "byte_size": 10,
        },
    )
    # 업로드는 pending 으로 생성된다 — 스캔 결과를 테스트 의도대로 세팅한다.
    fake.floorplan_assets[asset["id"]]["scan_status"] = scan_status
    return session["id"], owner


async def test_session_floorplan_no_image(monkeypatch) -> None:
    # 도면 미업로드 세션 → 임의 URL 호출 없이 SEGMENTATION_NO_IMAGE 로 degrade.
    db_fake.install_main_flow_fake(monkeypatch)
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    res = await segment_session_floorplan(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        settings=_settings(),
    )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_NO_IMAGE"


async def test_session_floorplan_signs_and_segments(monkeypatch) -> None:
    # 세션 asset 을 서명한 URL 로 세그멘테이션. LLM 은 URL 을 못 고른다(세션 고정).
    session_id, owner = await _session_with_asset(monkeypatch)

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        assert bucket == "session-floorplans"
        return f"https://signed.example/{object_path}?token=x"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    def handler(req: httpx.Request) -> httpx.Response:
        assert str(req.url).startswith("https://hf.example/seg")
        return httpx.Response(
            200, json={"instances": [{"label": "wall_other", "count": 2}]}
        )

    async with _client(handler) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=client,
        )
    assert res["ok"] is True
    assert {i["label"]: i["count"] for i in res["instances"]} == {"wall_other": 2}


async def test_session_floorplan_sign_failure_degrades(monkeypatch) -> None:
    session_id, owner = await _session_with_asset(monkeypatch)

    async def fail_sign(settings, **_: object) -> None:
        return None

    monkeypatch.setattr(storage, "sign_object_url", fail_sign)
    res = await segment_session_floorplan(
        session_id=session_id,
        owner_user_id=owner,
        owner_is_anonymous=False,
        settings=_settings(),
    )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_session_floorplan_pending_blocked_when_scan_required(
    monkeypatch,
) -> None:
    # 운영자가 agent_allow_unscanned_floorplans=False 로 좁히면 pending 은 차단(NOT_SCANNED).
    # 서명/HF 호출도 하지 않는다.
    session_id, owner = await _session_with_asset(monkeypatch, scan_status="pending")

    def boom(req: httpx.Request) -> httpx.Response:
        raise AssertionError("스캔 요구 모드에서는 HF 를 호출하면 안 된다")

    async def fake_sign(settings, **_: object) -> str:
        raise AssertionError("스캔 요구 모드에서는 서명도 하지 않는다")

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)
    async with _client(boom) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(agent_allow_unscanned_floorplans=False),
            client=client,
        )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_NOT_SCANNED"


async def test_session_floorplan_pending_analyzed_by_default(monkeypatch) -> None:
    # 기본값(allow_unscanned=True): 엣지 검증된 pending 도면은 분석된다(#unblock-analysis).
    session_id, owner = await _session_with_asset(monkeypatch, scan_status="pending")

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"instances": []})

    async with _client(handler) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),  # 기본 True
            client=client,
        )
    assert res["ok"] is True


async def test_session_floorplan_infected_always_blocked(monkeypatch) -> None:
    # infected 는 allow_unscanned 여부와 무관하게 항상 차단(clean/not_required/pending 만 통과).
    session_id, owner = await _session_with_asset(monkeypatch, scan_status="infected")

    async def fake_sign(settings, **_: object) -> str:
        raise AssertionError("infected 는 서명/HF 호출 금지")

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)
    res = await segment_session_floorplan(
        session_id=session_id,
        owner_user_id=owner,
        owner_is_anonymous=False,
        settings=_settings(),
    )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_NOT_SCANNED"
