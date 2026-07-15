"""우리집 체크(home-check) 서비스 — CODEF 전유부+표제부 조회 오케스트레이션 (ADR-0008).

라우터(``routers/home_check``)가 잡 행을 만들고 즉시 202 를 돌려준 뒤, 본 모듈의
백그라운드 처리(``run_home_check`` / ``resume_home_check``)가 **요청과 분리된 새 DB
연결**로 행을 갱신한다(요청 세션 재사용 금지 — 요청 종료 후 실행되기 때문).

판정/직렬화 매핑(행 → ``HomeCheckJob``)도 여기에 둔다.

PII 정책(ADR-0008 §2.3): 소유자/설계자 성명·주민번호·세움터 password 는 DB/로그/Redis
어디에도 저장하지 않는다. CODEF 클라이언트가 이미 이를 미노출하며(types.py), 본 모듈도
``resOwnedList`` 등에서 PII 필드를 읽지 않는다. 발급 PDF 만 Storage 에 원본 보관한다.
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any

import httpx
import redis.asyncio as aioredis
import sqlalchemy as sa

from ..config import Settings, get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..logging import get_logger, log_http_call
from ..models import HomeCheck, HomeCheckDocument
from ..schemas.home_check import (
    AddressInfo,
    BuildingHeading,
    ChangeEntry,
    DocumentRef,
    ErrorInfo,
    ExclusivePart,
    ExtensionCheck,
    HomeCheckJob,
    HomeCheckReport,
    MyHomeChecksResponse,
    NeedsInput,
    NeedsInputOption,
    ReportMeta,
    Violation,
)
from ..services.codef import (
    BuildingHeadingResult,
    BuildingRegisterQuery,
    CodefBuildingRegisterClient,
    CodefError,
    CodefNeedsUserInput,
    ExclusivePartResult,
)
from ..services.home_check_extension import judge_extension

logger = get_logger("zippin.home_check")

DISCLAIMER = (
    "본 결과는 건축물대장 기재사항을 조회 시점 기준으로 제공하는 참고용 정보이며, "
    "위법 여부의 최종 판단은 관할 행정청·전문가 확인이 필요합니다."
)

_VIOLATION_VALUE = "위반건축물"
_SCHEMA_VERSION = "1.2.0"

# 확장 verdict=uncertain 일 때 종합 신호에 덧붙이는 🟡 caution 사유(한국어).
_EXTENSION_UNCERTAIN_CAUTION = (
    "신고하신 확장 내용을 대장 변동사항과 자동으로 대조하지 못했습니다. "
    "변동사항 타임라인을 직접 확인해 주세요."
)

# re-export 로 라우터가 services 경유로 응답 모델을 쓰게 한다(기존 컨벤션 유지).
__all__ = ["MyHomeChecksResponse"]

# 사용자 안전 메시지 — CodefError 종류별 안내. 원자료/자격증명은 절대 노출하지 않는다.
_ERROR_MESSAGES: dict[str, str] = {
    "CodefAuthError": "조회 서비스 인증에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "CodefCircuitOpen": "조회 서비스가 일시적으로 혼잡합니다. 잠시 후 다시 시도해 주세요.",
    "CodefUpstreamError": "건축물대장 시스템(세움터) 점검 또는 지연으로 조회에 실패했습니다.",
    "CodefNotFound": "입력하신 주소·동·호에 해당하는 건축물대장을 찾지 못했습니다.",
    "CodefInvalidInput": "입력하신 주소 형식이 올바르지 않습니다. 다시 확인해 주세요.",
}
_ERROR_CODES: dict[str, str] = {
    "CodefAuthError": "UPSTREAM_AUTH",
    "CodefCircuitOpen": "UPSTREAM_BUSY",
    "CodefUpstreamError": "UPSTREAM_UNAVAILABLE",
    "CodefNotFound": "NOT_FOUND",
    "CodefInvalidInput": "INVALID_ADDRESS",
}


# ---------------------------------------------------------------------------
# 잡 행 생성 / 조회 (요청 경로 — pooler engine).
# ---------------------------------------------------------------------------
async def create_home_check(
    *,
    user_id: uuid.UUID,
    is_anonymous: bool,
    road_addr: str,
    jibun_addr: str | None,
    dong: str,
    ho: str,
    reported_extension: bool | None = None,
    extended_areas: str | None = None,
) -> dict[str, Any]:
    """우리집 체크 잡 한 건을 status='querying' 으로 생성한다."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.insert(HomeCheck)
                .values(
                    user_id=user_id,
                    is_anonymous=is_anonymous,
                    status="querying",
                    road_addr=road_addr,
                    jibun_addr=jibun_addr,
                    addr_dong=dong or None,
                    addr_ho=ho,
                    reported_extension=reported_extension,
                    extended_areas=extended_areas,
                )
                .returning(
                    HomeCheck.id,
                    HomeCheck.status,
                    HomeCheck.created_at,
                    HomeCheck.updated_at,
                )
            )
        ).one()
    return dict(row._mapping)


