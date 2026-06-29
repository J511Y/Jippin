"""도면 + 선택 벽체 오버레이 SVG 빌더 (CMP-DIRECT, REPORT PDF §1).

리포트 PDF 의 첫 필수 요소 — 업로드된 도면 이미지 위에 사용자가 고른 철거 대상
벽체(selected_walls)를 강조해 그린 **인라인 SVG** 를 만든다. 프론트의
``FloorplanOverlayCard`` 가 화면에서 하던 일을 서버에서 정적으로 재현한다.

좌표 정본 — ``judgment_schema.wall_objects[].coords`` (도면 좌표계의 폴리라인).
``selected_walls`` 는 ``wall_objects[].id`` 와 같은 id 공간이다(domain._derive_wall_type
참고). 이미지 크기는 asset 행에 없어 Pillow 로 직접 측정한다.

순수 모듈(네트워크 없음) — 이미지 바이트를 인자로 받는다. Pillow 로 못 열거나
좌표가 없으면 ``available=False`` 로 degrade 한다(리포트는 계속 발행).
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

# ① ~ ⑳ 원형 숫자. 초과분은 "(n)" 으로 폴백.
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def circled(n: int) -> str:
    """1-기반 순번을 원형 숫자(①…)로. 20 초과는 '(n)'."""

    return _CIRCLED[n - 1] if 1 <= n <= len(_CIRCLED) else f"({n})"


def selected_wall_entries(judgment_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """selected_walls 순서를 보존한 [{index, id, wall_type}] 목록.

    SVG 의 강조 번호와 리포트 본문의 '벽체별 판단' 목록이 같은 순번을 쓰도록
    단일 정본으로 둔다. selected_walls 가 비면 빈 목록.
    """

    selected = judgment_schema.get("selected_walls")
    walls = judgment_schema.get("wall_objects")
    if not isinstance(selected, list):
        return []
    by_id: dict[str, str] = {}
    if isinstance(walls, list):
        for w in walls:
            if isinstance(w, dict) and isinstance(w.get("id"), str):
                wt = w.get("wall_type")
                by_id[w["id"]] = wt if isinstance(wt, str) else "UNKNOWN"
    out: list[dict[str, Any]] = []
    for sid in selected:
        if not isinstance(sid, str):
            continue
        out.append(
            {
                "index": len(out) + 1,
                "id": sid,
                "wall_type": by_id.get(sid, "UNKNOWN"),
            }
        )
    return out


def _coords_of(wall: dict[str, Any]) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for c in wall.get("coords") or []:
        if isinstance(c, dict):
            x, y = c.get("x"), c.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                pts.append((float(x), float(y)))
    return pts


def _tone_stroke(wall_type: str) -> str:
    if wall_type == "NON_LOAD_BEARING":
        return "#1B7F46"  # success
    if wall_type == "LOAD_BEARING":
        return "#C0392B"  # danger
    return "#1F6F8B"  # info / unknown


def _points_attr(pts: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def build_overlay(
    *,
    image_bytes: bytes | None,
    content_type: str | None,
    judgment_schema: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """도면 이미지 + 벽체 오버레이 SVG 를 만든다.

    반환: ``{available, svg, caption, unavailable_reason}``. 이미지나 좌표가 없으면
    ``available=False`` + 사유. ``entries`` 는 ``selected_wall_entries`` 결과(번호 정합).
    """

    caption = (
        "주황 강조 = 선택한 철거 대상 벽체 · 초록 = 비내력벽 후보 · "
        "빨강 = 내력벽 후보(선택 불가) · 파랑 = 확인 필요"
    )

    if not image_bytes:
        return {
            "available": False,
            "svg": None,
            "caption": caption,
            "unavailable_reason": "분석에 사용한 도면 이미지를 불러오지 못했어요.",
        }

    # 임베드 래스터 최대 변(px). 원본은 50MiB 까지 허용되므로, 좌표·viewBox 는 원본 px
    # 공간 그대로 두고 base64 로 박는 래스터만 축소해 메모리·PDF 크기 폭증을 막는다.
    max_embed_dim = 1600
    try:
        from PIL import (
            Image,
        )  # 지연 임포트 — Pillow 는 WeasyPrint 의존성으로 함께 설치됨.

        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            if max(width, height) > max_embed_dim:
                # 임베드용으로만 축소(좌표는 원본 px → <image> 가 같은 박스로 늘려 정합).
                img.thumbnail((max_embed_dim, max_embed_dim))
                save_img = (
                    img
                    if img.mode in ("RGB", "RGBA", "L", "LA", "P")
                    else img.convert("RGB")
                )
                buf = BytesIO()
                save_img.save(buf, format="PNG", optimize=True)
                embed_bytes = buf.getvalue()
                embed_mime = "image/png"
            else:
                embed_bytes = image_bytes
                embed_mime = Image.MIME.get(
                    img.format or "", content_type or "image/png"
                )
    except Exception:  # noqa: BLE001 — 손상/미지원 포맷이면 degrade.
        return {
            "available": False,
            "svg": None,
            "caption": caption,
            "unavailable_reason": "도면 이미지를 해석하지 못했어요(지원하지 않는 형식).",
        }

    if width <= 0 or height <= 0:
        return {
            "available": False,
            "svg": None,
            "caption": caption,
            "unavailable_reason": "도면 이미지 크기를 확인하지 못했어요.",
        }

    walls = judgment_schema.get("wall_objects")
    walls = walls if isinstance(walls, list) else []
    selected_ids = {e["id"] for e in entries}
    index_by_id = {e["id"]: e["index"] for e in entries}

    # 좌표가 0~1 정규화로 들어오면 픽셀로 환산(폴리라인 최대값으로 추정).
    max_v = 0.0
    for w in walls:
        for x, y in _coords_of(w):
            max_v = max(max_v, x, y)
    scale_x, scale_y = (width, height) if 0 < max_v <= 1.5 else (1.0, 1.0)

    data_uri = f"data:{embed_mime};base64," + base64.b64encode(embed_bytes).decode(
        "ascii"
    )

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        f'<image href="{data_uri}" x="0" y="0" '
        f'width="{width}" height="{height}" preserveAspectRatio="none"/>',
        # 비선택 벽은 옅게 깔아 맥락만 보여준다.
    ]
    line_w = max(width, height) / 220.0  # 이미지 크기에 비례한 선 두께.

    for w in walls:
        if not isinstance(w, dict):
            continue
        pts = [(x * scale_x, y * scale_y) for x, y in _coords_of(w)]
        if len(pts) < 2:
            continue
        wid = w.get("id")
        wt = w.get("wall_type") if isinstance(w.get("wall_type"), str) else "UNKNOWN"
        is_selected = isinstance(wid, str) and wid in selected_ids
        attr = _points_attr(pts)
        if is_selected:
            # 강조: 굵은 주황 헤일로 + 종류 톤 실선.
            parts.append(
                f'<polyline points="{attr}" fill="none" stroke="#F26B4F" '
                f'stroke-opacity="0.45" stroke-width="{line_w * 3.2:.2f}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
            parts.append(
                f'<polyline points="{attr}" fill="none" stroke="{_tone_stroke(wt)}" '
                f'stroke-width="{line_w * 1.6:.2f}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
        else:
            # 비선택 벽도 종류 색으로 옅게 — 사용자가 왜 일부만 선택 가능한지 보이게.
            parts.append(
                f'<polyline points="{attr}" fill="none" stroke="{_tone_stroke(wt)}" '
                f'stroke-opacity="0.55" stroke-width="{line_w * 1.1:.2f}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )

    # 선택 벽 위에 번호 배지(본문 '벽체별 판단' 목록과 동일 순번).
    badge_r = max(width, height) / 36.0
    for w in walls:
        if not isinstance(w, dict):
            continue
        wid = w.get("id")
        if not (isinstance(wid, str) and wid in index_by_id):
            continue
        pts = [(x * scale_x, y * scale_y) for x, y in _coords_of(w)]
        if not pts:
            continue
        cx, cy = _centroid(pts)
        num = index_by_id[wid]
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{badge_r:.1f}" '
            f'fill="#F26B4F" stroke="#FFFFFF" stroke-width="{badge_r * 0.12:.2f}"/>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" fill="#FFFFFF" '
            f'font-size="{badge_r * 1.2:.1f}" font-weight="700" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-family="sans-serif">{num}</text>'
        )

    parts.append("</svg>")
    return {
        "available": True,
        "svg": "".join(parts),
        "caption": caption,
        "unavailable_reason": None,
    }
