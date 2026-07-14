"""세움터 워커를 호출하는 인하우스 클라이언트 (CODEF 클라이언트와 동형 인터페이스).

``home_check._new_client`` 이 ``CodefBuildingRegisterClient`` 대신 이걸 생성한다. 세 async
메서드(``fetch_exclusive_part``/``resume_exclusive_part``/``fetch_building_heading``)와 생성자
시그니처가 CODEF 와 동일하므로 오케스트레이터·테스트는 무변경이다.

세움터 워커 응답(JSON, models.BuildingRegisterResult 형)은 codef.types 결과 dataclass 로
매핑한다. 오류 category 는 CODEF 예외로 승격한다:
    auth→CodefAuthError, not_found→CodefNotFound, invalid→CodefInvalidInput,
    upstream→CodefUpstreamError, needs_input→CodefNeedsUserInput.

세움터 password/자격증명은 이 프로세스에 없다 — 워커(Fly secrets)만 보유한다.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any

import httpx
import redis.asyncio as redis
import structlog
from redis.exceptions import RedisError

from ..codef.circuit import CodefCircuitBreaker
from ..codef.types import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefAuthError,
    CodefError,
    CodefInvalidInput,
    CodefNeedsUserInput,
    CodefNotFound,
    CodefUpstreamError,
    ExclusivePartResult,
)

_log = structlog.get_logger(__name__)

_JOB_PATH = "/jobs/building-register"
_BUNDLE_PATH = "/jobs/building-register-bundle"
_HEALTH_PATH = "/healthz"
_RESUME_PREFIX = "seumteo:resume:"
_RESUME_TTL = 600


class SeumteoBuildingRegisterClient:
    def __init__(
        self,
        settings: Any,
        *,
        redis_client: redis.Redis | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client
        self._http = http_client
        self._wake_url = str(getattr(settings, "seumteo_worker_url", "") or "").rstrip(
            "/"
        )
        self._job_url = str(
            getattr(settings, "seumteo_worker_job_url", "") or self._wake_url
        ).rstrip("/")
        self._token = getattr(settings, "seumteo_worker_token", None)
        self._timeout = float(getattr(settings, "seumteo_worker_timeout_seconds", 180))
        self._bundle_timeout = float(
            getattr(settings, "seumteo_worker_bundle_timeout_seconds", 240)
        )
        self._warmup_timeout = float(
            getattr(settings, "seumteo_worker_warmup_timeout_seconds", 45)
        )
        self._warmup_poll = float(
            getattr(settings, "seumteo_worker_warmup_poll_seconds", 2)
        )
        self._breaker = CodefCircuitBreaker(
            error_threshold=settings.codef_breaker_error_threshold,
            window_seconds=settings.codef_breaker_window_seconds,
            open_seconds=settings.codef_breaker_open_seconds,
            redis_client=redis_client,
        )

    # ------------------------------------------------------------------
    # 전유부
    # ------------------------------------------------------------------
    async def fetch_exclusive_part(
        self, query: BuildingRegisterQuery
    ) -> ExclusivePartResult:
        if not query.road_addr.strip():
            raise CodefInvalidInput("도로명주소가 비어 있습니다.")
        data = await self._run_job(query, register_kind="exclusive")
        return _to_exclusive(data)

    async def resume_exclusive_part(
        self,
        resume_token: str,
        *,
        selection: str | None = None,
        dong: str | None = None,
        ho: str | None = None,
        secure_no: str | None = None,
    ) -> ExclusivePartResult:
        query = await self._resume_query(resume_token, selection, dong, ho)
        data = await self._run_job(query, register_kind="exclusive")
        return _to_exclusive(data)

    async def _resume_query(
        self,
        resume_token: str,
        selection: str | None,
        dong: str | None,
        ho: str | None,
    ) -> BuildingRegisterQuery:
        # 세움터 직결은 ES 유일매칭으로 2-way 가 거의 없다. needs_input 이 났던 경우에만
        # 저장 ctx 를 복원해 사용자가 고른 동/호(selection)로 재조회한다.
        ctx = await self._load_resume(resume_token)
        pending = ctx.get("field")
        # 사용자가 고른 값(selection). pending 축이 주소/동/호 어느 것이든 반영한다
        # (address 축을 빠뜨리면 원래 모호한 주소로 재조회돼 무한 재질문이 된다).
        chosen = selection or (
            ho if pending == "ho" else dong if pending == "dong" else None
        )
        road_addr = (chosen if pending == "address" else ctx.get("road_addr")) or ""
        if not road_addr.strip():
            raise CodefInvalidInput("도로명주소가 비어 있습니다.")
        return BuildingRegisterQuery(
            road_addr=road_addr,
            dong=(chosen if pending == "dong" else dong or ctx.get("dong") or ""),
            ho=(chosen if pending == "ho" else ho or ctx.get("ho") or ""),
            jibun_addr=ctx.get("jibun_addr"),
        )

    # ------------------------------------------------------------------
    # 표제부
    # ------------------------------------------------------------------
    async def fetch_building_heading(
        self, query: BuildingRegisterQuery
    ) -> BuildingHeadingResult:
        if not query.road_addr.strip():
            raise CodefInvalidInput("도로명주소가 비어 있습니다.")
        data = await self._run_job(query, register_kind="heading")
        return _to_heading(data)

    # ------------------------------------------------------------------
    # 통합 잡 (전유부+표제부 1회)
    # ------------------------------------------------------------------
    async def fetch_bundle(
        self, query: BuildingRegisterQuery
    ) -> tuple[ExclusivePartResult, BuildingHeadingResult | None, bool]:
        """전유부+표제부를 워커 통합 잡 1회로 조회한다.

        반환 ``(exclusive, heading|None, heading_error)`` — ``_process`` 의 순차 경로와
        동일한 의미(전유부 오류는 예외 전파, 표제부 실패는 caution 플래그). 구 워커
        (bundle 엔드포인트 부재, 404/405)면 기존 단건 2회 순차 호출로 내부 폴백한다.
        """

        if not query.road_addr.strip():
            raise CodefInvalidInput("도로명주소가 비어 있습니다.")
        if not self._wake_url or not self._job_url:
            raise CodefUpstreamError("세움터 워커 URL이 설정되지 않았습니다.")
        await self._breaker.ensure_closed()
        await self._ensure_worker_ready()

        payload = {
            "road_addr": query.road_addr.strip(),
            "dong": (query.dong or "").strip(),
            "ho": (query.ho or "").strip(),
            "jibun_addr": query.jibun_addr,
        }
        headers = self._worker_headers()
        headers["Content-Type"] = "application/json"
        resp = await self._post_raw(
            _BUNDLE_PATH, payload, headers, self._bundle_timeout
        )
        if resp.status_code in (404, 405):
            # 구 워커 배포(엔드포인트 없음) — 기존 단건 2회 순차 경로로 폴백(롤아웃 안전).
            _log.info("seumteo.bundle_endpoint_missing")
            return await self._fetch_bundle_sequential(query)
        data = self._parse_worker_response(resp)

        ex_env = data.get("exclusive") or {}
        head_env = data.get("heading") or {}
        _log.info(
            "seumteo.bundle_response",
            exclusive_ok=ex_env.get("ok"),
            heading_ok=head_env.get("ok"),
            exclusive_category=ex_env.get("category"),
            heading_category=head_env.get("category"),
        )

        if not ex_env.get("ok"):
            # 오류 봉투 → 예외 승격은 단건과 동일(_run_job 의 auth 서킷 카운트 포함).
            try:
                await self._raise_for_error(ex_env, query)
            except CodefAuthError:
                await self._breaker.record_auth_failure()
                raise
            raise CodefUpstreamError("세움터 응답 분류 실패")  # unreachable
        await self._breaker.record_success()
        exclusive = _to_exclusive(ex_env)

        heading: BuildingHeadingResult | None = None
        heading_error = False
        if head_env.get("ok"):
            heading = _to_heading(head_env)
        else:
            heading_error = True
        return exclusive, heading, heading_error

    async def resume_bundle(
        self,
        resume_token: str,
        *,
        selection: str | None = None,
        dong: str | None = None,
        ho: str | None = None,
        secure_no: str | None = None,
    ) -> tuple[ExclusivePartResult, BuildingHeadingResult | None, bool]:
        """needs_input 재개의 통합 잡 판 — resume 은 무상태 재조회라 그대로 성립한다."""

        query = await self._resume_query(resume_token, selection, dong, ho)
        return await self.fetch_bundle(query)

    async def _fetch_bundle_sequential(
        self, query: BuildingRegisterQuery
    ) -> tuple[ExclusivePartResult, BuildingHeadingResult | None, bool]:
        exclusive = _to_exclusive(
            await self._run_job(query, register_kind="exclusive")
        )
        heading: BuildingHeadingResult | None = None
        heading_error = False
        try:
            heading = _to_heading(await self._run_job(query, register_kind="heading"))
        except CodefError:
            heading_error = True
        except Exception:  # noqa: BLE001 — 표제부는 best-effort(_process 순차 경로와 동일).
            heading_error = True
        return exclusive, heading, heading_error

    # ------------------------------------------------------------------
    # 워커 호출
    # ------------------------------------------------------------------
    async def warmup(self) -> None:
        """scale-to-zero worker를 깨우고 Chromium 준비까지 기다린다.

        Flycast URL은 stopped machine을 autostart하지만 긴 발급 요청은 프록시 시간 제한에
        걸릴 수 있다. 따라서 화면 진입 warm-up과 실제 조회 직전 모두 이 가드를 거친 뒤,
        발급은 ``.internal`` job URL로 보낸다.
        """

        await self._ensure_worker_ready()

    async def _run_job(
        self, query: BuildingRegisterQuery, *, register_kind: str
    ) -> dict[str, Any]:
        if not self._wake_url or not self._job_url:
            raise CodefUpstreamError("세움터 워커 URL이 설정되지 않았습니다.")
        await self._breaker.ensure_closed()
        await self._ensure_worker_ready()

        payload = {
            "road_addr": query.road_addr.strip(),
            "dong": (query.dong or "").strip(),
            "ho": (query.ho or "").strip(),
            "jibun_addr": query.jibun_addr,
            "register_kind": register_kind,
        }
        headers = self._worker_headers()
        headers["Content-Type"] = "application/json"

        # 워커 토큰 401(인프라 오류)은 세움터 계정 서킷과 무관 — _post 가 upstream 으로 낸다.
        # 계정 자격증명 실패(로그인 실패)는 워커가 body category=="auth" 로 주고, 그것만
        # 아래 _raise_for_error 경로에서 서킷에 카운트한다.
        data = await self._post(payload, headers)

        _log.info(
            "seumteo.response",
            register_kind=register_kind,
            ok=data.get("ok"),
            category=data.get("category"),
            extraction=data.get("extraction"),
        )

        if data.get("ok"):
            await self._breaker.record_success()
            return data
        # 오류 봉투 → 예외. 워커 본문 auth 오류(로그인 실패)도 서킷에 카운트한다
        # (단일 세움터 계정 보호 — 자격증명 오류 누적 시 차단).
        try:
            await self._raise_for_error(data, query)
        except CodefAuthError:
            await self._breaker.record_auth_failure()
            raise
        raise CodefUpstreamError("세움터 응답 분류 실패")  # unreachable

    def _worker_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _ensure_worker_ready(self) -> None:
        if not self._wake_url:
            raise CodefUpstreamError("세움터 워커 URL이 설정되지 않았습니다.")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(1.0, self._warmup_timeout)
        attempt = 0
        last_error = "not_ready"
        _log.info("seumteo.warmup_started")

        while loop.time() < deadline:
            attempt += 1
            remaining = max(0.1, deadline - loop.time())
            # 첫 cold-start 연결이 Flycast 프록시에서 오래 붙들리지 않게 짧게 끊고 재시도한다.
            request_timeout = min(8.0, remaining)
            try:
                response = await self._health_probe(request_timeout)
                body = response.json() if response.is_success else {}
                if response.is_success and body.get("ok") and body.get("browser"):
                    _log.info("seumteo.warmup_ready", attempt=attempt)
                    return
                last_error = f"http_{response.status_code}"
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc.__class__.__name__

            delay = min(max(0.1, self._warmup_poll), max(0.0, deadline - loop.time()))
            if delay:
                await asyncio.sleep(delay)

        _log.warning("seumteo.warmup_timeout", attempts=attempt, error=last_error)
        raise CodefUpstreamError("세움터 조회 준비 시간이 초과되었습니다.")

    async def _health_probe(self, timeout: float) -> httpx.Response:
        url = f"{self._wake_url}{_HEALTH_PATH}"
        headers = self._worker_headers()
        if self._http is not None:
            return await self._http.get(url, headers=headers, timeout=timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.get(url, headers=headers)

    async def _post(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        resp = await self._post_raw(_JOB_PATH, payload, headers, self._timeout)
        return self._parse_worker_response(resp)

    async def _post_raw(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        url = f"{self._job_url}{path}"

        try:
            if self._http is not None:
                # 주입된 클라이언트(테스트/공유 풀)는 자체 타임아웃을 따른다.
                return await self._http.post(url, json=payload, headers=headers)
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise CodefUpstreamError("세움터 워커 응답 시간 초과.") from exc
        except httpx.HTTPError as exc:
            raise CodefUpstreamError("세움터 워커 호출에 실패했습니다.") from exc

    def _parse_worker_response(self, resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code == 401:
            # 워커 토큰 불일치 = api 설정 오류(인프라). 세움터 계정 인증 실패가 아니므로
            # auth 가 아니라 upstream 으로 낸다(계정 서킷브레이커 오트립 방지).
            raise CodefUpstreamError("세움터 워커 인증 실패(토큰 확인).")
        if resp.status_code >= 500:
            raise CodefUpstreamError("세움터 워커 오류.", code=str(resp.status_code))
        if resp.status_code >= 400:
            raise CodefUpstreamError(
                "세움터 워커 요청 거부.", code=str(resp.status_code)
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise CodefUpstreamError("세움터 워커 응답을 해석할 수 없습니다.") from exc

    async def _raise_for_error(
        self, data: dict[str, Any], query: BuildingRegisterQuery
    ) -> None:
        category = data.get("category")
        message = data.get("message") or "세움터 조회에 실패했습니다."
        if category == "auth":
            raise CodefAuthError(message)
        if category == "not_found":
            raise CodefNotFound(message)
        if category == "invalid":
            raise CodefInvalidInput(message)
        if category == "needs_input":
            # needs_input = 로그인 성공 후 추가입력 단계 → 서킷 성공으로 리셋(CODEF 동일).
            await self._breaker.record_success()
            token = await self._save_resume(query, data.get("field"))
            # options 는 계약(NeedsInputOption: value/label/area?) 로 정규화한다 —
            # 워커가 여분 키를 주면 serialize_job 의 NeedsInputOption(extra="forbid") 가
            # GET 응답에서 500 나므로 여기서 걸러낸다.
            raise CodefNeedsUserInput(
                "dong_ho",
                token,
                message,
                field=data.get("field"),  # type: ignore[arg-type]
                options=_normalize_options(data.get("options")),
            )
        raise CodefUpstreamError(message)

    # ------------------------------------------------------------------
    # resume ctx (needs_input 시에만) — 평문 자격증명 없음.
    # ------------------------------------------------------------------
    async def _save_resume(
        self, query: BuildingRegisterQuery, field: str | None
    ) -> str:
        token = secrets.token_urlsafe(24)
        payload = {
            "road_addr": query.road_addr,
            "jibun_addr": query.jibun_addr,
            "dong": query.dong,
            "ho": query.ho,
            "field": field,
        }
        raw = json.dumps(payload, ensure_ascii=False)
        if self._redis is not None:
            try:
                await self._redis.set(f"{_RESUME_PREFIX}{token}", raw, ex=_RESUME_TTL)
            except RedisError:
                pass
        return token

    async def _load_resume(self, token: str) -> dict[str, Any]:
        if self._redis is not None:
            try:
                raw = await self._redis.get(f"{_RESUME_PREFIX}{token}")
            except RedisError:
                raw = None
            if raw is not None:
                text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                return json.loads(text)
        raise CodefError("추가입력 세션이 만료되었습니다. 처음부터 다시 시도해 주세요.")


# ---------------------------------------------------------------------------
# 워커 응답(dict) → codef.types 결과 dataclass
# ---------------------------------------------------------------------------
def _s(v: Any) -> str | None:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def _list(v: Any) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _normalize_options(raw: Any) -> list[dict] | None:
    """워커 후보 → 계약 NeedsInputOption shape {value, label, area?} 로 정규화."""

    if not isinstance(raw, list):
        return None
    out: list[dict] = []
    for o in raw:
        if isinstance(o, dict) and o.get("value") is not None:
            out.append(
                {
                    "value": str(o["value"]),
                    "label": str(o.get("label") or o["value"]),
                    "area": o.get("area"),
                }
            )
    return out or None


def _to_exclusive(d: dict[str, Any]) -> ExclusivePartResult:
    return ExclusivePartResult(
        res_doc_no=_s(d.get("res_doc_no")),
        comm_unique_no=_s(d.get("comm_unique_no")),
        addr_dong=_s(d.get("addr_dong")),
        addr_ho=_s(d.get("addr_ho")),
        res_user_addr=_s(d.get("res_user_addr")),
        road_addr=_s(d.get("road_addr")),
        jibun_addr=_s(d.get("jibun_addr")),
        owned=_list(d.get("owned")),
        change_list=_list(d.get("change_list")),
        price_list=_list(d.get("price_list")),
        violation_status=_s(d.get("violation_status")),
        issue_date=_s(d.get("issue_date")),
        issue_org=_s(d.get("issue_org")),
        original_pdf_base64=_s(d.get("original_pdf_base64")),
    )


def _to_heading(d: dict[str, Any]) -> BuildingHeadingResult:
    return BuildingHeadingResult(
        res_doc_no=_s(d.get("res_doc_no")),
        comm_unique_no=_s(d.get("comm_unique_no")),
        res_user_addr=_s(d.get("res_user_addr")),
        detail_list=_list(d.get("detail_list")),
        building_status_list=_list(d.get("building_status_list")),
        change_list=_list(d.get("change_list")),
        violation_status=_s(d.get("violation_status")),
        issue_date=_s(d.get("issue_date")),
        issue_org=_s(d.get("issue_org")),
        original_pdf_base64=_s(d.get("original_pdf_base64")),
    )


__all__ = ["SeumteoBuildingRegisterClient"]
