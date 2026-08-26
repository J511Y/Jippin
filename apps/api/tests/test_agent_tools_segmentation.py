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

from src.agent.tools import segmentation as seg_module
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
        # 어휘 세대는 v4(교체 완료) 기준 — threshold 는 세대 기본값(0.35)으로 결정된다.
        "hf_segmentation_expected_vocab_version": 4,
        "hf_segmentation_threshold": None,
        "hf_segmentation_mask_threshold": 0.5,
        "hf_segmentation_max_tiles": 80,
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
        # 요청 본문이 모델 계약(inputs + parameters)인지 함께 확인한다. v4 는 원본 픽셀
        # 타일 추론이 전제라 **리사이즈 파라미터를 보내면 안 된다**(성능 붕괴).
        body = json.loads(req.content)
        assert body["inputs"] == _IMG
        assert body["parameters"] == {
            "threshold": 0.35,
            "mask_threshold": 0.5,
            "max_tiles": 80,  # 작업량 상한 명시(decompression bomb 방어)
        }
        assert "max_inference_side" not in body["parameters"]
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"class_name": "wall_nonbearing", "score": 0.9},
                    {"class_name": "wall_nonbearing", "score": 0.7},
                    {"class_name": "wall_nonbearing", "score": 0.8},
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
    assert by_label["wall_nonbearing"]["count"] == 3
    assert by_label["wall_nonbearing"]["mean_confidence"] == 0.8  # (0.9+0.7+0.8)/3
    assert by_label["wall_reinforced_concrete"]["count"] == 1
    assert "bogus" not in by_label  # 19 클래스 밖은 드롭
    assert "비내력벽 후보 3" in res["summary"]


async def test_200_uncertain_walls_count_and_summary() -> None:
    # 미확정 벽(wall_other = v4 판단 보류, wall_unknown = v3 이하 과거 데이터)은 드롭되지
    # 않고 집계되며, 검출됐을 때만 요약에 "미확정 벽 N" 으로 합산 노출된다(에이전트가
    # '확인 필요' 흐름을 타는 신호).
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"class_name": "wall_nonbearing", "score": 0.9},
                    {"class_name": "wall_other", "score": 0.4},
                    {"class_name": "wall_unknown", "score": 0.5},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    by_label = {i["label"]: i for i in res["instances"]}
    assert by_label["wall_other"]["count"] == 1
    assert by_label["wall_unknown"]["count"] == 1
    assert "비내력벽 후보 1" in res["summary"]
    assert "미확정 벽 2" in res["summary"]


async def test_200_no_uncertain_wall_omits_summary_segment() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"predictions": [{"class_name": "wall_nonbearing", "score": 0.9}]}
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert "미확정" not in res["summary"]


async def test_threshold_follows_expected_vocab_version() -> None:
    # threshold 는 **응답을 보기 전에** 정해진다 — 응답 기반 어휘 판별로는 못 맞춘다.
    # 교체 전(v3)에 v4 값(0.35)이 나가면 기존에 걸러지던 저점수 벽이 선택 대상으로
    # 올라와 판정이 흔들린다(#threshold-cutover). 설정 세대로 고르고, 명시값은 고정.
    seen: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content)["parameters"]["threshold"])
        return httpx.Response(200, json={"predictions": []})

    for expected, want in ((3, 0.5), (4, 0.35)):
        async with _client(handler) as client:
            await segment_floorplan_impl(
                image_url=_IMG,
                settings=_settings(
                    hf_segmentation_expected_vocab_version=expected,
                    hf_segmentation_threshold=None,
                ),
                client=client,
            )
        assert seen[-1] == want

    # 명시값은 세대와 무관하게 그대로 나간다(운영 튜닝).
    async with _client(handler) as client:
        await segment_floorplan_impl(
            image_url=_IMG,
            settings=_settings(
                hf_segmentation_expected_vocab_version=3,
                hf_segmentation_threshold=0.42,
            ),
            client=client,
        )
    assert seen[-1] == 0.42


def test_missing_vocab_setting_falls_back_to_deployed_v4() -> None:
    assert seg_module._expected_vocab_version(SimpleNamespace()) == 4


async def test_vocab_mismatch_is_warned(monkeypatch) -> None:
    # 설정 세대와 실제 서빙 모델이 어긋나면(교체 전후 스위치 뒤집기 누락) 경고로 드러난다.
    warnings: list[str] = []
    monkeypatch.setattr(
        seg_module.log, "warning", lambda event, **kw: warnings.append(event)
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": {"num_classes": 18},
                "predictions": [{"class_name": "wall_other", "score": 0.6}],
            },
        )

    async with _client(handler) as client:
        await segment_floorplan_impl(
            image_url=_IMG,
            settings=_settings(hf_segmentation_expected_vocab_version=4),
            client=client,
        )
    assert "segmentation_vocab_mismatch" in warnings


async def test_200_v3_endpoint_keeps_legacy_wall_roles() -> None:
    # 엔드포인트 모델 교체는 앱 배포와 별개의 수동 작업이다. 앱이 먼저 나가 v3 응답에
    # v4 의미를 씌우면 **초록 후보가 하나도 안 남아 모든 세션이 HOLD** 로 떨어진다.
    # 응답 어휘를 판별해 v3 이면 옛 역할(wall_other = 선택 가능한 비내력 후보)을 지킨다.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": {"num_classes": 18, "source_run": "confirmed573_ft"},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_other",
                        "score": 0.8,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                    },
                    {
                        "region_id": "pred:2",
                        "class_name": "wall_unknown",
                        "score": 0.4,
                        "polygon": [20, 20, 30, 20, 30, 30, 20, 30],
                    },
                ],
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    by_label = {i["label"]: i["count"] for i in res["instances"]}
    # v3 의 wall_other 는 비내력 후보 역할이었으므로 v4 어휘의 wall_nonbearing 으로 옮긴다.
    assert by_label == {"wall_nonbearing": 1, "wall_unknown": 1}
    assert "비내력벽 후보 1" in res["summary"]

    walls, _s, _w = seg_module.build_judgment_objects(res["regions"])
    by_id = {w["id"]: w["wall_type"] for w in walls}
    assert by_id == {"pred:1": "NON_LOAD_BEARING", "pred:2": "UNKNOWN"}


