"""CODEF 집합건축물대장 전유부+표제부 오케스트레이터 (ADR-0008).

``CodefBuildingRegisterClient`` 가 토큰 발급 → 제품 API POST → 봉투 분류 →
(필요 시) 2-way 자동매칭/2차 호출 → 결과 파싱까지 묶는다. 전유부와 표제부는
loginType=1 자격증명 **필드명이 다르다**(전유부 id/password, 표제부 userId/userPassword).

평문 password 는 ``_build_credentials`` 에서만 잠깐 만들어 RSA 암호화 직후 폐기한다 —
로그/Redis/DB 어디에도 평문을 남기지 않는다(ADR-0008 §2.3).
"""

from __future__ import annotations

from typing import Any

import httpx
import redis.asyncio as redis
import structlog

from . import error_codes
from .circuit import CodefCircuitBreaker
from .crypto import encrypt_password
from .token import CodefTokenProvider
from .transport import CodefEnvelope, CodefTransport
from .two_way import (
    ResumeStore,
    has_secure_no,
    match_dong,
    match_ho,
)
from .types import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefAuthError,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    CodefUpstreamError,
    ExclusivePartResult,
)

_log = structlog.get_logger(__name__)

_EXCLUSIVE_PATH = "/v1/kr/public/lt/eais/aggregate-buildings"
_HEADING_PATH = "/v1/kr/public/lt/eais/building-ledger-heading"

# result.code 기반 오류 분류는 error_codes.classify(정본 표) 를 1순위로 쓰고,
# 미등록 코드만 메시지 substring 으로 보수적 보강한다.
_AUTH_FAIL_HINTS = ("로그인", "아이디", "비밀번호", "패스워드", "인증서", "잠금", "계정")
_NOT_FOUND_HINTS = ("없는", "존재하지", "조회되지", "확인되지", "해당", "일치하는")
_UPSTREAM_HINTS = ("점검", "지연", "시간", "timeout", "초과", "서버", "오류가 발생")
_INVALID_HINTS = ("형식", "잘못", "유효하지", "필수", "올바르지")


