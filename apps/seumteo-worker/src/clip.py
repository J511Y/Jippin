"""CLIP Report HTML5 뷰어에서 대장 텍스트·PDF를 추출한다.

세움터 발급 뷰어(`/report/BCIAAA04V01`)는 ClipSoft CLIP Report HTML5 엔진(canvas client-paint).
텍스트는 canvas 에 그려져 DOM 에 없다. 뷰어가 페이지 데이터를 `POST /report/RPTCAA02R02`(JSON,
base64 `viewData`)로 받아 그리므로, 그 응답을 후킹해 디코드한다(paintReportText 후킹은 보조).

**중요(실측)**: 리포트는 **쪽 단위로 지연 로드**된다(viewData.pageNumList=[0]만). 건축물대장
전유부는 2쪽이고 **변동사항·'그 밖의 기재사항'(위반건축물 표시)은 2쪽**에 있다. 1쪽만 읽으면
위반표시를 놓쳐 실제 위반건축물이 정상으로 오안내된다(가장 위험). 그래서 '다음 페이지'를 눌러
모든 쪽의 RPTCAA02R02 를 __clipData 에 적재한 뒤 전 쪽 텍스트를 합쳐 위반을 판정한다.

PII: 리포트에는 소유자 성명·주소·(마스킹된)주민번호가 포함된다(ownrYn:N 이어도 갑지 소유자현황
표시). 본 모듈은 전체 텍스트를 반환하되 **저장은 하지 않으며**(위반여부 bool + 변동사항만 상위에서
사용), 원본 PDF 만 Storage 에 보관한다(ADR-0008).
"""

from __future__ import annotations

import base64
import re

import structlog
from playwright.async_api import Page

_log = structlog.get_logger(__name__)

_VIOLATION = "위반건축물"

# 컨텍스트의 모든 페이지(팝업 포함)에 렌더 전 주입되는 스크립트.
INIT_SCRIPT = r"""
(() => {
  if (window.__clipHooked) return;
  window.__clipHooked = true;
  window.__clipText = [];   // paintReportText 로 그려진 문자열 배열들
  window.__clipData = [];   // RPTCAA02R02 원문 응답들(쪽마다 1건씩 누적)

  // 1) paintReportText 가 정의되는 즉시(렌더 전) 후킹
  (function hook(){
    try {
      if (typeof window.paintReportText === 'function' && !window.paintReportText.__h) {
        const orig = window.paintReportText;
        const wrap = function(){
          try {
            const a = Array.prototype.slice.call(arguments);
            const s = a.filter(x => typeof x === 'string' && x.trim() !== '');
            if (s.length) window.__clipText.push(s);
          } catch(e){}
          return orig.apply(this, arguments);
        };
        wrap.__h = true;
        window.paintReportText = wrap;
      }
    } catch(e){}
    setTimeout(hook, 15);
  })();

  // 2) RPTCAA02R02(페이지 데이터) 응답 캡처 — XHR + fetch 모두 후킹
  try {
    const XP = XMLHttpRequest.prototype;
    const oOpen = XP.open, oSend = XP.send;
    XP.open = function(m,u){ this.__u = u; return oOpen.apply(this, arguments); };
    XP.send = function(b){
      this.addEventListener('load', () => {
        try {
          if (/RPTCAA02R02/.test(this.__u || '')) {
            const t = this.responseText;
            if (t && t.length > 2000) window.__clipData.push(t);
          }
        } catch(e){}
      });
      return oSend.apply(this, arguments);
    };
  } catch(e){}
  try {
    const oFetch = window.fetch;
    if (typeof oFetch === 'function') {
      window.fetch = function(){
        const url = String((arguments[0] && arguments[0].url) || arguments[0] || '');
        const p = oFetch.apply(this, arguments);
        try {
          if (/RPTCAA02R02/.test(url)) {
            p.then(r => { try { r.clone().text().then(t => { if (t && t.length > 2000) window.__clipData.push(t); }).catch(()=>{}); } catch(e){} });
          }
        } catch(e){}
        return p;
      };
    }
  } catch(e){}
})();
"""

# __clipData[k](한 쪽) 한 건을 디코드해 텍스트로. **엔트리별 개별 디코드**가 프레임 일괄
# 디코드보다 안정적이다(실측: 일괄은 레이스로 일부 쪽 누락). 파이썬에서 엔트리마다 호출한다.
_DECODE_ONE_JS = r"""
(k) => {
  try {
    const raw = (window.__clipData || [])[k];
    if (!raw || typeof window.base64DecodeJson !== 'function') return '';
    const j = JSON.parse(raw);
    const vd = j && j.resValue && j.resValue.viewData;
    if (!vd) return '';
    const dec = window.base64DecodeJson(vd);
    const parts = []; const seen = new Set();
    const walk = (o,d) => {
      if (d>16 || parts.length>30000) return;
      if (o == null) return;
      if (typeof o === 'string') {
        if (o.indexOf('%')>=0){ try{ parts.push(decodeURIComponent(o)); }catch(e){ parts.push(o); } }
        else if (o.trim()) { parts.push(o); }
        return;
      }
      if (typeof o !== 'object') return;
      if (seen.has(o)) return; seen.add(o);
      for (const key in o) { try { walk(o[key], d+1); } catch(e){} }
    };
    walk(dec, 0);
    return parts.join('\n');
  } catch(e){ return ''; }
}
"""

