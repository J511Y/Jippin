'use client';

/**
 * 도로명주소 검색 팝업 연동 (juso.go.kr 공식 "팝업 방식").
 *
 * 기존 백엔드 REST 프록시(`/leads/address/search`) 대신 공식 "팝업 방식" 을 사용한다.
 * 디바이스별 전용 엔드포인트를 쓴다:
 *   - PC:        business.juso.go.kr/addrlink/addrLinkUrl.do
 *   - 모바일/태블릿: business.juso.go.kr/jst/jstRoadNmAddrApiMobilePop
 * 팝업이 `useDetailAddr=Y` 로 상세주소(동/호)까지 받아 returnUrl(`/leads/juso-callback`)
 * 로 콜백하면, 그 라우트가 `window.opener.jusoCallBack(...)` 을 호출한다. 본 helper 는
 * 그 콜백을 Promise 로 감싸 한 번의 await 으로 선택 결과를 돌려준다.
 *
 * 팝업용 승인키는 REST API 승인키(백엔드 `JUSO_CONFM_KEY`)와 별개다 — juso 콘솔에서
 * "팝업" 용으로 발급/도메인 등록한 키를 주입한다. PC 는 `NEXT_PUBLIC_JUSO_POPUP_KEY`,
 * 모바일/태블릿은 `NEXT_PUBLIC_JUSO_POPUP_MOBILE_KEY` 를 쓴다.
 */

// PC 인터넷망 팝업. 모바일/태블릿은 juso "jst" 모바일 팝업을 사용한다(아래 isMobileOrTablet).
const JUSO_POPUP_URL_PC = 'https://business.juso.go.kr/addrlink/addrLinkUrl.do';
const JUSO_POPUP_URL_MOBILE = 'https://business.juso.go.kr/jst/jstRoadNmAddrApiMobilePop';
const POPUP_WINDOW_NAME = 'jusoPopup';

/**
 * 모바일/태블릿 여부. juso 팝업은 디바이스별 전용 엔드포인트(PC: addrLinkUrl.do,
 * 모바일: jst/jstRoadNmAddrApiMobilePop)와 별도 승인키를 쓴다.
 * iPadOS 13+ 는 데스크톱 UA 를 보내므로 touch 포인트로 보강 판별한다.
 */
function isMobileOrTablet(): boolean {
  const nav = window.navigator;
  if (/Android|iPhone|iPad|iPod|IEMobile|Opera Mini|Mobile|Tablet|Silk/i.test(nav.userAgent)) {
    return true;
  }
  // iPadOS 13+ : platform 은 'MacIntel' 이지만 멀티터치를 지원한다.
  return nav.platform === 'MacIntel' && nav.maxTouchPoints > 1;
}

export interface JusoAddressResult {
  /** 도로명 전체 주소 (예: "서울특별시 강남구 테헤란로 1 (역삼동)") */
  roadFullAddr: string;
  /** 기본 도로명주소 part1 */
  roadAddrPart1: string;
  /** 도로명주소 부가정보 part2 (괄호 안 동/건물명 등) */
  roadAddrPart2: string;
  /** 팝업에서 입력받은 상세주소 (useDetailAddr=Y) */
  addrDetail: string;
}

declare global {
  interface Window {
    jusoCallBack?: (...args: string[]) => void;
  }
}

/**
 * 도로명주소 팝업을 열고, 사용자가 주소를 선택하면 결과를 resolve 한다.
 * 사용자가 팝업을 닫으면(콜백 미수신) Promise 는 영구 pending 이므로, 호출부는
 * 별도 상태로 로딩을 관리하지 말고 결과 도착 시점에만 폼을 갱신한다.
 */
export function openJusoAddressPopup(): Promise<JusoAddressResult> {
  return new Promise((resolve) => {
    const mobile = isMobileOrTablet();
    const confmKey =
      (mobile
        ? process.env.NEXT_PUBLIC_JUSO_POPUP_MOBILE_KEY
        : process.env.NEXT_PUBLIC_JUSO_POPUP_KEY) ?? '';
    const popupUrl = mobile ? JUSO_POPUP_URL_MOBILE : JUSO_POPUP_URL_PC;
    // 콜백 라우트가 (useDetailAddr fallback 재전송 시) 같은 디바이스 엔드포인트/키를
    // 다시 쓰도록 mobile 플래그를 returnUrl 에 실어 보낸다.
    const returnUrl = `${window.location.origin}/leads/juso-callback${mobile ? '?mobile=1' : ''}`;

    // 콜백 등록 — returnUrl 라우트가 popup 창에서 window.opener.jusoCallBack 을 호출한다.
    // 콜백 인자 순서는 juso 공식 샘플(resultType=4)을 따른다.
    window.jusoCallBack = (
      roadFullAddr = '',
      roadAddrPart1 = '',
      addrDetail = '',
      roadAddrPart2 = '',
    ) => {
      resolve({ roadFullAddr, roadAddrPart1, roadAddrPart2, addrDetail });
    };

    // 먼저 빈 팝업 창을 연 뒤 그 창을 target 으로 form 을 submit 한다(팝업 차단 회피).
    // 모바일은 작은 고정 창 대신 새 탭/전체 화면으로 띄운다(juso 모바일 권장).
    const windowFeatures = mobile
      ? 'scrollbars=yes,resizable=yes'
      : 'width=570,height=420,scrollbars=yes,resizable=yes';
    window.open('', POPUP_WINDOW_NAME, windowFeatures);

    const form = document.createElement('form');
    form.method = 'post';
    form.action = popupUrl;
    form.target = POPUP_WINDOW_NAME;
    form.acceptCharset = 'UTF-8';

    const fields: Record<string, string> = {
      confmKey,
      returnUrl,
      resultType: '4',
      // 팝업 내부에서 상세주소(동/호)를 직접 입력받아 돌려준다.
      useDetailAddr: 'Y',
    };
    for (const [name, value] of Object.entries(fields)) {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }

    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  });
}
