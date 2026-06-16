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
    FIELD_ORDER,
    MAX_OPTIONS,
    ResumeStore,
    candidate_value,
    field_candidates,
    field_options,
    field_param_key,
    has_secure_no,
    resolve_candidate,
    select_message,
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

# CODEF 2-way 는 단계형일 수 있다(주소 선택 → 응답이 또 동 후보 → …). 같은 잡 안에서
# 자동매칭으로 여러 단계를 이어갈 수 있게 루프를 돌되, 무한루프 방지 상한을 둔다.
_MAX_TWO_WAY_ROUNDS = 6

# result.code 기반 오류 분류는 error_codes.classify(정본 표) 를 1순위로 쓰고,
# 미등록 코드만 메시지 substring 으로 보수적 보강한다.
_AUTH_FAIL_HINTS = (
    "로그인",
    "아이디",
    "비밀번호",
    "패스워드",
    "인증서",
    "잠금",
    "계정",
)
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
            raise CodefAuthError(
                envelope.message or "세움터 로그인에 실패했습니다.", code=code
            )
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
            raise CodefAuthError(
                envelope.message or "세움터 로그인에 실패했습니다.", code=code
            )
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
            "codef.unclassified_error",
            operation=operation,
            code=code,
            message=envelope.message,
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
            _EXCLUSIVE_PATH,
            body,
            operation="exclusive_first",
            timeout=self._first_timeout,
        )
        if envelope.is_success:
            return _parse_exclusive(envelope.data_dict())

        # CF-03002 → method 기반 자동매칭 루프.
        data = await self._drive_two_way(
            product="exclusive",
            path=_EXCLUSIVE_PATH,
            operation="exclusive_two_way",
            first_body=body,
            data=envelope.data_dict(),
            dong=query.dong,
            ho=query.ho,
        )
        return _parse_exclusive(data)

    async def resume_exclusive_part(
        self,
        resume_token: str,
        *,
        selection: str | None = None,
        dong: str | None = None,
        ho: str | None = None,
        secure_no: str | None = None,
    ) -> ExclusivePartResult:
        ctx = await self._resume.load(resume_token)
        first_body = self._rebuild_credentials(ctx["first_body"], product="exclusive")
        # 보안문자만 재개하는 경우 동·호가 안 올 수 있다 → 1차에 저장한 값으로 보강.
        dong = dong or ctx.get("dong") or ""
        ho = ho or ctx.get("ho") or ""
        data = await self._drive_two_way(
            product="exclusive",
            path=_EXCLUSIVE_PATH,
            operation="exclusive_resume",
            first_body=first_body,
            data=_resume_data(ctx),
            dong=dong,
            ho=ho,
            resolved=ctx.get("resolved") or {},
            selections=_resume_selections(ctx, selection),
            secure_no=secure_no,
        )
        return _parse_exclusive(data)

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

        data = await self._drive_two_way(
            product="heading",
            path=_HEADING_PATH,
            operation="heading_two_way",
            first_body=body,
            data=envelope.data_dict(),
            dong=query.dong,
            ho="",
        )
        return _parse_heading(data)

    # 참고: 표제부는 best-effort 라 home-check 오케스트레이터가 2-way 추가입력을 caution 으로
    # 흡수한다(사용자 재질문 안 함). 따라서 heading 전용 resume 진입점은 두지 않는다 —
    # 재개는 전유부(resume_exclusive_part)에서만 일어난다.

    # ------------------------------------------------------------------
    # 2-way 자동매칭 루프 (전유부/표제부 공용) — method/후보 기반 (ADR-0008 §2.2).
    #
    # CODEF 는 1차 CF-03002 에서 **그때 필요한 축만**(주소/동/호 중 일부) 후보로 돌려준다.
    # (실측: 동 없는 집합건물은 reqHoNumList 만, method="hoNum".) 따라서 세 축을 한꺼번에
    # 요구하지 않고 **응답에 실제로 존재하는 축만** 자동확정한다. 단일후보는 자동선택,
    # 동·호는 사용자 입력으로 유일매칭, 확정 불가면 후보를 실어 needs_input 으로 폴백한다.
    # 2차 응답이 또 CF-03002(단계형)면 다음 축으로 루프를 이어간다.
    # ------------------------------------------------------------------
    async def _drive_two_way(
        self,
        *,
        product: str,
        path: str,
        operation: str,
        first_body: dict[str, Any],
        data: dict[str, Any],
        dong: str,
        ho: str,
        resolved: dict[str, Any] | None = None,
        selections: dict[str, str] | None = None,
        secure_no: str | None = None,
    ) -> dict[str, Any]:
        extra = data.get("extraInfo") or {}
        two_way_info = _extract_two_way_info(data)
        resolved = dict(resolved or {})
        selections = dict(selections or {})

        for _ in range(_MAX_TWO_WAY_ROUNDS):
            present = [f for f in FIELD_ORDER if field_candidates(extra, f)]
            secure_needed = has_secure_no(extra)
            _log_two_way_step(product, extra, present, secure_needed=secure_needed)

            if secure_needed and not secure_no:
                token = await self._save_resume(
                    product, first_body, extra, two_way_info, resolved, dong=dong, ho=ho
                )
                raise CodefNeedsUserInput(
                    "secure_no", token, "보안문자를 입력해 주세요."
                )

            if not present and not secure_needed:
                # 2-way 인데 처리할 후보 축도 보안문자도 없다 → 분류 불가.
                _log.warning("codef.two_way_unresolvable", product=product)
                raise CodefUpstreamError("추가인증 응답을 해석할 수 없습니다.")

            # acc = 지금까지 확정된 후보 축 파라미터(이전 라운드/재개 선택 포함). 같은 응답에
            # 여러 축이 모호할 때, 앞 축을 확정한 뒤 뒤 축에서 needs_input 이 나도 앞 선택을
            # 잃지 않도록 acc 를 저장한다(저장 후 재개하면 이미 확정된 축은 다시 묻지 않음).
            acc: dict[str, Any] = dict(resolved)
            for field in present:
                key = field_param_key(field)
                if key in acc:
                    continue  # 이전 라운드/재개에서 이미 확정 — 다시 매칭/질문하지 않는다.
                candidates = field_candidates(extra, field)
                chosen = resolve_candidate(
                    field,
                    candidates,
                    dong=dong,
                    ho=ho,
                    selected_value=selections.get(field),
                )
                if chosen is None:
                    token = await self._save_resume(
                        product,
                        first_body,
                        extra,
                        two_way_info,
                        acc,  # 이번 라운드에서 앞서 확정한 축까지 보존.
                        pending_field=field,
                        dong=dong,
                        ho=ho,
                    )
                    options = field_options(candidates, field)
                    if len(candidates) > MAX_OPTIONS:
                        _log.warning(
                            "codef.two_way_options_truncated",
                            product=product,
                            field=field,
                            total=len(candidates),
                            kept=len(options),
                        )
                    _log.info(
                        "codef.two_way_needs_input",
                        product=product,
                        field=field,
                        candidate_count=len(candidates),
                    )
                    raise CodefNeedsUserInput(
                        "dong_ho",
                        token,
                        select_message(field),
                        field=field,  # type: ignore[arg-type]
                        options=options,
                    )
                acc[key] = candidate_value(field, chosen)

            resolved = acc  # 다음 (단계형) 라운드로 누적.
            selections = {}

            round_params = dict(acc)
            if secure_needed:
                round_params["secureNo"] = (
                    secure_no  # 일회성 — resolved 엔 넣지 않는다.
                )
                refresh = extra.get("reqSecureNoRefresh")
                if refresh:
                    round_params["secureNoRefresh"] = refresh
                secure_no = None

            body = {
                **first_body,
                **round_params,
                "is2Way": True,
                "twoWayInfo": two_way_info,
            }
            envelope = await self._request_guarded(
                path, body, operation=operation, timeout=self._two_way_timeout
            )
            if envelope.is_success:
                return envelope.data_dict()
            if not envelope.is_two_way:
                raise CodefNotFound(
                    "2차 조회 결과를 찾을 수 없습니다.", code=envelope.code
                )
            # 단계형 — 다음 라운드의 후보/세션으로 갱신.
            data = envelope.data_dict()
            extra = data.get("extraInfo") or {}
            two_way_info = _extract_two_way_info(data)

        raise CodefUpstreamError(
            "추가인증 단계가 예상보다 많습니다. 잠시 후 다시 시도해 주세요."
        )

    # ------------------------------------------------------------------
    # resume 토큰 저장/복원 — 평문 password 는 저장하지 않는다.
    # ------------------------------------------------------------------
    async def _save_resume(
        self,
        product: str,
        first_body: dict[str, Any],
        extra: dict[str, Any],
        two_way_info: dict[str, Any],
        resolved: dict[str, Any],
        *,
        pending_field: str | None = None,
        dong: str = "",
        ho: str = "",
    ) -> str:
        # 자격증명(password/암호화값)은 토큰 payload 에서 제거 — resume 시 재구성한다.
        sanitized = {
            k: v
            for k, v in first_body.items()
            if k not in ("password", "userPassword", "id", "userId")
        }
        # 1차에 입력한 동·호는 first_body 가 아니라 별도 보존(보안문자 재개 시 재매칭용).
        payload = {
            "product": product,
            "first_body": sanitized,
            "extra_info": extra,
            "two_way_info": two_way_info,
            "resolved": resolved,
            # 사용자에게 물은 축 — resume 의 selection 이 이 축에 적용된다.
            "pending_field": pending_field,
            "dong": dong or sanitized.get("dong") or "",
            "ho": ho,
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
def _log_two_way_step(
    product: str,
    extra: dict[str, Any],
    present: list[str],
    *,
    secure_needed: bool,
) -> None:
    """2-way 한 라운드의 후보 구조를 비-PII 로 남긴다.

    어느 축(주소/동/호)이 후보로 왔는지·개수·보안문자 발생을 기록한다 — 운영에서
    needs_input 이 왜 떴는지(축/개수)를 추적할 수 있게 한다. 동·호 **값**은 PII 소지라
    남기지 않고 개수만 남긴다.
    """

    _log.info(
        "codef.two_way_step",
        product=product,
        present_fields=present,
        secure_no=secure_needed,
        addr_candidates=len(extra.get("reqAddrList") or []),
        dong_candidates=len(extra.get("reqDongNumList") or []),
        ho_candidates=len(extra.get("reqHoNumList") or []),
        secure_no_refresh=bool(extra.get("reqSecureNoRefresh")),
    )


def _extract_two_way_info(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobIndex": data.get("jobIndex"),
        "threadIndex": data.get("threadIndex"),
        "jti": data.get("jti"),
        "twoWayTimestamp": data.get("twoWayTimestamp"),
    }


def _resume_data(ctx: dict[str, Any]) -> dict[str, Any]:
    """resume ctx(저장된 1차 컨텍스트) → _drive_two_way 가 받는 data dict 로 복원한다."""

    two_way_info = ctx.get("two_way_info") or {}
    return {"extraInfo": ctx.get("extra_info") or {}, **two_way_info}


def _resume_selections(ctx: dict[str, Any], selection: str | None) -> dict[str, str]:
    """사용자가 고른 selection 을 1차에 물었던 축(pending_field)에 매핑한다."""

    field = ctx.get("pending_field")
    if selection and field:
        return {field: selection}
    return {}


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