_CLIPDATA_CNT_JS = "() => (window.__clipData||[]).length"
_PAINT_JS = "() => (window.__clipText||[]).map(c => c.join(' ')).join('\\n')"

# 프레임별 __clipData 총 바이트(쪽 로드 진행 판정용).
_CLIPDATA_LEN_JS = "() => (window.__clipData||[]).reduce((a,b)=>a+(b?b.length:0),0)"


async def extract_report(popup: Page, *, timeout_ms: int) -> dict:
    """리포트 팝업에서 **전 쪽** 텍스트 + 위반여부 + PDF(base64)를 추출한다."""

    # 초기 렌더/데이터 도착 대기.
    try:
        await popup.wait_for_function(
            "() => (window.__clipData && window.__clipData.length) || document.querySelector('canvas')",
            timeout=timeout_ms,
        )
    except Exception:  # noqa: BLE001
        _log.warning("clip.render_wait_timeout")
    await popup.wait_for_timeout(1800)

    # 모든 쪽 로드 — 변동사항·위반표시(2쪽)를 반드시 포함시키기 위해.
    await _load_all_pages(popup)
    await popup.wait_for_timeout(800)

    # 팝업의 모든 프레임에서 **엔트리별로** 모든 쪽 텍스트를 수집·병합(레이스 회피).
    paint_parts: list[str] = []
    decoded_parts: list[str] = []
    warnings: list[str] = []
    for frame in popup.frames:
        try:
            n = await frame.evaluate(_CLIPDATA_CNT_JS)
        except Exception:  # noqa: BLE001
            n = 0
        for k in range(int(n or 0)):
            try:
                txt = await frame.evaluate(_DECODE_ONE_JS, k)
            except Exception:  # noqa: BLE001
                continue
            if txt and txt not in decoded_parts:  # 동일 쪽 중복 제거
                decoded_parts.append(txt)
        try:
            p = await frame.evaluate(_PAINT_JS)
            if p:
                paint_parts.append(p)
        except Exception:  # noqa: BLE001
            pass

    paint_text = "\n".join(paint_parts)
    decoded_text = "\n".join(decoded_parts)
    full_text = (paint_text + "\n" + decoded_text).strip()

    # CLIP 은 텍스트를 **글자 단위**로 저장한다("신규작성"→["신","규","작","성"]). 줄바꿈으로
    # 이으면 부분문자열 검색이 깨진다("신\n규\n작\n성"). 그래서 공백/줄바꿈 + CLIP 의 '+'(전체
    # 문자열 필드의 공백 인코딩)를 모두 제거한 compact 에서 위반표시("위반건축물")·섹션 앵커를
    # 검출한다 — 놓치면 위반건축물을 정상으로 오안내(silent-normal, 최악)한다. (전 쪽 로드 대상.)
    compact = re.sub(r"[\s+]+", "", full_text)
    violation = _VIOLATION in compact
    violation_source = "report_text" if full_text else None

    pdf_b64, pdf_source = await _capture_pdf(popup, timeout_ms=timeout_ms)

    _log.info(
        "clip.extracted",
        paint_len=len(paint_text),
        decoded_len=len(decoded_text),
        compact_len=len(compact),
        frames=len(popup.frames),
        violation=violation,
        has_pdf=bool(pdf_b64),
        pdf_source=pdf_source,
        warnings=warnings[:4],
    )
    return {
        "full_text": full_text,
        "compact_text": compact,
        "violation": violation,
        "violation_source": violation_source,
        "pdf_base64": pdf_b64,
        "pdf_source": pdf_source,
        "warnings": warnings,
    }


async def _clipdata_total(popup: Page) -> int:
    total = 0
    for fr in popup.frames:
        try:
            total += await fr.evaluate(_CLIPDATA_LEN_JS) or 0
        except Exception:  # noqa: BLE001
            continue
    return total


