r"""사람이 발급 서비스에 직접 로그인하고, **바로 그 로그인된 탭에서** 발급·CLIP 추출을 검증.

핵심 교훈(오늘 버그): 세움터 발급 페이지는 '발급 진입' 세션 상태를 요구한다. 새 탭 +
직접 URL 이동은 그 상태가 없어 로그인 게이트로 튕긴다(= 로그아웃처럼 보임). 그래서 이전
attended_poc 는 로그인한 탭을 닫고 새 탭에서 돌려 세션이 풀렸다. 이번엔 **로그인한 탭을
그대로 재사용**(assume_ready=True)하고, 새 탭/랜딩 재이동을 하지 않는다.

실행:
    cd apps/seumteo-worker
    .\.venv\Scripts\python.exe attended_poc.py "경기도 용인시 기흥구 구갈로 71-18" 102동 901호

절차:
 1) headed 창이 뜨면 **발급 서비스로 로그인**(회원 발급 → 아이디/비밀번호 로그인). '건축물대장
    신청내역' 표 화면이 보일 때까지 로그인한 뒤 터미널에서 Enter.
 2) 스크립트가 **그 탭에서** 전유부+표제부를 발급하고 CLIP 추출 결과를 출력, PDF 를 out/ 에 저장.
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

from src.browser import BrowserManager
from src.config import get_settings
from src.flow import FlowError, SeumteoFlow
from src.models import BuildingRegisterRequest


async def _enter(message: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input, message)


async def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(2)
    road, dong, ho = sys.argv[1], sys.argv[2], sys.argv[3]

    settings = get_settings()
    object.__setattr__(settings, "headless", False)  # 사람이 로그인 → headed(네이티브 UA)
    # 깨끗한 시작: 이전 실행이 남긴 stale storage_state 를 로드하지 않는다(충돌 방지).
    object.__setattr__(settings, "seumteo_storage_state_path", "")

    mgr = BrowserManager(settings)
    await mgr.start()
    try:
        page = await mgr.context.new_page()
        await page.goto(
            settings.eais_base_url + "/moct/bci/aaa04/BCIAAA04L01",
            wait_until="domcontentloaded",
        )
        print("=" * 64)
        print("발급 서비스로 로그인하세요(회원 발급 → 아이디/비밀번호 로그인).")
        print("'건축물대장 신청내역' 표 화면이 보이면 터미널에서 Enter 를 누르세요.")
        print("=" * 64)
        await _enter(">>> 발급 신청내역 화면이 보이면 Enter: ")

        print(f"[현재 URL] {page.url}")
        if "BCIAZA01F02" in page.url or "AWPABB01F1" in page.url:
            print("[경고] 아직 로그인/게이트 화면 같습니다. 그래도 진행은 해봅니다.")

        # 로그인한 이 탭을 그대로 재사용(새 탭/랜딩 재이동 금지 → 발급 진입 세션 유지).
        flow = SeumteoFlow(mgr, settings)
        for kind in ("exclusive", "heading"):
            print("=" * 64)
            print(f"[{kind}] 발급/추출 (같은 탭 재사용)")
            req = BuildingRegisterRequest(
                road_addr=road,
                dong=dong,
                ho=(ho if kind == "exclusive" else ""),
                register_kind=kind,  # type: ignore[arg-type]
            )
            try:
                r = await flow._run_on_page(page, req, assume_ready=True)
            except FlowError as e:
                print(f"  [FLOW ERROR] {e.category}/{e.field}: {e.message}")
                print(f"  [현재 URL] {page.url}")
                continue
            ex = r.extraction
            print(f"  violation_status : {r.violation_status!r} (src={ex.violation_source})")
            print(f"  report_text_len  : {ex.report_text_len}")
            print(f"  comm_unique_no   : {r.comm_unique_no}")
            print(f"  road/jibun       : {r.road_addr} / {r.jibun_addr}")
            print(f"  owned            : {r.owned}")
            print(f"  detail_list      : {r.detail_list}")
            print(f"  change_list[:5]  : {r.change_list[:5]}")
            print(f"  pdf              : {'yes' if r.original_pdf_base64 else 'NO'} (src={ex.pdf_source})")
            print(f"  warnings         : {ex.warnings}")
            if r.original_pdf_base64:
                out = Path("out")
                out.mkdir(exist_ok=True)
                p = out / f"{kind}.pdf"
                p.write_bytes(base64.b64decode(r.original_pdf_base64))
                print(f"  PDF saved: {p.resolve()} ({p.stat().st_size} bytes)")

        # 성공 시 세션 저장(이후 헤드리스 재사용 실험용) — 같은 탭 컨텍스트 기준.
        try:
            state = Path(".auth/state.json")
            state.parent.mkdir(parents=True, exist_ok=True)
            await mgr.context.storage_state(path=str(state))
            print(f"[세션 저장] {state.resolve()}")
        except Exception as e:  # noqa: BLE001
            print(f"[세션 저장 실패] {type(e).__name__}: {e}")

        print("=" * 64)
        print("완료. 결과를 붙여주세요.")
    finally:
        await mgr.stop()


if __name__ == "__main__":
    asyncio.run(main())
