"""에이전트 런마다 주입하는 '현재 세션 상태' 컨텍스트 빌더 (CMP-DIRECT).

deep agent 는 user 메시지 + 체크포인터 히스토리만 본다. 그래서 REST 로 갱신된 OVERLAY
선택(selected_walls)이나, 다른 경로로 확정된 주소·도면 분석 상태가 **에이전트에게
보이지 않아** (1) 사용자가 고른 벽을 모르고, (2) 이미 받은 정보를 또 묻는다.

매 런 system prompt 끝에 현재 세션 상태 스냅샷을 덧붙여 에이전트가 '이미 아는 것'을
정확히 알게 한다. prompts.py 의 '이미 아는 것을 다시 묻지 않기' 규칙의 실제 근거가 된다.
시스템 프롬프트는 체크포인트되지 않고 모델 호출 시점에 적용되므로, 런마다 최신 상태로
다시 주입된다(과거 스냅샷이 누적되지 않음).
"""

from __future__ import annotations

from typing import Any


def _wall_type_by_id(judgment: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    walls = judgment.get("wall_objects")
    if isinstance(walls, list):
        for w in walls:
            if isinstance(w, dict) and isinstance(w.get("id"), str):
                wt = w.get("wall_type")
                if isinstance(wt, str):
                    out[w["id"]] = wt
    return out


def build_session_state_context(
    session: dict[str, Any] | None,
    address: dict[str, Any] | None,
) -> str | None:
    """세션/주소 상태를 사람이 읽는 한국어 스냅샷 블록으로 만든다(없으면 None).

    주의: 이 블록은 '이미 확보된 사실'만 담아 에이전트가 재질문을 피하게 한다. 추측·미확정
    값은 넣지 않는다.
    """

    if not isinstance(session, dict):
        return None
    judgment = session.get("judgment_schema")
    judgment = judgment if isinstance(judgment, dict) else {}
    lines: list[str] = []

    # 주소 — 받았으면 다시 묻지 말 것.
    if isinstance(address, dict):
        parts = [address.get("road_address") or address.get("jibun_address")]
        for key in ("apartment_name", "building_dong", "unit_ho"):
            if address.get(key):
                parts.append(str(address[key]))
        addr_txt = " ".join(p for p in parts if p)
        if addr_txt:
            lines.append(f"- 확정 주소: {addr_txt} — 이미 받았으니 다시 묻지 말 것.")
        floor = address.get("floor_no")
        area = address.get("exclusive_area_m2")
        extra = []
        if floor is not None:
            extra.append(f"층수 {floor}")
        if area is not None:
            extra.append(f"전용 {area}㎡")
        if extra:
            lines.append(f"  (확정된 건물 정보: {', '.join(extra)})")

    # 도면 — 첨부/분석됐으면 도면 우선, 도면을 다시 요청하지 말 것.
    walls = judgment.get("wall_objects")
    if session.get("selected_floorplan_asset_id"):
        if isinstance(walls, list) and walls:
            nonload = sum(
                1
                for w in walls
                if isinstance(w, dict) and w.get("wall_type") == "NON_LOAD_BEARING"
            )
            load = sum(
                1
                for w in walls
                if isinstance(w, dict) and w.get("wall_type") == "LOAD_BEARING"
            )
            lines.append(
                f"- 평면도: 첨부 + 분석 완료 (비내력벽 후보 {nonload}곳, 내력벽 후보 "
                f"{load}곳). 도면이 이미 있으니 **도면 기준으로 진행**하고 도면을 다시 "
                f"요청하지 말 것. 주소는 도면 후보 탐색용일 뿐이라, 도면이 있으면 주소가 "
                f"없어도 분석/검토를 이어갈 수 있다."
            )
        else:
            lines.append(
                "- 평면도: 첨부됨(분석 진행/대기). 도면을 다시 요청하지 말 것."
            )

    # OVERLAY-002 선택 — 사용자가 도면에서 직접 고른 철거 대상 벽.
    selected = judgment.get("selected_walls")
    if isinstance(selected, list) and selected:
        ids = [s for s in selected if isinstance(s, str)]
        wt = _wall_type_by_id(judgment)
        all_nonload = bool(ids) and all(wt.get(i) == "NON_LOAD_BEARING" for i in ids)
        note = " (모두 비내력벽 후보)" if all_nonload else ""
        shown = ", ".join(ids[:10])
        lines.append(
            f"- 사용자가 도면에서 철거 대상으로 직접 선택한 벽: {len(ids)}곳{note}. "
            f"region_id: {shown}. 이 선택을 '이미 아는 것'으로 다루고, 사용자가 '내가 "
            f"고른/선택한 벽'을 물으면 이 선택을 근거로 답할 것(선택을 모른다고 하지 말 것)."
        )

    # 이미 수집된 판단값(있으면) — 같은 걸 또 묻지 않게.
    jv = judgment.get("judgment_values")
    if isinstance(jv, dict):
        known = {k: v for k, v in jv.items() if v is not None}
        if known:
            lines.append(
                f"- 이미 수집된 판단값: {known} — 같은 항목을 다시 묻지 말 것."
            )

    if not lines:
        return None
    return (
        "[현재 세션 상태 — 이미 확보된 정보. 아래 사실은 이미 알고 있으니 사용자에게 다시 "
        "묻지 말고 그대로 활용한다]\n" + "\n".join(lines)
    )