async def test_200_v4_endpoint_uses_new_wall_semantics() -> None:
    # 19클래스를 서빙하기 시작하면 자동으로 v4 의미로 넘어간다 — wall_other 는 미확정 벽.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": {
                    "num_classes": 19,
                    "source_run": "confirmed573v4_ft_tile_19c",
                },
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_other",
                        "score": 0.4,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                    }
                ],
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert {i["label"] for i in res["instances"]} == {"wall_other"}
    assert "미확정 벽 1" in res["summary"]
    walls, _s, _w = seg_module.build_judgment_objects(res["regions"])
    assert walls[0]["wall_type"] == "UNKNOWN"


async def test_200_detects_v4_from_predictions_without_model_block() -> None:
    # model 블록이 없어도 v4 에만 있는 wall_nonbearing 이 보이면 v4 로 본다.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"class_name": "wall_nonbearing", "score": 0.6},
                    {"class_name": "wall_other", "score": 0.4},
                ]
            },
        )

    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    by_label = {i["label"]: i["count"] for i in res["instances"]}
    assert by_label == {"wall_nonbearing": 1, "wall_other": 1}  # 재매핑 없음


async def test_metadata_free_response_follows_configured_generation() -> None:
    # 단서가 하나도 없는 응답(model 블록 없음 + wall_nonbearing 없음)은 설정 세대를 따른다.
    # 무조건 v3 으로 떨어뜨리면, 메타데이터 없는 **v4** 응답이 wall_other 만 담았을 때
    # 미확정 벽이 전부 비내력으로 승격돼 초록으로 그려지고 NON_LOAD_BEARING 으로
    # 영속된다 — HOLD 를 우회하는, 이 마이그레이션이 없애려던 반전이다.
    # (wall_nonbearing 부재는 v3 의 증거가 아니다: v4 도 확정 비내력이 0곳일 수 있다.)
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_other",
                        "score": 0.4,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                    }
                ]
            },
        )

    # 교체 완료(설정 4) → 미확정 벽 그대로 → 룰엔진 HOLD 경로.
    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG,
            settings=_settings(hf_segmentation_expected_vocab_version=4),
            client=client,
        )
    assert {i["label"] for i in res["instances"]} == {"wall_other"}
    walls, _s, _w = seg_module.build_judgment_objects(res["regions"])
    assert walls[0]["wall_type"] == "UNKNOWN"

    # 교체 전(설정 3) → 옛 역할(선택 가능한 비내력 후보) 유지.
    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG,
            settings=_settings(hf_segmentation_expected_vocab_version=3),
            client=client,
        )
    assert {i["label"] for i in res["instances"]} == {"wall_nonbearing"}
    walls, _s, _w = seg_module.build_judgment_objects(res["regions"])
    assert walls[0]["wall_type"] == "NON_LOAD_BEARING"


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
    # model 블록으로 v4 어휘를 명시한다 — 없으면 v3 로 판별돼 wall_other 가 옛 역할
    # (wall_nonbearing)로 옮겨지므로, 이 테스트의 관심사(형식 방어)가 흐려진다.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": {"num_classes": 19},
                "predictions": [
                    "not-a-dict",
                    {"score": 0.9},  # class_name 없음
                    {"class_name": "wall_other", "score": 0.5},
                    {"class_name": "wall_other"},  # score 없음 → count 만
                ],
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
                    {"class_name": "wall_nonbearing", "score": 0.8},
                    {"class_name": "wall_nonbearing", "score": 0.6},
                ]
            },
        )

    progress: list[str] = []
    async with _client(handler) as client:
        res = await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner,
            owner_is_anonymous=False,
            settings=_settings(),
            client=client,
            progress=progress.append,
        )
    assert res["ok"] is True
    assert {i["label"]: i["count"] for i in res["instances"]} == {"wall_nonbearing": 2}
    assert progress == [
        "도면 파일을 불러오고 있어요",
        "도면에서 벽과 공간을 찾고 있어요",
    ]


async def test_session_summary_counts_merged_walls_not_tile_fragments(
    monkeypatch,
) -> None:
    # v4 타일 추론에서 한 벽이 경계로 쪼개져 오면, 요약은 **병합 후** 기준이어야 한다 —
    # 원시 조각 수(3)를 그대로 말하면 에이전트가 "비내력벽 후보 3곳"이라 안내하는데
    # 오버레이엔 선택 가능한 벽이 1곳만 보이는 불일치가 난다(#summary-after-merge).
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    def handler(req: httpx.Request) -> httpx.Response:
        # 같은 벽이 타일 경계에서 3조각으로 잘려 온 응답.
        return httpx.Response(
            200,
            json={
                "image": {"width": 300, "height": 100},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
                        "touches_tile_border": True,
                        "tile_index": 1,
                    },
                    {
                        "region_id": "pred:2",
                        "class_name": "wall_nonbearing",
                        "score": 0.5,
                        "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
                        "touches_tile_border": True,
                        "tile_index": 2,
                    },
                    {
                        "region_id": "pred:3",
                        "class_name": "wall_nonbearing",
                        "score": 0.4,
                        "polygon": [202, 0, 300, 0, 300, 10, 202, 10],
                        "touches_tile_border": True,
                        "tile_index": 3,
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
    assert res["ok"] is True
    assert res["region_count"] == 1  # 3조각 → 벽 1개
    assert "비내력벽 후보 1" in res["summary"]

    # 판단스키마의 벽 객체도 병합본 1개 — 요약·오버레이·선택 대상이 모두 같은 수다.
    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    assert len(session["judgment_schema"]["wall_objects"]) == 1


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
                        "class_name": "wall_nonbearing",
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


async def test_session_zero_regions_persists_empty_analysis(monkeypatch) -> None:
    # #empty-analysis-persist: 검출 0 인 완료된 분석도 빈 산출로 영속한다 — 다음 턴
    # 세션 상태가 '분석 진행/대기'가 아니라 '분석 완료·후보 0(재업로드 예외)'을 준다.
    session_id, owner = await _session_with_asset(monkeypatch)

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
            settings=_settings(),
            client=client,
        )
    assert res["ok"] is True
    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    js = session["judgment_schema"]
    assert js["wall_objects"] == []
    assert js["window_objects"] == []
    assert js["space_objects"] == []


async def test_session_stale_asset_discards_merge(monkeypatch) -> None:
    # #analysis-merge-fingerprint: 분석 도중 도면이 교체되면 산출을 영속하지 않고
    # SEGMENTATION_STALE_INPUT 으로 degrade — 옛 도면 결과·오버레이가 새 도면에 붙지
    # 않는다(재제출 카드가 열어 준 동시 업로드 경로).
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
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.9,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                    }
                ]
            },
        )

    # 병합 직전에 다른 탭의 재업로드가 끼어든 상황을 재현 — 첫 merge 호출 전에 새
    # asset 으로 교체한 뒤 실제 merge 로 위임한다.
    real_merge = main_flow.merge_judgment_schema

    async def replace_then_merge(**kwargs):
        await main_flow.create_floorplan_asset(
            session_id=session_id,
            owner_user_id=owner,
            payload={
                "bucket": "session-floorplans",
                "object_key": f"{owner}/{session_id}/replaced.png",
                "content_type": "image/png",
                "byte_size": 10,
            },
        )
        return await real_merge(**kwargs)

    monkeypatch.setattr(main_flow, "merge_judgment_schema", replace_then_merge)

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
    assert res["ok"] is False
    assert res["error_code"] == "SEGMENTATION_STALE_INPUT"
    # 오버레이 카드도 방출되지 않는다(persist-before-emit).
    ui, _snapshot = ctx.drain_ui()
    assert ui == []
    # 옛 도면의 wall_objects 가 새 도면에 붙지 않았다(교체 초기화 상태 그대로).
    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    assert "wall_objects" not in session["judgment_schema"]


