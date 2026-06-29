"""HF 세그멘테이션 도구 실패 분류 테스트 — CMP-DIRECT.

httpx MockTransport 로 미배포/404/503-콜드스타트/타임아웃/연결오류/200/5xx/4xx 를
재현하고, segment_floorplan_impl 이 raise 없이 구조화 결과 + 안정적 error_code 로
매핑하는지 검증한다. LLM 미사용.
"""

from __future__ import annotations

import json
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
        "hf_segmentation_cold_start_poll_seconds": 10,
        "hf_segmentation_threshold": 0.5,
        "hf_segmentation_mask_threshold": 0.5,
        "hf_segmentation_max_inference_side": 1536,
        "hf_segmentation_allowed_image_hosts": [],
        # VLM(AI-002) — 테스트에선 interpret 를 모킹하므로 기본 비활성으로 둔다.
        "vlm_floorplan_enabled": False,
        "vlm_floorplan_timeout_seconds": 60,
        "agent_model": "openai:gpt-5.4-mini",
        "openai_api_key": None,
        "app_env": "test",
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


async def test_200_aggregates_predictions() -> None:
    # 모델 카드 응답: per-region predictions[]. 라벨별 count(=region 수) + score 평균으로 집계.
    def handler(req: httpx.Request) -> httpx.Response:
        # 요청 본문이 모델 계약(inputs + parameters)인지 함께 확인한다.
        body = json.loads(req.content)
        assert body["inputs"] == _IMG
        assert body["parameters"]["max_inference_side"] == 1536
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"class_name": "wall_other", "score": 0.9},
                    {"class_name": "wall_other", "score": 0.7},
                    {"class_name": "wall_other", "score": 0.8},
                    {"class_name": "wall_reinforced_concrete", "score": 0.6},
                    {"class_name": "bogus", "score": 0.99},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    by_label = {i["label"]: i for i in res["instances"]}
    assert by_label["wall_other"]["count"] == 3
    assert by_label["wall_other"]["mean_confidence"] == 0.8  # (0.9+0.7+0.8)/3
    assert by_label["wall_reinforced_concrete"]["count"] == 1
    assert "bogus" not in by_label  # 18 클래스 밖은 드롭
    assert "비내력벽 후보 3" in res["summary"]


async def test_200_missing_predictions_is_bad_response() -> None:
    # predictions 키가 없으면(포맷 불일치) ok=false 로 degrade.
    async with _client(lambda req: httpx.Response(200, json={"foo": 1})) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["error_code"] == "SEGMENTATION_BAD_RESPONSE"


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
    # score 가 [0,1] 밖인 region 은 평균에서 제외(count 엔 포함). door 는 유일 region 의
    # score 가 범위 밖 → mean_confidence 없음. window 는 0.5 반영.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"class_name": "door", "score": 1.4},
                    {"class_name": "window", "score": 0.5},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    by_label = {i["label"]: i for i in res["instances"]}
    assert by_label["door"]["count"] == 1
    assert "mean_confidence" not in by_label["door"]  # 1.4 는 평균서 드롭
    assert by_label["window"]["mean_confidence"] == 0.5


async def test_200_preserves_mask_asset_id() -> None:
    # 모델은 보통 mask_asset_id 를 안 주지만, 핸들러가 향후 UUID 를 주면 방어적으로 보존.
    mask_id = "11111111-1111-1111-1111-111111111111"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"predictions": [], "mask_asset_id": mask_id})

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    assert res["mask_asset_id"] == mask_id


async def test_200_drops_non_uuid_mask_asset_id() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"predictions": [], "mask_asset_id": "storage/key/not-a-uuid"}
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    assert res["mask_asset_id"] is None


async def test_200_skips_malformed_regions() -> None:
    # dict 아닌 항목·class_name 누락 region 은 건너뛰고 정상 region 만 집계한다.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    "not-a-dict",
                    {"score": 0.9},  # class_name 없음
                    {"class_name": "wall_other", "score": 0.5},
                    {"class_name": "wall_other"},  # score 없음 → count 만
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    by_label = {i["label"]: i for i in res["instances"]}
    assert by_label["wall_other"]["count"] == 2
    assert by_label["wall_other"]["mean_confidence"] == 0.5  # score 있는 1건 평균


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
            200,
            json={
                "predictions": [
                    {"class_name": "wall_other", "score": 0.8},
                    {"class_name": "wall_other", "score": 0.6},
                ]
            },
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


