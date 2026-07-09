"""세움터 건축물대장 발급 워커 (CODEF 대체, ADR-0009).

apps/api(jippin)가 Flycast 사설망으로 호출하는 Playwright headless Chromium 서비스.
전체 발급 플로우(로그인 → 주소검색 → 조회 → 담기 → 신청 → 발급 → CLIP 리포트 추출)를
브라우저 세션 하나로 수행하고, 구조화 필드 + 위반건축물 판정 + 원본 PDF(base64)를 돌려준다.
"""
