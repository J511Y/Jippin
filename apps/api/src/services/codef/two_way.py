"""2-way 추가인증 처리 — 동·호 정규화/매칭 + resume 토큰 Redis 저장 (ADR-0008 §2.2).

CODEF 전유부/표제부는 1차 요청(`address`) 후 CF-03002 로 후보 목록(`extraInfo`)을
돌려줄 수 있다. 사용자 query 의 동/호를 정규화해 후보와 **유일 매칭**되면 서버가 2차를
자동 이어가고, 0건/복수건이면 임의추정 없이 ``CodefNeedsUserInput`` 으로 폴백한다.

resume 토큰: 1차 ``twoWayInfo`` + 로그인 파라미터 + 후보를 Redis 에 단기(<170s) 저장한
키. 사용자가 동·호/보안문자를 골라 ``resume_*`` 를 호출하면 이걸 복원해 2차를 만든다.

저장 payload 에는 평문 password 가 들어가지 않는다 — 2차 재구성 시 password 는
``CodefBuildingRegisterClient`` 가 settings 에서 다시 읽어 RSA 암호화한다.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from .types import CodefError

_RESUME_KEY_PREFIX = "codef:twoway:"
# 2차 인증 제한시간(170s)보다 약간 길게. 만료된 토큰은 재인증을 요구한다.
_RESUME_TTL_SECONDS = 170


def normalize_unit(value: str | None) -> str:
    """동/호 문자열을 매칭용으로 정규화한다.

    접두 "제" 제거, 접미 "동"/"호" 제거, 공백 제거, 선행 0 제거.
    예: "제101동" -> "101", "0203호" -> "203", " B동 " -> "B".
    """

    text = (value or "").strip().replace(" ", "")
    if not text:
        return ""
    if text.startswith("제"):
        text = text[1:]
    if text.endswith("동") or text.endswith("호"):
        text = text[:-1]
    # 선행 0 제거하되, 전부 0 이거나 영문/혼합이면 보존.
    stripped = text.lstrip("0")
    if stripped == "" and text != "":
        return "0"
    if stripped.isdigit() or stripped == "":
        return stripped or text
    return stripped


def _match_unique(
    candidates: list[dict[str, Any]],
    *,
    target: str,
    value_keys: tuple[str, ...],
) -> dict[str, Any] | None:
    """정규화 target 과 유일하게 매칭되는 후보를 찾는다. 0건/복수건 → None."""

    norm_target = normalize_unit(target)
    if not norm_target:
        return None
    matches: list[dict[str, Any]] = []
    for cand in candidates:
        for key in value_keys:
            if normalize_unit(str(cand.get(key) or "")) == norm_target:
                matches.append(cand)
                break
    if len(matches) == 1:
        return matches[0]
    return None


def match_dong(candidates: list[dict[str, Any]], dong: str) -> dict[str, Any] | None:
    """reqDongNumList 후보에서 동을 유일 매칭. 키: commDongNum / reqDong."""

    return _match_unique(candidates, target=dong, value_keys=("commDongNum", "reqDong"))


def match_ho(candidates: list[dict[str, Any]], ho: str) -> dict[str, Any] | None:
    """reqHoNumList 후보에서 호를 유일 매칭. 키: commHoNum / reqHo."""

    return _match_unique(candidates, target=ho, value_keys=("commHoNum", "reqHo"))


def has_secure_no(extra_info: dict[str, Any]) -> bool:
    """extraInfo.reqSecureNo 가 비어있지 않으면 보안문자 입력이 필요하다."""

    return bool(str(extra_info.get("reqSecureNo") or "").strip())


# ---------------------------------------------------------------------------
# 후보 축(주소/동/호) 일반화 — CODEF 는 1차 CF-03002 에서 "그때 필요한 축만" 돌려준다.
# (예: 동이 없는 집합건물은 reqHoNumList 만, method="hoNum".) 그래서 세 축을 한꺼번에
# 요구하지 않고, **응답에 실제로 존재하는 축만** 매칭/선택한다.
# ---------------------------------------------------------------------------
# 2차 요청 파라미터로 보낼 때 우선순위(주소 → 동 → 호). CODEF 가 여러 축을 동시에 줄 때도
# 결정적 순서로 처리한다.
FIELD_ORDER: tuple[str, ...] = ("address", "dong", "ho")

# 각 축의 후보 리스트 키 / 2차 요청 파라미터 키.
_FIELD_LIST_KEY = {
    "address": "reqAddrList",
    "dong": "reqDongNumList",
    "ho": "reqHoNumList",
}
_FIELD_PARAM_KEY = {
    "address": "reqAddress",
    "dong": "dongNum",
    "ho": "hoNum",
}


def field_candidates(extra_info: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """extraInfo 에서 해당 축(주소/동/호)의 후보 dict 리스트를 꺼낸다(없으면 빈 리스트)."""

    raw = extra_info.get(_FIELD_LIST_KEY[field]) or []
    return [item for item in raw if isinstance(item, dict)]


def field_param_key(field: str) -> str:
    """2차 요청에서 해당 축이 채우는 파라미터 키(reqAddress/dongNum/hoNum)."""

    return _FIELD_PARAM_KEY[field]


def candidate_value(field: str, candidate: dict[str, Any]) -> str:
    """후보 → 2차 요청에 그대로 보낼 식별자(호=commHoNum, 동=commDongNum, 주소=지번/도로명)."""

    if field == "ho":
        return str(candidate.get("commHoNum") or "")
    if field == "dong":
        return str(candidate.get("commDongNum") or candidate.get("reqDong") or "")
    return str(
        candidate.get("commAddrLotNumber")
        or candidate.get("commAddrRoadName")
        or ""
    )


def candidate_label(field: str, candidate: dict[str, Any]) -> str:
    """후보 → 사용자 표시용 명칭. 식별자만 있고 명칭이 없으면 식별자로 폴백한다."""

    if field == "ho":
        return str(candidate.get("reqHo") or candidate.get("commHoNum") or "")
    if field == "dong":
        return str(candidate.get("reqDong") or candidate.get("commDongNum") or "")
    return str(
        candidate.get("commAddrRoadName")
        or candidate.get("commAddrLotNumber")
        or ""
    )


# 후보 목록이 비정상적으로 클 때의 안전 상한(직렬화/렌더 보호). 실무 reqHoNumList 는
# 대단지여도 수백 건이라 충분하다. 초과 시 잘렸음을 로깅한다(호출부).
MAX_OPTIONS = 600


def field_options(
    candidates: list[dict[str, Any]], field: str, *, limit: int = MAX_OPTIONS
) -> list[dict[str, Any]]:
    """후보 dict 리스트 → 계약(NeedsInputOption) shape {value,label,area?} 로 정규화한다.

    value 가 빈(식별 불가) 후보는 버린다 — 재개 시 보낼 식별자가 없기 때문.
    """

    options: list[dict[str, Any]] = []
    for cand in candidates[:limit]:
        value = candidate_value(field, cand)
        if not value:
            continue
        option: dict[str, Any] = {
            "value": value,
            "label": candidate_label(field, cand) or value,
        }
        if field == "ho":
            area = str(cand.get("reqArea") or "").strip()
            option["area"] = area or None
        options.append(option)
    return options


def resolve_candidate(
    field: str,
    candidates: list[dict[str, Any]],
    *,
    dong: str,
    ho: str,
    selected_value: str | None,
) -> dict[str, Any] | None:
    """해당 축의 후보를 자동 확정한다. 확정 불가(0건/복수건/불일치) → None(사용자 선택 필요).

    우선순위:
      1) selected_value(사용자가 후보에서 고른 식별자)와 정확히 일치하는 후보.
      2) 후보가 단 1건이면 그 후보(자동선택).
      3) 동/호는 사용자 입력을 정규화해 **유일 매칭**되면 그 후보.
      4) 주소는 신뢰할 사용자 키가 없어 자동확정하지 않는다(복수면 선택 요구).
    """

    if not candidates:
        return None
    if selected_value is not None:
        for cand in candidates:
            if candidate_value(field, cand) == selected_value:
                return cand
        return None  # 고른 값이 후보에 없다(만료/불일치) → 다시 선택 요구.
    if len(candidates) == 1:
        return candidates[0]
    if field == "ho":
        return match_ho(candidates, ho)
    if field == "dong":
        return match_dong(candidates, dong)
    return None


_SELECT_MESSAGES = {
    "address": "여러 건물이 검색됐어요. 아래 목록에서 해당 주소를 선택해 주세요.",
    "dong": "조회된 동 목록에서 해당 동을 선택해 주세요.",
    "ho": "조회된 호 목록에서 해당 호를 선택해 주세요. (면적으로 구분할 수 있어요)",
}


def select_message(field: str) -> str:
    """축별 사용자 안내 메시지."""

    return _SELECT_MESSAGES.get(field, "추가 선택이 필요합니다. 목록에서 선택해 주세요.")


class ResumeStore:
    """2-way 1차 컨텍스트를 Redis 에 단기 저장/복원한다.

    ``redis_client`` None 이면 in-process dict 폴백(테스트/단일프로세스). 폴백은
    TTL 을 만료시각으로 근사한다.
    """

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self._redis = redis_client
        self._local: dict[str, tuple[float, str]] = {}

    async def save(self, payload: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(24)
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        key = f"{_RESUME_KEY_PREFIX}{token}"
        if self._redis is not None:
            try:
                await self._redis.set(key, raw, ex=_RESUME_TTL_SECONDS)
                return token
            except RedisError:
                pass
        self._local[token] = (time.time() + _RESUME_TTL_SECONDS, raw)
        return token

    async def load(self, token: str) -> dict[str, Any]:
        key = f"{_RESUME_KEY_PREFIX}{token}"
        raw: str | None = None
        if self._redis is not None:
            try:
                value = await self._redis.get(key)
            except RedisError:
                value = None
            if value is not None:
                raw = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        if raw is None:
            entry = self._local.get(token)
            if entry is not None:
                expiry, stored = entry
                if expiry > time.time():
                    raw = stored
                else:
                    self._local.pop(token, None)
        if raw is None:
            raise CodefError(
                "추가인증 세션이 만료되었습니다. 처음부터 다시 시도해 주세요."
            )
        return json.loads(raw)
