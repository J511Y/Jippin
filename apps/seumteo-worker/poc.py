"""세움터 발급 플로우 로컬 PoC — 실주소로 추출을 검증한다.

배포 없이 워커 코드(browser+flow+clip)를 그대로 한 건 돌려본다. headed 모드로 눈으로 보며
디버깅하기 좋다. 위반건축물 케이스 주소로도 돌려 위반 검출을 확인할 것.

사전:
    pip install -r requirements.txt
    playwright install chromium
    set SEUMTER_ID=...            (PowerShell: $env:SEUMTER_ID="...")
    set SEUMTER_PASSWORD=...

실행:
    python poc.py "서울특별시 영등포구 여의대방로43나길 25" 104동 504호 exclusive
    python poc.py "서울특별시 영등포구 여의대방로43나길 25" 104동 "" heading

결과: 콘솔에 위반여부·텍스트길이·필드, PDF 는 ./out/<kind>.pdf 로 저장.
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path

from src.browser import BrowserManager
from src.config import get_settings
from src.flow import FlowError, SeumteoFlow
from src.models import BuildingRegisterRequest


async def main() -> None:
    if len(sys.argv) < 5:
        print(__doc__)
        raise SystemExit(2)
    road_addr, dong, ho, kind = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    settings = get_settings()
    # 로컬 디버깅은 headed 로 본다(env HEADLESS=1 로 강제 헤드리스 가능).
    object.__setattr__(settings, "headless", os.environ.get("HEADLESS") == "1")

    mgr = BrowserManager(settings)
    await mgr.start()
    try:
        flow = SeumteoFlow(mgr, settings)
        req = BuildingRegisterRequest(
            road_addr=road_addr, dong=dong, ho=ho, register_kind=kind  # type: ignore[arg-type]
        )
        try:
            result = await flow.run(req)
        except FlowError as exc:
            print(f"[FLOW ERROR] category={exc.category} field={exc.field} :: {exc.message}")
            raise SystemExit(1)

        print("=" * 60)
        print(f"register_kind      : {result.register_kind}")
        print(f"violation_status   : {result.violation_status!r}  (source={result.extraction.violation_source})")
        print(f"report_text_len    : {result.extraction.report_text_len}")
        print(f"comm_unique_no     : {result.comm_unique_no}")
        print(f"road/jibun         : {result.road_addr} / {result.jibun_addr}")
        print(f"owned              : {result.owned}")
        print(f"detail_list        : {result.detail_list}")
        print(f"change_list[:3]    : {result.change_list[:3]}")
        print(f"pdf                : {'yes' if result.original_pdf_base64 else 'NO'}  (source={result.extraction.pdf_source})")
        print(f"warnings           : {result.extraction.warnings}")
        print("=" * 60)

        if result.original_pdf_base64:
            out = Path("out")
            out.mkdir(exist_ok=True)
            pdf_path = out / f"{result.register_kind}.pdf"
            pdf_path.write_bytes(base64.b64decode(result.original_pdf_base64))
            print(f"PDF saved: {pdf_path.resolve()}  ({pdf_path.stat().st_size} bytes)")
    finally:
        await mgr.stop()


if __name__ == "__main__":
    asyncio.run(main())
