import { type NextRequest, NextResponse } from 'next/server';

/**
 * 도로명주소 팝업(`business.juso.go.kr`) returnUrl 핸들러.
 *
 * juso 팝업은 postMessage 가 아니라 "returnUrl 로 폼 전송 → 그 페이지가 opener.jusoCallBack
 * 호출 → 자기 자신을 닫음" 방식으로 동작한다. `useDetailAddr=Y` 이므로 도로명 + 상세주소(동/층/호)
 * 까지 juso 가 팝업 안에서 직접 받고, 사용자가 "주소입력" 을 누르면 `inputYn=Y` 로 이 returnUrl
 * 을 호출한다. 따라서 이 라우트는 팝업 안에서 잠깐 로드되어 부모창(opener)의 jusoCallBack 으로
 * 값을 넘기고 즉시 닫히는 "보이지 않는 중계 페이지" 다 — 별도의 상세주소 입력 폼을 렌더하지
 * 않는다(useDetailAddr=Y 와 중복되어 흐름이 꼬인다).
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

// juso resultType=4 콜백 인자 순서(공식 샘플과 동일). 상세주소는 addrDetail(또는 detailAddr).
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

function escapeJs(value: string): string {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

/** opener 의 jusoCallBack 을 호출하고 팝업을 닫는, 보이지 않는 중계 페이지. */
function renderCallback(params: URLSearchParams): string {
  // juso 가 echo 하는 공식 필드명은 addrDetail. 일부 흐름의 detailAddr 도 호환 처리한다.
  const detail = String(params.get('addrDetail') ?? params.get('detailAddr') ?? '');
  const args = CALLBACK_FIELDS.map((name) => {
    if (name === 'addrDetail') {
      return escapeJs(detail);
    }
    return escapeJs(String(params.get(name) ?? ''));
  }).join(',');
  return `<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><title>주소 선택</title></head>
<body>
<p style="font-family:system-ui,sans-serif;color:#6b7280;padding:16px">주소를 적용하는 중입니다…</p>
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
  return htmlResponse(renderCallback(params));
}

export function GET(request: NextRequest): Promise<NextResponse> {
  return handleJusoCallback(request);
}

export function POST(request: NextRequest): Promise<NextResponse> {
  return handleJusoCallback(request);
}
