from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from pydantic import (
    AliasChoices,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Sealed APP_ENV enum; DB branch selection comes from environment URLs.
# Any other value is treated as a human error signal and blocks boot.
ALLOWED_APP_ENVS: frozenset[str] = frozenset(
    {"development", "test", "staging", "production"}
)

# 알림톡 템플릿 ID 기본값(현재 SOLAPI 콘솔 승인본). 환경변수로 override 가능하되,
# 빈 문자열은 이 기본값으로 되돌린다(Settings._blank_template_to_default).
_DEFAULT_SOLAPI_TEMPLATE_EXPERT_LEAD_RECEIVED = "KA01TP260615064637638M5QKDCkV5cY"
_DEFAULT_SOLAPI_TEMPLATE_QUICK_LEAD_RECEIVED = "KA01TP260615064659016yiyiJPMBPAp"
_DEFAULT_SOLAPI_TEMPLATE_ASSIGNEE_ASSIGNED = "KA01TP260615064924018oPQFFMUCshw"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    request_id_header: str = Field(default="x-request-id")
    api_port: int = Field(default=8000)
    api_version: str = Field(default="0.1.0")

    database_url: str | None = Field(default=None)
    database_pool_url: str | None = Field(default=None)

    test_mode: bool = Field(default=False)
    anon_session_ttl_days: int = Field(default=30)
    redis_url: str = Field(default="redis://redis:6379/0")

    # 상담 리드(consultation leads) — CMP-DIRECT.
    # 도로명주소 API 승인키(business.juso.go.kr). 미설정 시 주소 검색 endpoint 가 503.
    juso_confm_key: str | None = Field(default=None)
    juso_api_url: str = Field(
        default="https://business.juso.go.kr/addrlink/addrLinkApi.do"
    )
    # 평면도 첨부 Supabase Storage 버킷명 (migration 0009 와 정합).
    lead_floorplan_bucket: str = Field(default="lead-floorplans")
    # 사전검토 세션 도면 업로드 Supabase Storage 버킷명. 운영자가 버킷 생성 + PUT CORS
    # 설정 필요(인프라 선행). 세그멘테이션은 이 버킷의 서명 URL 만 사용한다.
    session_floorplan_bucket: str = Field(default="session-floorplans")

    # 우리집 체크(home-check) — CODEF 세움터 집합건축물대장 전유부+표제부 조회.
    # 결정 정본: docs/adr/0008-home-check-building-register.md.
    # 인증 = loginType=1 (서비스 소유 단일 세움터 계정). id/password·RSA키·세움터
    # 자격증명은 전부 서버 전용 시크릿(프론트 비노출). 미설정 시 home-check 503.
    codef_client_id: str | None = Field(default=None)
    codef_client_secret: str | None = Field(default=None)
    # CODEF RSA 공개키(PEM 또는 Base64) — password 암호화용(cryptography PKCS1 v1.5).
    codef_public_key: str | None = Field(default=None)
    codef_oauth_url: str = Field(default="https://oauth.codef.io/oauth/token")
    # 정식 base. demo(development.codef.io)는 codef_use_demo=true 로만 전환.
    codef_api_base_url: str = Field(default="https://api.codef.io")
    codef_demo_base_url: str = Field(default="https://development.codef.io")
    codef_use_demo: bool = Field(default=False)
    # 전유부/표제부 공통 기관코드(고정 0008).
    codef_organization: str = Field(default="0008")
    # 서비스 소유 세움터 계정(loginType=1). password 는 RSA 암호화 후 전송 즉시 폐기.
    seumter_id: str | None = Field(default=None)
    seumter_password: str | None = Field(default=None)
    # OAuth access_token 캐시 Redis. 미설정 시 redis_url 공유(OAuth state 패턴과 동일).
    codef_token_redis_url: str | None = Field(default=None)
    # 스크래핑 응답이 느려 1차 300s / 2차(추가인증) 170s 까지 허용.
    codef_request_timeout_first_seconds: int = Field(default=300)
    codef_request_timeout_two_way_seconds: int = Field(default=170)
    # 단일 세움터 계정 보호 서킷브레이커(자격증명/계정잠금 오류 누적 시 차단).
    codef_breaker_error_threshold: int = Field(default=5)
    codef_breaker_window_seconds: int = Field(default=300)
    codef_breaker_open_seconds: int = Field(default=600)
    # 발급 PDF 보관 Supabase Storage 버킷명 (migration 0014 와 정합).
    home_check_doc_bucket: str = Field(default="home-check-docs")

    # CMP-609 Phase A 라우터 (sessions/floorplans/chat) 의 운영 노출 가드.
    # `services.main_flow` 는 DB-backed (CMP-608 상당) 로 전환되어 세션 유실
    # 위험은 없지만, Phase A 기능 자체가 미공개 상태이므로 운영 default 는
    # 계속 False 다. 테스트/로컬 dev 만 명시적으로 활성화하고, 출시 시점에
    # 별도 이슈로 켠다.
    phase_a_skeleton_enabled: bool = Field(default=False)

    # ── 에이전트 세션 (우리집 체크 대화형 에이전트) — CMP-DIRECT ────────────────
    # deepagents(LangGraph) 런타임. 운영 default 는 False — main.py 에서
    # phase_a_skeleton_enabled 와 함께 켜져야 agent 라우터가 등록된다. LLM/추적/HF
    # 시크릿은 Fly secrets 로 주입한다(.env.example 의 agent 섹션 참조).
    agent_enabled: bool = Field(default=False)
    agent_model: str = Field(default="openai:gpt-5.4-mini")
    # 단일 런 wall-clock 상한 — 초과 시 done/error 로 마감하고 체크포인터에 보존.
    agent_run_wallclock_timeout_seconds: int = Field(default=600)

    # AI-002 VLM 도면 문맥 해석(SDD §4.4). Mask2Former 레이블을 OpenAI Vision 으로 보완·
    # 정합성 검증한다. 모델/키는 agent 와 공유(gpt-5.4-mini). 비활성/실패 시 세그멘테이션
    # 단독으로 degrade(VLM_TIMEOUT). 0.6 미만 신뢰도는 ANALYSIS_LOW_CONFIDENCE 로 재업로드 권장.
    vlm_floorplan_enabled: bool = Field(default=True)
    vlm_floorplan_timeout_seconds: int = Field(default=60)

    openai_api_key: str | None = Field(default=None)

    # LangSmith 트레이싱 — env-var 자동 계측. langchain_tracing_v2=true 일 때만 동작.
    langchain_tracing_v2: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"),
    )
    langsmith_api_key: str | None = Field(default=None)
    langsmith_project: str = Field(default="jippin-agent")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")

    # LangGraph 체크포인터 — 전용 langgraph 스키마(migration 0015). 체크포인터는
    # psycopg prepared statement 때문에 트랜잭션 풀러(6543)에서 깨지므로 direct
    # (5432) database_url 을 쓴다(아래 _validate_agent_checkpointer_url).
    langgraph_db_schema: str = Field(default="langgraph")
    checkpointer_pool_min_size: int = Field(default=1)
    checkpointer_pool_max_size: int = Field(default=5)

    # HuggingFace 평면도 세그멘테이션 엣지 엔드포인트. 미설정/미배포 시 도구가
    # SEGMENTATION_ENDPOINT_UNAVAILABLE 로 degrade 한다(에이전트 흐름은 유지).
    hf_segmentation_endpoint_url: str | None = Field(default=None)
    hf_segmentation_token: str | None = Field(default=None)
    # 배포가 CPU(intel-spr) + scale-to-zero(15분) 라, 유휴 후 첫 요청은 콜드스타트로
    # TTFB 가 수십 초~수 분이다(모델 카드: "long request timeout"). 전용 엔드포인트는
    # 보통 503 재시도가 아니라 연결을 잡고 늘어지므로 per-request timeout 을 넉넉히 잡는다
    # (run wall-clock 600s 이내). 503 재시도는 폴백으로 둔다.
    hf_segmentation_timeout_seconds: int = Field(default=300)
    # 이 전용 엔드포인트는 scale-to-zero 에서 깨어나는 동안 **503** 을 즉시 돌려준다
    # (Retry-After/estimated_time 힌트 없음). CPU 스케일업이 수 분 걸릴 수 있어, 고정
    # 폴링 간격으로 준비될 때까지 재시도한다 — max_retries × poll 이 run wall-clock(600s)
    # 안에 들도록 잡는다(30 × 10s = 300s).
    hf_segmentation_cold_start_max_retries: int = Field(default=30)
    hf_segmentation_cold_start_poll_seconds: int = Field(default=10)
    # 추론 파라미터(모델 카드 cmp180_full). 학습은 1536 square resize. CPU 지연이 크면
    # max_inference_side 를 1280/1024 로 낮춰 절충할 수 있다(디테일 ↔ 지연).
    hf_segmentation_threshold: float = Field(default=0.5)
    hf_segmentation_mask_threshold: float = Field(default=0.5)
    hf_segmentation_max_inference_side: int = Field(default=1536)
    # 세그멘테이션에 넘길 이미지 URL 의 허용 호스트(스토리지 서명 URL 호스트). 비우면
    # SSRF 가드(https + 사설/로컬/메타데이터 차단)만 적용하고 공개 https 는 허용한다.
    # 운영에서는 스토리지 호스트로 채워 세션 경계를 강제하길 권장한다. (콤마 구분)
    # NoDecode: 콤마 문자열(또는 빈 문자열)을 pydantic-settings 의 JSON 디코딩 전에
    # _parse_comma_list 가 받도록 한다 — list[str] 기본 동작은 env 값을 JSON 으로 파싱해
    # `HOSTS=` 빈 문자열에서 settings 생성이 실패한다(#empty-list-env).
    hf_segmentation_allowed_image_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    # AV 스캔 파이프라인이 아직 없으므로, 엣지 검증(업로드 시 content-type=image/* +
    # owner-folder + 서명 URL 만 사용)을 거친 pending 도면을 기본 허용한다. 그렇지 않으면
    # 모든 업로드가 SEGMENTATION_NOT_SCANNED 로 막혀 분석/리포트가 불가능하다(#unblock-
    # analysis). 단 infected/failed/rejected 는 항상 차단한다. AV 스캔이 붙으면 운영자가
    # False 로 좁혀 'clean'/'not_required' 만 분석하도록 강제할 수 있다.
    agent_allow_unscanned_floorplans: bool = Field(default=True)

    oauth_state_redis_url: str | None = Field(default=None)
    auth_oauth_state_ttl_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices(
            "AUTH_OAUTH_STATE_TTL_SECONDS",
            "OAUTH_STATE_TTL_SECONDS",
        ),
    )
    kakao_rest_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("KAKAO_REST_API_KEY", "OAUTH_KAKAO_CLIENT_ID"),
    )
    kakao_client_secret: str | None = Field(default=None)
    kakao_redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("KAKAO_REDIRECT_URI", "OAUTH_KAKAO_REDIRECT_URI"),
    )
    google_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_OAUTH_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_ID"
        ),
    )
    google_oauth_client_secret: str | None = Field(default=None)
    google_oauth_redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_OAUTH_REDIRECT_URI", "OAUTH_GOOGLE_REDIRECT_URI"
        ),
    )
    naver_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NAVER_OAUTH_CLIENT_ID", "OAUTH_NAVER_CLIENT_ID"),
    )
    naver_oauth_client_secret: str | None = Field(default=None)
    naver_oauth_redirect_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NAVER_OAUTH_REDIRECT_URI", "OAUTH_NAVER_REDIRECT_URI"
        ),
    )
    # Derivation primitives (CMP-DIRECT). Most per-environment URLs are pure
    # functions of {Supabase project ref, public web origin}; instead of hand-
    # filling each one per environment, set these two and let _derive_from_
    # primitives() fill the rest. Any explicit env value still wins (escape
    # hatch) — derivation only fills fields the operator did not provide.
    #   - supabase_ref      -> supabase_jwks_url, supabase_jwt_issuer
    #   - public_web_origin -> frontend_auth_{success,failure,terms}_url, cors
    # NB: DATABASE_*_URL is intentionally NOT derived — it carries a secret
    # password and the pooler shard host is not a pure function of the ref.
    supabase_ref: str | None = Field(default=None)
    public_web_origin: str | None = Field(default=None)

    frontend_auth_success_url: str = Field(default="http://localhost:3000/auth/success")
    frontend_auth_failure_url: str = Field(default="http://localhost:3000/auth/failure")
    frontend_auth_terms_url: str = Field(default="http://localhost:3000/auth/terms")

    auth_jwt_secret: str | None = Field(default=None)
    auth_jwt_alg: str = Field(default="HS256")
    auth_session_ttl_days: int = Field(default=14)
    auth_cookie_name: str = Field(default="jippin_session")
    auth_cookie_domain: str | None = Field(default=None)
    auth_cookie_secure: bool | None = Field(default=None)

    supabase_jwt_issuer: str | None = Field(default=None)
    supabase_jwks_url: str | None = Field(default=None)
    supabase_jwt_secret: str | None = Field(default=None)
    supabase_jwt_audience: str = Field(default="authenticated")

    # 이메일/비밀번호 회원가입 — Supabase Auth GoTrue admin API 호출용 (CMP-DIRECT).
    # 비밀번호는 auth.users 가 단독 관리한다(우리 테이블에 password 컬럼 없음 — AGENTS §4.7 #3).
    # admin base 는 supabase_jwt_issuer(=https://<ref>.supabase.co/auth/v1)에서 파생한다.
    supabase_url: str | None = Field(default=None)
    supabase_service_role_key: str | None = Field(default=None)
    # 비밀번호 변경 시 현재 비밀번호 검증(GoTrue password grant)용 anon/publishable 키.
    supabase_publishable_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"),
    )
    # 회원가입 비밀번호 정책 (Supabase 콘솔 설정과 정합: 최소 6자, 영문+숫자).
    signup_min_password_length: int = Field(default=6)
    # 가입 시 이메일 자동 확인 여부. True 면 휴대폰 인증만으로 이메일을 confirmed 처리한다
    # (이메일 소유 미검증 — squatting 위험 존재). False 로 두려면 Supabase SMTP + 이메일
    # 확인 플로우가 필요하다. 보안 강화 시 False 권장(단, 가입 후 자동 로그인은 불가).
    signup_auto_confirm_email: bool = Field(default=True)

    # SOLAPI 문자 인증 (CMP-DIRECT). 발신번호는 SOLAPI 콘솔에 사전 등록된 번호여야 한다.
    solapi_api_key: str | None = Field(default=None)
    solapi_api_secret: str | None = Field(default=None)
    solapi_sender_phone: str | None = Field(default=None)
    solapi_api_url: str = Field(default="https://api.solapi.com")
    # 카카오 알림톡 채널 ID(pfId) — SOLAPI 콘솔에 연동된 카카오 비즈니스 채널. 미설정 시
    # 알림톡 발송이 비활성화된다(상담 접수 알림은 skip, 직접 발송은 503).
    solapi_channel_id: str | None = Field(default=None)
    # 알림톡 템플릿 ID — SOLAPI 콘솔에 등록·검수 승인된 것만 발송된다. 기본값은 현재
    # 승인본이며, 콘솔에서 템플릿을 재등록(ID 변경)하면 코드 배포 없이 환경변수로 교체한다.
    # 변수 목록이 달라지면 services/alimtalk.py 의 variables 도 함께 맞춰야 한다.
    # 빈 문자열 override(예: `SOLAPI_TEMPLATE_...=`)는 기본값으로 되돌린다(아래 validator).
    solapi_template_expert_lead_received: str = Field(
        default=_DEFAULT_SOLAPI_TEMPLATE_EXPERT_LEAD_RECEIVED  # 전문가 상담 접수
    )
    solapi_template_quick_lead_received: str = Field(
        default=_DEFAULT_SOLAPI_TEMPLATE_QUICK_LEAD_RECEIVED  # 빠른 상담 접수
    )
    solapi_template_assignee_assigned: str = Field(
        default=_DEFAULT_SOLAPI_TEMPLATE_ASSIGNEE_ASSIGNED  # 담당자 배정
    )

    # 휴대폰 OTP — Redis 저장. OAuth state store 와 같은 Redis 를 공유한다.
    phone_otp_code_length: int = Field(default=6)
    phone_otp_ttl_seconds: int = Field(default=180)
    # 인증 성공 후 가입/찾기/재설정 단계에서 쓰는 단기 검증 토큰의 수명.
    phone_otp_token_ttl_seconds: int = Field(default=600)
    phone_otp_max_attempts: int = Field(default=5)
    phone_otp_resend_cooldown_seconds: int = Field(default=30)
    phone_otp_daily_send_limit: int = Field(default=10)
    # 번호 회전 남용 방지 — 발송 전에 IP/글로벌 시간당 한도를 함께 적용한다(SMS 비용/스팸 가드).
    phone_otp_ip_hourly_limit: int = Field(default=20)
    phone_otp_global_hourly_limit: int = Field(default=300)
    # IP 한도의 신뢰 가능한 출처 헤더. 프록시(Fly)가 설정하는 헤더만 신뢰한다 — 클라이언트가
    # 위조 가능한 X-Forwarded-For 는 쓰지 않는다. 빈 값이면 소켓 peer(request.client.host)만 사용.
    phone_otp_trusted_ip_header: str = Field(default="fly-client-ip")
    # NoDecode: 콤마 문자열을 JSON 디코딩 전에 _parse_comma_list 가 받도록 한다.
    kakao_sync_required_term_tags: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["service_terms", "privacy_policy"]
    )

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("app_env", mode="before")
    @classmethod
    def _validate_app_env(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError(
                f"APP_ENV must be a string, got {type(v).__name__}. "
                f"Allowed: {sorted(ALLOWED_APP_ENVS)}."
            )
        normalized = v.strip().lower()
        if normalized not in ALLOWED_APP_ENVS:
            raise ValueError(
                f"APP_ENV={v!r} is not one of {sorted(ALLOWED_APP_ENVS)}. "
                "See AGENTS.md §4.4 and docs/runbooks/neon-branches.md."
            )
        return normalized

    @field_validator(
        "solapi_template_expert_lead_received",
        "solapi_template_quick_lead_received",
        "solapi_template_assignee_assigned",
        mode="before",
    )
    @classmethod
    def _blank_template_to_default(cls, v: object, info: ValidationInfo) -> object:
        # 빈/공백 override 는 미설정과 동일하게 취급해 승인본 기본값으로 되돌린다.
        # (빈 template_id 로 발송하면 SOLAPI 가 전건 거부한다.)
        if v is None or (isinstance(v, str) and not v.strip()):
            return cls.model_fields[info.field_name].default
        return v

    @field_validator("auth_oauth_state_ttl_seconds")
    @classmethod
    def _validate_oauth_state_ttl(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("AUTH_OAUTH_STATE_TTL_SECONDS must be positive.")
        return v

    @field_validator(
        "frontend_auth_success_url",
        "frontend_auth_failure_url",
        "frontend_auth_terms_url",
    )
    @classmethod
    def _validate_frontend_auth_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Frontend auth URLs must be absolute http(s) URLs.")
        return v

    @field_validator("auth_session_ttl_days")
    @classmethod
    def _validate_auth_session_ttl_days(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("AUTH_SESSION_TTL_DAYS must be positive.")
        return v

    @field_validator("auth_cookie_domain", "auth_cookie_secure", mode="before")
    @classmethod
    def _empty_cookie_settings_are_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator(
        "kakao_sync_required_term_tags",
        "hf_segmentation_allowed_image_hosts",
        mode="before",
    )
    @classmethod
    def _parse_comma_list(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("supabase_jwks_url", "supabase_jwt_issuer", mode="before")
    @classmethod
    def _blank_supabase_url_is_none(cls, v: object) -> object:
        # A `.env` copied from `.env.example` carries `SUPABASE_JWKS_URL=` (empty
        # string), which pydantic would otherwise treat as a provided value and
        # block derivation from SUPABASE_REF. Normalize blank -> unset.
        if v == "":
            return None
        return v

    @field_validator("public_web_origin", mode="before")
    @classmethod
    def _validate_public_web_origin(cls, v: object) -> object:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("PUBLIC_WEB_ORIGIN must be a string.")
        origin = v.rstrip("/")
        parsed = urlparse(origin)
        # Derived into cors_allow_origins, which Starlette compares against the
        # browser Origin header by exact string (scheme + host[:port], never a
        # path). Reject any path/query/fragment so a base-URL form like
        # https://dev.jippin.ai/app can't silently produce a CORS entry that
        # blocks every real browser call.
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PUBLIC_WEB_ORIGIN must be a bare origin (scheme + host[:port]) "
                "with no path/query/fragment, e.g. https://dev.jippin.ai."
            )
        return origin

    @model_validator(mode="after")
    def _derive_from_primitives(self) -> "Settings":
        """Fill per-environment URLs from {supabase_ref, public_web_origin}.

        Only fields the operator did NOT pass explicitly are derived — an env
        value always wins. This collapses the secrets surface to the irreducible
        inputs while keeping every field individually overridable (12-factor
        escape hatch).

        Supabase URLs derive whenever they are falsy (None / blank), so the
        documented "leave blank and set SUPABASE_REF" path works even when a
        copied `.env` provides them as empty strings. Fields with concrete
        defaults (frontend URLs, CORS) use ``model_fields_set`` so their
        defaults are not mistaken for an explicit override.
        """
        provided = self.model_fields_set
        if self.supabase_ref:
            base = f"https://{self.supabase_ref}.supabase.co/auth/v1"
            if not self.supabase_jwks_url:
                self.supabase_jwks_url = f"{base}/.well-known/jwks.json"
            if not self.supabase_jwt_issuer:
                self.supabase_jwt_issuer = base
        if self.public_web_origin:
            origin = self.public_web_origin
            if "frontend_auth_success_url" not in provided:
                self.frontend_auth_success_url = f"{origin}/auth/success"
            if "frontend_auth_failure_url" not in provided:
                self.frontend_auth_failure_url = f"{origin}/auth/failure"
            if "frontend_auth_terms_url" not in provided:
                self.frontend_auth_terms_url = f"{origin}/auth/terms"
            if "cors_allow_origins" not in provided:
                self.cors_allow_origins = [origin]
        return self

    @model_validator(mode="after")
    def _validate_agent_checkpointer_url(self) -> "Settings":
        """fail-safe: agent 활성화 시 체크포인터는 direct(:5432) DATABASE_URL 만 허용.

        LangGraph Postgres 체크포인터(psycopg)는 prepared statement 를 쓰므로
        Supabase 트랜잭션 풀러(:6543)에서 ``prepared statement already exists`` 로
        깨진다. 운영 사고를 부팅 시점에 차단한다 — pooler URL 로 agent 를 켜면 boot
        실패가 정상 동작이다.
        """

        # agent 라우터는 이제 phase_a 와 무관하게 agent_enabled 만으로 등록된다(main.py).
        # 따라서 과거의 phase_a_skeleton_enabled 선행 요구는 제거한다 — AGENT_ENABLED 만
        # 켠 배포가 settings 생성 단계에서 깨지지 않도록(#stale-phase-prereq).
        if self.agent_enabled and self.database_url and ":6543" in self.database_url:
            raise ValueError(
                "AGENT_ENABLED=true 는 LangGraph 체크포인터용 direct(:5432) "
                "DATABASE_URL 을 요구한다. 트랜잭션 풀러(:6543)는 psycopg prepared "
                "statement 를 깨뜨린다. DATABASE_URL 을 direct 연결로 설정하라."
            )
        # OpenAI 모델인데 키가 없으면 모든 런이 _build_agent 에서 깨진다 — 사용자가
        # 깨진 채팅을 보는 대신 부팅 시점에 차단한다(서비스는 unavailable 로 유지).
        if (
            self.agent_enabled
            and self.agent_model.startswith("openai")
            and not self.openai_api_key
        ):
            raise ValueError(
                "AGENT_ENABLED=true + OpenAI 모델은 OPENAI_API_KEY 를 요구한다. "
                "키를 설정하거나 AGENT_ENABLED 를 끈다."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