def test_build_judgment_objects_maps_wall_vocabulary() -> None:
    # v4 어휘: 확정 비내력(wall_nonbearing)만 NON_LOAD_BEARING 으로 승격하고, 판단 보류
    # (wall_other)·과거 데이터(wall_unknown)는 UNKNOWN 으로 둬 룰엔진 HOLD(확인 필요)
    # 경로를 타게 한다 — v3 까지 wall_other 를 비내력으로 읽던 반전을 바로잡는다.
    from src.agent.tools.segmentation import build_judgment_objects

    walls, _spaces, _windows = build_judgment_objects(
        [
            {
                "region_id": "pred:1",
                "class_name": "wall_unknown",
                "score": 0.4,
                "polygon": [0, 0, 10, 0, 10, 2, 0, 2],
            },
            {
                "region_id": "pred:2",
                "class_name": "wall_other",
                "score": 0.8,
                "polygon": [0, 0, 10, 0, 10, 2, 0, 2],
            },
            {
                "region_id": "pred:3",
                "class_name": "wall_nonbearing",
                "score": 0.6,
                "polygon": [0, 0, 10, 0, 10, 2, 0, 2],
            },
            {
                "region_id": "pred:4",
                "class_name": "wall_reinforced_concrete",
                "score": 0.7,
                "polygon": [0, 0, 10, 0, 10, 2, 0, 2],
            },
        ]
    )
    by_id = {w["id"]: w["wall_type"] for w in walls}
    assert by_id == {
        "pred:1": "UNKNOWN",
        "pred:2": "UNKNOWN",
        "pred:3": "NON_LOAD_BEARING",
        "pred:4": "LOAD_BEARING",
    }


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


def test_merge_joins_tile_border_fragments() -> None:
    # v4 타일 추론: 긴 벽이 타일 경계에서 조각으로 나뉘어 온다. 양쪽 모두
    # touches_tile_border 이고 서로 다른 타일에서 왔으며 틈이 미세하면(≤3px)
    # 하나의 벽으로 이어 붙인다.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
            "score": 0.6,
            "touches_tile_border": True,
            "tile_index": 1,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "score": 0.4,
            "touches_tile_border": True,
            "tile_index": 2,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert len(merged) == 1
    joined = merged[0]
    assert joined["region_id"].startswith("merged:")
    assert joined["touches_tile_border"] is True
    xs = joined["polygon"][0::2]
    ys = joined["polygon"][1::2]
    # 좌표는 원본 조각의 합집합 — 연결용 팽창분(3px)만큼 부풀지 않는다.
    assert min(xs) == 0.0 and max(xs) == 200.0
    assert min(ys) == 0.0 and max(ys) == 10.0


def test_merge_keeps_distant_border_fragments_apart() -> None:
    # 경계 조각이라도 틈이 병합 허용치(3px)보다 크면 서로 다른 벽 — 붙이지 않는다.
    # 4px 는 허용치 바로 밖이다. 양쪽을 각각 허용치만큼 부풀리면 6px 까지 묶여
    # 남남 벽이 한 덩어리가 된다(#join-gap-doubling) — 반지름은 허용치의 절반이어야 한다.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
            "touches_tile_border": True,
            "tile_index": 1,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [104, 0, 200, 0, 200, 10, 104, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert {r["region_id"] for r in merged} == {"pred:1", "pred:2"}


def test_merge_refuses_gap_join_without_tile_provenance() -> None:
    # 타일 번호가 없으면 '경계로 갈린 한 벽'인지 '가까운 남남 벽'인지 구분할 근거가 없다 —
    # 과소 병합(조각으로 남김)을 택한다(#unknown-tile-provenance). 1차 병합 결과가 타일
    # 번호를 잃으므로, 2차(VLM 후) 병합에서 이 규칙이 안전망이 된다.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "merged:1",  # 1차 병합본 — tile_index 없음
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
            "touches_tile_border": True,
        },
        {
            "region_id": "pred:9",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
    ]
    merged = _merge_overlapping_regions(regions, id_prefix="vlm-merged")
    assert {r["region_id"] for r in merged} == {"merged:1", "pred:9"}


