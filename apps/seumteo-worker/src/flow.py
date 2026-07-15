"""세움터 건축물대장 발급 플로우 (브라우저 세션 1개).

1~8단계는 로그인된 eais 페이지 컨텍스트에서 **in-page fetch**(page.evaluate)로 내부 JSON API를
호출한다 — 앱 XHR과 동일 출처·쿠키. payload 는 발급 정찰에서 실측한 값 그대로다
(reference: docs/adr/0009, memory reference_seumteo_issuance_endpoints).

  1) 주소검색   search.eais.go.kr/bldrgstmst/_search        → mgmUpperBldrgstPk(총괄PK)
  2) 동목록     search.eais.go.kr/bldrgsttitle/_search      → 표제부PK
  3) 호목록     search.eais.go.kr/bldrgstexpos/_search      → 전유부PK, recapTitlePk
  4) 조회       /bci/BCIAAA02R01, /bci/BCIAAA02R04          → 위치코드·면적·용도
  5) 담기       /bci/BCIAAA02C01 (ownrYn:"N" — 소유자 PII 제외)
  6) 장바구니   /bci/BCIAAA02R05                            → pbsvcResveDtlsSeqno
  7) 신청       /bci/BCIAZA02S01
  8) 신청내역   /bci/BCIAAA06R01                            → pbsvcRecpNo
  9) 발급       DOM: BCIAAA04L01 의 "발급" 링크 클릭 → CLIP 리포트 팝업 → clip.extract_report

9단계만 DOM 클릭이다 — 리포트 뷰어 URL 의 ``param`` 이 클라이언트측 AES 로 생성되므로
버튼을 눌러 앱이 자연스럽게 뷰어를 열게 한다(정찰 확인: 캡차·AnySign 없음).

PoC 검증 필요(실주소로 확인 후 조정): (a) 7단계 신청(S01) 요청 헤더·선행콜, (b) 단일 세션
장바구니 격리(잔여 항목), (c) DOM "발급" 링크가 방금 신청 건과 매칭되는지.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import io
import json
import re
from urllib.parse import quote

import structlog
from playwright.async_api import Page
from pypdf import PdfReader

from .browser import BrowserManager
from .config import Settings
from .models import (
    BuildingRegisterBundleRequest,
    BuildingRegisterBundleResponse,
    BuildingRegisterError,
    BuildingRegisterRequest,
    BuildingRegisterResult,
    ExtractionMeta,
)
from . import clip

_log = structlog.get_logger(__name__)

_UNT_CLSF_CD = "1020"  # 집합건축물대장 용도분류코드(정찰 실측)

# regstrKindCd: 1=총괄표제부, 3=표제부, 4=전유부
_REGSTR_KIND = {"exclusive": "4", "heading": "3"}

# CLIP 리포트명(발급 뷰어 param FileName="/bci/<reptNm>"). 전유부=djrBldexpos, 표제부=
# djrBldtitle (둘 다 실측 발급 확인). 세움터 신청내역/발급일은 KST 기준.
_REPT_NM = {"exclusive": "djrBldexpos", "heading": "djrBldtitle"}

# Fly 컨테이너는 UTC — date.today()는 00:00~09:00 KST 구간에 전날이 돼 방금 신청한 건을
# 놓치거나(fail-closed) 어제 잔재를 매칭한다(오건 발급). 한국은 DST 없어 고정 +9 로 KST 계산
# (tzdata 의존 없이 안전).
_KST = datetime.timezone(datetime.timedelta(hours=9))


def _kst_today() -> datetime.date:
    return datetime.datetime.now(_KST).date()


# 신청(S01) 접수번호 매칭: 공용 단일계정엔 같은 세대의 '과거 접수'가 [어제,오늘] 창에 남아 있을 수
# 있다. 신청 전 06R01 접수번호 스냅샷을 잡고, 신청 후 새로 생긴 동일 건물·동·호 행만 수용해
# 과거 접수의 '구발급'을 막는다(#recp-fresh). S01/D02 응답의 pbsvcRecpNo 는 응답 위치·의미가
# 안정적이지 않아 후보(tie-breaker)로만 쓰고, 새 행이 아직 신청내역에 안 뜨면 잠깐 폴링한다.
# 폴 간격은 백오프(짧게 시작) — 새 행은 대개 1초 안에 올라오므로 빠른 상류는 조기 완료하고,
# 느린 상류엔 기존(3×1500ms)보다 넉넉한 총예산을 준다.
_RECP_POLL_WAITS_MS = (400, 800, 1500, 2500, 3000)

# 발급 준비(06R03) FILE_ID 폴 간격 — 동일한 백오프 원칙(기존 6×1500ms 균등 대비 총예산 증가).
_R03_POLL_WAITS_MS = (400, 700, 1200, 1800, 2500, 3000, 3000)

# PDF(best-effort)는 잡 데드라인(main.py wait_for=job_deadline_ms)보다 이 여유만큼 일찍 끊어,
# 판정이 끝난 잡이 느린 PDF 때문에 취소(→과금된 발급이 오류로 보여 재시도→중복발급)되지 않게
# 한다(#pdf-budget). PDF 는 옵션이므로 예산 부족 시 생략하고 결과를 반환한다.
_PDF_RETURN_RESERVE_MS = 4000

# 통합 잡에서 전유부 PDF 마감에 추가로 남겨 두는 표제부 몫 — 표제부의 06R03 폴 + CLIP 렌더 +
# 텍스트 추출(필수 단계, 실측 ~30s)이 전유부 PDF 지연에 잡아먹히지 않게 한다.
_PER_KIND_RESERVE_MS = 35_000


def _extract_recp_nos(obj: object) -> list[str]:
    """S01/D02 응답에서 접수번호 후보(pbsvcRecpNo)를 **모두** 방어적으로 찾는다(중첩 관용).

    응답 구조가 버전마다 달라질 수 있어 dict/list 를 재귀로 훑는다. 이 값들은 06R01 실제
    접수번호와 다를 수 있으므로 정본으로 강제하지 않고, 신청 전후 이력 차집합이 복수일 때만
    tie-breaker 로 사용한다. 통합 신청(두 건 S01)은 응답에 접수번호가 여러 개 실릴 수 있다.
    """

    out: list[str] = []
    stack: list[object] = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            v = cur.get("pbsvcRecpNo")
            if isinstance(v, (str, int)) and str(v).strip():
                s = str(v).strip()
                if s not in out:
                    out.append(s)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def _extract_recp_no(obj: object) -> str:
    """단건 경로용 — 탐색 순서상 첫 접수번호 후보(없으면 빈 문자열)."""

    nos = _extract_recp_nos(obj)
    return nos[0] if nos else ""


def _norm_recp_no(value: object) -> str:
    """접수번호 비교용 정규화 — 영숫자만 보존하고 대문자로 통일한다."""

    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _receipt_history_body() -> dict:
    """06R01 발급이력 조회 조건. ``01`` 은 세움터 UI 의 전체 상태 플래그다."""

    today = _kst_today()
    return {
        "membNo": "",
        "pbsvcGbCd": "",
        "progStateFlagArr": ["01"],
        "pbsvcProcessGbCd": "",
        "firstSaveStartDate": (today - datetime.timedelta(days=1)).isoformat(),
        "firstSaveEndDate": today.isoformat(),
        "pageNo": 0,
        "recordSize": 50,
        "pageYn": "N",
    }


# 발급 뷰어 param 은 CryptoJS.AES(passphrase)로 암호화된다(뷰어 html2xmlDwg 가 같은 키로 복호,
# 실측). 뷰어와 동일한 crypto-js 로 인페이지 암호화한다 — Python 크립토 의존성 회피 + 정확.
_REPORT_PASSPHRASE = "cloud.cais.go.kr"
_ENCRYPT_PARAM_JS = """
async (args) => {
  if (typeof CryptoJS === 'undefined') {
    await new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = '/report/js/crypto-js/crypto-js.js';
      s.onload = res; s.onerror = () => rej(new Error('crypto-js load fail'));
      document.head.appendChild(s);
    });
  }
  const obj = Object.assign({}, args.obj, { timestamp: new Date().toISOString() });
  return CryptoJS.AES.encrypt(JSON.stringify(obj), args.pass).toString();
}
"""


class FlowError(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        field: str | None = None,
        options: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.field = field
        self.options = options


# in-page fetch — JSON POST. 반환 {status, text}.
# credentials 는 반드시 'same-origin' — /bci(동일출처)는 세션 쿠키가 가고, search.eais.go.kr
# (교차출처 ES 공개검색)은 자격증명을 보내지 않아 CORS 를 통과한다. 'include' 를 쓰면 교차출처
# ES 가 CORS-credential 실패("Failed to fetch")한다(실측으로 확인).
_FETCH_JS = """
async (args) => {
  const r = await fetch(args.url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json;charset=UTF-8'},
    credentials: 'same-origin',
    body: JSON.stringify(args.body),
  });
  const text = await r.text();
  return { status: r.status, text };
}
"""

# GET(세션 정보 등). 동일출처 세션 쿠키 전송.
_GET_FETCH_JS = """
async (args) => {
  const r = await fetch(args.url, { method: 'GET', credentials: 'same-origin' });
  const text = await r.text();
  return { status: r.status, text };
}
"""


def _norm_unit(value: str | None) -> str:
    """동/호 정규화 — 접두 '제', 접미 '동'/'호', 공백 제거, 선행 0 제거."""

    text = (value or "").strip().replace(" ", "")
    if not text:
        return ""
    if text.startswith("제"):
        text = text[1:]
    if text.endswith(("동", "호")):
        text = text[:-1]
    stripped = text.lstrip("0")
    if stripped.isdigit() or stripped == "":
        return stripped or ("0" if text else "")
    return stripped


def _suffix(value: str | None, suf: str) -> str:
    """DOM 행 매칭용 — 값에 동/호 접미가 없으면 붙인다('104'→'104동', '504호'→'504호')."""

    text = (value or "").strip()
    if not text:
        return ""
    return text if text.endswith(suf) else text + suf


def _addr_has_ho(addr: str, ho: str) -> bool:
    """신청내역 locDetlAddr("…102동 901"/"…901호")에서 호(ho)를 **동 뒤 구간**에서만 찾는다.

    호는 동 뒤에 온다. 동번호(예 '101동'의 101)를 호로 오인하면, 아직 내 접수건이 안 뜬 사이
    공용 계정의 다른 호('101동 1001호') 접수를 잘못 매칭해 엉뚱한 문서를 연다. '동' 이후 구간
    에서만 호 토큰을 확인해 이를 배제한다(#recp-ho-after-dong).
    """

    norm = (addr or "").replace(" ", "")
    if not ho:
        return False
    di = norm.rfind("동")
    seg = norm[di + 1 :] if di >= 0 else norm
    return bool(re.search(r"(?<!\d)" + re.escape(ho) + r"호?(?!\d)", seg))


def _parcel_address_key(jibun_addr: str, mnnm: str, slno: str) -> str:
    """지번 주소에서 실제 필지 번호까지의 정규화된 접두어를 반환한다.

    ``mnnm``이 법정동명(예: ``종로1가``)에 포함될 수 있으므로 첫 숫자 등장 위치를 쓰면 안
    된다. 공식 지번 주소에서 번지는 공백 뒤 독립 토큰이므로, 그 경계를 가진 본번/부번을 찾아
    시군구·법정동+필지 번호까지만 식별자로 사용한다.
    """

    main = str(mnnm or "").lstrip("0")
    sub = str(slno or "").lstrip("0")
    if not main:
        return ""
    parcel = f"{main}-{sub}" if sub else main
    match = re.search(
        r"(?<!\S)" + re.escape(parcel) + r"(?=\s|번지|$)", str(jibun_addr or "")
    )
    if match is None:
        return ""
    return re.sub(r"[\s()]", "", str(jibun_addr)[: match.end()])


def _es_field(hits: list[dict], pk: str, field: str) -> str | None:
    """_id 가 pk 인 ES hit 의 _source[field] 를 돌려준다(없으면 None)."""

    for h in hits:
        if str(h.get("_id")) == str(pk):
            return (h.get("_source") or {}).get(field)
    return None


def _loc_from(row: dict) -> dict:
    """R04(findExposList) / R01(jibunAddr) 응답행에서 담기용 위치코드를 뽑는다."""

    return {
        "sigunguCd": row.get("sigunguCd", ""),
        "bjdongCd": row.get("bjdongCd", ""),
        "platGbCd": row.get("platGbCd", "0"),
        "mnnm": row.get("mnnm", ""),
        "slno": row.get("slno", ""),
        "bldNm": row.get("bldNm"),
    }


class SeumteoFlow:
    def __init__(self, mgr: BrowserManager, settings: Settings) -> None:
        self._mgr = mgr
        self._s = settings
        # 신청자 정보(세션 계정 고정) 캐시 — S01 appntInfo. 세션당 1회만 조회.
        self._appnt: dict | None = None

    async def run(self, req: BuildingRegisterRequest) -> BuildingRegisterResult:
        await self._mgr.ensure_logged_in()
        # 잡 전체 데드라인(main.py wait_for=job_deadline_ms)보다 _PDF_RETURN_RESERVE_MS 만큼 일찍
        # PDF 를 끊기 위한 절대 마감시각(monotonic). 판정은 이미 끝났으니 PDF 지연이 잡을 취소
        # (→중복발급)시키지 않게 한다(#pdf-budget).
        loop = asyncio.get_event_loop()
        pdf_deadline = (
            loop.time()
            + max(0, self._s.job_deadline_ms - _PDF_RETURN_RESERVE_MS) / 1000
        )
        async with self._mgr.render_semaphore:
            page = await self._mgr.context.new_page()
            try:
                return await self._run_on_page(page, req, pdf_deadline=pdf_deadline)
            finally:
                await page.close()

    @staticmethod
    def _heading_error(exc: BaseException) -> BuildingRegisterError:
        """표제부 단계 예외 → 그 종류의 오류 봉투(전유부 결과를 지우지 않는다)."""

        if isinstance(exc, FlowError):
            return BuildingRegisterError(
                category=exc.category,
                message=exc.message,
                field=exc.field,
                options=exc.options,
            )
        return BuildingRegisterError(
            category="upstream", message="표제부 발급 처리 중 오류가 발생했습니다."
        )

    async def run_bundle(
        self, req: BuildingRegisterBundleRequest
    ) -> BuildingRegisterBundleResponse:
        """전유부+표제부 통합 잡 — 로그인·주소해석·카트·신청을 1회로 공유한다.

        전유부가 핵심 신호다: 공유 단계(로그인/공유 해석)와 전유부 단계 실패는 예외로
        전파돼 main.py 가 양쪽 봉투에 복제한다. 표제부는 **해석부터 추출까지 전 구간
        best-effort** — 순차 경로가 표제부 실패를 caution 으로 흡수하듯, 어느 단계에서
        실패해도 전유부 성공 결과를 버리지 않고 표제부 봉투에만 담는다. 표제부 추출은
        남은 예산으로 타임박스해 표제부 지연이 bundle 데드라인 전체를 태우지 않게 한다."""

        await self._mgr.ensure_logged_in()
        loop = asyncio.get_event_loop()
        overall_deadline = loop.time() + self._s.bundle_deadline_ms / 1000
        async with self._mgr.render_semaphore:
            page = await self._mgr.context.new_page()
            try:
                return await self._run_bundle_on_page(page, req, overall_deadline)
            finally:
                await page.close()

    async def _run_bundle_on_page(
        self,
        page: Page,
        req: BuildingRegisterBundleRequest,
        overall_deadline: float,
    ) -> BuildingRegisterBundleResponse:
        req_ex = BuildingRegisterRequest(
            road_addr=req.road_addr,
            dong=req.dong,
            ho=req.ho,
            jibun_addr=req.jibun_addr,
            register_kind="exclusive",
        )
        req_head = BuildingRegisterRequest(
            road_addr=req.road_addr,
            dong=req.dong,
            ho=req.ho,
            jibun_addr=req.jibun_addr,
            register_kind="heading",
        )

        await page.goto(
            self._s.eais_base_url + "/moct/bci/aaa02/BCIAAA02L01",
            wait_until="domcontentloaded",
        )
        # 공유 해석(총괄PK+동) 1회 → 종류별 해석은 상호 독립이라 동시 실행(같은 페이지의
        # in-page fetch 는 프로토콜상 병렬 안전 — 브라우저 동시 XHR 과 동일).
        # 전유부 해석 실패는 전체 실패(순차 경로 동일)지만, 표제부는 여기부터 전 구간
        # best-effort 다 — R01 이 비거나 일시 오류여도 전유부 성공 결과를 버리지 않고
        # 표제부 봉투에만 담는다(순차 경로의 caution 흡수와 동일 의미).
        shared = await self._resolve_shared(page, req_ex)
        t_ex_raw, t_head_raw = await asyncio.gather(
            self._resolve_kind(page, req_ex, shared),
            self._resolve_kind(page, req_head, shared),
            return_exceptions=True,
        )
        if isinstance(t_ex_raw, BaseException):
            raise t_ex_raw
        t_ex: dict = t_ex_raw
        t_head: dict | None = None
        heading_failure: BuildingRegisterError | None = None
        if isinstance(t_head_raw, BaseException):
            if not isinstance(t_head_raw, Exception):
                raise t_head_raw  # CancelledError 등 제어 예외는 삼키지 않는다.
            _log.warning(
                "flow.bundle_heading_failed",
                stage="resolve",
                error=str(t_head_raw)[:120],
            )
            heading_failure = self._heading_error(t_head_raw)
        else:
            t_head = t_head_raw

        await self._clear_cart(page)  # 잔재 카트 정리(#cart-preclean) — 잡당 1회
        await self._add_to_cart(page, req_ex, t_ex)
        if t_head is not None:
            try:
                await self._add_to_cart(page, req_head, t_head)
            except FlowError as exc:
                _log.warning(
                    "flow.bundle_heading_failed", stage="cart", category=exc.category
                )
                heading_failure = self._heading_error(exc)
                t_head = None

        targets_by_kind: dict[str, dict] = {"exclusive": t_ex}
        if t_head is not None:
            targets_by_kind["heading"] = t_head
        items = await self._isolate_cart_many(
            page, targets_by_kind, optional_kinds=frozenset({"heading"})
        )
        if t_head is not None and "heading" not in items:
            _log.warning("flow.bundle_heading_failed", stage="isolate")
            heading_failure = BuildingRegisterError(
                category="upstream",
                message="표제부 발급 예약 항목을 확인하지 못했습니다.",
            )
            t_head = None
        appnt = await self._appnt_info(page)
        known_receipts = await self._receipt_snapshot(page)

        item_list = [items["exclusive"]]
        if t_head is not None:
            item_list.append(items["heading"])

        # 신청 — 기본은 단일 S01(세움터 카트 UI 의 일괄 신청과 동일). 두 건 일괄이
        # 거부되면(자동화 경로 미검증 리스크) 같은 잡 안에서 종류별 순차 신청으로 폴백한다.
        # 부분 생성된 행이 있으면 종류별 새 행이 복수가 돼 _pick_receipt 가 fail-closed 한다.
        submitted: list[str]
        if self._s.seumteo_bundle_single_submit or len(item_list) == 1:
            try:
                submitted = await self._submit_many(page, item_list, appnt)
            except FlowError as exc:
                if len(item_list) == 1:
                    raise  # 전유부 단건 신청 실패 = 전체 실패(폴백 여지 없음).
                _log.warning(
                    "flow.bundle_submit_fallback",
                    category=exc.category,
                    message=exc.message[:120],
                )
                submitted = await self._submit_many(page, [items["exclusive"]], appnt)
                submitted += await self._submit_many(page, [items["heading"]], appnt)
        else:
            submitted = await self._submit_many(page, [items["exclusive"]], appnt)
            submitted += await self._submit_many(page, [items["heading"]], appnt)

        kinds: dict[str, tuple[BuildingRegisterRequest, dict]] = {
            "exclusive": (req_ex, t_ex)
        }
        if t_head is not None:
            kinds["heading"] = (req_head, t_head)
        recps = await self._find_recp_nos(
            page, kinds, known_receipts, submitted=submitted
        )

        # 전유부 먼저(핵심 신호) — 접수 미확인/추출 실패는 예외 전파(양쪽 실패 봉투).
        recp_ex = recps.get("exclusive")
        if recp_ex is None:
            raise FlowError("upstream", "신청한 발급 건을 확인하지 못했습니다.")
        pdf_deadline_ex = (
            overall_deadline
            - (_PDF_RETURN_RESERVE_MS + _PER_KIND_RESERVE_MS) / 1000
        )
        exclusive = await self._issue_and_extract(
            page, req_ex, t_ex, recp_ex, pdf_deadline=pdf_deadline_ex
        )

        # 표제부 — 실패는 이 종류의 봉투에만 담는다(호출측 caution 처리).
        heading: BuildingRegisterResult | BuildingRegisterError
        recp_head = recps.get("heading") if t_head is not None else None
        if t_head is None:
            heading = heading_failure or BuildingRegisterError(
                category="upstream",
                message="표제부 발급 처리 중 오류가 발생했습니다.",
            )
        elif recp_head is None:
            heading = BuildingRegisterError(
                category="upstream", message="표제부 발급 건을 확인하지 못했습니다."
            )
        else:
            # 남은 예산으로 타임박스 — 표제부가 렌더/다운로드에서 멈춰도 bundle 데드라인
            # (main.py wait_for)까지 끌려가 **전유부 성공 결과째 타임아웃**되지 않게 한다.
            # 마감은 표제부 PDF 마감과 동일 시점(응답 반환 예약분 확보).
            pdf_deadline_head = overall_deadline - _PDF_RETURN_RESERVE_MS / 1000
            remaining_s = pdf_deadline_head - asyncio.get_event_loop().time()
            try:
                if remaining_s <= 0:
                    raise asyncio.TimeoutError
                heading = await asyncio.wait_for(
                    self._issue_and_extract(
                        page, req_head, t_head, recp_head,
                        pdf_deadline=pdf_deadline_head,
                    ),
                    timeout=remaining_s,
                )
            except asyncio.TimeoutError:
                _log.warning("flow.bundle_heading_failed", stage="extract_timeout")
                heading = BuildingRegisterError(
                    category="upstream",
                    message="표제부 발급이 시간 내 완료되지 않았습니다.",
                )
            except FlowError as exc:
                _log.warning(
                    "flow.bundle_heading_failed",
                    stage="extract",
                    category=exc.category,
                    message=exc.message[:120],
                )
                heading = self._heading_error(exc)
            except Exception:  # noqa: BLE001 — 표제부 실패가 전유부 결과를 지우면 안 된다.
                _log.exception("flow.bundle_heading_unexpected")
                heading = BuildingRegisterError(
                    category="upstream",
                    message="표제부 발급 처리 중 오류가 발생했습니다.",
                )

        return BuildingRegisterBundleResponse(exclusive=exclusive, heading=heading)

    async def _run_on_page(
        self,
        page: Page,
        req: BuildingRegisterRequest,
        *,
        assume_ready: bool = False,
        pdf_deadline: float | None = None,
    ) -> BuildingRegisterResult:
        # assume_ready: 이미 발급 서비스에 로그인·진입한 페이지(같은 탭)를 그대로 쓴다.
        # 세움터 발급 페이지는 '발급 진입' 세션 플래그를 요구하는데, 새 탭 + 직접 URL 이동은
        # 그 플래그가 없어 로그인 게이트로 튕긴다(= 로그아웃처럼 보임). 진입된 탭을 재사용하면
        # 플래그가 유지된다. in-page fetch(1~8)는 same-origin 이라 랜딩 이동 없이도 동작한다.
        if not assume_ready:
            await page.goto(
                self._s.eais_base_url + "/moct/bci/aaa02/BCIAAA02L01",
                wait_until="domcontentloaded",
            )
        targets = await self._resolve(page, req)
        await self._clear_cart(page)  # 잔재 카트 정리(#cart-preclean) — 잡당 1회
        await self._add_to_cart(page, req, targets)  # 담기(C01)
        item = await self._isolate_cart(page, targets)  # R05: 내 항목 + 잔여 제거(D01)
        appnt = await self._appnt_info(page)  # 신청자 정보(세션+사업자)
        # 신청 전에 이미 존재하던 접수번호를 고정한다. 신청 응답의 pbsvcRecpNo 가 06R01 의
        # 실제 발급 접수번호와 다르더라도, 이후 새로 생긴 동일 세대 행을 안전하게 식별할 수 있다.
        known_receipts = await self._receipt_snapshot(page)
        submitted_recp = await self._submit(
            page, item, appnt
        )  # 신청(S01+D02)→ 방금 건 접수번호
        # 06R01 에서 신청 전 스냅샷에 없던 새 행만 수용(공용계정의 과거 접수 구발급 방지).
        recp = await self._find_recp_no(
            page, req, targets, known_receipts, submitted_recp
        )
        return await self._issue_and_extract(
            page, req, targets, recp, pdf_deadline=pdf_deadline
        )

    async def _issue_and_extract(
        self,
        page: Page,
        req: BuildingRegisterRequest,
        targets: dict,
        recp: dict,
        *,
        pdf_deadline: float | None = None,
    ) -> BuildingRegisterResult:
        """접수 건 발급 → CLIP 추출 → 완전성 게이트 → 결과 조립(종류별 단계)."""

        popup = await self._open_report(page, req, targets, recp)  # 그 건 발급→리포트
        try:
            extracted = await clip.extract_report(
                popup,
                timeout_ms=self._s.report_render_timeout_ms,
                pdf_deadline=pdf_deadline,
            )
        finally:
            await popup.close()

        # ── silent-normal 방지(가장 위험한 오류 = 실제 위반건축물을 정상으로 오안내) ──
        # 위반표시("위반건축물")는 갑지 표시 + **을지 '그 밖의 기재사항'**(2쪽 이후)에 실린다.
        # 그런데 CLIP 뷰어는 쪽 단위 지연 로드라, 1쪽만 실리고 2쪽(위반표시 페이지)이 조용히
        # 누락돼도 갑지 앵커만으로 통과하면 violation=False 로 오판한다. 그래서 (a) 갑지 앵커와
        # (b) **06R03 이 존재를 알려준 섹션이 실제 텍스트에 있는지**를 함께 요구한다. 있어야 할
        # 섹션이 없으면 그 페이지가 안 실린 것 → fail-closed(정상 단정 대신 오류→재시도).
        compact = extracted.get("compact_text") or re.sub(
            r"[\s+]+", "", extracted.get("full_text") or ""
        )
        if not any(a in compact for a in ("고유번호", "도로명", "건축물대장")):
            raise FlowError(
                "upstream",
                "건축물대장 리포트를 확인하지 못해 위반여부를 판정할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            )
        counts = targets.get("_section_counts") or {}

        def _cnt(key: str) -> int:
            try:
                return int(str(counts.get(key) or "0"))
            except (TypeError, ValueError):
                return 0

        # 완전성(을지 로드) 검증 — guess 독립적. 모든 건축물대장은 '변동사항 및 그 원인' 섹션을
        # 반드시 렌더한다(항목 없으면 '- 이하여백 -'). 이 헤더가 compact 에 없으면 을지(변동사항·
        # 그밖의기재사항의 위반표시가 실리는 쪽)가 미로드된 것 → violation=False 를 신뢰 불가 →
        # **fail-closed**. 06R03 섹션수(_section_counts)가 통째로 비어 있으면 완전성 확인 자체가
        # 불가하므로 역시 fail-closed(count 키 부재로 게이트가 조용히 통과되지 않게).
        if "변동사항" not in compact:
            raise FlowError(
                "upstream",
                "건축물대장의 변동사항 페이지를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            )
        if not counts:
            raise FlowError(
                "upstream",
                "건축물대장 리포트 구성을 확인하지 못해 위반여부를 판정할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            )
        # 위반표시가 실리는 '그 밖의 기재사항'이 있다는데 텍스트에 없으면 그 쪽 미로드.
        if _cnt("ETC_RCD_MATR_COUNT") >= 1 and "그밖의기재사항" not in compact:
            raise FlowError(
                "upstream",
                "건축물대장의 위반표시 페이지를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            )
        return self._build_result(req, targets, extracted)

    # ------------------------------------------------------------------
    # in-page fetch helpers
    # ------------------------------------------------------------------
    async def _post(self, page: Page, url: str, body: dict | list) -> dict:
        res = await page.evaluate(_FETCH_JS, {"url": url, "body": body})
        return self._parse_fetch(res)

    async def _get(self, page: Page, url: str) -> dict:
        res = await page.evaluate(_GET_FETCH_JS, {"url": url})
        return self._parse_fetch(res)

    @staticmethod
    def _parse_fetch(res: dict) -> dict:
        status = res.get("status")
        text = res.get("text") or ""
        if status == 401 or status == 403:
            raise FlowError("auth", "세움터 세션 인증이 거부되었습니다.")
        if not isinstance(status, int) or status >= 400:
            raise FlowError("upstream", f"세움터 응답 오류(status={status}).")
        try:
            return json.loads(text)
        except ValueError as exc:
            raise FlowError("upstream", "세움터 응답을 해석할 수 없습니다.") from exc

    @staticmethod
    def _check_cais(data: dict) -> None:
        msg = data.get("caisMessage") or {}
        code = msg.get("resultCode")
        if code and code != "S00000":
            text = msg.get("resultMessage") or ""
            cat = (
                "not_found"
                if any(h in text for h in ("없", "조회", "일치"))
                else "upstream"
            )
            raise FlowError(cat, text or f"세움터 오류({code}).")

    # ------------------------------------------------------------------
    # 1~4) 주소 → PK → 위치코드/면적
    # ------------------------------------------------------------------
    async def _resolve(self, page: Page, req: BuildingRegisterRequest) -> dict:
        shared = await self._resolve_shared(page, req)
        return await self._resolve_kind(page, req, shared)

    async def _resolve_shared(
        self, page: Page, req: BuildingRegisterRequest
    ) -> dict:
        """1~2단계(총괄PK + 표제부PK·동 매칭) — 대장 종류와 무관한 공유 단계.

        통합 잡은 이 결과를 전유부·표제부가 함께 재사용한다(ES 검색 중복 제거)."""

        search = self._s.eais_search_base_url

        # 1) 총괄PK
        mst = await self._post(
            page,
            f"{search}/bldrgstmst/_search",
            {
                "query": {
                    "multi_match": {
                        "query": req.road_addr.strip(),
                        "type": "cross_fields",
                        "operator": "and",
                        "fields": ["jibunAddr", "roadAddr^3"],
                        "tie_breaker": 0.3,
                    }
                },
                "collapse": {"field": "mgmUpperBldrgstPk"},
                "size": 20,
            },
        )
        hits = (((mst or {}).get("hits") or {}).get("hits")) or []
        if not hits:
            raise FlowError("not_found", "해당 주소의 건축물대장을 찾지 못했습니다.")
        src0 = hits[0].get("_source") or {}
        mgm_upper_pk = str(src0.get("mgmUpperBldrgstPk") or "")
        road_addr = src0.get("roadAddr")
        jibun_addr = src0.get("jibunAddr")
        # untClsfCd(용도분류코드)는 **건물마다 다르다**(예: 아파트 1020/1118). ES 원본값을
        # R01/R04 에 그대로 넣어야 한다 — 하드코딩(1020)하면 다른 건물에서 R01 이 빈 결과.
        unt = str(src0.get("untClsfCd") or _UNT_CLSF_CD)

        # 2) 표제부PK (동 매칭)
        title = await self._post(
            page,
            f"{search}/bldrgsttitle/_search",
            {
                "sort": [{"dongNm": "asc"}],
                "query": {
                    "bool": {"filter": [{"term": {"mgmUpperBldrgstPk": mgm_upper_pk}}]}
                },
                "size": 1000,  # 대단지(동 다수) — 요청 동이 잘려 not_found 나지 않게 넉넉히.
            },
        )
        thits = (((title or {}).get("hits") or {}).get("hits")) or []
        title_pk = self._match_dong(thits, req.dong)
        if title_pk is None:
            raise FlowError("not_found", "입력한 동을 찾지 못했습니다.", field="dong")
        # 담기(C01) loc* 는 사용자 입력(req)이 아니라 ES 원본값을 쓴다(앱 동작과 일치 —
        # 건물별로 "504호"/"901" 처럼 포맷이 달라짐).
        es_dong_nm = _es_field(thits, title_pk, "dongNm") or req.dong

        return {
            "mgm_upper_pk": mgm_upper_pk,
            "title_pk": title_pk,
            "unt": unt,
            "road_addr": road_addr,
            "jibun_addr": jibun_addr,
            "es_dong_nm": es_dong_nm,
        }

    async def _resolve_kind(
        self, page: Page, req: BuildingRegisterRequest, shared: dict
    ) -> dict:
        """3~4단계(종류별 PK·위치코드·면적) — shared 를 복사해 종류별 targets 로 완성한다.

        반환 dict 는 종류별로 **독립 사본**이다(_cart_seqno/_section_counts 등 이후 단계가
        쓰는 키가 종류 간에 섞이지 않게 — 완전성 게이트 crosstalk 방지)."""

        search = self._s.eais_search_base_url
        title_pk = shared["title_pk"]
        unt = shared["unt"]

        expos_pk = None
        recap_pk = None
        es_ho_nm = ""
        if req.register_kind == "exclusive":
            # 3) 전유부PK (호 매칭)
            expos = await self._post(
                page,
                f"{search}/bldrgstexpos/_search",
                {
                    "sort": [{"hoNm": "asc"}],
                    "query": {
                        "bool": {"filter": [{"term": {"mgmUpperBldrgstPk": title_pk}}]}
                    },
                    "size": 5000,  # 대형 동(수천 세대) — 요청 호가 잘려 not_found 나지 않게.
                },
            )
            ehits = (((expos or {}).get("hits") or {}).get("hits")) or []
            expos_pk, recap_pk = self._match_ho(ehits, req.ho)
            if expos_pk is None:
                raise FlowError("not_found", "입력한 호를 찾지 못했습니다.", field="ho")
            es_ho_nm = _es_field(ehits, expos_pk, "hoNm") or req.ho

        # 4) 조회 — 위치코드(loc*)·면적·용도. **loc 는 R04(전유부)/R01(표제부)에서** 얻는다.
        #    R01(총괄PK)은 빌라 등에서 빈 결과(jibunAddr:[])라 loc 소스로 부적합(실측:
        #    노원/송파 빌라). R04/R01표제부 응답행에 sigunguCd/bjdongCd/mnnm/slno 가 있다.
        exclusive_area = None
        dong_nm = None
        main_prpos = None
        loc: dict = {}
        if req.register_kind == "exclusive":
            r04 = await self._post(
                page,
                f"{self._s.eais_base_url}/bci/BCIAAA02R04",
                {
                    "inqireGbCd": "1",
                    "bldrgstCurdiGbCd": "0",
                    "upperBldrgstSeqno": "",
                    "bldrgstSeqno": expos_pk,
                    "untClsfCd": unt,
                },
            )
            self._check_cais(r04)
            elist = r04.get("findExposList") or []
            if not elist:
                raise FlowError("not_found", "전유부 정보를 확인하지 못했습니다.")
            e0 = elist[0]
            exclusive_area = e0.get("totArea")
            dong_nm = e0.get("dongNm")
            loc = _loc_from(e0)
        else:
            r01t = await self._post(
                page,
                f"{self._s.eais_base_url}/bci/BCIAAA02R01",
                self._r01_body(title_pk, unt),
            )
            self._check_cais(r01t)
            trow = (r01t.get("jibunAddr") or [{}])[0]
            dong_nm = trow.get("dongNm")
            main_prpos = trow.get("mainPrposNm")
            loc = _loc_from(trow)

        return {
            **shared,
            "expos_pk": expos_pk,
            "recap_pk": recap_pk or shared["mgm_upper_pk"],
            "loc": loc,
            "bld_nm": loc.get("bldNm"),
            "dong_nm": dong_nm,
            "es_ho_nm": es_ho_nm,
            "main_prpos": main_prpos,
            "exclusive_area": exclusive_area,
        }

    def _r01_body(self, seqno: str, unt: str) -> dict:
        return {
            "addrGbCd": "2",
            "inqireGbCd": "0",
            "bldrgstCurdiGbCd": "0",
            "bldrgstSeqno": seqno,
            "reqSigunguCd": "",
            "sidoClsfCd": "",
            "bjdongCd": "",
            "platGbCd": "",
            "mnnm": "",
            "slno": "",
            "splotNm": "",
            "blockNm": "",
            "lotNm": "",
            "roadNmCd": "",
            "bldMnnm": "",
            "bldSlno": "",
            "sigunguCd": "",
            "untClsfCd": unt,
        }

    def _match_dong(self, hits: list[dict], dong: str) -> str | None:
        norm = _norm_unit(dong)
        if not hits:
            return None
        if not norm and len(hits) == 1:
            return str(hits[0].get("_id"))
        for h in hits:
            if _norm_unit((h.get("_source") or {}).get("dongNm")) == norm:
                return str(h.get("_id"))
        # 동이 하나뿐이면 그것으로.
        if len(hits) == 1:
            return str(hits[0].get("_id"))
        return None

    def _match_ho(self, hits: list[dict], ho: str) -> tuple[str | None, str | None]:
        norm = _norm_unit(ho)
        for h in hits:
            src = h.get("_source") or {}
            if _norm_unit(src.get("hoNm")) == norm:
                return str(h.get("_id")), str(src.get("recapTitlePk") or "")
        return None, None

    # ------------------------------------------------------------------
    # 5) 담기 — ownrYn:"N"(소유자 미표시). loc* 는 조회 응답값 그대로.
    # ------------------------------------------------------------------
    async def _add_to_cart(
        self, page: Page, req: BuildingRegisterRequest, t: dict
    ) -> None:
        loc = t["loc"]
        kind = _REGSTR_KIND[req.register_kind]
        seqno = t["expos_pk"] if req.register_kind == "exclusive" else t["title_pk"]
        # loc* 는 ES 원본값(앱 동작과 일치). 동/호 포맷이 건물별로 다르므로 req 가 아니라
        # ES 값(es_dong_nm/es_ho_nm)을 쓴다.
        es_dong = t.get("es_dong_nm") or req.dong or ""
        es_ho = t.get("es_ho_nm") or req.ho if req.register_kind == "exclusive" else ""
        detl = " ".join(
            x
            for x in [
                t.get("jibun_addr") or req.jibun_addr or req.road_addr,
                es_dong,
                es_ho,
            ]
            if x
        ).strip()
        body = {
            "bldrgstSeqno": seqno,
            "regstrGbCd": "2",
            "regstrKindCd": kind,
            "mjrfmlyIssueYn": "N",
            "rntyBrhsIssueYn": "N",
            "locSigunguCd": loc.get("sigunguCd", ""),
            "locBjdongCd": loc.get("bjdongCd", ""),
            "locPlatGbCd": loc.get("platGbCd", "0"),
            "locDetlAddr": detl,
            "locMnnm": loc.get("mnnm", ""),
            "locSlno": loc.get("slno", ""),
            "locDongNm": es_dong,
            "locHoNm": es_ho,
            "locBldNm": t.get("bld_nm") or "",
            "ownrYn": "N",
            "multiUseBildYn": "N",
            "bldrgstCurdiGbCd": "0",
        }
        # 잔재 카트 정리(#cart-preclean)는 호출측이 잡당 1회 수행한다(_clear_cart) — 통합
        # 잡은 두 번째 담기 전에 비우면 첫 건이 지워지므로 여기서 비우면 안 된다.
        data = await self._post(page, f"{self._s.eais_base_url}/bci/BCIAAA02C01", body)
        self._check_cais(data)
        t["_cart_seqno"] = seqno
        t["_locDetlAddr"] = detl

    async def _clear_cart(self, page: Page) -> None:
        """담기 전 계정 장바구니를 비운다(잔재로 인한 카트 만석 → C01 실패 방지).

        직렬화(concurrency==1)라 남은 항목은 모두 이전 잡 잔재다. concurrency>1 이면 다른 진행
        잡 항목을 지울 수 있어 생략한다(단일 머신 배포가 전제 — README). R05/D01 실패는 무시.
        """

        if self._s.seumteo_max_concurrency > 1:
            return
        base = self._s.eais_base_url
        try:
            data = await self._post(page, f"{base}/bci/BCIAAA02R05", {})
        except FlowError:
            return
        for it in data.get("findPbsvcResveDtls") or []:
            s = str(it.get("pbsvcResveDtlsSeqno") or "")
            if not s:
                continue
            try:
                await self._post(
                    page, f"{base}/bci/BCIAAA02D01", {"pbsvcResveDtlsSeqno": s}
                )
            except FlowError:
                pass

    # ------------------------------------------------------------------
    # 6) 장바구니(R05) — 내 항목 확보 + 잔여 항목 제거(D01).
    #    단일 계정이라 카트가 maxIssueCnt(10)까지 차면 담기(C01)가 실패한다. 이번 잡 항목만
    #    남기고 나머지(이전 잡 잔재)는 D01 로 지운다(렌더 세마포어로 직렬화돼 동시 잡 없음).
    # ------------------------------------------------------------------
    async def _isolate_cart(self, page: Page, t: dict) -> dict:
        return (await self._isolate_cart_many(page, {"only": t}))["only"]

    async def _isolate_cart_many(
        self,
        page: Page,
        targets_by_kind: dict[str, dict],
        *,
        optional_kinds: frozenset[str] = frozenset(),
    ) -> dict[str, dict]:
        """이번 잡의 항목들을 종류별로 확보하고, 어느 종류에도 속하지 않는 잔재만 제거한다.

        통합 잡에서는 전유부·표제부 두 행이 함께 카트에 있으므로, 단건 격리처럼 '선택 1건
        외 전부 삭제'하면 **상대 종류의 행을 지워** 신청이 깨진다 — 선택된 행 집합을 먼저
        확정한 뒤 그 밖의 행만 지운다. ``optional_kinds``(통합 잡의 표제부 등 best-effort
        종류)는 확보 실패 시 반환에서 빠질 뿐 예외를 내지 않고, 그 외 종류는 fail-closed."""

        base = self._s.eais_base_url
        data = await self._post(page, f"{base}/bci/BCIAAA02R05", {})
        items = data.get("findPbsvcResveDtls") or []

        def _is_mine(it: dict, t: dict) -> bool:
            if str(it.get("bldrgstSeqno")) != str(t.get("_cart_seqno")):
                return False
            # 같은 건물 다른 호를 구분(전유부). 동/호 세팅돼 있으면 대조.
            ho = str(t.get("es_ho_nm") or "")
            dong = str(t.get("es_dong_nm") or "")
            if ho and str(it.get("locHoNm") or "") != ho:
                return False
            if dong and str(it.get("locDongNm") or "") != dong:
                return False
            return True

        chosen_by_kind: dict[str, dict] = {}
        chosen_seqs: set[str] = set()
        for kind, t in targets_by_kind.items():
            mine = [it for it in items if _is_mine(it, t)]
            if not mine:
                mine = [
                    it
                    for it in items
                    if str(it.get("bldrgstSeqno")) == str(t.get("_cart_seqno"))
                ]
            if not mine:
                if kind in optional_kinds:
                    continue  # best-effort 종류 — 호출측이 오류 봉투로 처리한다.
                raise FlowError("upstream", "발급 예약 항목을 확인하지 못했습니다.")
            mine.sort(key=lambda it: str(it.get("firstCrtnDt") or ""), reverse=True)
            chosen = mine[0]
            chosen["ownrExprsYn"] = "N"  # S01 요구값(R05 는 null 로 옴).
            chosen_by_kind[kind] = chosen
            chosen_seqs.add(str(chosen.get("pbsvcResveDtlsSeqno") or ""))

        # 나머지 예약(잔재) 제거 — 실패는 무시(있으면 좋고 없어도 신청은 진행).
        # **동시성 1일 때만** 안전하다: 잡이 직렬화(render_semaphore)돼 있으므로 다른 항목은
        # 이전 잡 잔재다. concurrency>1 이면 다른 진행 잡의 카트를 지울 수 있어 삭제를 생략한다
        # (그 경우 _submit 이 내 항목만 제출하므로 정확성은 유지, 카트 누적만 감수).
        if self._s.seumteo_max_concurrency <= 1:
            for it in items:
                s = str(it.get("pbsvcResveDtlsSeqno") or "")
                if s and s not in chosen_seqs:
                    try:
                        await self._post(
                            page, f"{base}/bci/BCIAAA02D01", {"pbsvcResveDtlsSeqno": s}
                        )
                    except FlowError:
                        pass

        return chosen_by_kind

    # 신청자 정보(세션 계정) — S01 appntInfo. 세션당 1회 조회 후 캐시.
    async def _appnt_info(self, page: Page) -> dict:
        if self._appnt is not None:
            return self._appnt
        base = self._s.eais_base_url
        rep: dict = {}
        try:
            sess = await self._get(page, f"{base}/cba/CBAAZA02R01")
            rep = sess.get("ds_SessionRep") or {}
        except FlowError:
            rep = {}
        memb_no = str(rep.get("membNo") or "")
        appnt_gb = str(rep.get("membGbCd") or "06")
        appnt_nm = str(rep.get("sessionUserNm") or "")
        bizno = ""
        try:
            acc = await self._post(page, f"{base}/awp/AWPACC01R03", {"membId": memb_no})
            results = ((acc.get("resultData") or {}).get("results")) or []
            if results:
                bizno = str(results[0].get("bizno") or "")
                appnt_nm = appnt_nm or str(results[0].get("nm") or "")
        except FlowError:
            pass
        self._appnt = {
            "appntGbCd": appnt_gb,
            "appntJmno1": None,
            "appntJmno2": "",
            "appntJmno": "",
            "appntBizno": bizno,
            "appntNm": appnt_nm,
            "appntMtelno": "",
            "appntSigunguCd": "",
            "naAppntBjdongCd": "",
            "naAppntRoadCd": "",
            "naAppntMnnm": "",
            "naAppntSlno": "",
            "naAppntGrndUgrndGbCd": "",
            "naAppntDetlAddr": "",
            "appntCorpno": "",
            "appntCoprNm": "",
        }
        return self._appnt

    # ------------------------------------------------------------------
    # 7) 신청 — S01(완전체) + D02. D02 가 빠지면 신청내역에 완료(progStateCd:91)로 안 올라온다.
    #    세움터 카트는 원래 복수 건 일괄 신청 UI(maxIssueCnt=10)라 items 리스트를 그대로 싣는다.
    # ------------------------------------------------------------------
    async def _submit_many(
        self, page: Page, items: list[dict], appnt: dict
    ) -> list[str]:
        base = self._s.eais_base_url
        s01 = {
            "pbsvcResveDtls": items,
            "ownrExprsYn": "N",
            "bldrgstGbCd": "1",
            "pbsvcRecpInfo": {
                "pbsvcGbCd": "01",
                "issueReadGbCd": "0",
                "certDn": None,
                "pbsvcResveDtlsCnt": len(items),
            },
            "appntInfo": appnt,
            "indvGbCd": None,
        }
        data = await self._post(page, f"{base}/bci/BCIAZA02S01", s01)
        self._check_cais(data)
        d02 = await self._post(page, f"{base}/bci/BCIAAA02D02", items)
        self._check_cais(d02)
        # 접수번호 후보들 — 06R01 신청 전후 차집합이 복수일 때만 tie-breaker 로 쓴다.
        out = _extract_recp_nos(data)
        for cand in _extract_recp_nos(d02):
            if cand not in out:
                out.append(cand)
        return out

    async def _submit(self, page: Page, item: dict, appnt: dict) -> str:
        candidates = await self._submit_many(page, [item], appnt)
        return candidates[0] if candidates else ""

    # ------------------------------------------------------------------
    # 8) 신청내역(06R01) — 신청 전후 접수번호 차집합에서 방금 신청한 건을 확보한다.
    #    대장서식(regstrKindCd)+주소(동/호)가 일치하는 새 행만 허용하고, 실패/복수면
    #    fail-closed(다른 건 발급 방지).
    # ------------------------------------------------------------------
    async def _receipt_snapshot(self, page: Page) -> set[str]:
        """신청 전에 존재한 최근 접수번호를 캡처한다.

        이 조회가 실패하면 신청 자체를 시작하지 않는다. 스냅샷 없이 최신 행으로 폴백하면
        공용 계정의 과거 발급을 잘못 열 수 있기 때문이다.
        """

        data = await self._post(
            page,
            f"{self._s.eais_base_url}/bci/BCIAAA06R01",
            _receipt_history_body(),
        )
        self._check_cais(data)
        rows = data.get("IssueReadHistList") or []
        return {recp for row in rows if (recp := _norm_recp_no(row.get("pbsvcRecpNo")))}

    async def _find_recp_no(
        self,
        page: Page,
        req: BuildingRegisterRequest,
        t: dict,
        known_receipts: set[str],
        submitted_recp: str = "",
    ) -> dict:
        found = await self._find_recp_nos(
            page,
            {req.register_kind: (req, t)},
            known_receipts,
            submitted=[submitted_recp] if submitted_recp else [],
        )
        hit = found.get(req.register_kind)
        if hit is None:
            raise FlowError("upstream", "신청한 발급 건을 확인하지 못했습니다.")
        return hit

    async def _find_recp_nos(
        self,
        page: Page,
        kinds: dict[str, tuple[BuildingRegisterRequest, dict]],
        known_receipts: set[str],
        submitted: list[str] | None = None,
    ) -> dict[str, dict]:
        """종류별 새 접수 행을 하나의 폴 루프에서 확보한다(06R01 조회는 iteration 당 1회).

        반환은 확보된 종류만 담는다(부분 성공 허용 — 통합 잡에서 표제부만 실패하면 호출측이
        그 종류만 오류 봉투로 처리한다). 한 종류의 접수번호를 known_receipts 에 추가하지
        않는다 — 통합 신청은 두 행이 **같은 pbsvcRecpNo 를 공유**할 수 있고(행 구분은
        regstrKindCd+mgmNo), 추가하면 두 번째 종류가 자기 행을 못 찾는다."""

        base = self._s.eais_base_url
        body = _receipt_history_body()
        wants = {w for w in (_norm_recp_no(s) for s in submitted or []) if w}
        found: dict[str, dict] = {}
        # 새 행이 06R01 에 올라올 때까지 잠깐 폴링한다. 신청 응답에 접수번호가 없더라도 스냅샷
        # 차집합으로 식별할 수 있으므로 동일하게 폴링한다. 마지막 조회 뒤에는 기다리지 않는다.
        for wait_ms in (*_RECP_POLL_WAITS_MS, 0):
            data = await self._post(page, f"{base}/bci/BCIAAA06R01", body)
            self._check_cais(data)
            rows = data.get("IssueReadHistList") or []
            for key, (req, t) in kinds.items():
                if key in found:
                    continue
                hit = self._pick_receipt(rows, req, t, known_receipts, wants)
                if hit is not None:
                    found[key] = hit
            if len(found) == len(kinds):
                return found
            if wait_ms:
                await page.wait_for_timeout(wait_ms)
        return found

    def _pick_receipt(
        self,
        rows: list[dict],
        req: BuildingRegisterRequest,
        t: dict,
        known_receipts: set[str],
        wants: set[str],
    ) -> dict | None:
        kind = _REGSTR_KIND[req.register_kind]
        dong = _norm_unit(t.get("es_dong_nm") or req.dong)
        ho = _norm_unit(t.get("es_ho_nm") or req.ho)
        # 건물 식별자 — 공용 계정에 다른 단지의 같은 동/호(예: 다른 단지 101동 1001호)가 섞여
        # 있어, 동/호만으로 매칭하면 **엉뚱한 건물의 발급 문서**를 열 수 있다. 건물명과
        # **'시군구·법정동+본번' 지번 프리픽스**(짧은 본번의 부분일치 오매칭 방지)를 모두
        # 확보한다. 세움터 검색(bldNm)과 신청이력(locDetlAddr)은 단지명에 법정동 접두어를
        # 넣거나 빼는 식으로 표기가 달라질 수 있으므로, 건물명 불일치만으로 같은 강한 지번
        # 식별자를 버리면 안 된다(#recp-building-name-variant).
        bld_nm = re.sub(r"[\s()]", "", str(t.get("bld_nm") or ""))
        loc = t.get("loc") or {}
        # 시군구·법정동+실제 필지 번호를 강한 식별자로 삼는다. 법정동명에 숫자가 들어가도
        # 첫 숫자 위치를 잘못 집지 않도록, 지번 토큰 경계에서만 본번/부번을 파싱한다.
        jibun_key = _parcel_address_key(
            str(t.get("jibun_addr") or ""),
            str(loc.get("mnnm") or ""),
            str(loc.get("slno") or ""),
        )
        # 본번 488은 4880과 달라야 한다. 위에서 필지 토큰을 포함한 key를 만들었으므로,
        # 이력 주소에서는 숫자·하이픈 경계를 보존해 부분 문자열 오매칭을 막는다.
        parcel_pattern = (
            re.compile(re.escape(jibun_key) + r"(?![\d-])")
            if len(jibun_key) >= 8
            else None
        )
        # S01/D02 응답에서 얻은 번호는 새 행이 여러 개일 때의 tie-breaker 로만 사용한다. 실측상
        # 신청은 완료됐지만 응답에서 재귀 추출한 번호가 06R01 의 실제 pbsvcRecpNo 와 달라,
        # 정확 일치만 강제하면 완료 행을 모두 버리고 중복 발급을 유발했다.

        # 최신순 정렬 후, 신청 전 스냅샷에 없던 동일 대상 행만 모은다.
        rows = sorted(
            rows, key=lambda r: str(r.get("firstCrtnDt") or ""), reverse=True
        )
        candidates: list[dict] = []
        for r in rows:
            if str(r.get("regstrKindCd")) != kind:
                continue
            addr = str(r.get("locDetlAddr") or "")
            addr_norm = re.sub(r"[\s()]", "", addr)
            name_matches = bool(bld_nm and bld_nm in addr_norm)
            jibun_matches = bool(parcel_pattern and parcel_pattern.search(addr_norm))
            if not (name_matches or jibun_matches):
                continue  # 건물 식별자 부재/불충분 → 안전하게 스킵(오건 방지).
            if dong and (dong + "동") not in addr_norm:
                continue
            if (
                req.register_kind == "exclusive"
                and ho
                and not _addr_has_ho(addr, ho)
            ):
                continue
            recp = _norm_recp_no(r.get("pbsvcRecpNo"))
            if not recp or recp in known_receipts:
                continue
            candidates.append(r)

        if wants:
            exact = [
                row
                for row in candidates
                if _norm_recp_no(row.get("pbsvcRecpNo")) in wants
            ]
            if len(exact) == 1:
                candidates = exact
        if len(candidates) != 1:
            if len(candidates) > 1:
                _log.warning(
                    "flow.recp_ambiguous",
                    candidate_count=len(candidates),
                    submitted_candidate=bool(wants),
                )
            return None

        r = candidates[0]
        recp = str(r.get("pbsvcRecpNo") or "")
        by_submit = _norm_recp_no(recp) in wants
        _log.info(
            "flow.recp_no",
            recp_no=recp,
            prog=r.get("progStateCd"),
            by_submit=by_submit,
            by_snapshot=not by_submit,
        )
        # 발급 준비(06R03)는 이 접수의 처리일 기준이다. 검색창이 [어제,오늘]이라 어제 건이
        # 매칭될 수 있으니, 오늘로 재계산하지 말고 이 행의 처리일을 그대로 넘긴다(#recp-date).
        app_date = (
            str(r.get("realProcessDateStr") or "")
            or str(r.get("recpDate") or "").replace("-", "")
            or str(r.get("firstCrtnDt") or "")[:8]
        )
        return {
            "pbsvcRecpNo": recp,
            "mgmNo": str(r.get("mgmNo") or ""),
            "issueReadGbCd": str(r.get("issueReadGbCd") or "0"),
            "bldrgstGbCd": str(r.get("bldrgstGbCd") or "1"),
            "appDate": app_date,
        }

    # ------------------------------------------------------------------
    # 9) 발급 — **순수 API 로 리포트 뷰어를 연다**(신청내역 DOM/게이트 불필요 → 헤드리스 가능).
    #
    # 세움터 발급 페이지는 sessionStorage 기반 '발급 진입' 상태를 요구해 새 탭/직접이동이
    # 게이트로 튕긴다(반면 API 는 쿠키 세션만으로 동작). 그래서 신청내역 DOM 클릭 대신:
    #   CBAAZD04R01(리포트준비) + report/06R03(FILE_ID·섹션수) → 뷰어 param JSON 조립 →
    #   CryptoJS.AES(passphrase "cloud.cais.go.kr")로 암호화(뷰어 html2xmlDwg 가 같은 키로
    #   복호, 실측) → /report/BCIAAA04V01?param=... 로 직접 이동. param 구조·키는 뷰어 JS 실측.
    # ------------------------------------------------------------------
    async def _open_report(
        self, page: Page, req: BuildingRegisterRequest, t: dict, recp: dict
    ) -> Page:
        base = self._s.eais_base_url
        # 발급 준비일은 오늘로 재계산하지 않고 매칭 접수 행의 처리일을 쓴다(어제 경계 대비, #recp-date).
        rept = _REPT_NM[req.register_kind]
        app_date = recp.get("appDate") or _kst_today().strftime("%Y%m%d")

        # 리포트 준비 + FILE_ID/섹션수 확보(발급 버튼이 내부적으로 하던 호출).
        await self._post(
            page,
            f"{base}/cba/CBAAZD04R01",
            {"sysLocGbCd": "3", "reptNm": rept, "recpDay": app_date, "jobGbCd": "BC"},
        )
        # 발급이 아직 준비 전이면 06R03 에 FILE_ID 가 없다 — 잠깐 대기 후 재조회한다(방금 신청건이
        # 완료 상태에 이르기 전이면 곧 준비되므로 잡을 성급히 실패시키지 않는다, #recp-ready).
        # 백오프 스케줄로 폴링 — 준비돼 있으면 첫 조회로 끝나고, 마지막 조회 뒤에는 기다리지 않는다.
        counts: dict = {}
        for wait_ms in (*_R03_POLL_WAITS_MS, 0):
            r03 = await self._post(
                page,
                f"{base}/report/BCIAAA06R03",
                {"issueReadAppDate": app_date, "pbsvcRecpNo": recp["pbsvcRecpNo"]},
            )
            counts = r03.get("count") or {}
            if counts.get("FILE_ID"):
                break
            if wait_ms:
                await page.wait_for_timeout(wait_ms)
        if not counts.get("FILE_ID"):
            raise FlowError("upstream", "발급 리포트를 준비하지 못했습니다.")
        # 완전성 검증용 섹션 수(위반표시가 실리는 '그 밖의 기재사항' 등)를 넘겨 둔다.
        t["_section_counts"] = counts

        payload = {
            "FileName": f"/bci/{rept}",
            "markAnyYn": "Y",
            "actionIdParam": "BCIAAA04L01",
            "bldrgstCurdiGbCd": "0",
            "issueReadAppDate": app_date,
            "pbsvcRecpNo": recp["pbsvcRecpNo"],
            "mgmNo": recp["mgmNo"],
            "ISSUE_READ_GB_CD": recp.get("issueReadGbCd", "0"),
            "BLDRGST_GB_CD": recp.get("bldrgstGbCd", "1"),
            **{str(k): v for k, v in counts.items()},  # FILE_ID + *_COUNT
        }
        param = await page.evaluate(
            _ENCRYPT_PARAM_JS, {"obj": payload, "pass": _REPORT_PASSPHRASE}
        )

        viewer = await self._mgr.context.new_page()
        try:
            await viewer.goto(
                f"{base}/report/BCIAAA04V01?param={quote(param, safe='')}"
                "&actionId=BCIAAA04L01",
                wait_until="domcontentloaded",
            )
            return viewer
        except Exception:
            if not viewer.is_closed():
                await viewer.close()
            raise

    # ------------------------------------------------------------------
    # 결과 조립
    # ------------------------------------------------------------------
    def _build_result(
        self, req: BuildingRegisterRequest, t: dict, ex: dict
    ) -> BuildingRegisterResult:
        violation_status = "위반건축물" if ex.get("violation") else None
        # 발급 PDF 텍스트 레이어는 여기서 **한 번만** 추출한다 — pypdf 전 쪽 추출은 쪽수에
        # 비례해 수 초씩 걸려(실측: 표제부 ~9s), 대장상세·변동사항 파서가 각자 추출하면
        # 그 비용이 두 배가 된다. 파서들은 추출된 쪽 텍스트를 공유한다.
        pdf_pages = _pdf_page_texts(ex.get("pdf_base64"))
        owned: list[dict] = []
        detail_list: list[dict] = []
        if req.register_kind == "exclusive":
            # R04 의 전유면적이 정본, 층/구조/용도는 PDF 전유부분 표에서 보강한다
            # (JSON 에 없어 리포트 '대장 상세'가 면적만 남던 결함).
            owned_row: dict = {"resType": "0"}
            area = t.get("exclusive_area")
            if area is not None:
                owned_row["resArea"] = str(area)
            pdf_detail = _parse_exclusive_detail_pdf(pdf_pages, area_hint=area)
            for key, value in (pdf_detail or {}).items():
                owned_row.setdefault(key, value)
            if len(owned_row) > 1:
                owned.append(owned_row)
        else:
            # R01 의 mainPrposNm(주용도)이 정본, 층수/인허가 일자는 PDF 에서 보강.
            detail_map = _parse_heading_detail_pdf(pdf_pages) or {}
            if t.get("main_prpos"):
                detail_map["주용도"] = t["main_prpos"]
            for label in ("주용도", "주구조", "층수", "허가일", "착공일", "사용승인일"):
                value = detail_map.get(label)
                if value:
                    detail_list.append({"resType": label, "resContents": value})
        _log.info(
            "flow.register_detail",
            kind=req.register_kind,
            owned_fields=sorted(owned[0].keys()) if owned else [],
            detail_labels=[d["resType"] for d in detail_list],
        )

        # 변동사항은 발급 PDF 텍스트 레이어가 정본이다 — CLIP viewData(글자단위 분절 +
        # 좌표숫자 잡음) 채굴은 절단/중복/필러 행을 만든다(실측: 세션 903c0c36). PDF 가
        # 없거나(예산 초과 생략) 파싱 불가일 때만 CLIP 텍스트로 폴백한다.
        change_list = _parse_changes_pdf(pdf_pages)
        change_source = "pdf"
        if change_list is None:
            change_list = _parse_changes(ex.get("full_text") or "")
            change_source = "clip_text"
        _log.info("flow.changes", source=change_source, rows=len(change_list))

        return BuildingRegisterResult(
            register_kind=req.register_kind,
            comm_unique_no=t.get("recap_pk")
            if req.register_kind == "exclusive"
            else t.get("title_pk"),
            addr_dong=req.dong or t.get("dong_nm"),
            addr_ho=req.ho or None,
            road_addr=t.get("road_addr") or req.road_addr,
            jibun_addr=t.get("jibun_addr") or req.jibun_addr,
            violation_status=violation_status,
            owned=owned,
            change_list=change_list,
            detail_list=detail_list,
            original_pdf_base64=ex.get("pdf_base64"),
            extraction=ExtractionMeta(
                violation_source=ex.get("violation_source"),
                report_text_len=len(ex.get("full_text") or ""),
                pdf_source=ex.get("pdf_source"),
                warnings=ex.get("warnings") or [],
            ),
        )


# 실연도(19/20xx) 날짜만 — 고유번호(4146310100-3-07…) 등 잡음 배제.
_YEAR_DATE = re.compile(r"((?:19|20)\d{2})[.\-](\d{1,2})[.\-](\d{1,2})")
# PDF 텍스트의 변동사항 행 시작 — 줄머리 변동일 + 같은 줄 변동내용(있으면).
_ROW_DATE = re.compile(r"^((?:19|20)\d{2})[.\-](\d{1,2})[.\-](\d{1,2})\.?\s*(.*)$")
# 건축 변동 사유 키워드(확장 등재 판정 신호). 소유권이전 등 소유자 변동은 제외(PII·무관).
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
    "사용승인",
    "직권",
    "말소",
    "위반건축물",
    "표시변경",
)
# 서식 라벨/빈칸 필러 — 이것만으로 이뤄진 문구는 변동 이력이 아니다("사용승인일,사용승인일 ,,").
_FORM_LABEL_CORES = (
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
# PDF 줄 스캔에서 변동 행의 연속(continuation)을 끊는 서식 고정 문구 줄머리. 변동사항 표
# 다음에 오는 인접 표(대지위치/설계자·감리자 성명 등)가 사유에 빨려 들어가는 것을 막는다(PII).
_STRUCTURAL_PREFIXES = (
    "변동사항",
    "변동일",
    "그 밖의",
    "그밖의",
    "공 용 부 분",
    "공용부분",
    "대지위치",
    "건물ID",
    "고유번호",
    "도로명주소",
    "지번",
    "구분",
    "집합건축물대장",
    "이 등(초)본",
    "발급일",
    "담 당 자",
    "담당자",
    "전 화",
    "건축물 현황",
    "건 축 물 현 황",
    "건축물현황",
    "건축물 관리",
    "건축물 구조",
    "인허가",
    "허가일",
    "착공일",
    "사용승인일",
    "건축주",
    "설계자",
    "공사감리자",
    "공사시공자",
    "호수/",
    "명칭",
    "※",
    "■",
    "297",
)


def _normalize_change_date(y: str, m: str, d: str) -> str | None:
    """변동일 표기("2011.5.20.")를 ISO("2011-05-20")로 — 표시/정렬/대조 일관성."""

    try:
        return datetime.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def _reason_core(reason: str) -> str:
    """사유의 문자 골자(한글·영문만) — 필러(서식 라벨) 판정용."""

    return re.sub(r"[^가-힣A-Za-z]", "", reason)


def _dedupe_key(reason: str) -> str:
    """근사중복 비교 키 — 숫자(문서번호·일자)를 보존해 상용구("…과-N호 의거")끼리의
    오붕괴를 막는다. 구두점·공백만 제거한다."""

    return re.sub(r"[^가-힣A-Za-z0-9]", "", reason)


def _is_meaningful_reason(reason: str) -> bool:
    """서식 라벨/필러를 걷어낸 뒤에도 실질 내용이 남는 사유만 변동 이력으로 인정한다.

    "증축"/"말소"처럼 짧아도 변동 키워드면 인정한다(2글자 사유 절삭 방지).
    """

    core = _reason_core(reason)
    for label in _FORM_LABEL_CORES:
        core = core.replace(label, "")
    return len(core) >= 4 or any(kw in core for kw in _CHANGE_KEYWORDS)


def _dedupe_changes(rows: list[dict]) -> list[dict]:
    """같은 행의 절단본(한쪽 골자가 다른 쪽에 포함)을 붕괴시킨다 — 더 긴 사유를 남긴다.

    날짜가 서로 다르면 별개 변동으로 보고 붕괴하지 않는다(같은 사유 반복 변동 보존).
    """

    kept: list[dict] = []
    keys: list[str] = []
    for row in rows:
        key = _dedupe_key(row["resChangeReason"])
        merged = False
        for i, k in enumerate(kept):
            if (
                row["resChangeDate"] is not None
                and k["resChangeDate"] is not None
                and row["resChangeDate"] != k["resChangeDate"]
            ):
                continue
            if key != keys[i] and key not in keys[i] and keys[i] not in key:
                continue
            if len(key) > len(keys[i]):
                k["resChangeReason"] = row["resChangeReason"]
                keys[i] = key
            if k["resChangeDate"] is None:
                k["resChangeDate"] = row["resChangeDate"]
            merged = True
            break
        if not merged:
            kept.append(dict(row))
            keys.append(key)
    return kept


def _scan_change_lines(lines: list[str]) -> list[dict]:
    """PDF 텍스트 줄에서 변동사항 행(변동일 줄머리 + 이어지는 내용 줄)을 모은다.

    셀 폭 줄바꿈은 단어 중간에서 갈라지므로("확장(6" + ".84㎡)") 공백 없이 잇는다.
    날짜 줄머리라도 사유에 한글 실질이 없으면(공동주택가격 "858,000,000", 인허가 시기의
    날짜 단독 줄) `_is_meaningful_reason` 이 걸러낸다.
    """

    rows: list[dict] = []
    date: str | None = None
    parts: list[str] = []

    def flush() -> None:
        nonlocal date, parts
        if date is not None:
            reason = re.sub(r"\s+", " ", "".join(parts)).strip()[:400]
            if _is_meaningful_reason(reason):
                rows.append({"resChangeDate": date, "resChangeReason": reason})
        date, parts = None, []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = _ROW_DATE.match(line)
        if m:
            flush()
            date = _normalize_change_date(m.group(1), m.group(2), m.group(3))
            parts = [m.group(4)] if m.group(4) else []
            continue
        if date is None:
            continue
        if "이하여백" in line or line.startswith(_STRUCTURAL_PREFIXES):
            flush()
            continue
        parts.append(line)
    flush()
    return rows


def _parse_changes_pdf(pages: list[str] | None) -> list[dict] | None:
    """발급 PDF 쪽별 텍스트(_pdf_page_texts 결과)에서 변동사항을 파싱한다(정본 경로).

    '변동사항'이 있는 쪽만 훑으므로 갑지 소유자현황(성명·주소·주민번호) 쪽은 열지 않는다.
    반환 None 은 "파싱 불가(PDF 없음/깨짐/변동사항 쪽 없음)" — 호출측이 CLIP 텍스트로
    폴백한다. 빈 리스트는 "변동 이력 없음"으로 신뢰한다(폴백해 잡음을 만들지 않는다).
    """

    if pages is None:
        return None
    found_section = False
    rows: list[dict] = []
    for text in pages:
        if "변동사항" not in text:
            continue
        found_section = True
        rows.extend(_scan_change_lines(text.splitlines()))
    if not found_section:
        return None
    return _dedupe_changes(rows)[:20]


def _pdf_page_texts(pdf_b64: str | None) -> list[str] | None:
    """발급 PDF 의 쪽별 텍스트 레이어. None = PDF 없음/깨짐(호출측 폴백/생략 신호)."""

    if not pdf_b64:
        return None
    try:
        reader = PdfReader(io.BytesIO(base64.b64decode(pdf_b64)))
        pages: list[str] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 — 한 쪽 추출 실패는 그 쪽만 건너뛴다.
                pages.append("")
        return pages
    except Exception:  # noqa: BLE001 — 디코드/파싱 실패는 폴백으로.
        _log.warning("flow.pdf_text_failed", exc_info=True)
        return None


def _clean_reason(s: str) -> str:
    """CLIP 메타(좌표·플래그 숫자런, true/false/blank)와 빈칸 필러를 걷어낸다(폴백 경로).

    좌표/문서번호/면적 숫자런은 부위명 판정에 불필요하므로 제거하되, 한글 부위명(거실/발코니 등)과
    구조 구분자(〈 〉 / ㎡)는 보존한다 — 판정 LLM 이 신고 부위와 대조할 근거다.
    """

    # "이하여백"은 셀 내용의 끝 표식 — 그 뒤는 이웃 셀/표의 텍스트이므로 창을 절단한다.
    cut = s.find("이하여백")
    if cut >= 0:
        s = s[:cut]
    s = re.sub(r"(?:true|false|blank|null)", " ", s)
    s = re.sub(r"-?\d[\d.,\-]{2,}", " ", s)
    s = re.sub(r"[|]+", " ", s)
    s = re.sub(r"[,]{2,}", " ", s)
    # 창 절단이 남긴 선두 숫자·구두점("9.", ".") — 같은 행 절단본의 중복 붕괴를 방해한다.
    s = re.sub(r"^[\d.,\-)\s]+", "", s)
    return re.sub(r"\s+", " ", s).strip(" ,-")[:80]


def _parse_changes(text: str) -> list[dict]:
    """CLIP viewData 텍스트에서 변동사항을 채굴한다(**PDF 부재 시 폴백**).

    CLIP viewData 는 글자단위 분절 + 위치숫자 잡음이 심하다. 소유자현황(성명·주소·주민번호)을
    피하려 '변동사항' 헤더 이후, 다음 섹션 전까지만 본다(→ PII 안전). 건축 변동 키워드 주변 창을
    잡아 CLIP 메타를 정리해 사유로 넣는다 — **키워드만 넣으면 부위(거실/발코니 등)가 사라져**
    판정 LLM 이 신고 부위와 대조할 수 없다(#change-area). 인접에 실연도 날짜가 있으면 붙인다.
    창 방식은 같은 행의 절단본을 여러 개 만들므로 필러 필터+근사중복 붕괴로 정리한다.
    """

    compact = re.sub(
        r"[\s+]+", "", text
    )  # 게이트/위반검출과 동일 압축(CLIP '+' 공백 제거).
    idx = compact.find("변동사항")
    seg = compact[idx:] if idx >= 0 else compact
    # 다음 섹션(공용부분/증명문/발급일자) 전까지로 한정 — 변동 원문만.
    for marker in ("공용부분", "이등(초)본은", "발급일자"):
        p = seg.find(marker, 5)
        if p > 0:
            seg = seg[:p]
    out: list[dict] = []
    seen: set[tuple[str | None, str]] = set()
    # 같은 키워드가 다른 부위로 여러 번 나올 수 있다(행위허가/사용검사 여러 건). 첫 등장만 잡으면
    # 뒤 부위가 누락돼 판정 LLM 이 신고 부위를 오탐한다 → **모든 등장**을 훑고 (날짜,사유)로 중복만
    # 제거한다(#change-multi).
    for kw in _CHANGE_KEYWORDS:
        for m0 in re.finditer(re.escape(kw), seg):
            pos = m0.start()
            # 키워드 + 뒤따르는 부위/면적(〈…〉)을 포함하도록 창을 잡고 메타를 정리한다.
            # 정리 후 빈 사유 = 창이 순수 잡음(필러 꼬리 등) — 행으로 만들지 않는다.
            reason = _clean_reason(seg[max(0, pos - 12) : pos + 72])
            if not reason or not _is_meaningful_reason(reason):
                continue
            m = _YEAR_DATE.search(seg[max(0, pos - 40) : pos + 72])
            date = _normalize_change_date(*m.groups()) if m else None
            if (date, reason) in seen:
                continue
            seen.add((date, reason))
            out.append({"resChangeDate": date, "resChangeReason": reason})
    return _dedupe_changes(out)[:20]


# ---------------------------------------------------------------------------
# 대장 상세(전유부 층/구조/용도/면적 + 표제부 주용도/층수/인허가 일자) — PDF 보강.
# 내부 JSON(R04/R01)은 totArea/mainPrposNm 만 주므로, 나머지는 발급 PDF 텍스트에서
# 채운다(변동사항 파서와 동일한 정본 소스). 실패는 전부 조용히 생략 — 기존 필드 유지.
# ---------------------------------------------------------------------------
# 전유부분/공용부분/건축물현황 표의 행: "구분 층별 구조 용도 면적" (예: "주 15층 철근콘크리트구조 아파트 59.98")
_DETAIL_ROW = re.compile(
    r"^(주\d*|부\d*)\s+(\S+)\s+(\S+)\s+(.+?)\s+([\d,]+(?:\.\d+)?)$"
)
# 표제부 1쪽 값줄: "…<주구조> <주용도> 지하: N층, 지상: M층"
_STRUCT_USE_FLOORS = re.compile(r"(\S*구조)\s+(.+?)\s+(지하\s*:.*)$")
_FLOORS = re.compile(r"지하\s*:\s*(\d*)\s*층?\s*[,·]?\s*지상\s*:\s*(\d+)\s*층")
# 인허가 시기 값(날짜 단독 줄) — 변동/가격 행은 날짜 뒤에 내용이 붙어 매칭되지 않는다.
_DATE_ONLY = re.compile(r"^((?:19|20)\d{2})[.\-](\d{1,2})[.\-](\d{1,2})\.?$")


def _parse_exclusive_detail_pdf(
    pages: list[str] | None, *, area_hint: object = None
) -> dict | None:
    """전유부 PDF 쪽별 텍스트에서 우리 세대 행(층/구조/용도/면적)을 뽑는다.

    같은 쪽에 공용부분 표가 붙어 있으므로, R04 가 준 전유면적(area_hint)과 면적이
    일치하는 행을 우선 선택하고, 없으면 '주' 행(전유 주 용도)으로 폴백한다.
    소유자현황(성명·주소·주민번호) 줄은 행 패턴(구분+층별+구조+용도+면적)에 걸리지 않는다.
    """

    if pages is None:
        return None
    rows: list[tuple[str, ...]] = []
    for text in pages:
        if "전유부분" not in re.sub(r"\s+", "", text):
            continue
        for raw in text.splitlines():
            m = _DETAIL_ROW.match(raw.strip())
            if m:
                rows.append(m.groups())
    if not rows:
        return None

    hint: float | None = None
    if area_hint is not None:
        try:
            hint = float(str(area_hint).replace(",", ""))
        except ValueError:
            hint = None
    chosen: tuple[str, ...] | None = None
    if hint is not None:
        for row in rows:
            try:
                area = float(row[4].replace(",", ""))
            except ValueError:
                continue
            if abs(area - hint) < 0.005:
                chosen = row
                break
    if chosen is None:
        chosen = next((r for r in rows if r[0].startswith("주")), None)
    if chosen is None:
        return None
    return {
        "resArea": chosen[4].replace(",", ""),
        "resFloor": chosen[1],
        "resStructure": chosen[2],
        "resUseType": chosen[3].strip(),
    }


def _parse_heading_detail_pdf(pages: list[str] | None) -> dict[str, str] | None:
    """표제부 PDF 쪽별 텍스트에서 주구조/주용도/층수(1쪽 값줄)와 허가일/착공일/사용승인일을 뽑는다.

    인허가 일자는 서식상 라벨(허가일/착공일/사용승인일)과 값이 떨어져 추출되므로,
    해당 쪽의 **날짜 단독 줄 연속 3개**가 정확히 한 묶음일 때만 서식 순서대로 매핑한다
    (묶음이 없거나 애매하면 채우지 않는다 — 오매핑이 누락보다 나쁘다).
    """

    if pages is None:
        return None
    out: dict[str, str] = {}
    for text in pages:
        compact_page = re.sub(r"\s+", "", text)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        if "주용도" in compact_page and "층수" not in out:
            for ln in lines:
                m = _STRUCT_USE_FLOORS.search(ln)
                if m is None:
                    continue
                out.setdefault("주구조", m.group(1))
                out.setdefault("주용도", m.group(2).strip())
                fl = _FLOORS.search(m.group(3))
                if fl:
                    under, ground = fl.group(1), fl.group(2)
                    parts = [f"지하 {under}층" if under else None, f"지상 {ground}층"]
                    out.setdefault("층수", "/".join(p for p in parts if p))
                else:
                    out.setdefault("층수", m.group(3).strip())
                break

        if "인허가" in compact_page and "사용승인일" not in out:
            runs: list[list[tuple[str, ...]]] = []
            cur: list[tuple[str, ...]] = []
            for ln in lines:
                m = _DATE_ONLY.match(ln)
                if m:
                    cur.append(m.groups())
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            triples = [r for r in runs if len(r) == 3]
            if len(triples) == 1:
                permit, start, approval = triples[0]
                for label, ymd in (
                    ("허가일", permit),
                    ("착공일", start),
                    ("사용승인일", approval),
                ):
                    value = _normalize_change_date(*ymd)
                    if value:
                        out.setdefault(label, value)
    return out or None
