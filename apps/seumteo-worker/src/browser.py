"""브라우저 매니저 — 세움터 로그인 세션 하나를 유지·재사용한다.

단일 계정(운영자 합의) 모델이라 컨텍스트를 요청마다 새로 만들지 않고, **로그인된 컨텍스트
하나를 상주**시키고 잡마다 페이지만 생성/폐기한다. 렌더는 세마포어로 직렬화(메모리 보호).

**로그인 판단은 폼 유무가 아니라 '능동 인증 확인'으로 한다.** eais 로그인 페이지는 Nuxt CSR
(클라이언트 렌더)이라 domcontentloaded 직후엔 `#membId` 폼이 아직 없다 — 이를 "폼 없음 = 이미
로그인"으로 오판하면 프로덕션(세션파일 없는 콜드스타트)에서 **한 번도 실제 로그인하지 못한 채**
익명 세션으로 진행돼, 담기/장바구니(R05)가 빈 결과로 실패한다. 그래서 세션 엔드포인트
(`/cba/CBAAZA02R01`)로 실제 로그인 여부를 확인하고(401/403/빈 membNo = 세션 끊김), 끊겼으면
로그인 폼 hydrate 를 기다렸다 자격증명으로 로그인한 뒤 재검증한다. (참고 구현: excel-macro
detect_login_status / wait_for_login_form.)

로그인은 세움터 일반 로그인(아이디/비밀번호) — 인증서·간편인증·보안문자 없음(발급 정찰로 확인).
"""

from __future__ import annotations

import asyncio
import json
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

# 세션 엔드포인트 능동 확인용 in-page fetch(same-origin, 4xx 에도 throw 하지 않고 status 반환).
_SESSION_CHECK_JS = """
async (url) => {
  try {
    const r = await fetch(url, { method: 'GET', credentials: 'same-origin' });
    const text = await r.text();
    return { status: r.status, text: text.slice(0, 20000) };
  } catch (e) { return { status: 0, text: '' }; }
}
"""


class LoginError(RuntimeError):
    """세움터 로그인 실패(자격증명/계정잠금 등). api 는 auth 로 매핑."""