async def find_reusable_home_check(
    *,
    user_id: uuid.UUID,
    road_addr: str,
    dong: str,
    ho: str,
) -> dict[str, Any] | None:
    """같은 입력(소유자+도로명+동+호)으로 아직 진행 중(querying/needs_input)인 잡을
    돌려준다(없으면 None).

    에이전트 도구가 잡 생성 후 결과 체크포인트 전에 끊겨 같은 tool call 이 replay 되면
    create_home_check 가 동일 주소로 또 하나의 querying 잡을 만들고 느린 CODEF 작업을
    중복 실행한다. 진행 중 잡이 있으면 그것을 재사용해 멱등하게 만든다(#codef-idempotent).
    completed/failed(terminal)은 매칭하지 않으므로 재조회는 정상적으로 새 잡을 만든다.
    """

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(HomeCheck)
                .where(
                    HomeCheck.user_id == user_id,
                    HomeCheck.road_addr == road_addr,
                    HomeCheck.addr_dong == (dong or None),
                    HomeCheck.addr_ho == ho,
                    HomeCheck.status.in_(("querying", "needs_input")),
                )
                .order_by(HomeCheck.created_at.desc())
                .limit(1)
            )
        ).first()
    return dict(row._mapping) if row else None


async def get_home_check_row(
    *, home_check_id: uuid.UUID, user_id: uuid.UUID
) -> dict[str, Any] | None:
    """소유자(user_id) 본인의 잡 한 건을 조회한다. 타인/없음 → None."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(HomeCheck).where(
                    HomeCheck.id == home_check_id,
                    HomeCheck.user_id == user_id,
                )
            )
        ).first()
    return dict(row._mapping) if row else None


async def list_home_checks_for_user(*, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """본인(user_id)의 우리집 체크 이력을 최신순으로 조회한다(마이페이지)."""

    async with get_engine().begin() as conn:
        rows = (
            await conn.execute(
                sa.select(HomeCheck)
                .where(HomeCheck.user_id == user_id)
                .order_by(HomeCheck.created_at.desc())
                .limit(100)
            )
        ).all()
    return [dict(row._mapping) for row in rows]


async def _load_documents(conn: Any, home_check_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await conn.execute(
            sa.select(
                HomeCheckDocument.kind,
                HomeCheckDocument.bucket,
                HomeCheckDocument.object_path,
            ).where(HomeCheckDocument.home_check_id == home_check_id)
        )
    ).all()
    return [dict(row._mapping) for row in rows]


async def get_home_check_documents(*, home_check_id: uuid.UUID) -> list[dict[str, Any]]:
    async with get_engine().begin() as conn:
        return await _load_documents(conn, home_check_id)


# ---------------------------------------------------------------------------
# 백그라운드 처리 — 새 DB 연결로 행을 갱신한다(요청 세션 재사용 금지).
#
# TODO(워커 타임아웃): 1차 조회가 최대 300s 까지 걸려 gunicorn/uvicorn 워커 타임아웃에
# 걸릴 수 있다. v1 은 BackgroundTasks(같은 워커 프로세스)로 수용하되, 출시 후 부하/타임아웃
# 지표를 보고 전용 큐(예: Redis 큐 + 별도 워커)로 분리한다.
# ---------------------------------------------------------------------------
# 2-way resume 토큰·OAuth 토큰·서킷 상태를 **백그라운드 잡과 /continue 재개 사이**에서
# 공유해야 한다(요청마다 새 클라이언트가 생성되므로). in-process dict 폴백이면 토큰을
# 저장한 클라이언트가 폐기된 뒤 resume 가 항상 만료로 떨어진다 → 프로세스 공유 Redis 사용.
_codef_redis: aioredis.Redis | None = None
_worker_warmup_lock: asyncio.Lock | None = None
_worker_warmup_last_attempt = 0.0
_WORKER_WARMUP_COOLDOWN_SECONDS = 45.0


def _get_codef_redis() -> aioredis.Redis:
    """프로세스 공유 async Redis(지연 생성). OAuth state store 와 동일 URL 규칙."""

    global _codef_redis
    if _codef_redis is None:
        settings = get_settings()
        url = settings.codef_token_redis_url or settings.redis_url
        _codef_redis = aioredis.from_url(url)
    return _codef_redis


def _new_client() -> CodefBuildingRegisterClient:
    """백그라운드 처리용 건축물대장 클라이언트 — 공유 Redis(토큰/2-way/서킷)를 주입한다.

    ``seumteo_enabled`` 면 세움터 직결 클라이언트(CODEF 대체, ADR-0009)를, 아니면 CODEF
    클라이언트를 만든다. 둘은 동형 인터페이스(fetch_exclusive_part/resume_exclusive_part/
    fetch_building_heading + codef.types 결과)라 호출부·판정·PDF 저장은 무변경이다.

    테스트는 ``src.services.home_check._new_client`` 를 monkeypatch 해 외부 호출을 막는다.
    """

    settings = get_settings()
    if getattr(settings, "seumteo_enabled", False):
        from ..services.seumteo import SeumteoBuildingRegisterClient

        return SeumteoBuildingRegisterClient(  # type: ignore[return-value]
            settings, redis_client=_get_codef_redis()
        )
    return CodefBuildingRegisterClient(settings, redis_client=_get_codef_redis())


async def warm_home_check_worker() -> None:
    """우리집 체크 화면 진입 시 scale-to-zero 세움터 worker를 best-effort로 준비한다.

    실제 발급 경로도 ``SeumteoBuildingRegisterClient._run_job``에서 ready를 다시 확인하므로,
    이 background warm-up이 아직 끝나지 않은 상태로 사용자가 즉시 제출해도 안전하다.
    """

    global _worker_warmup_lock, _worker_warmup_last_attempt
    if _worker_warmup_lock is None:
        _worker_warmup_lock = asyncio.Lock()

    async with _worker_warmup_lock:
        now = time.monotonic()
        if now - _worker_warmup_last_attempt < _WORKER_WARMUP_COOLDOWN_SECONDS:
            logger.info("home_check_worker_warmup_skipped", reason="cooldown")
            return
        _worker_warmup_last_attempt = now

    client = _new_client()
    warmup = getattr(client, "warmup", None)
    if not callable(warmup):
        return
    try:
        await warmup()
        logger.info("home_check_worker_warmed")
    except CodefError as exc:
        # 화면 진입 warm-up 실패는 조회 자체를 막지 않는다. 제출 시 ready 가드가 재시도하고,
        # 그 결과만 잡 상태에 반영한다.
        logger.info("home_check_worker_warmup_failed", error=type(exc).__name__)
    except Exception:  # noqa: BLE001 — warm-up은 best-effort.
        logger.warning("home_check_worker_warmup_unexpected", exc_info=True)


def _use_bundle(client: Any) -> bool:
    """통합 잡(전유부+표제부 1회) 사용 여부 — 플래그 on + 클라이언트가 지원할 때만.

    CODEF 클라이언트는 fetch_bundle 이 없어 자동으로 순차 경로를 탄다."""

    return bool(getattr(get_settings(), "seumteo_bundle_enabled", False)) and callable(
        getattr(client, "fetch_bundle", None)
    )


async def run_home_check(
    home_check_id: uuid.UUID,
    *,
    road_addr: str,
    jibun_addr: str | None,
    dong: str,
    ho: str,
) -> None:
    """1차 조회(전유부+표제부) 백그라운드 처리."""

    client = _new_client()
    query = BuildingRegisterQuery(
        road_addr=road_addr, dong=dong, ho=ho, jibun_addr=jibun_addr
    )
    if _use_bundle(client):
        await _process(home_check_id, bundle_factory=lambda: client.fetch_bundle(query))
        return
    await _process(
        home_check_id,
        exclusive_factory=lambda: client.fetch_exclusive_part(query),
        heading_factory=lambda: client.fetch_building_heading(query),
    )


async def resume_home_check(
    home_check_id: uuid.UUID,
    *,
    resume_token: str,
    selection: str | None,
    dong: str | None,
    ho: str | None,
    secure_no: str | None,
    other_road_addr: str,
    other_jibun_addr: str | None,
    other_dong: str,
    other_ho: str,
) -> None:
    """needs_input 재개 — 전유부 resume + 표제부 재조회.

    needs_input(추가입력)은 **전유부에서만** 발생한다 — 표제부는 best-effort 라
    2-way 자동매칭 실패를 사용자 재질문 대신 caution 으로 흡수한다(``_process``).
    따라서 재개는 항상 전유부 resume 이고, 표제부는 정상 fetch 로 다시 시도한다.
    """

    client = _new_client()
    query = BuildingRegisterQuery(
        road_addr=other_road_addr,
        dong=other_dong,
        ho=other_ho,
        jibun_addr=other_jibun_addr,
    )
    if _use_bundle(client) and callable(getattr(client, "resume_bundle", None)):
        await _process(
            home_check_id,
            bundle_factory=lambda: client.resume_bundle(
                resume_token,
                selection=selection,
                dong=dong,
                ho=ho,
                secure_no=secure_no,
            ),
        )
        return
    await _process(
        home_check_id,
        exclusive_factory=lambda: client.resume_exclusive_part(
            resume_token, selection=selection, dong=dong, ho=ho, secure_no=secure_no
        ),
        heading_factory=lambda: client.fetch_building_heading(query),
    )


async def _process(
    home_check_id: uuid.UUID,
    *,
    exclusive_factory: Any = None,
    heading_factory: Any = None,
    bundle_factory: Any = None,
) -> None:
    """전유부+표제부 조회를 수행하고 결과/예외를 행에 반영한다.

    전유부는 핵심 신호이므로 먼저 await 한다. 전유부가 일찍 종료(needs_input/오류)하면
    표제부 조회는 시작조차 하지 않는다(coroutine 은 factory 로 지연 생성). 표제부 조회
    실패는 치명이 아니라 caution 사유로만 반영한다(ADR-0008 §2.4 신호등).

    ``bundle_factory`` 가 주어지면 두 대장을 워커 통합 잡 1회로 받는다 — 반환
    ``(exclusive, heading|None, heading_error)`` 는 순차 경로와 동일한 의미이고,
    needs_input(공유 해석 단계에서 발생)은 전유부와 같은 예외로 온다.
    """

    if bundle_factory is not None:
        try:
            exclusive, heading, heading_error = await bundle_factory()
        except CodefNeedsUserInput as exc:
            await _mark_needs_input(home_check_id, exc, product="exclusive")
            return
        except CodefError as exc:
            await _mark_failed(home_check_id, exc)
            return
        except Exception:  # noqa: BLE001 — 예기치 못한 오류도 안전 메시지로 마감.
            await _mark_unexpected(home_check_id)
            return
        await _mark_completed(
            home_check_id, exclusive, heading, heading_error=heading_error
        )
        return

    # 전유부 — needs_input/오류면 즉시 행 반영 후 종료.
    try:
        exclusive = await exclusive_factory()
    except CodefNeedsUserInput as exc:
        await _mark_needs_input(home_check_id, exc, product="exclusive")
        return
    except CodefError as exc:
        await _mark_failed(home_check_id, exc)
        return
    except Exception:  # noqa: BLE001 — 예기치 못한 오류도 안전 메시지로 마감.
        await _mark_unexpected(home_check_id)
        return

    # 표제부 — best-effort. 모든 실패(2-way 추가입력 포함)를 caution 으로 흡수한다.
    # needs_input 까지 사용자에게 되묻지 않는 이유: ① 표제부는 건물 위반표시 보조신호일
    # 뿐이고(ADR-0008 §2.4), ② 전유부에서 이미 주소·동·호를 받았는데 표제부 때문에 또
    # 묻는 건 UX 후퇴이며, ③ 전유부·표제부가 둘 다 주소 모호일 때 재질문이 서로 맞물려
    # 루프가 된다. heading=None → "건물 위반표시 미확인" caution 사유로 표시된다.
    heading: BuildingHeadingResult | None = None
    heading_error = False
    try:
        heading = await heading_factory()
    except CodefError:  # CodefNeedsUserInput(서브클래스) 포함.
        heading_error = True
    except Exception:  # noqa: BLE001
        heading_error = True

    await _mark_completed(
        home_check_id, exclusive, heading, heading_error=heading_error
    )


# ---------------------------------------------------------------------------
# 판정 (정본 — ADR-0008 §2 / 작업지시 판정 규칙).
# ---------------------------------------------------------------------------
def _judge(
    exclusive: ExclusivePartResult, heading: BuildingHeadingResult | None
) -> tuple[bool, bool, bool, str, list[str]]:
    """(exclusive_violation, heading_violation, violation, signal, caution_reasons)."""

    exclusive_violation = exclusive.violation_status == _VIOLATION_VALUE
    heading_violation = (
        heading is not None and heading.violation_status == _VIOLATION_VALUE
    )
    violation = exclusive_violation or heading_violation

    caution_reasons: list[str] = []
    if violation:
        signal = "violation"
    else:
        if heading is None:
            caution_reasons.append(
                "건물 전체(표제부) 위반표시를 확인하지 못했습니다. 별도 확인이 필요합니다."
            )
        if _exclusive_core_missing(exclusive):
            caution_reasons.append(
                "전유부 핵심 정보(전유면적/구조 등)를 확인하지 못했습니다."
            )
        signal = "caution" if caution_reasons else "normal"
    return exclusive_violation, heading_violation, violation, signal, caution_reasons


def _exclusive_core_missing(exclusive: ExclusivePartResult) -> bool:
    summary = _summarize_exclusive(exclusive)
    return summary.area_m2 is None and summary.use_type is None


# ---------------------------------------------------------------------------
# 요약 추출 (PII-free).
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _summarize_exclusive(exclusive: ExclusivePartResult) -> ExclusivePart:
    """resOwnedList 중 resType=='0'(전유부분) 첫 행에서 면적/용도/구조/층 추출."""

    for item in exclusive.owned:
        if str(item.get("resType")) == "0":
            return ExclusivePart(
                area_m2=_to_float(item.get("resArea")),
                use_type=_str_or_none(item.get("resUseType")),
                structure=_str_or_none(item.get("resStructure")),
                floor=_str_or_none(item.get("resFloor")),
            )
    return ExclusivePart()


# detail_list(resContents)에서 추출할 항목명 — 공백/※ 변형을 관용한다.
_HEADING_KEYS = {
    "main_use": ("주용도",),
    "floors": ("층수",),
    "approval_date": ("사용승인일",),
    "permit_date": ("허가일",),
}


def _normalize_label(label: Any) -> str:
    return str(label or "").replace("※", "").replace(" ", "").strip()


def _summarize_heading(heading: BuildingHeadingResult) -> BuildingHeading:
    extracted: dict[str, str | None] = {
        "main_use": None,
        "floors": None,
        "approval_date": None,
        "permit_date": None,
    }
    for item in heading.detail_list:
        label = _normalize_label(item.get("resType"))
        contents = _str_or_none(item.get("resContents"))
        if contents is None:
            continue
        for field, candidates in _HEADING_KEYS.items():
            if extracted[field] is not None:
                continue
            for cand in candidates:
                if label == _normalize_label(cand):
                    extracted[field] = contents
                    break
    return BuildingHeading(
        main_use=extracted["main_use"],
        floors=extracted["floors"],
        approval_date=extracted["approval_date"],
        permit_date=extracted["permit_date"],
        comm_unique_no=heading.comm_unique_no,
    )


def _merge_change_history(
    exclusive: ExclusivePartResult, heading: BuildingHeadingResult | None
) -> list[ChangeEntry]:
    entries: list[ChangeEntry] = []
    for item in exclusive.change_list:
        reason = _str_or_none(item.get("resChangeReason"))
        if reason is None:
            continue
        entries.append(
            ChangeEntry(
                date=_str_or_none(item.get("resChangeDate")),
                reason=reason,
                source="exclusive",
            )
        )
    if heading is not None:
        for item in heading.change_list:
            reason = _str_or_none(item.get("resChangeReason"))
            if reason is None:
                continue
            entries.append(
                ChangeEntry(
                    date=_str_or_none(item.get("resChangeDate")),
                    reason=reason,
                    source="heading",
                )
            )
    return entries


# 서식 라벨/필러 골자 — 구 워커가 변동 이력으로 잘못 승격했던 문구(읽기 시점 정화용).
_CHANGE_LABEL_CORES = (
    "이하여백",
    "사용승인일",
    "허가일",
    "착공일",
    "변동내용및원인",
    "변동내용",
    "변동원인",
    "변동일자",
    "변동일",
    "변동사항",
    "그밖의기재사항",
)
# 짧아도 실질인 변동 키워드("증축" 단독 행 보존).
_CHANGE_KEYWORDS = (
    "신규작성",
    "신축",
    "증축",
    "개축",
    "재축",
    "대수선",
    "용도변경",
    "행위허가",
    "사용검사",
    "직권",
    "말소",
    "위반건축물",
    "표시변경",
)


def _present_change_history(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """저장된 change_list 의 표시 전 정화 — 구 워커가 남긴 절단 중복·필러 행을 걷어낸다.

    새 워커(PDF 텍스트 파싱)는 깨끗한 행을 저장하지만, 이미 저장된 세션(공유 링크로
    재열람되는 리포트)도 타임라인이 읽혀야 하므로 직렬화 시점에 방어적으로 정리한다.
    같은 행의 절단본(숫자 보존 키가 한쪽에 포함)은 더 긴 사유로 붕괴한다. DB 원본은 불변.
    """

    cleaned: list[dict[str, Any]] = []
    keys: list[str] = []
    for entry in entries:
        reason = str(entry.get("reason") or "")
        # "이하여백"은 셀 끝 표식 — 그 뒤는 이웃 셀 잡음이므로 절단.
        cut = reason.find("이하여백")
        if cut >= 0:
            reason = reason[:cut]
        reason = re.sub(r"^[\d.,\-)\s]+", "", reason).strip(" ,-")
        core = re.sub(r"[^가-힣A-Za-z]", "", reason)
        for label in _CHANGE_LABEL_CORES:
            core = core.replace(label, "")
        if len(core) < 4 and not any(kw in core for kw in _CHANGE_KEYWORDS):
            continue
        key = re.sub(r"[^가-힣A-Za-z0-9]", "", reason)
        date_value = entry.get("date")
        merged = False
        for i, kept in enumerate(cleaned):
            if date_value and kept.get("date") and date_value != kept["date"]:
                continue
            if key != keys[i] and key not in keys[i] and keys[i] not in key:
                continue
            if len(key) > len(keys[i]):
                kept["reason"] = reason
                keys[i] = key
            if not kept.get("date"):
                kept["date"] = date_value
            merged = True
            break
        if not merged:
            cleaned.append({**entry, "reason": reason})
            keys.append(key)
    return cleaned


def _parse_date(value: Any) -> date | None:
    text = _str_or_none(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# 행 갱신 (백그라운드 — 새 연결).
# ---------------------------------------------------------------------------
async def _load_extension_input(
    home_check_id: uuid.UUID,
) -> tuple[bool | None, str | None]:
    """확장 판정 입력(reported_extension/extended_areas)만 좁게 읽는다(PII 아님)."""

    async with get_engine().begin() as conn:
        row = (
            await conn.execute(
                sa.select(
                    HomeCheck.reported_extension,
                    HomeCheck.extended_areas,
                ).where(HomeCheck.id == home_check_id)
            )
        ).first()
    if row is None:
        return None, None
    return row.reported_extension, row.extended_areas


async def _mark_completed(
    home_check_id: uuid.UUID,
    exclusive: ExclusivePartResult,
    heading: BuildingHeadingResult | None,
    *,
    heading_error: bool,
) -> None:
    (
        exclusive_violation,
        heading_violation,
        violation,
        signal,
        caution_reasons,
    ) = _judge(exclusive, heading)

    exclusive_summary = _summarize_exclusive(exclusive)
    heading_summary = _summarize_heading(heading) if heading is not None else None
    change_history = _merge_change_history(exclusive, heading)

    # 확장 신고 ↔ 변동사항 LLM 대조(별개 축). 기능 게이트가 꺼져 있으면(default) 판정을
    # 건너뛰어 extension_check 는 없고 신호는 공식 축(_judge) 그대로다 — OpenAI 의존 없음.
    # 공식 노란딱지 축(exclusive_violation/heading_violation/violation)은 절대 건드리지
    # 않고, 종합 signal 과 caution_reasons 에만 확장 verdict 를 접는다.
    extension_check: dict[str, Any] | None = None
    settings = get_settings()
    if settings.extension_judge_enabled:
        reported_extension, extended_areas = await _load_extension_input(home_check_id)
        # 판정 입력은 **전유부(unit)** 변동사항만 쓴다. 신고 확장은 이 세대(전유부)에 대한 것이고,
        # 표제부(건물/공용) 변동은 다른 세대·공용부 변동일 수 있어, 섞으면 무관한 표제부 변동을
        # 이 세대 확장의 '등재'로 오인(→미등재를 legal 로 오판)할 수 있다(#ext-unit-scope).
        unit_changes = [e for e in change_history if e.source == "exclusive"]
        judgment = await judge_extension(
            reported_extension=reported_extension,
            extended_areas=extended_areas,
            change_history=unit_changes,
            settings=settings,
        )
        if judgment is not None:
            extension_check = {
                "verdict": judgment.verdict,
                "reason": judgment.reason,
                "reported_areas": judgment.reported_areas,
                "matched_areas": judgment.matched_areas,
                "unrecorded_areas": judgment.unrecorded_areas,
            }
            if judgment.verdict == "uncertain":
                caution_reasons = [*caution_reasons, _EXTENSION_UNCERTAIN_CAUTION]
            # 공식 violation 은 불변. signal 만 재계산해 확장 verdict 를 접는다.
            if violation or judgment.verdict == "violation":
                signal = "violation"
            elif caution_reasons or judgment.verdict == "uncertain":
                signal = "caution"
            else:
                signal = "normal"

    # PDF 보관(best-effort) — 실패해도 잡은 completed 로 둔다(문서 링크만 생략).
    await _store_pdfs(home_check_id, exclusive, heading)

    values: dict[str, Any] = {
        "status": "completed",
        "signal": signal,
        "exclusive_violation": exclusive_violation,
        "heading_violation": heading_violation,
        "violation": violation,
        "exclusive_area_m2": exclusive_summary.area_m2,
        "exclusive_use_type": exclusive_summary.use_type,
        "exclusive_structure": exclusive_summary.structure,
        "exclusive_floor": exclusive_summary.floor,
        "comm_unique_no": exclusive.comm_unique_no,
        "heading_comm_unique_no": heading.comm_unique_no if heading else None,
        "res_doc_no": exclusive.res_doc_no,
        "heading_res_doc_no": heading.res_doc_no if heading else None,
        "res_issue_date": _parse_date(exclusive.issue_date),
        "change_list": [e.model_dump(mode="json") for e in change_history],
        "result_fields": {
            "caution_reasons": caution_reasons,
            "extension_check": extension_check,
        },
        "error_code": None,
        "error_message": None,
        "queried_at": datetime.now(timezone.utc),
    }
    if heading_summary is not None:
        values["building_main_use"] = heading_summary.main_use
        values["building_floors"] = heading_summary.floors
        values["building_approval_date"] = _parse_date(heading_summary.approval_date)
        values["building_permit_date"] = _parse_date(heading_summary.permit_date)

    await _update_row(home_check_id, values)
    logger.info(
        "home_check_completed",
        home_check_id=str(home_check_id),
        signal=signal,
        violation=violation,
        heading_error=heading_error,
    )


async def _mark_needs_input(
    home_check_id: uuid.UUID, exc: CodefNeedsUserInput, *, product: str
) -> None:
    await _update_row(
        home_check_id,
        {
            "status": "needs_input",
            # resume_token 은 PII 가 아니다(1차 결과 복원용 핸들) — 보안문자 이미지 등 PII 는
            # 저장하지 않는다. field/options 는 CODEF 후보(주소/동/호)로, 프론트가 드롭다운으로
            # 제시한다(동·호 번호 자체는 PII 가 아님).
            "result_fields": {
                "resume_token": exc.resume_token,
                "product": product,
                "kind": exc.kind,
                "message": exc.message,
                "field": exc.field,
                "options": exc.options,
            },
            "queried_at": datetime.now(timezone.utc),
        },
    )
    logger.info(
        "home_check_needs_input",
        home_check_id=str(home_check_id),
        product=product,
        kind=exc.kind,
        field=exc.field,
        option_count=len(exc.options or []),
    )


async def _mark_failed(home_check_id: uuid.UUID, exc: CodefError) -> None:
    name = type(exc).__name__
    code = _ERROR_CODES.get(name, "UPSTREAM_UNAVAILABLE")
    message = _ERROR_MESSAGES.get(
        name, "조회에 실패했습니다. 잠시 후 다시 시도해 주세요."
    )
    await _update_row(
        home_check_id,
        {
            "status": "failed",
            "error_code": code,
            "error_message": message,
            "queried_at": datetime.now(timezone.utc),
        },
    )
    # 원자료/자격증명은 로깅하지 않는다 — 예외 타입과 잡 id 만 남긴다.
    logger.warning(
        "home_check_failed",
        home_check_id=str(home_check_id),
        error=name,
        error_code=code,
    )


async def _mark_unexpected(home_check_id: uuid.UUID) -> None:
    await _update_row(
        home_check_id,
        {
            "status": "failed",
            "error_code": "INTERNAL_ERROR",
            "error_message": "조회 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "queried_at": datetime.now(timezone.utc),
        },
    )
    logger.warning("home_check_unexpected_error", home_check_id=str(home_check_id))


async def reset_for_resume(home_check_id: uuid.UUID) -> None:
    """needs_input 잡을 querying 으로 되돌린다(continue 백그라운드 재개 전).

    signal_requires_completed CHECK 때문에 signal 은 항상 null 인 상태이므로 status 만
    바꾼다. resume_token 등 result_fields 는 재개 호출이 끝나며 _mark_* 가 덮어쓴다.
    """

    await _update_row(home_check_id, {"status": "querying"})


async def _update_row(home_check_id: uuid.UUID, values: dict[str, Any]) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            sa.update(HomeCheck).where(HomeCheck.id == home_check_id).values(**values)
        )


# ---------------------------------------------------------------------------
# PDF 보관 (Supabase Storage, service_role) — best-effort.
# ---------------------------------------------------------------------------
def _storage_base(settings: Settings) -> str | None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return settings.supabase_url.rstrip("/") + "/storage/v1"


async def _store_pdfs(
    home_check_id: uuid.UUID,
    exclusive: ExclusivePartResult,
    heading: BuildingHeadingResult | None,
) -> None:
    settings = get_settings()
    base = _storage_base(settings)
    if base is None:
        return

    bucket = settings.home_check_doc_bucket
    targets: list[tuple[str, str, str | None]] = [
        ("exclusive_part", "exclusive_part.pdf", exclusive.original_pdf_base64),
    ]
    if heading is not None:
        targets.append(
            ("building_heading", "building_heading.pdf", heading.original_pdf_base64)
        )

    for kind, filename, pdf_b64 in targets:
        if not pdf_b64:
            continue
        try:
            raw = base64.b64decode(pdf_b64)
        except (ValueError, TypeError):
            logger.warning(
                "home_check_pdf_decode_failed",
                home_check_id=str(home_check_id),
                kind=kind,
            )
            continue
        object_path = f"{home_check_id}/{filename}"
        try:
            await _upload_pdf(
                settings,
                base=base,
                bucket=bucket,
                object_path=object_path,
                raw=raw,
            )
        except Exception:  # noqa: BLE001
            # 업로드 실패는 치명 아님 — 문서 링크만 생략하고 리포트는 완료한다.
            logger.warning(
                "home_check_pdf_upload_failed",
                home_check_id=str(home_check_id),
                kind=kind,
            )
            continue
        await _insert_document(
            home_check_id=home_check_id,
            kind=kind,
            bucket=bucket,
            object_path=object_path,
            byte_size=len(raw),
        )


async def _upload_pdf(
    settings: Settings,
    *,
    base: str,
    bucket: str,
    object_path: str,
    raw: bytes,
) -> None:
    url = f"{base}/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
        "Content-Type": "application/pdf",
        "x-upsert": "true",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(url, content=raw, headers=headers)

    response = await log_http_call("supabase_storage", "upload_home_check_pdf", _do)
    if response.status_code not in (200, 201):
        raise ZippinException(
            "PDF 업로드에 실패했습니다.",
            code="STORAGE_UPLOAD_FAILED",
            http_status=502,
        )


async def _insert_document(
    *,
    home_check_id: uuid.UUID,
    kind: str,
    bucket: str,
    object_path: str,
    byte_size: int,
) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            sa.insert(HomeCheckDocument).values(
                home_check_id=home_check_id,
                kind=kind,
                bucket=bucket,
                object_path=object_path,
                byte_size=byte_size,
            )
        )


async def _sign_document_url(
    settings: Settings, *, bucket: str, object_path: str
) -> str | None:
    """단기(1h) 서명 다운로드 URL 을 발급한다. 실패하면 None(링크만 생략)."""

    base = _storage_base(settings)
    if base is None:
        return None
    url = f"{base}/object/sign/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
        "Content-Type": "application/json",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(url, json={"expiresIn": 3600}, headers=headers)

    try:
        response = await log_http_call("supabase_storage", "sign_home_check_pdf", _do)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        signed = response.json().get("signedURL")
    except ValueError:
        return None
    if not signed:
        return None
    return settings.supabase_url.rstrip("/") + "/storage/v1" + signed


# ---------------------------------------------------------------------------
# 직렬화 — 행(dict) → HomeCheckJob / HomeCheckReport.
# ---------------------------------------------------------------------------
def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


async def serialize_job(
    row: dict[str, Any], *, with_documents: bool = True
) -> HomeCheckJob:
    """행을 ``HomeCheckJob`` 으로 직렬화한다.

    completed → report, needs_input → needs_input, failed → error 를 채운다.
    ``with_documents`` 가 False 면 문서 서명 URL 발급(외부 호출)을 생략한다(목록용).
    """

    status = row["status"]
    job_kwargs: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "id": str(row["id"]),
        "status": status,
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }

    if status == "completed":
        job_kwargs["signal"] = row.get("signal")
        job_kwargs["report"] = await _build_report(row, with_documents=with_documents)
    elif status == "needs_input":
        fields = row.get("result_fields") or {}
        raw_options = fields.get("options") or None
        options = (
            [NeedsInputOption(**opt) for opt in raw_options] if raw_options else None
        )
        job_kwargs["needs_input"] = NeedsInput(
            kind=fields.get("kind") or "dong_ho",
            message=fields.get("message") or "추가 입력이 필요합니다.",
            field=fields.get("field"),
            options=options,
        )
    elif status == "failed":
        job_kwargs["error"] = ErrorInfo(
            code=row.get("error_code") or "UPSTREAM_UNAVAILABLE",
            message=row.get("error_message")
            or "조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return HomeCheckJob(**job_kwargs)


async def _build_report(
    row: dict[str, Any], *, with_documents: bool
) -> HomeCheckReport:
    signal = row.get("signal") or "normal"
    fields = row.get("result_fields") or {}
    caution_reasons = fields.get("caution_reasons") or None

    address = AddressInfo(
        road_addr=row.get("road_addr"),
        jibun_addr=row.get("jibun_addr"),
        dong=row.get("addr_dong"),
        ho=row.get("addr_ho"),
    )
    violation = Violation(
        is_violation=bool(row.get("violation")),
        exclusive=row.get("exclusive_violation"),
        heading=row.get("heading_violation"),
        raw=_VIOLATION_VALUE if row.get("violation") else None,
    )

    exclusive_part = None
    if any(
        row.get(k) is not None
        for k in (
            "exclusive_area_m2",
            "exclusive_use_type",
            "exclusive_structure",
            "exclusive_floor",
        )
    ):
        exclusive_part = ExclusivePart(
            area_m2=(
                float(row["exclusive_area_m2"])
                if row.get("exclusive_area_m2") is not None
                else None
            ),
            use_type=row.get("exclusive_use_type"),
            structure=row.get("exclusive_structure"),
            floor=row.get("exclusive_floor"),
        )

    building = None
    if any(
        row.get(k) is not None
        for k in (
            "building_main_use",
            "building_floors",
            "building_approval_date",
            "building_permit_date",
            "heading_comm_unique_no",
        )
    ):
        building = BuildingHeading(
            main_use=row.get("building_main_use"),
            floors=row.get("building_floors"),
            approval_date=_iso(row.get("building_approval_date")),
            permit_date=_iso(row.get("building_permit_date")),
            comm_unique_no=row.get("heading_comm_unique_no"),
        )

    change_history = [
        ChangeEntry(**entry)
        for entry in _present_change_history(row.get("change_list") or [])
    ] or None

    raw_extension = fields.get("extension_check")
    extension_check = ExtensionCheck(**raw_extension) if raw_extension else None

    documents = None
    if with_documents:
        documents = await _report_documents(row)

    meta = ReportMeta(
        comm_unique_no=row.get("comm_unique_no"),
        res_doc_no=row.get("res_doc_no"),
        issue_date=_iso(row.get("res_issue_date")),
        queried_at=_iso(row.get("queried_at")),
    )

    return HomeCheckReport(
        signal=signal,
        violation=violation,
        address=address,
        exclusive_part=exclusive_part,
        building=building,
        change_history=change_history,
        extension_check=extension_check,
        documents=documents,
        caution_reasons=caution_reasons,
        meta=meta,
        disclaimer=DISCLAIMER,
    )


async def _report_documents(row: dict[str, Any]) -> list[DocumentRef] | None:
    docs = await get_home_check_documents(home_check_id=row["id"])
    if not docs:
        return None
    settings = get_settings()
    refs: list[DocumentRef] = []
    for doc in docs:
        url = await _sign_document_url(
            settings, bucket=doc["bucket"], object_path=doc["object_path"]
        )
        refs.append(DocumentRef(kind=doc["kind"], url=url))
    return refs
