'use client';

/**
 * 리포트 화면의 **읽기 전용** 도면 오버레이 — 세션의 선택 도면 위에 판단스키마의 벽체·창호를
 * 그리고, 사용자가 고른 철거 검토 대상에 번호 배지를 얹는다(PDF `report_overlay.py` 와 같은
 * 문법·같은 색). 채팅의 `FloorplanOverlayCard` 는 선택 인터랙션용이라 리포트에서는 쓰지 않는다.
 *
 * 좌표 정본: `judgment_schema.wall_objects[].coords` / `window_objects[].coords` 는 원본
 * 이미지 픽셀 좌표계의 폴리라인이다. 서명 URL 로 받은 원본 이미지의 natural 크기를 viewBox 로
 * 쓰면 별도 스케일 없이 겹친다.
 *
 * 이미지·좌표가 없으면 아무것도 렌더하지 않는다(리포트 본문이 도면 없이도 성립).
 */

import { Skeleton, Text } from '@mantine/core';
import { useEffect, useMemo, useState } from 'react';

import { getFloorplanAssetSignedUrl } from '@/lib/sessions/api';

type Pt = { x: number; y: number };
type WallLike = { id: string; kind: 'wall' | 'window'; wallType: string; pts: Pt[] };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function toPts(raw: unknown): Pt[] {
  if (!Array.isArray(raw)) return [];
  const out: Pt[] = [];
  for (const c of raw) {
    if (!isRecord(c)) continue;
    const x = Number(c.x);
    const y = Number(c.y);
    if (Number.isFinite(x) && Number.isFinite(y)) out.push({ x, y });
  }
  return out;
}

/** 판단스키마 → 그리기 대상 목록(벽체 다음 창호). 좌표 2점 미만은 제외. */
export function overlayObjectsOf(judgment: unknown): WallLike[] {
  if (!isRecord(judgment)) return [];
  const out: WallLike[] = [];
  const walls = Array.isArray(judgment.wall_objects) ? judgment.wall_objects : [];
  for (const w of walls) {
    if (!isRecord(w) || typeof w.id !== 'string') continue;
    const pts = toPts(w.coords);
    if (pts.length < 2) continue;
    out.push({
      id: w.id,
      kind: 'wall',
      wallType: typeof w.wall_type === 'string' ? w.wall_type : 'UNKNOWN',
      pts
    });
  }
  const windows = Array.isArray(judgment.window_objects) ? judgment.window_objects : [];
  for (const w of windows) {
    if (!isRecord(w) || typeof w.id !== 'string') continue;
    const pts = toPts(w.coords);
    if (pts.length < 2) continue;
    out.push({ id: w.id, kind: 'window', wallType: 'WINDOW', pts });
  }
  return out;
}

/** 선택 순서를 보존한 선택 id 목록(벽체 → 창호) — PDF `selected_wall_entries` 와 동일 규칙. */
export function selectedIdsOf(judgment: unknown): string[] {
  if (!isRecord(judgment)) return [];
  const ids: string[] = [];
  for (const key of ['selected_walls', 'selected_windows'] as const) {
    const arr = judgment[key];
    if (!Array.isArray(arr)) continue;
    for (const v of arr) if (typeof v === 'string' && !ids.includes(v)) ids.push(v);
  }
  return ids;
}

function strokeOf(wallType: string): string {
  switch (wallType) {
    case 'NON_LOAD_BEARING':
      return 'var(--floorplan-wall-nonload)';
    case 'LOAD_BEARING':
      return 'var(--floorplan-wall-load)';
    case 'WINDOW':
      return 'var(--floorplan-window)';
    default:
      return 'var(--floorplan-wall-uncertain)';
  }
}

function pointsAttr(pts: Pt[]): string {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
}

function centroid(pts: Pt[]): Pt {
  const n = pts.length || 1;
  return {
    x: pts.reduce((s, p) => s + p.x, 0) / n,
    y: pts.reduce((s, p) => s + p.y, 0) / n
  };
}

