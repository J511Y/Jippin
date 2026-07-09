"""워커 설정 — 세움터 자격증명·엔드포인트·타임아웃.

자격증명은 Fly secrets(앱 단위)로 주입한다:
    fly secrets set -a jippin-seumteo-worker SEUMTER_ID=... SEUMTER_PASSWORD=... SEUMTEO_WORKER_TOKEN=...
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # 세움터 단일 계정(운영자 합의 — 계정 분리 금지, ADR-0009). 로그인은 ID/비번(인증서 미사용).
    seumter_id: str | None = Field(default=None)
    seumter_password: str | None = Field(default=None)

    # api↔worker 공유 시크릿(Flycast 사설망 위 추가 방어). 미설정 시 인증 생략.
    seumteo_worker_token: str | None = Field(default=None)

    # 저장된 로그인 세션(storage_state) 경로. 파일이 있으면 그 세션을 재사용하고, 없으면
    # ID/비번 로그인으로 폴백한다(프로덕션 Fly 는 파일 없음 → secrets 로 자동 로그인, 무변경).
    # 로컬 PoC 는 login.py 로 사람이 한 번 로그인해 이 파일을 만들면 이후 발급은 세션 재사용
    # 으로 돌아가 자동화가 비밀번호를 입력하지 않는다.
    seumteo_storage_state_path: str = Field(default=".auth/state.json")

    # 세움터 베이스 URL. 발급 플로우 캡처 근거는 docs/adr/0009 및 worker README 참조.
    eais_base_url: str = Field(default="https://www.eais.go.kr")
    eais_search_base_url: str = Field(default="https://search.eais.go.kr")
    eais_login_path: str = Field(default="/moct/awp/abb01/AWPABB01F13")

    # 렌더 동시성(2GB에서 1 권장). fly.toml SEUMTEO_MAX_CONCURRENCY 와 맞춘다.
    seumteo_max_concurrency: int = Field(default=1)

    # 브라우저 User-Agent 고정. 헤드리스 기본 UA("HeadlessChrome")는 정부 통합인증(Any-ID)
    # 세션에서 거부/재인증을 유발할 수 있어, headed 로그인과 headless 재사용이 같은 UA 를
    # 쓰도록 일반 Chrome UA 로 통일한다(세션 이식성 향상). 번들 chromium 131 에 맞춘다.
    browser_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
    )

    # 브라우저/네비게이션 타임아웃(ms). 세움터는 느릴 수 있어 넉넉히.
    headless: bool = Field(default=True)
    nav_timeout_ms: int = Field(default=45_000)
    action_timeout_ms: int = Field(default=30_000)
    # 리포트 렌더 완료(RPTCAA02R02 응답 + 캔버스) 대기 상한. 2쪽 발급은 실측 ~10s 라 넉넉.
    report_render_timeout_ms: int = Field(default=45_000)
    # 단일 잡 전체 상한. **Flycast 프록시(~60s)보다 짧게** 잡아, 실제 발급까지 마친 느린 잡이
    # 프록시 절단으로 오류처럼 보여 재시도→중복발급되는 것을 막는다(잡이 프록시보다 먼저 깨끗이
    # 실패). 더 긴 렌더가 필요하면 fly.toml 을 .internal 직결 + auto_stop=off 로 바꾼다(README).
    job_deadline_ms: int = Field(default=55_000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
