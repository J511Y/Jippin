// 유닛(jsdom) 테스트 공용 셋업 — vitest.config.ts unit 프로젝트의 setupFiles.
// jsdom 에는 없지만 Mantine 컴포넌트가 의존하는 브라우저 API 를 폴리필한다.
// (앱 전체가 Mantine 기반이므로, 컴포넌트를 렌더하는 모든 유닛 테스트가 이 셋업에 의존한다.)

if (typeof window !== 'undefined') {
  if (typeof window.matchMedia !== 'function') {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false
    })) as unknown as typeof window.matchMedia;
  }

  if (typeof window.ResizeObserver === 'undefined') {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  }
}

if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
