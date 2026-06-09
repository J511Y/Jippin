import { type NextRequest, NextResponse } from 'next/server';

/**
 * 도로명주소 팝업(`business.juso.go.kr`) returnUrl 핸들러.
 *
 * `useDetailAddr=Y` 흐름은 returnUrl 을 **두 번** 호출한다(juso 공식 샘플과 동일):
 *   1) 주소 선택 직후: `inputYn != 'Y'` — 팝업 안에서 상세주소(동/호)를 입력받는 폼을
 *      렌더한다. 확인 시 juso `addrLinkUrl.do` 로 모든 필드 + `detailAddr` + `inputYn=Y`
 *      를 재전송한다.
 *   2) 상세주소 입력 후: `inputYn == 'Y'` — `window.opener.jusoCallBack(...)`
 *      (lib/leads/juso-popup.ts 가 등록)을 호출하고 팝업을 닫는다.
 *
 * 외부(juso) 도메인에서 오는 POST 이므로 CSRF 토큰을 요구하지 않는다 — 응답은 받은 값을
 * opener 로 되돌려줄 뿐이고, 신뢰 경계는 폼 제출 시점의 서버 검증에 있다.
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const JUSO_POPUP_URL = 'https://business.juso.go.kr/addrlink/addrLinkUrl.do';

// juso resultType=4 콜백 인자 순서(공식 샘플과 동일). 상세주소(addrDetail)는 detailAddr 로 대체된다.
const CALLBACK_FIELDS = [
  'roadFullAddr',
  'roadAddrPart1',
  'addrDetail',
  'roadAddrPart2',
  'engAddr',
  'jibunAddr',
  'zipNo',
  'admCd',
  'rnMgtSn',
  'bdMgtSn',
  'detBdNmList',
  'bdNm',
  'bdKdcd',
  'siNm',
  'sggNm',
  'emdNm',
  'liNm',
  'rn',
  'udrtYn',
  'buldMnnm',
  'buldSlno',
  'mtYn',
  'lnbrMnnm',
  'lnbrSlno',
  'emdNo',
] as const;

// 상세주소 입력 폼이 juso 로 재전송해야 하는 주소 필드(콜백 필드와 동일 집합).
const PASSTHROUGH_FIELDS = [...CALLBACK_FIELDS];

function escapeHtmlAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeJs(value: string): string {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

/** 1단계 — 팝업 안에서 상세주소를 입력받는 폼(확인 시 juso 로 재전송). */
function renderDetailForm(form: FormData, confmKey: string, returnUrl: string): string {
  const hidden = PASSTHROUGH_FIELDS.map((name) => {
    const value = String(form.get(name) ?? '');
    return `<input type="hidden" name="${name}" value="${escapeHtmlAttr(value)}"/>`;
  }).join('\n');
  const roadAddr = escapeHtmlAttr(String(form.get('roadFullAddr') ?? ''));
  return `<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>상세주소 입력</title>
<style>
  body{font-family:system-ui,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;margin:0;padding:20px;color:#1f2937}
  .addr{font-size:14px;color:#374151;margin-bottom:12px;word-break:keep-all}
  input[type=text]{width:100%;box-sizing:border-box;padding:10px 12px;font-size:15px;border:1px solid #d1d5db;border-radius:8px;margin-bottom:12px}
  button{width:100%;padding:11px;font-size:15px;font-weight:600;color:#fff;background:#2f6df6;border:0;border-radius:8px;cursor:pointer}
</style>
</head>
<body>
<form name="detailForm" action="${escapeHtmlAttr(JUSO_POPUP_URL)}" method="post" accept-charset="UTF-8" target="_self">
  <input type="hidden" name="confmKey" value="${escapeHtmlAttr(confmKey)}"/>
  <input type="hidden" name="returnUrl" value="${escapeHtmlAttr(returnUrl)}"/>
  <input type="hidden" name="resultType" value="4"/>
  <input type="hidden" name="useDetailAddr" value="N"/>
  <input type="hidden" name="inputYn" value="Y"/>
${hidden}
  <div class="addr">${roadAddr}</div>
  <input type="text" id="addrDetail" name="addrDetail" placeholder="상세 주소 (예: 101동 1001호)" autofocus
    onkeydown="if(event.key==='Enter'){event.preventDefault();document.detailForm.submit();}"/>
  <button type="submit">확인</button>
</form>
</body>
</html>`;
}

/** 콜백 단계 — opener 의 jusoCallBack 호출 후 팝업 종료. */
function renderCallback(form: FormData, detail: string): string {
  const args = CALLBACK_FIELDS.map((name) => {
    // 상세주소(addrDetail) 자리에는 확정된 detail 값을 싣는다.
    if (name === 'addrDetail') {
      return escapeJs(detail);
    }
    return escapeJs(String(form.get(name) ?? ''));
  }).join(',');
  return `<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><title>주소 선택</title></head>
<body>
<script>
  (function () {
    try {
      if (window.opener && typeof window.opener.jusoCallBack === 'function') {
        window.opener.jusoCallBack(${args});
      }
    } catch (e) {}
    window.close();
  })();
</script>
</body>
</html>`;
}

function htmlResponse(body: string): NextResponse {
  return new NextResponse(body, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const form = await request.formData();
  const inputYn = String(form.get('inputYn') ?? '');
  // juso 가 echo 하는 공식 필드명은 addrDetail. 일부 흐름의 detailAddr 도 호환 처리한다.
  const detail = String(form.get('addrDetail') ?? form.get('detailAddr') ?? '');

  // 콜백 단계 — useDetailAddr=Y 팝업이 상세주소를 내부 처리해 한 번에 돌려주거나(detail 존재),
  // 2단계 상세주소 입력을 마친 경우(inputYn=Y) opener 로 결과를 반환한다.
  if (detail || inputYn === 'Y') {
    return htmlResponse(renderCallback(form, detail));
  }

  // 1단계 — 상세주소가 아직 없으면 팝업 창 안에서 입력 폼을 렌더한다(fallback).
  const confmKey = process.env.NEXT_PUBLIC_JUSO_POPUP_KEY ?? '';
  const returnUrl = new URL('/leads/juso-callback', request.nextUrl.origin).toString();
  return htmlResponse(renderDetailForm(form, confmKey, returnUrl));
}
