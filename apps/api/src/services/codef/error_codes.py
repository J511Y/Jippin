"""CODEF result.code → 도메인 오류 분류 (정본: CODEF_API_오류코드 표, 2026-06-15).

building_register 가 오류 봉투를 받으면 ``classify(code)`` 로 카테고리를 얻어
도메인 예외로 매핑한다. 미등록 코드는 None → 보수적으로 재시도 가능한 upstream 으로 본다.

카테고리:
  - AUTH      : 자격증명/계정/토큰/암호화 실패. **재시도 금지 + 서킷 카운트.**
  - INVALID   : 요청 파라미터·2way 입력 오류. 재시도 무의미.
  - NOT_FOUND : 조회 결과 없음.
  - UPSTREAM  : 점검/지연/네트워크/일시 제한/2way 타임아웃. 재시도 가능.
"""

from __future__ import annotations

AUTH = "auth"
INVALID = "invalid"
NOT_FOUND = "not_found"
UPSTREAM = "upstream"

# 자격증명/계정/토큰/암호화 — 재시도 금지.
_AUTH_CODES = frozenset(
    {
        "CF-00010",  # 유효한 라이센스 아님
        "CF-00013",  # 허용 IP 아님
        "CF-00014",  # 클라이언트 정보 필요
        "CF-00015",  # 퍼블릭키 필요
        "CF-00026",  # 유효하지 않은 토큰
        "CF-04005",  # client_id 없음
        "CF-04020",  # 비밀번호 복호화 실패 (RSA 암호화/패딩 오류 신호)
        "CF-04028",  # 암호화 파라미터 공백/URL인코딩
        "CF-04036",  # identity 복호화 실패
        "CF-04030",  # 회원가입/인증서 등록 필요 기관
        "CF-04033",  # 존재하지 않는 기관(organization)
        "CF-09990",  # OAuth2.0 토큰 에러
        "CF-09991",  # 비정상 OAuth 토큰
        "CF-09992",  # OAuth 토큰 만료
        "CF-09993",  # OAuth 토큰 고객정보 없음
        "CF-09994",  # OAuth 토큰 없음
        "CF-12048",  # 미지정 단말기
        "CF-12058",  # 대상기관 제한 계정
        "CF-12074",  # 사용자 정보 불일치 (세움터 아이디/비밀번호 오류)
    }
)

# 요청/입력 오류 — 재시도 무의미.
_INVALID_CODES = frozenset(
    {
        "CF-00001",  # 필수 파라미터 누락
        "CF-00002",  # json 형식 오류
        "CF-00007",  # 파라미터 올바르지 않음
        "CF-00008",  # 파라미터 타입 오류
        "CF-00009",  # 인코딩 오류
        "CF-00024",  # 추가인증 입력부 불일치
        "CF-00400",
        "CF-00401",
        "CF-00403",
        "CF-00405",
        "CF-03001",  # 2way 정보 없음
        "CF-03003",  # 2way 항목 불일치
        "CF-03004",  # 2way 메서드 오류
        "CF-03007",  # 요청 비정상 처리
        "CF-03008",  # 인증코드 오류
        "CF-12004",  # 구문 예외
        "CF-12005",  # 입력 파라미터 체계 오류
    }
)

# 조회 결과 없음.
_NOT_FOUND_CODES = frozenset(
    {
        "CF-03999",  # 조회 결과 없음
        "CF-00404",
        "CF-12050",  # 대상기관 미제공 업무
    }
)

# 점검/지연/네트워크/일시 제한/2way 타임아웃 — 재시도 가능.
_UPSTREAM_CODES = frozenset(
    {
        "CF-00006",  # 1회 요청 제한 초과
        "CF-00011",  # 정보수집 서버 없음(20분 후)
        "CF-00012",  # 일 100건 초과
        "CF-00016",  # 동일 요청 처리 중
        "CF-00018",  # 서비스 이용 시간 아님(점검)
        "CF-00022",  # 일일 요청 초과
        "CF-00023",  # IP차단 일일 제한
        "CF-01001",
        "CF-01002",
        "CF-01003",
        "CF-01004",  # 응답 대기 초과
        "CF-01005",  # 엔진 초기화 중
        "CF-01006",  # 중복 로그인 방지
        "CF-01007",  # 네트워크 일시 오류
        "CF-05001",
        "CF-09980",
        "CF-09981",
        "CF-09999",  # 서버 처리 중 에러
        "CF-11022",  # 업데이트 타임아웃
        "CF-12000",  # 알 수 없는 에러
        "CF-12001",  # 사용자 입력 시간 초과(2way timeout)
        "CF-12003",  # 기관 서버 오류
        "CF-12041",  # 이용 가능 시간 아님(점검)
        "CF-12078",  # 보안문자 입력 필요(2way 외 단발 — 자동 처리 불가, 재시도 유도)
    }
)

# RSA/암호화 실패 — dev 스모크에서 패딩/공개키 진단을 위해 WARNING 으로 부각.
RSA_PASSWORD_HINT_CODES = frozenset({"CF-04020", "CF-04028", "CF-04036"})

_BY_CODE: dict[str, str] = {}
for _code in _AUTH_CODES:
    _BY_CODE[_code] = AUTH
for _code in _INVALID_CODES:
    _BY_CODE[_code] = INVALID
for _code in _NOT_FOUND_CODES:
    _BY_CODE[_code] = NOT_FOUND
for _code in _UPSTREAM_CODES:
    _BY_CODE[_code] = UPSTREAM


def classify(code: str | None) -> str | None:
    """result.code → 카테고리. 미등록/None 이면 None(호출부가 보수적 폴백)."""

    if not code:
        return None
    return _BY_CODE.get(code.strip().upper())