class CodefBuildingRegisterClient:
    """전유부/표제부 조회 + 2-way resume 를 제공하는 인하우스 CODEF 클라이언트."""

    def __init__(
        self,
        settings: Any,
        *,
        redis_client: redis.Redis | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        base_url = (
            settings.codef_demo_base_url
            if getattr(settings, "codef_use_demo", False)
            else settings.codef_api_base_url
        )
        self._token = CodefTokenProvider(
            oauth_url=settings.codef_oauth_url,
            client_id=settings.codef_client_id,
            client_secret=settings.codef_client_secret,
            redis_client=redis_client,
            http_client=http_client,
        )
        self._transport = CodefTransport(base_url=base_url, http_client=http_client)
        self._breaker = CodefCircuitBreaker(
            error_threshold=settings.codef_breaker_error_threshold,
            window_seconds=settings.codef_breaker_window_seconds,
            open_seconds=settings.codef_breaker_open_seconds,
            redis_client=redis_client,
        )
        self._resume = ResumeStore(redis_client=redis_client)
        self._first_timeout = float(settings.codef_request_timeout_first_seconds)
        self._two_way_timeout = float(settings.codef_request_timeout_two_way_seconds)

    # ------------------------------------------------------------------
    # 자격증명 빌더 — 전유부/표제부 필드명이 다르다.
    # ------------------------------------------------------------------
    def _encrypt_password(self) -> str:
        password = self._settings.seumter_password
        if not password:
            raise CodefAuthError("세움터 계정 자격증명이 설정되지 않았습니다.")
        public_key = self._settings.codef_public_key
        if not public_key:
            raise CodefAuthError("CODEF RSA 공개키가 설정되지 않았습니다.")
        # 평문 password 는 이 지역변수에서만 존재 → 암호화 후 함수 종료로 폐기.
        return encrypt_password(password, public_key)

    def _exclusive_credentials(self) -> dict[str, str]:
        if not self._settings.seumter_id:
            raise CodefAuthError("세움터 계정 자격증명이 설정되지 않았습니다.")
        return {
            "id": self._settings.seumter_id,
            "password": self._encrypt_password(),
        }

    def _heading_credentials(self) -> dict[str, str]:
        if not self._settings.seumter_id:
            raise CodefAuthError("세움터 계정 자격증명이 설정되지 않았습니다.")
        return {
            "userId": self._settings.seumter_id,
            "userPassword": self._encrypt_password(),
        }

    def _base_body(self) -> dict[str, Any]:
        return {
            "organization": self._settings.codef_organization,
            "loginType": "1",
            "originDataYN": "1",
        }

    # ------------------------------------------------------------------
    # 전송 + 봉투 분류 (서킷브레이커 + 토큰 401 재발급 1회).
    # ------------------------------------------------------------------
    async def _request(
        self,
        path: str,
        body: dict[str, Any],
        *,
        operation: str,
        timeout: float,
    ) -> CodefEnvelope:
        await self._breaker.ensure_closed()
        token = await self._token.get_token()
        try:
            envelope = await self._transport.post(
                path,
                body,
                access_token=token,
                operation=operation,
                timeout_seconds=timeout,
            )
        except CodefUpstreamError as exc:
            # 401 = 토큰 만료/무효 → 재발급 후 1회 재시도.
            if exc.code == "401":
                token = await self._token.get_token(force_refresh=True)
                envelope = await self._transport.post(
                    path,
                    body,
                    access_token=token,
                    operation=operation,
                    timeout_seconds=timeout,
                )
            else:
                raise

        # 응답 코드/메시지는 PII 가 아니므로 dev 스모크 진단용으로 남긴다.
        _log.info(
            "codef.response",
            operation=operation,
            code=envelope.code,
            message=envelope.message,
            extra_message=envelope.extra_message,
        )

        if envelope.is_success or envelope.is_two_way:
            await self._breaker.record_success()
            return envelope

        # 오류 봉투 → 도메인 예외 매핑.
        self._raise_for_error(envelope, operation=operation)
        raise CodefUpstreamError("CODEF 응답 분류에 실패했습니다.")  # unreachable

    def _raise_for_error(self, envelope: CodefEnvelope, *, operation: str) -> None:
        message = (envelope.message or "") + " " + (envelope.extra_message or "")
        code = envelope.code or None

        # RSA/암호화 실패는 dev 스모크에서 패딩·공개키를 바로 진단할 수 있게 부각.
        if code in error_codes.RSA_PASSWORD_HINT_CODES:
            _log.warning(
                "codef.rsa_password_decrypt_failed",
                operation=operation,
                code=code,
                message=envelope.message,
                hint="CODEF RSA 공개키/패딩(PKCS1 v1.5) 또는 password URL인코딩을 확인하세요.",
            )

        # 1순위: 정본 코드 표.
        category = error_codes.classify(code)
        if category == error_codes.AUTH:
            raise CodefAuthError(envelope.message or "세움터 로그인에 실패했습니다.", code=code)
        if category == error_codes.NOT_FOUND:
            raise CodefNotFound(
                envelope.message or "해당 건축물대장을 찾을 수 없습니다.", code=code
            )
        if category == error_codes.INVALID:
            raise CodefInvalidInput(
                envelope.message or "입력값이 올바르지 않습니다.", code=code
            )
        if category == error_codes.UPSTREAM:
            raise CodefUpstreamError(
                envelope.message or "세움터 점검 또는 지연입니다.", code=code
            )

        # 2순위(미등록 코드): 메시지 substring 보강.
        def _hit(hints: tuple[str, ...]) -> bool:
            return any(h.lower() in message.lower() for h in hints)

        if _hit(_AUTH_FAIL_HINTS):
            raise CodefAuthError(envelope.message or "세움터 로그인에 실패했습니다.", code=code)
        if _hit(_NOT_FOUND_HINTS):
            raise CodefNotFound(
                envelope.message or "해당 건축물대장을 찾을 수 없습니다.", code=code
            )
        if _hit(_INVALID_HINTS):
            raise CodefInvalidInput(
                envelope.message or "입력값이 올바르지 않습니다.", code=code
            )
        if _hit(_UPSTREAM_HINTS):
            raise CodefUpstreamError(
                envelope.message or "세움터 점검 또는 지연입니다.", code=code
            )
        # 미분류 → 보수적으로 상류 오류로 본다(재시도 가능, 서킷 미카운트).
        # dev 스모크에서 분류 누락을 발견하도록 WARNING.
        _log.warning(
            "codef.unclassified_error", operation=operation, code=code, message=envelope.message
        )
        raise CodefUpstreamError(
            envelope.message or "CODEF 오류가 발생했습니다.", code=code
        )

    async def _request_guarded(
        self,
        path: str,
        body: dict[str, Any],
        *,
        operation: str,
        timeout: float,
    ) -> CodefEnvelope:
        """_request 래퍼 — 자격증명 오류를 서킷에 카운트한다."""

        try:
            return await self._request(path, body, operation=operation, timeout=timeout)
        except CodefAuthError:
            await self._breaker.record_auth_failure()
            raise

    # ------------------------------------------------------------------
    # 전유부
    # ------------------------------------------------------------------
    async def fetch_exclusive_part(
        self, query: BuildingRegisterQuery
    ) -> ExclusivePartResult:
        if not query.road_addr.strip():
            raise CodefInvalidInput("도로명주소가 비어 있습니다.")

        body = {
            **self._base_body(),
            **self._exclusive_credentials(),
            "address": query.road_addr.strip(),
        }
        envelope = await self._request_guarded(
            _EXCLUSIVE_PATH, body, operation="exclusive_first", timeout=self._first_timeout
        )
        if envelope.is_success:
            return _parse_exclusive(envelope.data_dict())

        # CF-03002 → 자동매칭 시도.
        return await self._resolve_exclusive_two_way(
            envelope, body, dong=query.dong, ho=query.ho
        )

    async def _resolve_exclusive_two_way(
        self,
        envelope: CodefEnvelope,
        first_body: dict[str, Any],
        *,
        dong: str,
        ho: str,
    ) -> ExclusivePartResult:
        data = envelope.data_dict()
        extra = data.get("extraInfo") or {}
        two_way_info = _extract_two_way_info(data)
        _log_two_way_shape("exclusive", extra)

        if has_secure_no(extra):
            token = await self._save_resume(
                "exclusive", first_body, data, two_way_info
            )
            raise CodefNeedsUserInput(
                "secure_no", token, "보안문자 입력이 필요합니다."
            )

        addr_choice = _pick_single_address(extra)
        dong_match = match_dong(extra.get("reqDongNumList") or [], dong)
        ho_match = match_ho(extra.get("reqHoNumList") or [], ho)

        if dong_match is None or ho_match is None or addr_choice is None:
            token = await self._save_resume(
                "exclusive", first_body, data, two_way_info
            )
            raise CodefNeedsUserInput(
                "dong_ho", token, "동·호를 선택해 주세요."
            )

        second_body = _build_exclusive_second_body(
            first_body, addr_choice, dong_match, ho_match, two_way_info
        )
        envelope2 = await self._request_guarded(
            _EXCLUSIVE_PATH,
            second_body,
            operation="exclusive_second",
            timeout=self._two_way_timeout,
        )
        if not envelope2.is_success:
            raise CodefNotFound("2차 조회 결과를 찾을 수 없습니다.", code=envelope2.code)
        return _parse_exclusive(envelope2.data_dict())

    async def resume_exclusive_part(
        self,
        resume_token: str,
        *,
        dong: str | None = None,
        ho: str | None = None,
        secure_no: str | None = None,
    ) -> ExclusivePartResult:
        ctx = await self._resume.load(resume_token)
        first_body = self._rebuild_credentials(ctx["first_body"], product="exclusive")
        extra = ctx["extra_info"]
        two_way_info = ctx["two_way_info"]

        addr_choice = _pick_single_address(extra) or _first(extra.get("reqAddrList"))
        dong_match = match_dong(extra.get("reqDongNumList") or [], dong or "")
        ho_match = match_ho(extra.get("reqHoNumList") or [], ho or "")
        if dong_match is None or ho_match is None:
            raise CodefNeedsUserInput("dong_ho", resume_token, "동·호 선택이 유효하지 않습니다.")

        second_body = _build_exclusive_second_body(
            first_body, addr_choice or {}, dong_match, ho_match, two_way_info
        )
        if secure_no:
            second_body["secureNo"] = secure_no
            refresh = extra.get("reqSecureNoRefresh")
            if refresh:
                second_body["secureNoRefresh"] = refresh
        envelope = await self._request_guarded(
            _EXCLUSIVE_PATH,
            second_body,
            operation="exclusive_resume",
            timeout=self._two_way_timeout,
        )
        if not envelope.is_success:
            raise CodefNotFound("2차 조회 결과를 찾을 수 없습니다.", code=envelope.code)
        return _parse_exclusive(envelope.data_dict())

    # ------------------------------------------------------------------
    # 표제부
    # ------------------------------------------------------------------
    async def fetch_building_heading(
        self, query: BuildingRegisterQuery
    ) -> BuildingHeadingResult:
        if not query.road_addr.strip():
            raise CodefInvalidInput("도로명주소가 비어 있습니다.")

        body = {
            **self._base_body(),
            **self._heading_credentials(),
            "address": query.road_addr.strip(),
        }
        if query.dong.strip():
            body["dong"] = query.dong.strip()

        envelope = await self._request_guarded(
            _HEADING_PATH, body, operation="heading_first", timeout=self._first_timeout
        )
        if envelope.is_success:
            return _parse_heading(envelope.data_dict())

        return await self._resolve_heading_two_way(envelope, body, dong=query.dong)

    async def _resolve_heading_two_way(
        self,
        envelope: CodefEnvelope,
        first_body: dict[str, Any],
        *,
        dong: str,
    ) -> BuildingHeadingResult:
        data = envelope.data_dict()
        extra = data.get("extraInfo") or {}
        two_way_info = _extract_two_way_info(data)
        _log_two_way_shape("heading", extra)

        if has_secure_no(extra):
            token = await self._save_resume("heading", first_body, data, two_way_info)
            raise CodefNeedsUserInput("secure_no", token, "보안문자 입력이 필요합니다.")

        addr_choice = _pick_single_address(extra)
        dong_match = match_dong(extra.get("reqDongNumList") or [], dong)
        if dong_match is None or addr_choice is None:
            token = await self._save_resume("heading", first_body, data, two_way_info)
            raise CodefNeedsUserInput("dong_ho", token, "동을 선택해 주세요.")

        second_body = _build_heading_second_body(
            first_body, addr_choice, dong_match, two_way_info
        )
        envelope2 = await self._request_guarded(
            _HEADING_PATH,
            second_body,
            operation="heading_second",
            timeout=self._two_way_timeout,
        )
        if not envelope2.is_success:
            raise CodefNotFound("2차 조회 결과를 찾을 수 없습니다.", code=envelope2.code)
        return _parse_heading(envelope2.data_dict())

    async def resume_building_heading(
        self,
        resume_token: str,
        *,
        dong: str | None = None,
        secure_no: str | None = None,
    ) -> BuildingHeadingResult:
        ctx = await self._resume.load(resume_token)
        first_body = self._rebuild_credentials(ctx["first_body"], product="heading")
        extra = ctx["extra_info"]
        two_way_info = ctx["two_way_info"]

        addr_choice = _pick_single_address(extra) or _first(extra.get("reqAddrList"))
        dong_match = match_dong(extra.get("reqDongNumList") or [], dong or "")
        if dong_match is None:
            raise CodefNeedsUserInput("dong_ho", resume_token, "동 선택이 유효하지 않습니다.")

        second_body = _build_heading_second_body(
            first_body, addr_choice or {}, dong_match, two_way_info
        )
        if secure_no:
            second_body["secureNo"] = secure_no
        envelope = await self._request_guarded(
            _HEADING_PATH,
            second_body,
            operation="heading_resume",
            timeout=self._two_way_timeout,
        )
        if not envelope.is_success:
            raise CodefNotFound("2차 조회 결과를 찾을 수 없습니다.", code=envelope.code)
        return _parse_heading(envelope.data_dict())

    # ------------------------------------------------------------------
    # resume 토큰 저장/복원 — 평문 password 는 저장하지 않는다.
    # ------------------------------------------------------------------
    async def _save_resume(
        self,
        product: str,
        first_body: dict[str, Any],
        data: dict[str, Any],
        two_way_info: dict[str, Any],
    ) -> str:
        # 자격증명(password/암호화값)은 토큰 payload 에서 제거 — resume 시 재구성한다.
        sanitized = {
            k: v
            for k, v in first_body.items()
            if k not in ("password", "userPassword", "id", "userId")
        }
        payload = {
            "product": product,
            "first_body": sanitized,
            "extra_info": data.get("extraInfo") or {},
            "two_way_info": two_way_info,
        }
        return await self._resume.save(payload)

    def _rebuild_credentials(
        self, first_body: dict[str, Any], *, product: str
    ) -> dict[str, Any]:
        body = dict(first_body)
        if product == "exclusive":
            body.update(self._exclusive_credentials())
        else:
            body.update(self._heading_credentials())
        return body


# ---------------------------------------------------------------------------
# 2-way body 빌더 / 후보 선택 헬퍼
# ---------------------------------------------------------------------------
def _log_two_way_shape(product: str, extra: dict[str, Any]) -> None:
    """2-way 후보 구조를 비-PII 로 남긴다 — dev 스모크에서 보안문자 발생·후보 형태 확인용."""

    _log.info(
        "codef.two_way",
        product=product,
        has_secure_no=has_secure_no(extra),
        addr_candidates=len(extra.get("reqAddrList") or []),
        dong_candidates=len(extra.get("reqDongNumList") or []),
        ho_candidates=len(extra.get("reqHoNumList") or []),
        secure_no_refresh=extra.get("reqSecureNoRefresh"),
    )


def _first(seq: Any) -> dict[str, Any] | None:
    if isinstance(seq, list) and seq and isinstance(seq[0], dict):
        return seq[0]
    return None


def _pick_single_address(extra: dict[str, Any]) -> dict[str, Any] | None:
    """reqAddrList 가 단일이면 그 주소를, 복수면 자동선택 불가로 None."""

    addr_list = extra.get("reqAddrList") or []
    if len(addr_list) == 1 and isinstance(addr_list[0], dict):
        return addr_list[0]
    return None


def _extract_two_way_info(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobIndex": data.get("jobIndex"),
        "threadIndex": data.get("threadIndex"),
        "jti": data.get("jti"),
        "twoWayTimestamp": data.get("twoWayTimestamp"),
    }


def _req_address(addr_choice: dict[str, Any]) -> str:
    return str(
        addr_choice.get("commAddrLotNumber")
        or addr_choice.get("commAddrRoadName")
        or ""
    )


def _build_exclusive_second_body(
    first_body: dict[str, Any],
    addr_choice: dict[str, Any],
    dong_match: dict[str, Any],
    ho_match: dict[str, Any],
    two_way_info: dict[str, Any],
) -> dict[str, Any]:
    body = dict(first_body)
    body["reqAddress"] = _req_address(addr_choice)
    body["dongNum"] = str(dong_match.get("commDongNum") or dong_match.get("reqDong") or "")
    body["hoNum"] = str(ho_match.get("commHoNum") or ho_match.get("reqHo") or "")
    body["is2Way"] = True
    body["twoWayInfo"] = two_way_info
    return body


def _build_heading_second_body(
    first_body: dict[str, Any],
    addr_choice: dict[str, Any],
    dong_match: dict[str, Any],
    two_way_info: dict[str, Any],
) -> dict[str, Any]:
    body = dict(first_body)
    body["reqAddress"] = _req_address(addr_choice)
    body["dongNum"] = str(dong_match.get("commDongNum") or dong_match.get("reqDong") or "")
    body["is2Way"] = True
    body["twoWayInfo"] = two_way_info
    return body


# ---------------------------------------------------------------------------
# 결과 파서 — PII(resOwnerList/resLicenseClassList)는 의도적으로 읽지 않는다.
# ---------------------------------------------------------------------------
def _as_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_exclusive(data: dict[str, Any]) -> ExclusivePartResult:
    # 키는 CODEF 출력부 정본(PDF) 기준. 특히 고유번호는 commUniqeNo(철자 'Uniqe'),
    # 동/호는 resAddrDong/resAddrHo, 발급기관은 resIssueOgzNm 임에 유의.
    return ExclusivePartResult(
        res_doc_no=_str_or_none(data.get("resDocNo")),
        comm_unique_no=_str_or_none(data.get("commUniqeNo")),
        addr_dong=_str_or_none(data.get("resAddrDong")),
        addr_ho=_str_or_none(data.get("resAddrHo")),
        res_user_addr=_str_or_none(data.get("resUserAddr")),
        road_addr=_str_or_none(data.get("commAddrRoadName")),
        jibun_addr=_str_or_none(data.get("commAddrLotNumber")),
        owned=_as_list(data.get("resOwnedList")),
        change_list=_as_list(data.get("resChangeList")),
        price_list=_as_list(data.get("resPriceList")),
        violation_status=_str_or_none(data.get("resViolationStatus")),
        issue_date=_str_or_none(data.get("resIssueDate")),
        issue_org=_str_or_none(data.get("resIssueOgzNm")),
        original_pdf_base64=_str_or_none(data.get("resOriGinalData")),
    )


def _parse_heading(data: dict[str, Any]) -> BuildingHeadingResult:
    return BuildingHeadingResult(
        res_doc_no=_str_or_none(data.get("resDocNo")),
        comm_unique_no=_str_or_none(data.get("commUniqeNo")),
        res_user_addr=_str_or_none(data.get("resUserAddr")),
        detail_list=_as_list(data.get("resDetailList")),
        building_status_list=_as_list(data.get("resBuildingStatusList")),
        change_list=_as_list(data.get("resChangeList")),
        violation_status=_str_or_none(data.get("resViolationStatus")),
        issue_date=_str_or_none(data.get("resIssueDate")),
        issue_org=_str_or_none(data.get("resIssueOgzNm")),
        original_pdf_base64=_str_or_none(data.get("resOriGinalData")),
    )


__all__ = ["CodefBuildingRegisterClient"]