def test_merge_blocks_transitive_union_across_shared_tile() -> None:
    # 사슬 결합 차단: 타일 1 — 타일 2 — 타일 1 이 나란히 놓이면 쌍 단위로는 1↔2, 2↔1 이
    # 각각 통과하지만, 다 합치면 **타일 1 조각 둘**이 한 덩어리가 된다. 합치기 직전에
    # 루트의 누적 타일 집합으로 다시 확인한다(#transitive-tile-union).
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
            "touches_tile_border": True,
            "tile_index": 1,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
        {
            "region_id": "pred:3",
            "class_name": "wall_nonbearing",
            "polygon": [202, 0, 300, 0, 300, 10, 202, 10],
            "touches_tile_border": True,
            "tile_index": 1,  # 첫 조각과 같은 타일 — 한 덩어리가 되면 안 된다
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert len(merged) == 2  # 1+2 만 결합, 3 은 남는다
    assert "pred:3" in {r["region_id"] for r in merged}


def test_parse_regions_rejects_malformed_tile_metadata() -> None:
    # 핸들러가 계약(1.4.0)을 어긴 값을 보내도 그대로 믿지 않는다. 문자열 "false" 를
    # bool() 로 넘기면 truthy → True 가 되고, 그 region 이 병합 단계에서 부풀려져
    # 남남 벽까지 묶인다(#tile-meta-validation). 음수 tile_index 도 계약 위반이라 뺀다.
    from src.agent.tools.segmentation import _parse_regions

    regions = _parse_regions(
        [
            {
                "region_id": "pred:1",
                "class_name": "wall_nonbearing",
                "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                "touches_tile_border": "false",  # 문자열 — bool 아님
                "tile_index": -1,  # 계약 minimum=0 위반
            },
            {
                "region_id": "pred:2",
                "class_name": "wall_nonbearing",
                "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                "touches_tile_border": True,
                "tile_index": 0,
            },
        ]
    )
    assert regions[0]["touches_tile_border"] is False
    assert "tile_index" not in regions[0]
    assert regions[1]["touches_tile_border"] is True
    assert regions[1]["tile_index"] == 0


def test_overlay_payload_is_safe_for_old_web_bundles() -> None:
    # web(Vercel)/api(Fly) 는 따로 배포되고 열려 있던 탭은 옛 번들로 남는다. 옛 카드는
    # wall_other 를 초록 '비내력벽 후보'로 그리므로, v4 미확정 벽을 그대로 실으면 철거
    # 불가일 수 있는 벽이 철거 가능 후보로 보인다(#deploy-skew). 미확정은 옛·새 카드가
    # 모두 회색으로 읽는 wall_unknown 으로 통일해 내보낸다.
    from src.agent.tools.segmentation import build_overlay_spec

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_other",
            "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [20, 20, 30, 20, 30, 30, 20, 30],
        },
    ]
    spec = build_overlay_spec(
        asset_id="a1", image={"width": 100, "height": 100}, regions=regions
    )
    props = spec["elements"]["ov"]["props"]
    assert props["vocab_version"] == 4
    by_id = {r["region_id"]: r["class_name"] for r in props["regions"]}
    assert by_id == {"pred:1": "wall_unknown", "pred:2": "wall_nonbearing"}
    # 원본은 건드리지 않는다 — 판단객체·룰 입력은 v4 어휘 그대로 쓴다.
    assert regions[0]["class_name"] == "wall_other"


def test_merge_component_tile_set_counts_all_members() -> None:
    # 성분의 타일 점유는 **모든 멤버** 기준이어야 한다. 경계 조각만 세면 타일 1 경계 조각 +
    # 타일 2 평범한 예측으로 이뤄진 성분이 {1} 로 잡혀, 타일 2 의 다른 벽과 '안 겹친다'며
    # 이어 붙는다(#component-tile-coverage).
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        # 겹쳐서 한 성분이 되는 둘: 타일 1 경계 조각 + 타일 2 비경계 예측.
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 60, 0, 60, 10, 0, 10],
            "touches_tile_border": True,
            "tile_index": 1,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [50, 0, 100, 0, 100, 10, 50, 10],
            "touches_tile_border": False,
            "tile_index": 2,
        },
        # 2px 옆의 타일 2 경계 조각 — 위 성분이 이미 타일 2 를 점유하므로 붙이면 안 된다.
        {
            "region_id": "pred:3",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert "pred:3" in {r["region_id"] for r in merged}
    assert len(merged) == 2  # (겹친 1+2) + pred:3


def test_merge_does_not_duplicate_point_touching_walls() -> None:
    # 모서리(꼭짓점) 한 점만 맞닿은 두 벽. unary_union 은 이를 2개 part 로 두는데,
    # intersects 로 소속을 정하면 점 접촉도 True 라 **양쪽 part 가 두 벽을 모두** 멤버로
    # 가져가 같은 병합본이 두 번 생성된다(개수·오버레이·판단객체 부풀림).
    # 소속은 양의 면적 겹침으로 정해야 한다(#point-touch-duplication).
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
            "score": 0.6,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [10, 10, 20, 10, 20, 20, 10, 20],
            "score": 0.5,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    # 점 접촉은 병합 사유가 아니다 — 원본 둘이 그대로 남아야 한다(중복 없음).
    assert len(merged) == 2
    assert {r["region_id"] for r in merged} == {"pred:1", "pred:2"}


def test_merge_preserves_vlm_provenance_and_custom_id_prefix() -> None:
    # VLM 이 교정한 조각이 섞이면 병합본도 VLM 출처를 유지한다 — 잃으면 판단객체의
    # source_engine 이 MASK2FORMER 로 되돌아가 교정 이력이 사라진다. id 접두사는
    # 2차 병합이 1차 병합 id(merged:N)와 충돌하지 않도록 갈아 끼울 수 있어야 한다.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "merged:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
            "source_engine": "VLM",
        },
        {
            "region_id": "pred:9",
            "class_name": "wall_nonbearing",
            "polygon": [5, 0, 15, 0, 15, 10, 5, 10],
        },
    ]
    merged = _merge_overlapping_regions(regions, id_prefix="vlm-merged")
    assert len(merged) == 1
    assert merged[0]["region_id"] == "vlm-merged:1"  # 1차 id 와 충돌 없음
    assert merged[0]["source_engine"] == "VLM"


def test_merge_requires_both_sides_to_be_border_fragments() -> None:
    # 한쪽만 경계 조각이면 잇지 않는다 — 경계 조각을 부풀려 판정하면 경계와 무관한
    # 이웃 벽이 딸려 들어와 서로 다른 벽이 하나의 선택 대상이 된다(#both-sides-border).
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
            "touches_tile_border": True,
        },
        {
            "region_id": "pred:2",  # 평범한 벽(경계 조각 아님)이 2px 옆에 있다
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "touches_tile_border": False,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert {r["region_id"] for r in merged} == {"pred:1", "pred:2"}


def test_merge_skips_border_fragments_from_the_same_tile() -> None:
    # 같은 타일에서 나온 두 경계 조각은 경계로 갈라진 한 벽이 아니라 원래 다른 벽이다.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert {r["region_id"] for r in merged} == {"pred:1", "pred:2"}

    # 서로 다른 타일이면 같은 좌표라도 이어 붙인다(경계로 갈린 한 벽).
    regions[1]["tile_index"] = 3
    joined = _merge_overlapping_regions(regions)
    assert len(joined) == 1


def test_merge_rejects_partially_overlapping_tile_sets() -> None:
    # 성분이 여러 타일 조각을 품을 수 있다. {1,2} 와 {2} 처럼 **일부만** 겹쳐도 한 타일을
    # 공유하므로 경계로 갈린 조각이 아니다 — '집합이 같을 때만' 막으면 새어 나간다
    # (#tile-overlap-not-equality).
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        # 겹쳐서 한 성분이 되는 두 조각(타일 1, 2).
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 60, 0, 60, 10, 0, 10],
            "touches_tile_border": True,
            "tile_index": 1,
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [50, 0, 100, 0, 100, 10, 50, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
        # 2px 떨어진 별개 벽 — 타일 2 를 공유하므로 이어 붙이면 안 된다.
        {
            "region_id": "pred:3",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
            "touches_tile_border": True,
            "tile_index": 2,
        },
    ]
    merged = _merge_overlapping_regions(regions)
    ids = {r["region_id"] for r in merged}
    assert "pred:3" in ids  # 남남 벽은 따로 남는다
    assert len(merged) == 2  # (겹친 1+2 병합) + pred:3


