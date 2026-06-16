"""CODEF 세움터 집합건축물대장 인하우스 클라이언트 테스트 (ADR-0008).

실제 CODEF 호출은 전혀 하지 않는다 — httpx 와 Redis 를 fake 로 주입한다.
검증 시나리오:
  (a) 전유부 1차 CF-03002 → 자동매칭 → 2차 CF-00000 happy path
  (b) 동·호 복수후보 → CodefNeedsUserInput
  (c) 표제부 동 직접조회 성공
  (d) URL-encoded 응답 디코딩
  (e) RSA 암호화가 base64 문자열 산출
  (f) CodefAuthError 재시도 안 함
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote_plus

import pytest
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from src.services.codef import (
    BuildingRegisterQuery,
    CodefAuthError,
    CodefBuildingRegisterClient,
    CodefNeedsUserInput,
    ExclusivePartResult,
)
from src.services.codef.crypto import encrypt_password
from src.services.codef.transport import decode_envelope

# ---------------------------------------------------------------------------
# 픽스처: RSA 키페어 + Base64(DER) 공개키
# ---------------------------------------------------------------------------
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_DER = _PRIVATE_KEY.public_key().public_bytes(
    Encoding.DER, PublicFormat.SubjectPublicKeyInfo
)
_PUBLIC_KEY_B64 = base64.b64encode(_PUBLIC_DER).decode("ascii")


class _Settings:
    """CodefBuildingRegisterClient 가 읽는 설정만 갖춘 가짜 settings."""

    codef_oauth_url = "https://oauth.codef.io/oauth/token"
    codef_client_id = "cid"
    codef_client_secret = "csecret"
    codef_public_key = _PUBLIC_KEY_B64
    codef_api_base_url = "https://api.codef.io"
    codef_demo_base_url = "https://development.codef.io"
    codef_use_demo = False
    codef_organization = "0008"
    seumter_id = "seumter-user"
    seumter_password = "seumter-pass"
    codef_request_timeout_first_seconds = 300
    codef_request_timeout_two_way_seconds = 170
    codef_breaker_error_threshold = 5
    codef_breaker_window_seconds = 300
    codef_breaker_open_seconds = 600


def _encode_body(envelope: dict[str, Any]) -> str:
    """CODEF 처럼 JSON 을 URL-encode 한 본문 문자열."""

    return quote_plus(json.dumps(envelope, ensure_ascii=False))


class _FakeResponse:
    def __init__(self, body: str, status_code: int = 200):
        self.text = body
        self.status_code = status_code

    def json(self) -> dict:
        return json.loads(self.text)


class _FakeHttpClient:
    """주입형 httpx 대체. POST 호출을 큐에 쌓인 응답으로 처리한다.

    OAuth 토큰 발급(oauth.codef.io)과 제품 API POST 를 URL 로 구분한다.
    """

    def __init__(self, product_responses: list[_FakeResponse]):
        self._product_responses = list(product_responses)
        self.product_calls: list[dict[str, Any]] = []
        self.token_calls = 0

    async def post(self, url: str, *, headers=None, json=None, data=None):
        if "oauth.codef.io" in url:
            self.token_calls += 1
            return _FakeResponse(
                __import__("json").dumps(
                    {"access_token": "tok-123", "expires_in": 3600}
                )
            )
        self.product_calls.append({"url": url, "body": json})
        if not self._product_responses:
            raise AssertionError("예상보다 많은 제품 API 호출이 발생했습니다.")
        return self._product_responses.pop(0)


def _make_client(
    responses: list[_FakeResponse],
) -> tuple[CodefBuildingRegisterClient, _FakeHttpClient]:
    fake_http = _FakeHttpClient(responses)
    client = CodefBuildingRegisterClient(
        _Settings(), redis_client=None, http_client=fake_http
    )
    return client, fake_http


# ---------------------------------------------------------------------------
# (e) RSA 암호화가 base64 문자열 산출 + 복호화 검증
# ---------------------------------------------------------------------------
def test_encrypt_password_returns_base64_and_roundtrips() -> None:
    cipher_b64 = encrypt_password("my-secret", _PUBLIC_KEY_B64)
    assert isinstance(cipher_b64, str)
    cipher = base64.b64decode(cipher_b64)  # 유효한 base64 여야 한다.
    recovered = _PRIVATE_KEY.decrypt(cipher, padding.PKCS1v15())
    assert recovered == b"my-secret"


def test_encrypt_password_accepts_pem() -> None:
    pem = (
        _PRIVATE_KEY.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    cipher_b64 = encrypt_password("x", pem)
    assert base64.b64decode(cipher_b64)


# ---------------------------------------------------------------------------
# (d) URL-encoded 응답 디코딩
# ---------------------------------------------------------------------------
def test_decode_envelope_handles_url_encoded() -> None:
    raw = _encode_body(
        {
            "result": {"code": "CF-00000", "message": "성공"},
            "data": {"commUniqeNo": "123", "resViolationStatus": "위반건축물"},
        }
    )
    env = decode_envelope(raw)
    assert env.is_success
    assert env.code == "CF-00000"
    assert env.data_dict()["resViolationStatus"] == "위반건축물"


# ---------------------------------------------------------------------------
# (a) 전유부 1차 CF-03002 → 자동매칭 → 2차 CF-00000
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exclusive_two_way_auto_match_happy_path() -> None:
    first = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "추가인증"},
                "data": {
                    "continue2Way": True,
                    "jobIndex": 0,
                    "threadIndex": 0,
                    "jti": "jti-1",
                    "twoWayTimestamp": 1700000000,
                    "extraInfo": {
                        "reqSecureNo": "",
                        "reqAddrList": [
                            {
                                "commAddrLotNumber": "서울 강남구 역삼동 1",
                                "commAddrRoadName": "서울 강남구 테헤란로 1",
                            }
                        ],
                        "reqDongNumList": [
                            {"commDongNum": "101", "reqDong": "제101동"}
                        ],
                        "reqHoNumList": [
                            {"commHoNum": "1503", "reqHo": "1503호", "reqArea": "84"}
                        ],
                    },
                },
            }
        )
    )
    second = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-00000", "message": "성공"},
                "data": {
                    "commUniqeNo": "U-1",
                    "resViolationStatus": "위반건축물",
                    "resOwnedList": [{"resType": "0", "resArea": "84"}],
                    "resOriGinalData": "PDFBASE64",
                    "resOwnerList": [{"resOwner": "홍길동"}],  # PII — 파싱 안 됨.
                },
            }
        )
    )
    client, fake = _make_client([first, second])
    result = await client.fetch_exclusive_part(
        BuildingRegisterQuery(road_addr="서울 강남구 테헤란로 1", dong="101", ho="1503")
    )
    assert isinstance(result, ExclusivePartResult)
    assert result.comm_unique_no == "U-1"
    assert result.violation_status == "위반건축물"
    assert result.original_pdf_base64 == "PDFBASE64"
    # 2차 요청 body 검증: is2Way + dongNum/hoNum + twoWayInfo.
    second_body = fake.product_calls[1]["body"]
    assert second_body["is2Way"] is True
    assert second_body["dongNum"] == "101"
    assert second_body["hoNum"] == "1503"
    assert second_body["twoWayInfo"]["jti"] == "jti-1"
    # 전유부 자격증명 필드명: id/password.
    assert "id" in second_body and "password" in second_body
    # PII 미노출 확인 — ExclusivePartResult 에 owner 필드 자체가 없다.
    assert not hasattr(result, "owner_list")


# ---------------------------------------------------------------------------
# (b) 동·호 복수후보 → CodefNeedsUserInput
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exclusive_multiple_ho_needs_user_input() -> None:
    first = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "추가인증"},
                "data": {
                    "jobIndex": 0,
                    "threadIndex": 0,
                    "jti": "jti-2",
                    "twoWayTimestamp": 1700000001,
                    "extraInfo": {
                        "reqSecureNo": "",
                        "reqAddrList": [
                            {"commAddrLotNumber": "addr", "commAddrRoadName": "road"}
                        ],
                        "reqDongNumList": [{"commDongNum": "101"}],
                        # 사용자가 "1503" 입력했지만 후보가 모호(둘 다 정규화 1503).
                        "reqHoNumList": [
                            {"commHoNum": "1503"},
                            {"commHoNum": "1503호"},
                        ],
                    },
                },
            }
        )
    )
    client, _ = _make_client([first])
    with pytest.raises(CodefNeedsUserInput) as exc:
        await client.fetch_exclusive_part(
            BuildingRegisterQuery(road_addr="road", dong="101", ho="1503")
        )
    assert exc.value.kind == "dong_ho"
    assert exc.value.resume_token


# ---------------------------------------------------------------------------
# (b2) 동 없는 집합건물 — reqHoNumList 만(method=hoNum), 동 비움 → 호 유일매칭 자동 2차.
#      실측 CF-03002(양천로 400-12) 구조: extraInfo 에 reqAddrList/reqDongNumList 가 아예 없다.
#      과거 코드는 주소·동까지 강제해 영구 needs_input 이었다(이 회귀의 핵심 케이스).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exclusive_ho_only_no_dong_auto_match() -> None:
    first = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "성공"},
                "data": {
                    "jobIndex": 0,
                    "threadIndex": 0,
                    "jti": "jti-ho",
                    "twoWayTimestamp": 1781492184739,
                    "continue2Way": True,
                    "method": "hoNum",
                    "extraInfo": {
                        "reqHoNumList": [
                            {"reqHo": "B101", "commHoNum": "X-B101", "reqArea": "90.72"},
                            {"reqHo": "101", "commHoNum": "X-101", "reqArea": "57.96"},
                            {"reqHo": "102", "commHoNum": "X-102", "reqArea": "57.96"},
                        ],
                        "commHoNum": "",
                    },
                },
            }
        )
    )
    second = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-00000", "message": "성공"},
                "data": {"commUniqeNo": "U-HO", "resViolationStatus": ""},
            }
        )
    )
    client, fake = _make_client([first, second])
    result = await client.fetch_exclusive_part(
        BuildingRegisterQuery(road_addr="양천로 400-12", dong="", ho="101")
    )
    assert result.comm_unique_no == "U-HO"
    # 2차는 호만 보낸다 — 없는 축(주소/동)을 임의로 채우지 않는다.
    second_body = fake.product_calls[1]["body"]
    assert second_body["hoNum"] == "X-101"
    assert "dongNum" not in second_body
    assert "reqAddress" not in second_body
    assert second_body["is2Way"] is True


# ---------------------------------------------------------------------------
# (b3) 호 후보가 단일이면 사용자가 호를 비워도 자동선택한다.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exclusive_single_ho_candidate_auto_selected() -> None:
    first = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "성공"},
                "data": {
                    "jti": "jti-single",
                    "method": "hoNum",
                    "extraInfo": {
                        "reqHoNumList": [{"reqHo": "101", "commHoNum": "ONLY"}]
                    },
                },
            }
        )
    )
    second = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-00000", "message": "성공"},
                "data": {"commUniqeNo": "U-SINGLE"},
            }
        )
    )
    client, fake = _make_client([first, second])
    result = await client.fetch_exclusive_part(
        BuildingRegisterQuery(road_addr="road", dong="", ho="")
    )
    assert result.comm_unique_no == "U-SINGLE"
    assert fake.product_calls[1]["body"]["hoNum"] == "ONLY"


# ---------------------------------------------------------------------------
# (b4) 호 복수후보 매칭 실패 → needs_input 에 후보 options 동봉 → selection 으로 재개.
#      같은 번호의 호가 여럿(정규화 충돌)이라 자유입력으론 못 풀고, 사용자가 골라야 한다.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exclusive_ambiguous_ho_surfaces_options_then_resume() -> None:
    first = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "성공"},
                "data": {
                    "jti": "jti-dup",
                    "method": "hoNum",
                    "extraInfo": {
                        "reqHoNumList": [
                            {"reqHo": "101", "commHoNum": "A", "reqArea": "59"},
                            {"reqHo": "101", "commHoNum": "B", "reqArea": "84"},
                        ]
                    },
                },
            }
        )
    )
    second = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-00000", "message": "성공"},
                "data": {"commUniqeNo": "U-PICK"},
            }
        )
    )
    client, fake = _make_client([first, second])
    with pytest.raises(CodefNeedsUserInput) as exc:
        await client.fetch_exclusive_part(
            BuildingRegisterQuery(road_addr="road", dong="", ho="101")
        )
    assert exc.value.kind == "dong_ho"
    assert exc.value.field == "ho"
    # CODEF 후보를 그대로 노출 — 사용자는 면적으로 구분해 고른다.
    values = {opt["value"] for opt in exc.value.options}
    assert values == {"A", "B"}
    assert any(opt.get("area") == "84" for opt in exc.value.options)

    # 사용자가 B(84㎡)를 골라 재개 → 2차는 hoNum=B.
    token = exc.value.resume_token
    result = await client.resume_exclusive_part(token, selection="B")
    assert result.comm_unique_no == "U-PICK"
    assert fake.product_calls[1]["body"]["hoNum"] == "B"


# ---------------------------------------------------------------------------
# (b5) 단계형 2-way — 주소 복수 → 선택 → 2차가 또 CF-03002(호) → 호 단일 자동 → 성공.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exclusive_staged_address_then_ho() -> None:
    first = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "성공"},
                "data": {
                    "jti": "jti-stage1",
                    "method": "reqAddress",
                    "extraInfo": {
                        "reqAddrList": [
                            {"commAddrRoadName": "양천로 400-12", "commAddrLotNumber": "신정동 1"},
                            {"commAddrRoadName": "양천로 400-12", "commAddrLotNumber": "신정동 2"},
                        ]
                    },
                },
            }
        )
    )
    second = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-03002", "message": "성공"},
                "data": {
                    "jti": "jti-stage2",
                    "method": "hoNum",
                    "extraInfo": {"reqHoNumList": [{"reqHo": "101", "commHoNum": "H1"}]},
                },
            }
        )
    )
    third = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-00000", "message": "성공"},
                "data": {"commUniqeNo": "U-STAGE"},
            }
        )
    )
    client, fake = _make_client([first, second, third])
    with pytest.raises(CodefNeedsUserInput) as exc:
        await client.fetch_exclusive_part(
            BuildingRegisterQuery(road_addr="양천로 400-12", dong="", ho="101")
        )
    assert exc.value.field == "address"
    token = exc.value.resume_token
    # 주소 선택 → 2차(reqAddress) → 응답이 또 호 후보(단일) → 자동 3차 → 성공.
    result = await client.resume_exclusive_part(token, selection="신정동 2")
    assert result.comm_unique_no == "U-STAGE"
    assert fake.product_calls[1]["body"]["reqAddress"] == "신정동 2"
    assert fake.product_calls[2]["body"]["hoNum"] == "H1"


# ---------------------------------------------------------------------------
# (c) 표제부 동 직접조회 성공 (2-way 미발생)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_heading_direct_success() -> None:
    resp = _FakeResponse(
        _encode_body(
            {
                "result": {"code": "CF-00000", "message": "성공"},
                "data": {
                    "commUniqeNo": "H-1",
                    "resViolationStatus": "",
                    "resDetailList": [{"resType": "연면적", "resContents": "1000"}],
                    "resBuildingStatusList": [{"resFloor": "1"}],
                    "resOriGinalData": "HEADINGPDF",
                    "resLicenseClassList": [{"resName": "설계자"}],  # PII — 미파싱.
                },
            }
        )
    )
    client, fake = _make_client([resp])
    result = await client.fetch_building_heading(
        BuildingRegisterQuery(road_addr="서울 강남구 테헤란로 1", dong="101", ho="")
    )
    assert result.comm_unique_no == "H-1"
    assert result.detail_list[0]["resContents"] == "1000"
    assert result.original_pdf_base64 == "HEADINGPDF"
    # 표제부 자격증명 필드명: userId/userPassword + dong 직접 전달.
    body = fake.product_calls[0]["body"]
    assert "userId" in body and "userPassword" in body
    assert body["dong"] == "101"


# ---------------------------------------------------------------------------
# (f) CodefAuthError 는 재시도하지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auth_error_does_not_retry() -> None:
    auth_fail = _FakeResponse(
        _encode_body(
            {
                "result": {
                    "code": "CF-12074",
                    "message": "사용자 정보가 일치하지 않습니다. 확인 후 거래하시기 바랍니다.",
                },
                "data": {},
            }
        )
    )
    client, fake = _make_client([auth_fail])
    with pytest.raises(CodefAuthError):
        await client.fetch_exclusive_part(
            BuildingRegisterQuery(road_addr="road", dong="101", ho="1503")
        )
    # 자격증명 오류는 단 1회 제품 호출 후 즉시 중단(재시도 없음).
    assert len(fake.product_calls) == 1


# ---------------------------------------------------------------------------
# RSA 비밀번호 복호화 실패(CF-04020) → AUTH 분류 (dev 스모크 패딩 진단 신호)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rsa_password_decrypt_failure_maps_to_auth() -> None:
    rsa_fail = _FakeResponse(
        _encode_body(
            {
                "result": {
                    "code": "CF-04020",
                    "message": "비밀번호 복호화에 문제가 발생했습니다.",
                },
                "data": {},
            }
        )
    )
    client, fake = _make_client([rsa_fail])
    with pytest.raises(CodefAuthError) as exc:
        await client.fetch_exclusive_part(
            BuildingRegisterQuery(road_addr="road", dong="101", ho="1503")
        )
    assert exc.value.code == "CF-04020"
    assert len(fake.product_calls) == 1