export function ReportFloorplan({
  sessionId,
  assetId,
  judgment
}: {
  sessionId: string;
  assetId: string;
  judgment: unknown;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);

  const objects = useMemo(() => overlayObjectsOf(judgment), [judgment]);
  const selected = useMemo(() => selectedIdsOf(judgment), [judgment]);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        const signed = await getFloorplanAssetSignedUrl(sessionId, assetId);
        if (ignore) return;
        // natural 크기를 알아야 viewBox 를 잡을 수 있다 — 이미지를 먼저 로드한다.
        const img = new Image();
        img.onload = () => {
          if (ignore) return;
          setDims({ w: img.naturalWidth, h: img.naturalHeight });
          setUrl(signed);
        };
        img.onerror = () => {
          if (!ignore) setFailed(true);
        };
        img.src = signed;
      } catch {
        if (!ignore) setFailed(true);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId, assetId]);

  if (failed) return null;
  if (!url || !dims) {
    return <Skeleton height={220} radius="md" data-testid="report-floorplan-loading" />;
  }

  const base = Math.max(dims.w, dims.h);
  const lineW = Math.max(2, base / 220);
  const badgeR = Math.max(10, base / 36);

  return (
    <div className="report-floorplan">
      <div className="report-floorplan__stage">
        <svg
          viewBox={`0 0 ${dims.w} ${dims.h}`}
          role="img"
          aria-label={
            selected.length
              ? `도면 위에 선택한 철거 검토 대상 ${selected.length}곳을 번호로 표시`
              : '분석한 도면'
          }
        >
          <image href={url} width={dims.w} height={dims.h} />
          {/* 선택 대상은 코랄 헤일로 + 진한 선, 나머지는 옅게 — PDF 와 동일 위계. */}
          {objects.map((o) => {
            const picked = selected.includes(o.id);
            const attr = pointsAttr(o.pts);
            return picked ? (
              <g key={o.id}>
                <polyline
                  points={attr}
                  fill="none"
                  stroke="var(--jippin-brand-cta)"
                  strokeOpacity={0.45}
                  strokeWidth={lineW * 3.2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <polyline
                  points={attr}
                  fill="none"
                  stroke={strokeOf(o.wallType)}
                  strokeWidth={lineW * 1.6}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            ) : (
              <polyline
                key={o.id}
                points={attr}
                fill="none"
                stroke={strokeOf(o.wallType)}
                strokeOpacity={0.55}
                strokeWidth={lineW * 1.1}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}
          {selected.map((id, i) => {
            const o = objects.find((x) => x.id === id);
            if (!o) return null;
            const c = centroid(o.pts);
            return (
              <g key={`badge-${id}`}>
                <circle
                  cx={c.x}
                  cy={c.y}
                  r={badgeR}
                  fill="var(--jippin-brand-cta)"
                  stroke="#FFFFFF"
                  strokeWidth={badgeR * 0.12}
                />
                <text
                  x={c.x}
                  y={c.y}
                  fill="#FFFFFF"
                  fontSize={badgeR * 1.2}
                  fontWeight={700}
                  textAnchor="middle"
                  dominantBaseline="central"
                >
                  {i + 1}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {/* 색 단독 전달 금지(DESIGN §2.4) — 범례 라벨을 항상 붙인다. */}
      <div className="report-legend" aria-hidden>
        <span className="pick">번호 = 선택한 철거 검토 대상</span>
        <span style={{ '--sw': 'var(--floorplan-wall-nonload)' } as React.CSSProperties}>
          비내력벽 후보
        </span>
        <span style={{ '--sw': 'var(--floorplan-wall-load)' } as React.CSSProperties}>
          내력벽 후보(선택 불가)
        </span>
        <span style={{ '--sw': 'var(--floorplan-window)' } as React.CSSProperties}>창호</span>
        <span style={{ '--sw': 'var(--floorplan-wall-uncertain)' } as React.CSSProperties}>
          미확정 벽
        </span>
      </div>
      <Text size="xs" c="dimmed" mt={6} style={{ wordBreak: 'keep-all' }}>
        도면상 비내력벽으로 보여도 실제 시공·현장 조건에 따라 다를 수 있어요. 최종 철거 가부는
        전문가 정밀 검토와 구조안전확인서로 확정합니다.
      </Text>
    </div>
  );
}