def test_merge_ignores_border_gap_for_non_border_fragments() -> None:
    # touches_tile_border 가 아니면 미세한 틈이어도 잇지 않는다 — 타일 경계에서
    # 쪼개진 조각에만 적용되는 보정이다.
    from src.agent.tools.segmentation import _merge_overlapping_regions

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [102, 0, 200, 0, 200, 10, 102, 10],
        },
    ]
    merged = _merge_overlapping_regions(regions)
    assert {r["region_id"] for r in merged} == {"pred:1", "pred:2"}


async def test_200_carries_tile_metadata_and_warns_on_downscaled_input(
    monkeypatch,
) -> None:
    # tile_index/touches_tile_border 는 region 으로 보존되고, 핸들러가 입력이 작다고
    # 알리면(notes) 경고로 남긴다 — v4 는 축소 입력에서 성능이 붕괴한다.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 800, "height": 600},
                "notes": ["input_long_side_below_expected: 800 < 1536"],
                "tiling": {"windows": 1, "returned_predictions": 1},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.5,
                        "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
                        "tile_index": 3,
                        "touches_tile_border": True,
                    }
                ],
            },
        )

    warnings: list[str] = []
    monkeypatch.setattr(
        seg_module.log, "warning", lambda event, **kw: warnings.append(event)
    )
    async with _client(handler) as client:
        res = await segment_floorplan_impl(
            image_url=_IMG, settings=_settings(), client=client
        )
    assert res["ok"] is True
    region = res["regions"][0]
    assert region["tile_index"] == 3
    assert region["touches_tile_border"] is True
    assert "segmentation_input_downscaled" in warnings


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


async def test_session_floorplan_remerges_after_vlm_unifies_fragment_classes(
    monkeypatch,
) -> None:
    # 한 벽의 타일 조각이 서로 다른 클래스로 나오면 1차 병합(클래스별)은 둘을 남남으로
    # 남긴다. VLM 이 그 불일치를 정리해 같은 클래스로 만들면 다시 합쳐야 한다 —
    # 안 그러면 오버레이에 같은 벽이 둘로 뜨고 개수도 부풀려진다(#remerge-after-vlm).
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    async def fake_vlm(*, image_url, regions, image, settings, user_context=None):
        # 미확정으로 잡힌 조각을 옆 조각과 같은 확정 비내력으로 교정.
        return {
            "provider": "OPENAI",
            "model": "gpt-5.4-mini",
            "notes": [],
            "reclassifications": [
                {
                    "object_id": "pred:2",
                    "new_label": "wall_nonbearing",
                    "reason": "같은 벽의 연속 구간",
                }
            ],
            "confidence": 0.8,
            "is_floorplan": True,
        }

    monkeypatch.setattr("src.agent.tools.vlm.interpret_floorplan_impl", fake_vlm)

    def handler(req: httpx.Request) -> httpx.Response:
        # 겹치는 두 조각인데 클래스가 달라 1차 병합에서 안 합쳐진다.
        return httpx.Response(
            200,
            json={
                "image": {"width": 300, "height": 100},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
                    },
                    {
                        "region_id": "pred:2",
                        "class_name": "wall_other",
                        "score": 0.4,
                        "polygon": [90, 0, 200, 0, 200, 10, 90, 10],
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
    assert res["ok"] is True
    assert res["region_count"] == 1  # 교정 후 재병합 → 벽 1개
    assert "비내력벽 후보 1" in res["summary"]

    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    walls = session["judgment_schema"]["wall_objects"]
    assert len(walls) == 1
    assert walls[0]["wall_type"] == "NON_LOAD_BEARING"
    # 교정 조각이 섞였으므로 병합본의 출처도 VLM 이어야 한다(교정 이력 보존).
    assert walls[0]["source_engine"] == "VLM"


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


def test_rc_priority_drops_fully_overlapped_nonbearing() -> None:
    # #rc-priority: 같은 벽이 비내력·RC 양쪽으로 판정되면 RC 우선 — RC 안에 완전히
    # 들어간 비내력 판정은 통째로 무시된다.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [10, 2, 90, 2, 90, 8, 10, 8],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    assert [r["region_id"] for r in out] == ["pred:1"]  # RC 만 남는다


def test_rc_priority_trims_partial_overlap() -> None:
    # 부분 겹침이면 교집합만 도려내고 잔여를 남긴다 — 잔여엔 RC 와의 겹침이 없다.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [80, 0, 150, 0, 150, 10, 80, 10],
            "score": 0.6,
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = [r for r in out if r["class_name"] == "wall_nonbearing"]
    assert len(nb) == 1
    # 잘린 조각은 원본 id 를 물려받지 않고 기하 지문 id 를 받는다
    # (#rc-clip-geometry-id) — 기하가 바뀐 잔여가 저장된 선택(id 교집합)에 옛 벽으로
    # 살아남으면 안 된다.
    assert nb[0]["region_id"].startswith("pred:2~")
    assert nb[0]["region_id"] != "pred:2"
    assert nb[0]["score"] == 0.6  # 속성 보존
    xs = nb[0]["polygon"][0::2]
    assert min(xs) >= 100.0  # RC(x<=100) 구간이 도려내졌다


def test_rc_priority_splits_remainder_into_pieces() -> None:
    # RC 가 비내력벽 가운데를 가로지르면 잔여 두 조각이 각각 별도 region 으로 남는다
    # (실제로 서로 떨어진 후보 벽). 원본 id 는 사라지고 모든 조각이 `{id}:N` 새 id.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [45, 0, 55, 0, 55, 50, 45, 50],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [0, 20, 100, 20, 100, 30, 0, 30],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = [r for r in out if r["class_name"] == "wall_nonbearing"]
    assert len(nb) == 2
    ids = {r["region_id"] for r in nb}
    assert len(ids) == 2  # 두 조각이 서로 다른 기하 지문 id
    assert all(i.startswith("pred:2~") for i in ids)
    for r in nb:
        xs = r["polygon"][0::2]
        # 각 조각은 RC 스트립(45..55) 바깥에만 있다.
        assert max(xs) <= 45.0 or min(xs) >= 55.0


def test_rc_priority_ignores_edge_contact_and_other_classes() -> None:
    # 점/모서리 접촉(면적 0 교집합)은 겹침이 아니고, 미확정 벽(wall_other)은 겹쳐도
    # 건드리지 않는다 — UNKNOWN 이라 철거 후보로 승격되지 않는다.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
        },
        {
            # RC 와 변을 공유(면적 0) — 유지.
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [10, 0, 20, 0, 20, 10, 10, 10],
        },
        {
            # RC 와 면적 겹침이지만 미확정 벽 — 유지.
            "region_id": "pred:3",
            "class_name": "wall_other",
            "polygon": [5, 0, 15, 0, 15, 10, 5, 10],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    assert {r["region_id"] for r in out} == {"pred:1", "pred:2", "pred:3"}
    nb = next(r for r in out if r["region_id"] == "pred:2")
    assert nb["polygon"] == [10, 0, 20, 0, 20, 10, 10, 10]  # 무변형


def test_rc_priority_noop_without_rc() -> None:
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 10, 0, 10, 10, 0, 10],
        }
    ]
    assert _suppress_rc_overlapped_nonbearing(regions) == regions


