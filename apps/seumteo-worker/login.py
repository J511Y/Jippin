r"""세움터 로그인 세션을 1회 저장한다(사람이 직접 로그인 → storage_state 저장).

자동화가 계정 비밀번호를 폼에 입력하지 않도록, 로컬 검증에서는 **사람이 브라우저에서 한 번
직접 로그인**하고 그 세션 쿠키를 파일로 저장한다. 이후 poc.py / 워커는 이 세션을 재사용한다
(``config.seumteo_storage_state_path``, 기본 ``.auth/state.json``).

실행:
    cd apps/seumteo-worker
    .\.venv\Scripts\python.exe login.py

세움터 메인 페이지가 뜨면 우측 상단 **로그인**으로 아이디/비밀번호 로그인하세요. 로그인을
끝낸 뒤 **이 터미널에서 Enter** 를 누르면 현재 세션을 저장하고 창이 닫힙니다. (DOM 자동감지
대신 사람 확인을 쓰는 이유: 세움터 로그인 폼 URL/셀렉터가 배포마다 달라 오탐이 나기 때문.)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from src.config import get_settings


async def _prompt_enter(message: str) -> None:
    """이벤트 루프를 막지 않고 콘솔 Enter 를 기다린다."""

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input, message)


async def main() -> None:
    settings = get_settings()
    state_path = Path(settings.seumteo_storage_state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="ko-KR", accept_downloads=True)
        page = await ctx.new_page()
        # 메인 페이지에서 사용자가 '로그인'으로 직접 인증한다(폼 URL 을 가정하지 않음).
        await page.goto(settings.eais_base_url, wait_until="domcontentloaded")

        print("=" * 64)
        print("세움터 창에서 '로그인'으로 아이디/비밀번호 로그인 하세요.")
        print("로그인을 끝낸 뒤 여기(터미널)에서 Enter 를 누르세요.")
        print("=" * 64)
        await _prompt_enter(">>> 로그인 완료 후 Enter: ")

        # 로그인 성공 확인(약한 sanity): 세션 쿠키가 하나라도 있어야 한다.
        cookies = await ctx.cookies()
        session_like = [
            c for c in cookies if "eais.go.kr" in (c.get("domain") or "")
        ]
        if not session_like:
            print("[경고] eais.go.kr 쿠키가 없습니다. 로그인이 안 된 것 같아요.")
            print("       로그인을 마친 뒤 다시 실행해 주세요. (저장하지 않음)")
            await browser.close()
            raise SystemExit(1)

        await ctx.storage_state(path=str(state_path))
        print(f"[완료] 세션 저장됨: {state_path.resolve()}  (쿠키 {len(cookies)}개)")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