class BrowserManager:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._login_lock = asyncio.Lock()
        self._keepalive_task: asyncio.Task | None = None
        self.render_semaphore = asyncio.Semaphore(
            max(1, settings.seumteo_max_concurrency)
        )

    async def _launch_browser(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self._s.headless, args=_LAUNCH_ARGS
        )
        self._context = await self._new_context()

    async def start(self) -> None:
        await self._launch_browser()
        # 세션 keep-alive — ~60분 TTL 이 만료되기 전에 능동 검증으로 갱신(상시가동+유휴 대비).
        # _restart 로 브라우저만 재기동될 때 이 supervisor 태스크는 살아남는다(중복 생성 금지).
        interval = getattr(self._s, "seumteo_session_keepalive_seconds", 0) or 0
        if interval > 0 and self._keepalive_task is None:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop(interval))
        _log.info("browser.started", headless=self._s.headless)

    async def _close_browser(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
        finally:
            if self._browser is not None:
                await self._browser.close()
            if self._pw is not None:
                await self._pw.stop()
        self._context = None
        self._browser = None
        self._pw = None

    async def stop(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._keepalive_task = None
        await self._close_browser()
        _log.info("browser.stopped")

    async def _keepalive_loop(self, interval: int) -> None:
        """주기적으로 능동 로그인 검증(→ 필요 시 재로그인)해 세션 TTL 을 갱신한다.

        검증 요청 자체가 세션 만료 시각을 뒤로 미룬다. 잡과는 _login_lock 으로 직렬화되므로
        동시 로그인은 발생하지 않는다(read-only 검증은 잡의 세션 사용과 겹쳐도 무해)."""

        while True:
            try:
                await asyncio.sleep(interval)
                # 잡과 겹치지 않게 render_semaphore 를 잡고 검증한다 — 잡 도중 재로그인이 공용
                # 세션을 갈아엎는 것을 방지(유휴 시엔 즉시 획득되어 사실상 무비용). 잡은 L 을
                # 먼저 놓고 S 를 잡으므로 순환대기(deadlock) 없음.
                async with self.render_semaphore:
                    await self.ensure_logged_in()
                _log.info("login.keepalive")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                _log.warning("login.keepalive_failed", error=str(exc)[:160])

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
        # 브라우저만 재기동한다 — keepalive supervisor 태스크는 건드리지 않는다(keepalive 가
        # ensure_logged_in→_restart 를 부를 수 있어, 자기 자신을 cancel/await 하면 데드락).
        try:
            await self._close_browser()
        except Exception:  # noqa: BLE001
            pass
        await self._launch_browser()

    async def _is_authenticated(self, page: Page) -> bool:
        """세션 엔드포인트(/cba/CBAAZA02R01)로 실제 로그인 여부를 능동 확인한다.

        폼 유무 heuristic 은 Nuxt CSR 에서 오탐한다(렌더 전엔 폼이 없어 '로그인됨'으로 오판).
        대신 인증 세션에서만 membNo 가 채워지는 세션 엔드포인트를 직접 친다:
        401/403(세션 만료) · 비200 · 빈 membNo → 미인증. 요청은 same-origin 이라 eais 위에서 실행."""

        base = self._s.eais_base_url
        if not (page.url or "").startswith(base):
            try:
                await page.goto(base + "/", wait_until="domcontentloaded")
            except Exception:  # noqa: BLE001
                return False
        try:
            res = await page.evaluate(_SESSION_CHECK_JS, f"{base}/cba/CBAAZA02R01")
        except Exception:  # noqa: BLE001
            return False
        status = res.get("status") if isinstance(res, dict) else None
        if status != 200:  # 401/403(세션 끊김) 포함 — 비200 은 미인증 취급.
            return False
        try:
            data = json.loads(res.get("text") or "{}")
        except (ValueError, TypeError):
            return False
        rep = data.get("ds_SessionRep") or {}
        return bool(str(rep.get("membNo") or "").strip())

    async def _wait_for_login_form(self, page: Page) -> bool:
        """SPA hydrate 로 로그인 폼(#membId)이 렌더될 때까지 대기(핵심 수정)."""

        try:
            await page.wait_for_selector(
                "#membId", state="visible", timeout=self._s.login_form_timeout_ms
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _login_if_needed(self, page: Page) -> None:
        # 1) 능동 인증 확인 — 폼 유무(SPA 오탐) 대신 세션 엔드포인트로 실제 로그인 여부를 본다.
        if await self._is_authenticated(page):
            _log.info("login.session_valid")
            return

        # 2) 세션 끊김(401/403/빈 membNo) → 자격증명으로 로그인.
        if not self._s.seumter_id or not self._s.seumter_password:
            raise LoginError(
                "세움터 자격증명(SEUMTER_ID/PASSWORD)이 설정되지 않았습니다."
            )

        url = self._s.eais_base_url + self._s.eais_login_path
        await page.goto(url, wait_until="domcontentloaded")
        # Nuxt CSR — domcontentloaded 직후엔 #membId 가 아직 없다. 폼 hydrate 를 기다린다.
        if not await self._wait_for_login_form(page):
            raise LoginError(
                "세움터 로그인 폼을 찾지 못했습니다(페이지 구조 변경/네트워크 확인)."
            )

        await page.fill("#membId", self._s.seumter_id)
        await page.fill("#pwd", self._s.seumter_password)

        # 로그인 버튼 — 여러 셀렉터를 관용적으로 시도, 최후엔 Enter.
        clicked = False
        for sel in (
            "button.login-btn",
            "button:has-text('로그인')",
            "a:has-text('로그인')",
        ):
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

        # 제출 처리 대기 — 폼이 사라지면 진행. (폼이 남아도 아래 재검증이 최종 판단.)
        try:
            await page.wait_for_function(
                "!document.querySelector('#pwd')", timeout=self._s.action_timeout_ms
            )
        except Exception:  # noqa: BLE001
            pass

        # 3) 재검증 — 폼 사라짐 ≠ 인증 성공일 수 있어, 능동 확인으로 로그인 성공을 보장.
        if not await self._is_authenticated(page):
            raise LoginError("세움터 로그인에 실패했습니다(자격증명/계정 확인).")
        _log.info("login.ok")
