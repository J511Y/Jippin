"""브라우저 매니저 — 세움터 로그인 세션 하나를 유지·재사용한다.

단일 계정(운영자 합의) 모델이라 컨텍스트를 요청마다 새로 만들지 않고, **로그인된 컨텍스트
하나를 상주**시키고 잡마다 페이지만 생성/폐기한다. 렌더는 세마포어로 직렬화(메모리 보호).
세션이 끊기면(로그인 폼이 다시 보이면) 재로그인한다.

로그인은 세움터 일반 로그인(아이디/비밀번호) — 인증서·간편인증·보안문자 없음(발급 정찰로 확인).
"""

from __future__ import annotations

import asyncio
import os

import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from . import clip
from .config import Settings

_log = structlog.get_logger(__name__)

# 헤드리스 컨테이너용 안전 플래그(조사 결과). --single-process 는 크래시 잦아 제외.
_LAUNCH_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--no-first-run",
    "--font-render-hinting=none",
]


class LoginError(RuntimeError):
    """세움터 로그인 실패(자격증명/계정잠금 등). api 는 auth 로 매핑."""


class BrowserManager:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._login_lock = asyncio.Lock()
        self.render_semaphore = asyncio.Semaphore(max(1, settings.seumteo_max_concurrency))

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self._s.headless, args=_LAUNCH_ARGS
        )
        self._context = await self._new_context()
        _log.info("browser.started", headless=self._s.headless)

    async def stop(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        finally:
            if self._browser is not None:
                await self._browser.close()
            if self._pw is not None:
                await self._pw.stop()
        _log.info("browser.stopped")

    async def _new_context(self) -> BrowserContext:
        # 저장된 세션(storage_state)이 있으면 재사용해 로그인 없이 시작한다(자동화가 비번을
        # 입력하지 않음). 없으면 새 컨텍스트 → ensure_logged_in 이 ID/비번으로 로그인한다.
        ctx_kwargs: dict = {"locale": "ko-KR", "accept_downloads": True}
        # UA 고정은 헤드리스에서만. headed(사람 로그인)는 네이티브 Chrome UA 를 써서 UA↔
        # client-hints 불일치로 인한 세션 거부 가능성을 없앤다. 헤드리스 기본 UA 는
        # "HeadlessChrome" 라 거부될 수 있어 일반 Chrome UA 로 대체한다.
        if self._s.headless and getattr(self._s, "browser_user_agent", None):
            ctx_kwargs["user_agent"] = self._s.browser_user_agent
        state_path = self._s.seumteo_storage_state_path
        if state_path and os.path.exists(state_path):
            ctx_kwargs["storage_state"] = state_path
            _log.info("browser.storage_state_loaded", path=state_path)
        ctx = await self._browser.new_context(**ctx_kwargs)
        ctx.set_default_timeout(self._s.action_timeout_ms)
        ctx.set_default_navigation_timeout(self._s.nav_timeout_ms)
        # 모든 페이지(팝업 포함)에 렌더 전 CLIP 후킹 주입 — 리포트 텍스트 캡처의 전제.
        await ctx.add_init_script(clip.INIT_SCRIPT)
        return ctx

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("browser not started")
        return self._context

    def is_healthy(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    # ------------------------------------------------------------------
    # 로그인
    # ------------------------------------------------------------------
    async def ensure_logged_in(self) -> None:
        """로그인 상태 보장. 폼이 보이면 자격증명으로 로그인한다(동시 진입은 lock 으로 1회만)."""

        async with self._login_lock:
            if not self.is_healthy():
                # 브라우저가 죽었으면 재기동 후 새 컨텍스트.
                await self._restart()
            page = await self._context.new_page()
            try:
                await self._login_if_needed(page)
            finally:
                await page.close()

    async def _restart(self) -> None:
        try:
            await self.stop()
        except Exception:  # noqa: BLE001
            pass
        await self.start()

    async def _login_if_needed(self, page: Page) -> None:
        url = self._s.eais_base_url + self._s.eais_login_path
        await page.goto(url, wait_until="domcontentloaded")

        # 로그인 폼(#membId/#pwd)이 있으면 로그인 필요. 없으면 이미 로그인된 세션(메인으로 리다이렉트).
        has_form = await page.locator("#membId").count() > 0
        if not has_form:
            _log.info("login.reuse_session")
            return

        if not self._s.seumter_id or not self._s.seumter_password:
            raise LoginError("세움터 자격증명(SEUMTER_ID/PASSWORD)이 설정되지 않았습니다.")

        await page.fill("#membId", self._s.seumter_id)
        await page.fill("#pwd", self._s.seumter_password)

        # 로그인 버튼 — 여러 셀렉터를 관용적으로 시도, 최후엔 Enter.
        clicked = False
        for sel in ("button.login-btn", "button:has-text('로그인')", "a:has-text('로그인')"):
            loc = page.locator(sel)
            if await loc.count() > 0:
                try:
                    await loc.first.click()
                    clicked = True
                    break
                except Exception:  # noqa: BLE001
                    continue
        if not clicked:
            await page.locator("#pwd").press("Enter")

        # 로그인 결과 대기 — 폼이 사라지면 성공. 실패 시 알럿/에러 메시지가 남는다.
        try:
            await page.wait_for_function(
                "!document.querySelector('#pwd')", timeout=self._s.action_timeout_ms
            )
        except Exception as exc:  # noqa: BLE001
            # 여전히 폼이 보이면 자격증명 오류로 간주(재시도 금지).
            raise LoginError("세움터 로그인에 실패했습니다(자격증명/계정 확인).") from exc
        _log.info("login.ok")