async def test_session_floorplan_emits_overlay_and_persists_objects(
    monkeypatch,
) -> None:
    # 폴리곤 있는 predictions → 오버레이 카드 방출 + 판단스키마(wall/space objects) 누적 +
    # LLM 반환분에서 좌표 제거(컨텍스트 leanness).
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_other",
                        "score": 0.9,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                        "requires_hitl": True,
                    },
                    {
                        "region_id": "pred:2",
                        "class_name": "wall_reinforced_concrete",
                        "score": 0.8,
                        "polygon": [20, 20, 30, 20, 30, 30],
                    },
                    {
                        "region_id": "pred:3",
                        "class_name": "space_living_room",
                        "score": 0.95,
                        "polygon": [40, 40, 60, 40, 60, 60, 40, 60],
                    },
                    {
                        "region_id": "pred:4",
                        "class_name": "door",
                        "score": 0.7,
                        "polygon": [1, 1, 2, 1, 2, 2],
                    },
                ],
            },
        )

    ctx = RunContext()
    async with _client(handler) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=client,
            run_context=ctx,
            run_id=run["id"],
        )
    # LLM 반환분: 원시 분석값(좌표·regions·image·instances) 전부 제거 + 오버레이 플래그만.
    assert res["ok"] is True
    assert res["overlay_emitted"] is True
    assert "regions" not in res
    assert "image" not in res
    assert "instances" not in res
    assert res["region_count"] == 4  # 4개 모두 polygon 유효(door 포함)

    # 오버레이 카드(FloorplanOverlay)가 방출됐다.
    ui, _snapshot = ctx.drain_ui()
    assert "FloorplanOverlay" in json.dumps(ui)

    # 판단스키마에 wall/space objects 누적(door 는 둘 다 아님 → 제외).
    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    js = session["judgment_schema"]
    assert {w["id"] for w in js["wall_objects"]} == {"pred:1", "pred:2"}
    assert {w["wall_type"] for w in js["wall_objects"]} == {
        "NON_LOAD_BEARING",
        "LOAD_BEARING",
    }
    assert {s["id"] for s in js["space_objects"]} == {"pred:3"}


def test_compute_crop_box_pads_and_clamps() -> None:
    # 검출 엔티티 전체 bbox(50..150) + 24px 패딩, 이미지(0..200) 안으로 클램프.
    from src.agent.tools.segmentation import _compute_crop_box

    regions = [
        {"polygon": [50, 60, 150, 60, 150, 140, 50, 140]},
        {"polygon": [80, 70, 120, 70, 120, 100, 80, 100]},
    ]
    crop = _compute_crop_box(regions, {"width": 200, "height": 200})
    assert crop == {"x": 26.0, "y": 36.0, "w": 148.0, "h": 128.0}


def test_compute_crop_box_clamps_to_image_bounds() -> None:
    # 패딩이 캔버스 밖으로 나가면 이미지 경계로 자른다(음수/초과 방지).
    from src.agent.tools.segmentation import _compute_crop_box

    regions = [{"polygon": [0, 0, 100, 0, 100, 100, 0, 100]}]
    crop = _compute_crop_box(regions, {"width": 100, "height": 100})
    assert crop == {"x": 0.0, "y": 0.0, "w": 100.0, "h": 100.0}


def test_compute_crop_box_none_without_regions() -> None:
    from src.agent.tools.segmentation import _compute_crop_box

    assert _compute_crop_box([], {"width": 100, "height": 100}) is None


def test_build_overlay_spec_includes_crop() -> None:
    from src.agent.tools.segmentation import build_overlay_spec

    spec = build_overlay_spec(
        asset_id="a1",
        image={"width": 300, "height": 300},
        regions=[
            {
                "region_id": "pred:1",
                "class_name": "wall_other",
                "polygon": [50, 50, 150, 50, 150, 150, 50, 150],
            }
        ],
    )
    props = spec["elements"]["ov"]["props"]
    assert "crop" in props
    assert props["crop"]["x"] == 26.0 and props["crop"]["y"] == 26.0


