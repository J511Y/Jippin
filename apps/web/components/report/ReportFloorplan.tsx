'use client';

/**
 * 리포트 화면의 **읽기 전용** 도면 오버레이 — 세션의 선택 도면 위에 판단스키마의 벽체·창호를
 * 그리고, 사용자가 고른 철거 검토 대상에 번호 배지를 얹는다(PDF `report_overlay.py` 와 같은
 * 문법·같은 색). 채팅의 `FloorplanOverlayCard` 는 선택 인터랙션용이라 리포트에서는 쓰지 않는다.
 *
 * 좌표 정본: `judgment_schema.wall_objects[].coords` / `window_objects[].coords` 는 원본
 * 이미지 픽셀 좌표계의 폴리라인이다. 계약상 0~1 정규화 좌표도 허용되므로(MaskCoord), PDF 와
 * 같은 규칙으로 최대값이 1.5 이하면 이미지 크기로 환산한다.
 *
 * 선택 강조색은 Blueprint Navy(`brand.professional`, 도면 분석 UI 강조 축) — coral 은 전환 CTA
 * 전용이라 마커·배지에 쓰지 않는다(AGENTS §4.8.1).
 *
 * 이미지·좌표를 못 가져오면 '준비할 수 없음' 상태를 명시적으로 보여준다(조용히 사라지면
 * 도면이 없는 리포트와 구분이 안 됨).
 */

import { Button, Skeleton, Text } from '@mantine/core';
import { IconRefresh } from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { getFloorplanAssetSignedUrl } from '@/lib/sessions/api';

type Pt = { x: number; y: number };
type WallLike = { id: string; kind: 'wall' | 'window'; wallType: string; pts: Pt[] };

const SELECT_STROKE = 'var(--jippin-brand-professional)';

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

/**
 * 0~1 정규화 좌표(MaskCoord)를 이미지 픽셀로 환산 — PDF `report_overlay.build_overlay` 와 같은
 * 판정(폴리라인 최대값이 0 초과 1.5 이하면 정규화로 본다).
 */
export function scaleObjectsToImage(
  objects: WallLike[],
  dims: { w: number; h: number }
): WallLike[] {
  let maxV = 0;
  for (const o of objects) for (const p of o.pts) maxV = Math.max(maxV, p.x, p.y);
  if (!(maxV > 0 && maxV <= 1.5)) return objects;
  return objects.map((o) => ({
    ...o,
    pts: o.pts.map((p) => ({ x: p.x * dims.w, y: p.y * dims.h }))
  }));
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

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; url: string; dims: { w: number; h: number } }
  | { kind: 'failed' };

/**
 * 도면 구역의 '불러올 수 없음' 상태 — 리포트 화면이 세션 메타 조회에 실패했을 때와,
 * 이 컴포넌트가 서명 URL·이미지 로드에 실패했을 때 같은 모양으로 보여준다.
 */
export function FloorplanUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="report-floorplan report-floorplan--unavailable" role="status">
      <Text size="sm" fw={600}>
        도면 이미지를 지금 불러올 수 없어요
      </Text>
      {/* PDF 도 같은 저장 객체를 읽으므로 '도면이 PDF 엔 있다'고 약속하지 않는다(중립 문구). */}
      <Text size="xs" c="dimmed" mt={4} style={{ wordBreak: 'keep-all' }}>
        판정과 근거는 그대로 유효해요. 잠시 후 다시 시도해 주세요.
      </Text>
      {/* 모바일 터치 타깃 ≥44px(AGENTS §4.8.1) — 실패 복구의 유일한 액션. */}
      <Button
        mt="sm"
        size="sm"
        mih={44}
        variant="light"
        color="jippin"
        radius="md"
        leftSection={<IconRefresh size={16} aria-hidden />}
        onClick={onRetry}
      >
        다시 시도
      </Button>
    </div>
  );
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
  const [state, setState] = useState<LoadState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const rawObjects = useMemo(() => overlayObjectsOf(judgment), [judgment]);
  const selected = useMemo(() => selectedIdsOf(judgment), [judgment]);

  useEffect(() => {
    let ignore = false;
    // attempt 가 바뀌면(재시도) 로딩부터 다시 — await 이후 setState 라 cascading 아님.
    void (async () => {
      try {
        const signed = await getFloorplanAssetSignedUrl(sessionId, assetId);
        if (ignore) return;
        // natural 크기를 알아야 viewBox 를 잡을 수 있다 — 이미지를 먼저 로드한다.
        const img = new Image();
        img.onload = () => {
          if (ignore) return;
          setState({
            kind: 'ready',
            url: signed,
            dims: { w: img.naturalWidth, h: img.naturalHeight }
          });
        };
        img.onerror = () => {
          if (!ignore) setState({ kind: 'failed' });
        };
        img.src = signed;
      } catch {
        if (!ignore) setState({ kind: 'failed' });
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId, assetId, attempt]);

  if (state.kind === 'failed') {
    return (
      <FloorplanUnavailable
        onRetry={() => {
          setState({ kind: 'loading' });
          retry();
        }}
      />
    );
  }
  if (state.kind === 'loading') {
    return <Skeleton height={220} radius="md" data-testid="report-floorplan-loading" />;
  }

  const { url, dims } = state;
  const objects = scaleObjectsToImage(rawObjects, dims);
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
          {/* 선택 대상은 네이비 헤일로 + 진한 선, 나머지는 옅게 — PDF 와 동일 위계. */}
          {objects.map((o) => {
            const picked = selected.includes(o.id);
            const attr = pointsAttr(o.pts);
            return picked ? (
              <g key={o.id}>
                <polyline
                  points={attr}
                  fill="none"
                  stroke={SELECT_STROKE}
                  strokeOpacity={0.4}
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
                  fill={SELECT_STROKE}
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