def test_rc_priority_drops_remainder_smaller_than_10x10() -> None:
    # 잘려 남은 비내력 조각이 10×10px(100px²) 미만이면 벽으로 보기 어려운 크기라
    # 후보에서 제외한다(2026-08-19 모델 레포 지시). 비율(5%)로는 통과하는 크기라
    # 절대 하한이 실제로 작동하는지를 본다.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
        },
        {
            # 원본 130px² — 잔여(x 100..108)는 80px² < 100px² 인데 비율은 61%.
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [95, 0, 108, 0, 108, 10, 95, 10],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    assert [r["region_id"] for r in out] == ["pred:1"]


def test_rc_priority_preserves_hole_when_rc_fully_inside() -> None:
    # #rc-hole-preservation: RC 가 비내력벽 안에 완전히 포함되면 difference 가 구멍 뚫린
    # 폴리곤을 낸다. exterior 만 직렬화하면 도려낸 RC 영역이 초록 후보로 되살아나므로,
    # 구멍 없는 조각들로 분해해 어떤 조각도 RC 중심을 덮지 않아야 한다.
    from shapely.geometry import Point, Polygon

    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [40, 40, 60, 40, 60, 60, 40, 60],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 100, 0, 100],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = [r for r in out if r["class_name"] == "wall_nonbearing"]
    assert len(nb) >= 2  # 도넛 → 구멍 없는 조각 분해
    total = 0.0
    rc_center = Point(50, 50)
    for r in nb:
        poly = r["polygon"]
        shape = Polygon([(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)])
        assert not shape.interiors  # 조각엔 구멍이 없다
        assert not shape.contains(rc_center)  # RC 영역을 덮는 조각이 없다
        total += shape.area
    assert abs(total - 9600.0) < 1.0  # 10000 − RC 400 이 보존된다