def test_merge_overlapping_regions() -> None:
    # 겹치는 같은-클래스 벽 둘 → 하나로 병합(merged:N), 떨어진 벽 → 원본 id 유지.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_other",
            "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
            "score": 0.9,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_other",
            "polygon": [5, 0, 15, 0, 15, 10, 5, 10],
            "score": 0.7,
        },
        {
            "region_id": "pred:3",
            "class_name": "wall_other",
            "polygon": [100, 100, 110, 100, 110, 110, 100, 110],
            "score": 0.8,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    walls = [r for r in merged if r["class_name"] == "wall_other"]
    assert len(walls) == 2  # 겹친 둘→하나 + 떨어진 하나
    ids = {r["region_id"] for r in walls}
    assert "pred:3" in ids  # 안 겹친 건 원본 id 보존
    assert any(i.startswith("merged:") for i in ids)  # 겹친 건 병합 id


async def test_session_floorplan_merges_vlm_reclassification(monkeypatch) -> None:
    # AI-002+AI-003: VLM 이 이미지로 wall_other 를 내력벽으로 보정하면 regions/judgment 가
    # 머지되고 source_engine=VLM, vlm_supplement 가 판단스키마에 저장된다.
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    async def fake_vlm(*, image_url, regions, image, settings, user_context=None):
        return {
            "provider": "OPENAI",
            "model": "gpt-5.4-mini",
            "notes": ["거실 남측 벽은 연속 외벽이라 구조벽 의심"],
            "reclassifications": [
                {
                    "object_id": "pred:1",
                    "new_label": "wall_reinforced_concrete",
                    "reason": "연속 외벽",
                }
            ],
            "confidence": 0.7,
            "is_floorplan": True,
        }

    monkeypatch.setattr("src.agent.tools.vlm.interpret_floorplan_impl", fake_vlm)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_other",
                        "score": 0.9,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                    }
                ],
            },
        )

    ctx = RunContext()
    async with _client(handler) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=client,
            run_context=ctx,
            run_id=run["id"],
        )
    assert res["ok"] is True
    assert res["overlay_emitted"] is True
    # LLM 반환엔 원시 분석값(vlm_notes/vlm_reclassified/instances)을 싣지 않는다
    # (#no-analysis-dump) — 보정/관찰은 아래 영속된 judgment_schema 로만 검증한다.
    assert "vlm_notes" not in res
    assert "vlm_reclassified" not in res
    assert "instances" not in res

    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    js = session["judgment_schema"]
    wall = next(w for w in js["wall_objects"] if w["id"] == "pred:1")
    assert wall["wall_type"] == "LOAD_BEARING"  # VLM 보정 반영
    assert wall["source_engine"] == "VLM"
    assert js["vlm_supplement"]["confidence"] == 0.7
    assert js["vlm_supplement"]["provider"] == "OPENAI"


async def test_session_floorplan_degrades_when_vlm_says_not_floorplan(
    monkeypatch,
) -> None:
    # VLM is_floorplan=false → 오버레이/판정으로 안 흐르고 ok=false(다른 도면 요청).
    session_id, owner = await _session_with_asset(monkeypatch)

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    async def fake_vlm(*, image_url, regions, image, settings, user_context=None):
        return {
            "provider": "OPENAI",
            "model": "gpt-5.4-mini",
            "notes": [],
            "reclassifications": [],
            "confidence": 0.3,
            "is_floorplan": False,  # 평면도가 아님
        }

    monkeypatch.setattr("src.agent.tools.vlm.interpret_floorplan_impl", fake_vlm)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_other",
                        "score": 0.9,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                    }
                ],
            },
        )

    async with _client(handler) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=client,
        )
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_NOT_FLOORPLAN"
    assert not res.get("overlay_emitted")


async def test_session_floorplan_records_input_fingerprint(monkeypatch) -> None:
    # #analysis-input-fingerprint: 분석 시작 시점의 입력(asset_id/address_id)을 run_context
    # 에 기록해 evaluate_rules 가 그 지문 기준으로 verdict 영속을 조건부화하게 한다.
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    asset_id, address_id = await main_flow.get_session_inputs(session_id)

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)
    ctx = RunContext()
    async with _client(lambda req: httpx.Response(200, json={"predictions": []})) as c:
        await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=c,
            run_context=ctx,
        )
    assert ctx.analysis_inputs == (asset_id, address_id)


async def test_session_floorplan_persists_durable_fingerprint(monkeypatch) -> None:
    # #analysis-input-fingerprint: run_id 가 오면 분석 시작 지문을 런에 내구화해
    # resume(새 RunContext)에서도 복원되게 한다. get_run_analysis_inputs 로 왕복 확인.
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    asset_id, address_id = await main_flow.get_session_inputs(session_id)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)
    ctx = RunContext()
    async with _client(lambda req: httpx.Response(200, json={"predictions": []})) as c:
        await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=c,
            run_context=ctx,
            run_id=run["id"],
        )
    # 내구 버퍼에서 복원되면 메모리 지문과 동일해야 한다(resume 복원의 정본).
    restored = await main_flow.get_run_analysis_inputs(run_id=run["id"])
    assert restored == (asset_id, address_id)


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
        return httpx.Response(200, json={"predictions": []})

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