async def _load_all_pages(popup: Page, *, max_pages: int = 25, page_wait_ms: int = 1200) -> None:
    """'다음 페이지'(``.report_menu_right_button``)를 눌러 모든 쪽을 로드한다.

    각 쪽 이동은 새 RPTCAA02R02 를 유발해 __clipData 가 늘어난다. 클릭 후에도 데이터가 늘지
    않으면 마지막 쪽으로 보고 종료(fail-safe: 버튼 미발견/오류도 조용히 종료 — 1쪽만이라도 유지)."""

    next_loc = None
    for fr in popup.frames:
        try:
            loc = fr.locator(".report_menu_right_button")
            if await loc.count() > 0:
                next_loc = loc.first
                break
        except Exception:  # noqa: BLE001
            continue
    if next_loc is None:
        _log.info("clip.pager_absent")
        return

    prev = await _clipdata_total(popup)
    for _ in range(max_pages):
        try:
            await next_loc.click(timeout=3000)
        except Exception:  # noqa: BLE001
            break
        # 슬로우 정부 서버 대비: 클릭 후 여러 번 폴링해 데이터 증가를 기다린다. 단발성 1.2s
        # 체크는 느린 RPTCAA02R02(>1.2s)를 '마지막 쪽'으로 오인해 2쪽(위반표시)을 놓친다.
        grew = False
        for _ in range(5):
            await popup.wait_for_timeout(page_wait_ms // 2 or 600)
            cur = await _clipdata_total(popup)
            if cur > prev:
                prev = cur
                grew = True
                break
        if not grew:  # 여러 번 폴링해도 새 쪽 데이터 없음 = 마지막 쪽.
            break


# 뷰어 프레임에서 CLIP Report 인스턴스(m_reportHashMap[hash])와 렌더 완료 상태를 찾는다.
_FIND_REPORT_JS = r"""
() => {
  const m = window.m_reportHashMap || {};
  const keys = Object.keys(m);
  if (!keys.length) return null;
  const h = keys[0]; const r = m[h];
  return {
    hash: h,
    ready: !!(r && r.m_isEndReport),
    hasPdf: !!(r && typeof r.pdfDownLoad === 'function'),
  };
}
"""


async def _capture_pdf(popup: Page, *, timeout_ms: int) -> tuple[str | None, str | None]:
    """리포트를 PDF(base64)로 확보한다.

    툴바 'PDF 저장' 버튼은 서버 설정(m_disControl)으로 비활성이지만, 그 버튼이 부르는 Report
    인스턴스 메서드 ``m_reportHashMap[hash].pdfDownLoad()``(clipreport.js 실측)를 **렌더 완료
    (``m_isEndReport``) 후** 직접 호출하면 서버가 전 쪽 PDF 를 생성해 다운로드된다. 렌더 전
    호출은 무시되므로 완료를 폴링한다. (CReportPrintPDf 는 이 HTML5/iframe 뷰어엔 부적합 — 실측.)
    """

    # PDF 는 best-effort 다(위반여부·변동사항은 이미 판정됨). 잡 전체 데드라인(main.py wait_for)
    # 을 잡아먹지 않도록 **타이트하게** 예산을 잡는다 — 느린 PDF 가 판정 끝난 잡을 취소시키면
    # 이미 발급(과금)된 문서가 오류로 보여 재시도→중복발급된다. 이미 전 쪽 렌더 후라 보통 즉시.
    pdf_wait = min(timeout_ms, 15_000)

    # 렌더 완료된 리포트 인스턴스를 폴링(최대 ~10s; 이미 렌더돼 대개 즉시).
    target_frame = None
    report_hash = None
    for _ in range(20):
        for fr in popup.frames:
            try:
                info = await fr.evaluate(_FIND_REPORT_JS)
            except Exception:  # noqa: BLE001
                info = None
            if info and info.get("hasPdf"):
                target_frame, report_hash = fr, info["hash"]
                if info.get("ready"):
                    break
        if target_frame is not None and report_hash:
            try:
                ready = await target_frame.evaluate(
                    "(h) => !!(window.m_reportHashMap[h] && window.m_reportHashMap[h].m_isEndReport)",
                    report_hash,
                )
            except Exception:  # noqa: BLE001
                ready = False
            if ready:
                break
        await popup.wait_for_timeout(500)

    if target_frame is None or not report_hash:
        _log.warning("clip.pdf_no_report")
        return None, None

    try:
        async with popup.expect_download(timeout=pdf_wait) as dl_info:
            await target_frame.evaluate(
                "(h) => window.m_reportHashMap[h].pdfDownLoad()", report_hash
            )
        download = await dl_info.value
        path = await download.path()
        if path:
            with open(path, "rb") as fh:
                data = fh.read()
            if data[:5] == b"%PDF-":
                return base64.b64encode(data).decode("ascii"), "pdf_download"
            _log.warning("clip.pdf_not_pdf", head=str(data[:8]))
    except Exception as exc:  # noqa: BLE001
        _log.warning("clip.pdf_download_failed", err=str(exc)[:120])

    return None, None
