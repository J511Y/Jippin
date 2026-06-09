'use client';

/**
 * 도로명주소 검색 팝업 연동 (juso.go.kr — business.juso.go.kr/jst/jstRoadNmAddrApiPop).
 *
 * 기존 백엔드 REST 프록시(`/leads/address/search`) 대신 공식 "팝업 방식" 을 사용한다.
 * 팝업이 `useDetailAddr=Y` 로 상세주소(동/호)까지 받아 returnUrl(`/leads/juso-callback`)
 * 로 POST 하면, 그 라우트가 `window.opener.jusoCallBack(...)` 을 호출한다. 본 helper 는
 * 그 콜백을 Promise 로 감싸 한 번의 await 으로 선택 결과를 돌려준다.
 *
 * 팝업용 승인키(`NEXT_PUBLIC_JUSO_POPUP_KEY`)는 REST API 승인키(백엔드 `JUSO_CONFM_KEY`)
 * 와 별개다 — juso 콘솔에서 "팝업" 용으로 발급/도메인 등록한 키를 주입한다.
 */

const JUSO_POPUP_URL = 'https://business.juso.go.kr/addrlink/addrLinkUrl.do';
const POPUP_WINDOW_NAME = 'jusoPopup';

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
    const confmKey = process.env.NEXT_PUBLIC_JUSO_POPUP_KEY ?? '';
    const returnUrl = `${window.location.origin}/leads/juso-callback`;

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
    window.open('', POPUP_WINDOW_NAME, 'width=570,height=420,scrollbars=yes,resizable=yes');

    const form = document.createElement('form');
    form.method = 'post';
    form.action = JUSO_POPUP_URL;
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