def test_rc_priority_split_ids_avoid_existing_siblings() -> None:
    # #rc-split-id-collision: 기존 region 과 id 가 절대 충돌하지 않는다 — 잘린 조각은
    # 기하 지문 id(`{id}~<지문>`)를 받고, 이전 패스가 남긴 형제 id 는 그대로 보존된다.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [45, 0, 55, 0, 55, 50, 45, 50],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [0, 20, 100, 20, 100, 30, 0, 30],
        },
        {
            # 앞선 패스가 만들었을 법한 형제 id — RC 와 안 겹쳐 그대로 남는다.
            "region_id": "pred:2:2",
            "class_name": "wall_nonbearing",
            "polygon": [200, 0, 220, 0, 220, 20, 200, 20],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    ids = [r["region_id"] for r in out]
    assert len(ids) == len(set(ids))  # 전역 유일
    assert "pred:1" in ids and "pred:2:2" in ids  # RC·기존 형제는 그대로
    clipped = [i for i in ids if i.startswith("pred:2~")]
    assert len(clipped) == 2  # 분할 조각 둘은 기하 지문 id


def test_rc_priority_clears_border_flag_on_clipped_pieces() -> None:
    # 잘린 조각은 touches_tile_border 를 해제한다 — 경계에 닿던 부분이 도려내졌을 수
    # 있는데 표식이 남으면 2차 병합의 경계 잇기(≤3px)가 무관한 벽을 붙인다.
    # tile_index 는 여전히 사실이라 보존한다.
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [80, 0, 150, 0, 150, 10, 80, 10],
            "touches_tile_border": True,
            "tile_index": 1,
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = next(r for r in out if r["class_name"] == "wall_nonbearing")
    assert nb["touches_tile_border"] is False
    assert nb["tile_index"] == 1


async def test_session_floorplan_prunes_stale_selection(monkeypatch) -> None:
    # #stale-selection-prune: 재분석으로 region id 가 바뀌면(병합/RC 억제/드롭) 저장된
    # selected_walls/windows 가 유령 id 나 내력벽 id 를 가리킬 수 있다 — 새 '선택 가능'
    # id(비내력·미확정 벽 + 창호)와의 교집합으로 줄여 영속한다.
    session_id, owner = await _session_with_asset(monkeypatch)
    await main_flow.merge_judgment_schema(
        session_id=session_id,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={
            # pred:1 은 살아남고, ghost:9 는 이번 분석에 없는 id, pred:3 은 내력벽이
            # 되는 id — 뒤의 둘은 걸러져야 한다.
            "selected_walls": ["pred:1", "pred:3", "ghost:9"],
            "selected_windows": ["pred:2", "ghost:w"],
        },
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
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [0, 0, 20, 0, 20, 20, 0, 20],
                    },
                    {
                        "region_id": "pred:2",
                        "class_name": "window",
                        "score": 0.7,
                        "polygon": [200, 0, 220, 0, 220, 10, 200, 10],
                    },
                    {
                        "region_id": "pred:3",
                        "class_name": "wall_reinforced_concrete",
                        "score": 0.8,
                        "polygon": [400, 0, 420, 0, 420, 10, 400, 10],
                    },
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
    assert res["ok"] is True

    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    js = session["judgment_schema"]
    assert js["selected_walls"] == ["pred:1"]  # 유령·내력벽 id 제거
    assert js["selected_windows"] == ["pred:2"]


async def test_session_floorplan_invalidates_selection_of_clipped_wall(
    monkeypatch,
) -> None:
    # #rc-clip-id-invalidation: 선택했던 벽이 RC 억제로 잘리면 잔여 조각은 새 id 를
    # 받으므로 저장된 선택이 프루닝에서 자동 무효화된다 — 기하가 달라진 잔여를
    # 사용자가 고른 벽으로 계속 취급하지 않고, 다시 확인·선택하게 한다.
    session_id, owner = await _session_with_asset(monkeypatch)
    await main_flow.merge_judgment_schema(
        session_id=session_id,
        owner_user_id=owner,
        owner_is_anonymous=False,
        patch={"selected_walls": ["pred:1"]},
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    def handler(req: httpx.Request) -> httpx.Response:
        # pred:1 이 RC(pred:2)와 부분 겹침 → 잔여는 기하 지문 id(pred:1~…)를 받는다.
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [80, 0, 150, 0, 150, 10, 80, 10],
                    },
                    {
                        "region_id": "pred:2",
                        "class_name": "wall_reinforced_concrete",
                        "score": 0.8,
                        "polygon": [0, 0, 100, 0, 100, 10, 0, 10],
                    },
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
    assert res["ok"] is True

    session = await main_flow.get_owned_session(
        session_id, owner_user_id=owner, owner_is_anonymous=False
    )
    js = session["judgment_schema"]
    assert js["selected_walls"] == []  # 잘린 벽의 선택은 무효화
    wall_ids = {w["id"] for w in js["wall_objects"]}
    assert any(i.startswith("pred:1~") for i in wall_ids)
    assert "pred:1" not in wall_ids
    # 선택이 전부 무효화됐으므로 배지도 오버레이 단계로 재개된다 — 선택 완료
    # (collecting_info)에 남으면 SSE/퍼널이 현실과 어긋난다(#selection-invalidation-reopen).
    assert session["status"] == "awaiting_overlay"


def test_rc_priority_size_threshold_ignores_decomposition_cuts() -> None:
    # #threshold-before-decomposition: 크기 임계값은 연결 잔여(구멍 분해 전) 기준이다.
    # 벽 가장자리 근처의 작은 RC 구멍은 절단선이 얇은 스트립을 만들지만, 그 스트립은
    # RC 와 겹친 적 없는 유효 영역이라 비율 컷으로 버리면 안 된다.
    from shapely.geometry import Point, Polygon

    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    regions = [
        {
            # 100×100 벽의 왼쪽 가장자리 근처(x 2..6)에 완전히 포함된 작은 RC.
            "region_id": "pred:1",
            "class_name": "wall_reinforced_concrete",
            "polygon": [2, 40, 6, 40, 6, 60, 2, 60],
        },
        {
            "region_id": "pred:2",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 100, 0, 100, 100, 0, 100],
        },
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = [r for r in out if r["class_name"] == "wall_nonbearing"]
    assert len(nb) >= 2  # 절단 스트립(~360px², 비율 컷 미만)도 살아남는다
    total = 0.0
    rc_center = Point(4.0, 50.0)
    for r in nb:
        poly = r["polygon"]
        shape = Polygon([(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)])
        assert not shape.contains(rc_center)  # RC 영역은 여전히 비어 있다
        total += shape.area
    assert abs(total - (10000.0 - 80.0)) < 1.0  # 연결 잔여 전체가 보존된다


def test_rc_priority_preserves_geometry_with_many_holes() -> None:
    # #hole-cap-drop: RC 섬이 8개를 넘어도(여기선 9개) 분해가 잔여를 통째로 버리지
    # 않는다 — 워크리스트 반복은 총 구멍 수가 단조 감소해 개수와 무관하게 끝난다.
    from shapely.geometry import Point, Polygon

    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    rc_regions = [
        {
            "region_id": f"rc:{k}",
            "class_name": "wall_reinforced_concrete",
            "polygon": [
                50 + 100 * k,
                40,
                70 + 100 * k,
                40,
                70 + 100 * k,
                60,
                50 + 100 * k,
                60,
            ],
        }
        for k in range(9)
    ]
    regions = rc_regions + [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 1000, 0, 1000, 100, 0, 100],
        }
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = [r for r in out if r["class_name"] == "wall_nonbearing"]
    assert nb  # 잔여가 통째로 사라지지 않는다
    total = 0.0
    centers = [Point(60 + 100 * k, 50) for k in range(9)]
    for r in nb:
        poly = r["polygon"]
        shape = Polygon([(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)])
        assert not shape.interiors  # 모든 조각은 구멍이 없다
        assert all(not shape.contains(c) for c in centers)  # RC 영역은 비어 있다
        total += shape.area
    # 벽 100,000 − RC 9×400 = 96,400 이 (노이즈 컷 오차 내에서) 보존된다.
    assert abs(total - 96400.0) < 2.0


def test_rc_priority_clip_ids_track_geometry() -> None:
    # #rc-clip-geometry-id: 같은 기하로 재분석되면 잘린 조각 id 가 같아 저장된 선택이
    # 보존되고, RC 경계가 이동해 잔여 기하가 달라지면 id 도 달라져 id 기준 프루닝·검증이
    # 선택을 무효화한다 — 순번 접미사는 이 구분을 못 한다(결정적 재사용).
    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    def regions(rc_right: float) -> list[dict]:
        return [
            {
                "region_id": "pred:1",
                "class_name": "wall_reinforced_concrete",
                "polygon": [0, 0, rc_right, 0, rc_right, 10, 0, 10],
            },
            {
                "region_id": "pred:2",
                "class_name": "wall_nonbearing",
                "polygon": [80, 0, 200, 0, 200, 10, 80, 10],
            },
        ]

    def clipped_id(out: list[dict]) -> str:
        return next(r["region_id"] for r in out if r["class_name"] == "wall_nonbearing")

    id_a = clipped_id(_suppress_rc_overlapped_nonbearing(regions(100.0)))
    id_b = clipped_id(_suppress_rc_overlapped_nonbearing(regions(100.0)))
    id_c = clipped_id(_suppress_rc_overlapped_nonbearing(regions(120.0)))
    assert id_a == id_b  # 동일 기하 → 동일 id(선택 보존)
    assert id_a != id_c  # 경계 이동 → 다른 id(선택 무효화)


