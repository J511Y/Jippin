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
 * juso 는 단계에 따라 returnUrl 을 GET 또는 POST 로 호출한다(공식 JSP 샘플은
 * `request.getParameter()` 로 method 무관하게 읽는다). 따라서 GET·POST 를 모두 받아
 * 쿼리스트링과 폼 바디를 합쳐 동일하게 처리한다 — POST 만 노출하면 GET 콜백에서 405 가 난다.
 *
 * 외부(juso) 도메인에서 오는 요청이므로 CSRF 토큰을 요구하지 않는다 — 응답은 받은 값을
 * opener 로 되돌려줄 뿐이고, 신뢰 경계는 폼 제출 시점의 서버 검증에 있다.
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// 디바이스별 juso 팝업 엔드포인트(lib/leads/juso-popup.ts 와 동일, addrlink 패밀리).
// useDetailAddr fallback 단계에서 같은 엔드포인트로 재전송하기 위해 mobile 플래그
// (returnUrl ?mobile=1)로 분기한다.
const JUSO_POPUP_URL_PC = 'https://business.juso.go.kr/addrlink/addrLinkUrl.do';
const JUSO_POPUP_URL_MOBILE = 'https://business.juso.go.kr/addrlink/addrMobileLinkUrl.do';

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

// 상세주소 입력 폼이 juso 로 재전송하는 주소 필드. addrDetail 은 사용자가 직접 입력하는
// visible input 으로 따로 두므로 hidden passthrough 에서 제외한다(중복 시 빈 hidden 값이
// 먼저 읽혀 입력한 상세주소가 유실되는 것을 방지).
const PASSTHROUGH_FIELDS = CALLBACK_FIELDS.filter((name) => name !== 'addrDetail');

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
function renderDetailForm(
  params: URLSearchParams,
  confmKey: string,
  returnUrl: string,
  popupUrl: string,
): string {
  const hidden = PASSTHROUGH_FIELDS.map((name) => {
    const value = String(params.get(name) ?? '');
    return `<input type="hidden" name="${name}" value="${escapeHtmlAttr(value)}"/>`;
  }).join('\n');
  const roadAddr = escapeHtmlAttr(String(params.get('roadFullAddr') ?? ''));
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
<form name="detailForm" action="${escapeHtmlAttr(popupUrl)}" method="post" accept-charset="UTF-8" target="_self">
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
function renderCallback(params: URLSearchParams, detail: string): string {
  const args = CALLBACK_FIELDS.map((name) => {
    // 상세주소(addrDetail) 자리에는 확정된 detail 값을 싣는다.
    if (name === 'addrDetail') {
      return escapeJs(detail);
    }
    return escapeJs(String(params.get(name) ?? ''));
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

/**
 * 쿼리스트링 + (POST 면) 폼 바디를 하나로 합친다 — juso 가 GET·POST 중 무엇으로
 * 콜백하든 동일하게 읽기 위함(공식 JSP 의 request.getParameter 동작과 일치).
 * 같은 키가 양쪽에 있으면 바디 값이 우선한다.
 */
async function readParams(request: NextRequest): Promise<URLSearchParams> {
  const params = new URLSearchParams(request.nextUrl.searchParams);
  if (request.method === 'POST') {
    const form = await request.formData();
    for (const [name, value] of form.entries()) {
      params.set(name, typeof value === 'string' ? value : '');
    }
  }
  return params;
}

async function handleJusoCallback(request: NextRequest): Promise<NextResponse> {
  const params = await readParams(request);
  const inputYn = String(params.get('inputYn') ?? '');
  // juso 가 echo 하는 공식 필드명은 addrDetail. 일부 흐름의 detailAddr 도 호환 처리한다.
  const detail = String(params.get('addrDetail') ?? params.get('detailAddr') ?? '');

  // 콜백 단계 — useDetailAddr=Y 팝업이 상세주소를 내부 처리해 한 번에 돌려주거나(detail 존재),
  // 2단계 상세주소 입력을 마친 경우(inputYn=Y) opener 로 결과를 반환한다.
  if (detail || inputYn === 'Y') {
    return htmlResponse(renderCallback(params, detail));
  }

  // 1단계 — 상세주소가 아직 없으면 팝업 창 안에서 입력 폼을 렌더한다(fallback).
  // 디바이스에 맞는 엔드포인트/승인키로 재전송하도록 mobile 플래그를 유지한다.
  const mobile = params.get('mobile') === '1';
  const confmKey =
    (mobile
      ? process.env.NEXT_PUBLIC_JUSO_POPUP_MOBILE_KEY
      : process.env.NEXT_PUBLIC_JUSO_POPUP_KEY) ?? '';
  const popupUrl = mobile ? JUSO_POPUP_URL_MOBILE : JUSO_POPUP_URL_PC;
  const returnUrl = new URL(
    `/leads/juso-callback${mobile ? '?mobile=1' : ''}`,
    request.nextUrl.origin,
  ).toString();
  return htmlResponse(renderDetailForm(params, confmKey, returnUrl, popupUrl));
}

export function GET(request: NextRequest): Promise<NextResponse> {
  return handleJusoCallback(request);
}

export function POST(request: NextRequest): Promise<NextResponse> {
  return handleJusoCallback(request);
}
