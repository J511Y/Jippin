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

import datetime
import json
import re
from urllib.parse import quote

import structlog
from playwright.async_api import Page

from .browser import BrowserManager
from .config import Settings
from .models import BuildingRegisterRequest, BuildingRegisterResult, ExtractionMeta
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
    """신청내역 locDetlAddr("…102동 901"/"…901호")에 정규화 호(ho)가 토큰으로 들어있나."""

    norm = (addr or "").replace(" ", "")
    if not ho:
        return False
    return bool(re.search(r"(?<!\d)" + re.escape(ho) + r"호?(?!\d)", norm))


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
        async with self._mgr.render_semaphore:
            page = await self._mgr.context.new_page()
            try:
                return await self._run_on_page(page, req)
            finally:
                await page.close()

    async def _run_on_page(
        self,
        page: Page,
        req: BuildingRegisterRequest,
        *,
        assume_ready: bool = False,
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
        await self._add_to_cart(page, req, targets)          # 담기(C01)
        item = await self._isolate_cart(page, targets)       # R05: 내 항목 + 잔여 제거(D01)
        appnt = await self._appnt_info(page)                 # 신청자 정보(세션+사업자)
        await self._submit(page, item, appnt)                # 신청(S01 완전체 + D02)
        recp = await self._find_recp_no(page, req, targets)  # 신청내역(06R01)→ 내 접수번호
        popup = await self._open_report(page, req, targets, recp)  # 그 건 발급→리포트
        try:
            extracted = await clip.extract_report(
                popup, timeout_ms=self._s.report_render_timeout_ms
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
            cat = "not_found" if any(h in text for h in ("없", "조회", "일치")) else "upstream"
            raise FlowError(cat, text or f"세움터 오류({code}).")

    # ------------------------------------------------------------------
    # 1~4) 주소 → PK → 위치코드/면적
    # ------------------------------------------------------------------
    async def _resolve(self, page: Page, req: BuildingRegisterRequest) -> dict:
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
                "query": {"bool": {"filter": [{"term": {"mgmUpperBldrgstPk": mgm_upper_pk}}]}},
                "size": 1000,  # 대단지(동 다수) — 요청 동이 잘려 not_found 나지 않게 넉넉히.
            },
        )
        thits = (((title or {}).get("hits") or {}).get("hits")) or []
        title_pk = self._match_dong(thits, req.dong)
        if title_pk is None:
            raise FlowError(
                "not_found", "입력한 동을 찾지 못했습니다.", field="dong"
            )
        # 담기(C01) loc* 는 사용자 입력(req)이 아니라 ES 원본값을 쓴다(앱 동작과 일치 —
        # 건물별로 "504호"/"901" 처럼 포맷이 달라짐).
        es_dong_nm = _es_field(thits, title_pk, "dongNm") or req.dong

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
                    "query": {"bool": {"filter": [{"term": {"mgmUpperBldrgstPk": title_pk}}]}},
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
            "mgm_upper_pk": mgm_upper_pk,
            "title_pk": title_pk,
            "expos_pk": expos_pk,
            "recap_pk": recap_pk or mgm_upper_pk,
            "unt": unt,
            "loc": loc,
            "road_addr": road_addr,
            "jibun_addr": jibun_addr,
            "bld_nm": loc.get("bldNm"),
            "dong_nm": dong_nm,
            "es_dong_nm": es_dong_nm,
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
            x for x in [t.get("jibun_addr") or req.jibun_addr or req.road_addr, es_dong, es_ho] if x
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
        data = await self._post(page, f"{self._s.eais_base_url}/bci/BCIAAA02C01", body)
        self._check_cais(data)
        t["_cart_seqno"] = seqno
        t["_locDetlAddr"] = detl

    # ------------------------------------------------------------------
    # 6) 장바구니(R05) — 내 항목 확보 + 잔여 항목 제거(D01).
    #    단일 계정이라 카트가 maxIssueCnt(10)까지 차면 담기(C01)가 실패한다. 이번 잡 항목만
    #    남기고 나머지(이전 잡 잔재)는 D01 로 지운다(렌더 세마포어로 직렬화돼 동시 잡 없음).
    # ------------------------------------------------------------------
    async def _isolate_cart(self, page: Page, t: dict) -> dict:
        base = self._s.eais_base_url
        data = await self._post(page, f"{base}/bci/BCIAAA02R05", {})
        items = data.get("findPbsvcResveDtls") or []
        seqno = str(t.get("_cart_seqno"))
        dong = str(t.get("es_dong_nm") or "")
        ho = str(t.get("es_ho_nm") or "")

        def _is_mine(it: dict) -> bool:
            if str(it.get("bldrgstSeqno")) != seqno:
                return False
            # 같은 건물 다른 호를 구분(전유부). 동/호 세팅돼 있으면 대조.
            if ho and str(it.get("locHoNm") or "") != ho:
                return False
            if dong and str(it.get("locDongNm") or "") != dong:
                return False
            return True

        mine = [it for it in items if _is_mine(it)]
        if not mine:
            mine = [it for it in items if str(it.get("bldrgstSeqno")) == seqno]
        if not mine:
            raise FlowError("upstream", "발급 예약 항목을 확인하지 못했습니다.")
        mine.sort(key=lambda it: str(it.get("firstCrtnDt") or ""), reverse=True)
        chosen = mine[0]
        chosen_seq = str(chosen.get("pbsvcResveDtlsSeqno") or "")

        # 나머지 예약(잔재) 제거 — 실패는 무시(있으면 좋고 없어도 신청은 진행).
        # **동시성 1일 때만** 안전하다: 잡이 직렬화(render_semaphore)돼 있으므로 다른 항목은
        # 이전 잡 잔재다. concurrency>1 이면 다른 진행 잡의 카트를 지울 수 있어 삭제를 생략한다
        # (그 경우 _submit 이 내 항목만 제출하므로 정확성은 유지, 카트 누적만 감수).
        if self._s.seumteo_max_concurrency <= 1:
            for it in items:
                s = str(it.get("pbsvcResveDtlsSeqno") or "")
                if s and s != chosen_seq:
                    try:
                        await self._post(
                            page, f"{base}/bci/BCIAAA02D01", {"pbsvcResveDtlsSeqno": s}
                        )
                    except FlowError:
                        pass

        chosen["ownrExprsYn"] = "N"  # S01 요구값(R05 는 null 로 옴).
        return chosen

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
    # ------------------------------------------------------------------
    async def _submit(self, page: Page, item: dict, appnt: dict) -> None:
        base = self._s.eais_base_url
        s01 = {
            "pbsvcResveDtls": [item],
            "ownrExprsYn": "N",
            "bldrgstGbCd": "1",
            "pbsvcRecpInfo": {
                "pbsvcGbCd": "01",
                "issueReadGbCd": "0",
                "certDn": None,
                "pbsvcResveDtlsCnt": 1,
            },
            "appntInfo": appnt,
            "indvGbCd": None,
        }
        data = await self._post(page, f"{base}/bci/BCIAZA02S01", s01)
        self._check_cais(data)
        d02 = await self._post(page, f"{base}/bci/BCIAAA02D02", [item])
        self._check_cais(d02)

    # ------------------------------------------------------------------
    # 8) 신청내역(06R01) — 방금 신청한 건의 접수번호(pbsvcRecpNo)를 확보한다.
    #    최신순으로 정렬해 대장서식(regstrKindCd)+주소(동/호) 일치 + progStateCd:91(완료) 매칭.
    #    실패 시 fail-closed(다른 건 발급 방지).
    # ------------------------------------------------------------------
    async def _find_recp_no(
        self, page: Page, req: BuildingRegisterRequest, t: dict
    ) -> dict:
        base = self._s.eais_base_url
        today = _kst_today()  # KST — UTC date.today()면 심야 구간에 하루 어긋남.
        # 방금(초 단위 전) 신청한 건 근처로 좁히되, KST 경계·서버 시계 오차 대비 어제까지 포함.
        body = {
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
        data = await self._post(page, f"{base}/bci/BCIAAA06R01", body)
        rows = data.get("IssueReadHistList") or []
        rows.sort(key=lambda r: str(r.get("firstCrtnDt") or ""), reverse=True)
        kind = _REGSTR_KIND[req.register_kind]
        dong = _norm_unit(t.get("es_dong_nm") or req.dong)
        ho = _norm_unit(t.get("es_ho_nm") or req.ho)
        for r in rows:
            if str(r.get("regstrKindCd")) != kind:
                continue
            addr = str(r.get("locDetlAddr") or "")
            addr_norm = addr.replace(" ", "")
            if dong and (dong + "동") not in addr_norm:
                continue
            if req.register_kind == "exclusive" and ho and not _addr_has_ho(addr, ho):
                continue
            recp = str(r.get("pbsvcRecpNo") or "")
            if recp:
                _log.info("flow.recp_no", recp_no=recp, prog=r.get("progStateCd"))
                return {
                    "pbsvcRecpNo": recp,
                    "mgmNo": str(r.get("mgmNo") or ""),
                    "issueReadGbCd": str(r.get("issueReadGbCd") or "0"),
                    "bldrgstGbCd": str(r.get("bldrgstGbCd") or "1"),
                }
        raise FlowError("upstream", "신청한 발급 건을 확인하지 못했습니다.")

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
        today = _kst_today().strftime("%Y%m%d")  # KST — recpDay/issueReadAppDate 정합.
        rept = _REPT_NM[req.register_kind]

        # 리포트 준비 + FILE_ID/섹션수 확보(발급 버튼이 내부적으로 하던 호출).
        await self._post(
            page,
            f"{base}/cba/CBAAZD04R01",
            {"sysLocGbCd": "3", "reptNm": rept, "recpDay": today, "jobGbCd": "BC"},
        )
        r03 = await self._post(
            page,
            f"{base}/report/BCIAAA06R03",
            {"issueReadAppDate": today, "pbsvcRecpNo": recp["pbsvcRecpNo"]},
        )
        counts = r03.get("count") or {}
        if not counts.get("FILE_ID"):
            raise FlowError("upstream", "발급 리포트를 준비하지 못했습니다.")
        # 완전성 검증용 섹션 수(위반표시가 실리는 '그 밖의 기재사항' 등)를 넘겨 둔다.
        t["_section_counts"] = counts

        payload = {
            "FileName": f"/bci/{rept}",
            "markAnyYn": "Y",
            "actionIdParam": "BCIAAA04L01",
            "bldrgstCurdiGbCd": "0",
            "issueReadAppDate": today,
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
        owned: list[dict] = []
        detail_list: list[dict] = []
        if req.register_kind == "exclusive":
            area = t.get("exclusive_area")
            if area is not None:
                owned.append({"resType": "0", "resArea": str(area)})
        else:
            if t.get("main_prpos"):
                detail_list.append({"resType": "주용도", "resContents": t["main_prpos"]})

        change_list = _parse_changes(ex.get("full_text") or "")

        return BuildingRegisterResult(
            register_kind=req.register_kind,
            comm_unique_no=t.get("recap_pk") if req.register_kind == "exclusive" else t.get("title_pk"),
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
_YEAR_DATE = re.compile(r"(?:19|20)\d{2}[.\-]\d{1,2}[.\-]\d{1,2}")
# 건축 변동 사유 키워드(확장 등재 판정 신호). 소유권이전 등 소유자 변동은 제외(PII·무관).
_CHANGE_KEYWORDS = (
    "신규작성", "신축", "증축", "개축", "재축", "대수선", "용도변경",
    "행위허가", "사용검사", "사용승인", "직권", "말소", "위반건축물", "표시변경",
)


def _clean_reason(s: str) -> str:
    """CLIP 메타(좌표·플래그 숫자런, true/false/blank)를 걷어내고 한글 부위·〈면적〉·구분자만 남긴다.

    좌표/문서번호/면적 숫자런은 부위명 판정에 불필요하므로 제거하되, 한글 부위명(거실/발코니 등)과
    구조 구분자(〈 〉 / ㎡)는 보존한다 — 판정 LLM 이 신고 부위와 대조할 근거다.
    """

    s = re.sub(r"(?:true|false|blank|null)", " ", s)
    s = re.sub(r"-?\d[\d.,\-]{2,}", " ", s)
    s = re.sub(r"[|]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()[:80]


def _parse_changes(text: str) -> list[dict]:
    """변동사항 사유(**부위 포함**)+가능 시 날짜를 추출한다(PII·잡음 배제, 판정 LLM 입력용).

    CLIP viewData 는 글자단위 분절 + 위치숫자 잡음이 심하다. 소유자현황(성명·주소·주민번호)을
    피하려 '변동사항' 헤더 이후, 다음 섹션 전까지만 본다(→ PII 안전). 건축 변동 키워드 주변 창을
    잡아 CLIP 메타를 정리해 사유로 넣는다 — **키워드만 넣으면 부위(거실/발코니 등)가 사라져**
    판정 LLM 이 신고 부위와 대조할 수 없다(#change-area). 인접에 실연도 날짜가 있으면 붙인다.
    """

    compact = re.sub(r"[\s+]+", "", text)  # 게이트/위반검출과 동일 압축(CLIP '+' 공백 제거).
    idx = compact.find("변동사항")
    seg = compact[idx:] if idx >= 0 else compact
    # 다음 섹션(공용부분/증명문/발급일자) 전까지로 한정 — 변동 원문만.
    for marker in ("공용부분", "이등(초)본은", "발급일자"):
        p = seg.find(marker, 5)
        if p > 0:
            seg = seg[:p]
    out: list[dict] = []
    seen: set[str] = set()
    for kw in _CHANGE_KEYWORDS:
        pos = seg.find(kw)
        if pos < 0 or kw in seen:
            continue
        seen.add(kw)
        # 키워드 + 뒤따르는 부위/면적(〈…〉)을 포함하도록 창을 잡고 메타를 정리한다.
        reason = _clean_reason(seg[max(0, pos - 12) : pos + 72]) or kw
        m = _YEAR_DATE.search(seg[max(0, pos - 40) : pos + 72])
        out.append(
            {"resChangeDate": m.group(0) if m else None, "resChangeReason": reason}
        )
        if len(out) >= 20:
            break
    return out