async def test_session_floorplan_persists_before_emitting_overlay(
    monkeypatch,
) -> None:
    # #persist-before-emit: 판단객체 영속이 오버레이 방출보다 먼저다 — 카드를 먼저
    # 내보내면 즉시 제출이 옛 wall_objects 기준 검증에 걸려(SELECTION_STALE) 방금 나온
    # 카드가 만료 표시된다.
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.6-luna"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    order: list[str] = []
    real_merge = main_flow.merge_judgment_schema

    async def merge_spy(**kwargs):
        order.append("persist")
        return await real_merge(**kwargs)

    async def emit_spy(**kwargs):
        order.append("emit")
        return {"ok": True}

    monkeypatch.setattr(main_flow, "merge_judgment_schema", merge_spy)
    monkeypatch.setattr("src.agent.tools.domain.emit_ui_component_impl", emit_spy)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [0, 0, 20, 0, 20, 20, 0, 20],
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
            run_context=RunContext(),
            run_id=run["id"],
        )
    assert res["ok"] is True
    assert res["overlay_emitted"] is True
    assert order == ["persist", "emit"]  # 영속이 항상 방출보다 먼저


async def test_session_floorplan_skips_overlay_when_persist_fails(
    monkeypatch,
) -> None:
    # #persist-before-emit: 영속이 실패하면 카드를 내보내지 않는다 — 제출이 영영
    # 불가능한(SELECTION_STALE) 오버레이를 사용자에게 보여 주지 않는다.
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.6-luna"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    async def merge_boom(**kwargs):
        raise RuntimeError("persist failed")

    emitted: list[object] = []

    async def emit_spy(**kwargs):
        emitted.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(main_flow, "merge_judgment_schema", merge_boom)
    monkeypatch.setattr("src.agent.tools.domain.emit_ui_component_impl", emit_spy)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [0, 0, 20, 0, 20, 20, 0, 20],
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
            run_context=RunContext(),
            run_id=run["id"],
        )
    assert res["ok"] is True  # 분석 자체는 무르지 않는다(best-effort)
    assert res["overlay_emitted"] is False
    assert emitted == []  # 카드 미방출


def test_clip_geometry_digest_is_representation_invariant() -> None:
    # #canonical-ring-digest: 같은 링이면 시작 꼭짓점 순환·감기 방향·닫힘점 포함 여부와
    # 무관하게 지문이 같아야 한다 — 표현이 지문을 바꾸면 재분석에서 유효한 선택이
    # 이유 없이 무효화된다. 기하가 다르면 지문도 달라야 한다.
    from src.agent.tools.segmentation import _clip_geometry_digest

    base = [0, 0, 10, 0, 10, 10, 0, 10]
    rotated = [10, 0, 10, 10, 0, 10, 0, 0]  # 시작 꼭짓점 순환
    rewound = [0, 0, 0, 10, 10, 10, 10, 0]  # 반대 감기 방향
    closed = [0, 0, 10, 0, 10, 10, 0, 10, 0, 0]  # 닫힘점 포함 표현
    digests = {_clip_geometry_digest(p) for p in (base, rotated, rewound, closed)}
    assert len(digests) == 1  # 표현 불변
    assert _clip_geometry_digest([0, 0, 12, 0, 12, 10, 0, 10]) not in digests


def test_rc_priority_scales_past_moderate_hole_counts() -> None:
    # #hole-count-cap-drop: 분해에 개수 상한이 없다 — RC 섬이 많아도(여기선 25개)
    # 스택에 남은 유효 잔여를 버리지 않고 전체 면적이 보존된다(종료는 총 구멍 수
    # 단조 감소로 보장).
    from shapely.geometry import Polygon

    from src.agent.tools.segmentation import _suppress_rc_overlapped_nonbearing

    count = 25
    rc_regions = [
        {
            "region_id": f"rc:{k}",
            "class_name": "wall_reinforced_concrete",
            "polygon": [
                50 + 100 * k,
                40,
                70 + 100 * k,
                40,
                70 + 100 * k,
                60,
                50 + 100 * k,
                60,
            ],
        }
        for k in range(count)
    ]
    regions = rc_regions + [
        {
            "region_id": "pred:1",
            "class_name": "wall_nonbearing",
            "polygon": [0, 0, 2600, 0, 2600, 100, 0, 100],
        }
    ]
    out = _suppress_rc_overlapped_nonbearing(regions)
    nb = [r for r in out if r["class_name"] == "wall_nonbearing"]
    total = 0.0
    for r in nb:
        poly = r["polygon"]
        shape = Polygon([(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)])
        assert not shape.interiors
        total += shape.area
    assert abs(total - (260000.0 - count * 400.0)) < 2.0


async def test_session_floorplan_overlay_flag_tracks_inmemory_buffer(
    monkeypatch,
) -> None:
    # #emit-flag-from-buffer: 내구 버퍼(pending_ui) 쓰기가 실패해도 in-memory 버퍼에
    # 카드가 들어갔으면 이번 스트림 drain 이 카드를 첨부한다 — overlay_emitted 는
    # 실제 버퍼 도달 기준이어야 에이전트가 중복 방출/모순 안내를 하지 않는다.
    from src.agent.tools.domain import RunContext

    session_id, owner = await _session_with_asset(monkeypatch)
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.6-luna"
    )

    async def fake_sign(settings, *, bucket, object_path, **_: object) -> str:
        return f"https://signed.example/{object_path}"

    monkeypatch.setattr(storage, "sign_object_url", fake_sign)

    async def boom_append(**kwargs):
        raise RuntimeError("durable buffer down")

    monkeypatch.setattr(main_flow, "append_pending_ui", boom_append)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "image": {"width": 1000, "height": 800},
                "predictions": [
                    {
                        "region_id": "pred:1",
                        "class_name": "wall_nonbearing",
                        "score": 0.6,
                        "polygon": [0, 0, 20, 0, 20, 20, 0, 20],
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
    assert len(ctx.pending_ui_components) == 1  # in-memory 버퍼엔 들어갔다
    assert res["overlay_emitted"] is True  # 버퍼 도달 기준으로 True
