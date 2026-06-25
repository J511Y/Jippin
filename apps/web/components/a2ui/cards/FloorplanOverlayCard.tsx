'use client';

/**
 * A2UI `FloorplanOverlay` 카드 — 도면 위 분석 영역 오버레이 + 비내력벽 선택 (CMP-DIRECT).
 *
 * 기능명세서 §2.5 OVERLAY-001/002, SDD §4.5 OVERLAY 모듈의 프론트 정본.
 * - OVERLAY-001: AI 분석 결과(폴리곤/클래스)를 평면도 위에 반투명 색상 + 레이블 + 범례로
 *   오버레이. SVG 기반(폴리곤=DOM 요소 → 클릭/접근성 용이, 의존성 0). 핀치 줌·드래그 팬 지원.
 * - OVERLAY-002: 비내력벽 후보(wall_other)를 클릭으로 단일/복수 선택 → selected_walls 로
 *   판단스키마에 기록(updateSelectedWalls). 내력벽 후보는 보이되 선택 불가(철거 대상 아님).
 *
 * 안전 어휘(모델 카드 + BRAND): '후보/추정/검토 필요'만 쓰고 '철거 가능 확정/내력벽 확정'은
 * 절대 쓰지 않는다. 모델 출력은 사람 검토(HITL)용 입력이지 법적/구조 판정이 아니다.
 *
 * payload: { asset_id?, image?: {width,height}, regions: Region[] }. payload 는 서버가
 * 구성하지만(LLM 미관여) 런타임 형태 방어를 위해 좁혀서 읽는다.
 */

import { ActionIcon, Box, Group, Loader, Stack, Text, Tooltip } from '@mantine/core';
import {
  IconArrowsMaximize,
  IconHandFinger,
  IconMinus,
  IconPhotoExclamation,
  IconPlus,
  IconVectorTriangle
} from '@tabler/icons-react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { useChatActions } from '@/components/agent/chat-actions';
import { getSession, updateSelectedWalls } from '@/lib/sessions/api';
import { getFloorplanAssetSignedUrl } from '@/lib/sessions/api';

import { CardHeader, CardRule, CardShell } from './CardShell';

export type OverlayRegion = {
  region_id: string;
  class_name: string;
  polygon: number[];
  bbox?: number[];
  score?: number;
  requires_hitl?: boolean;
};

export type FloorplanOverlayPayload = {
  asset_id?: string;
  image?: { width?: number; height?: number };
  regions?: OverlayRegion[];
};

type ClassKind = 'wall' | 'opening' | 'space';

type ClassStyle = {
  color: string;
  label: string;
  kind: ClassKind;
};

// 18 클래스 → 색/라벨/종류. 색은 데이터 시각화용 고대비 팔레트.
const CLASS_STYLE: Record<string, ClassStyle> = {
  wall_reinforced_concrete: { color: '#E03131', label: '내력벽 후보', kind: 'wall' },
  wall_other: { color: '#2F9E44', label: '비내력벽 후보', kind: 'wall' },
  wall_unknown: { color: '#868E96', label: '미분류 벽', kind: 'wall' },
  door: { color: '#1971C2', label: '문', kind: 'opening' },
  window: { color: '#1098AD', label: '창문', kind: 'opening' },
  space_balcony: { color: '#F08C00', label: '발코니', kind: 'space' },
  space_living_room: { color: '#7048E8', label: '거실', kind: 'space' },
  space_kitchen: { color: '#0CA678', label: '주방', kind: 'space' },
  space_bedroom: { color: '#4263EB', label: '침실', kind: 'space' },
  space_bathroom: { color: '#15AABF', label: '욕실', kind: 'space' },
  space_entrance: { color: '#9C36B5', label: '현관', kind: 'space' },
  space_stairwell: { color: '#5C940D', label: '계단실', kind: 'space' },
  space_elevator_hall: { color: '#A9A9A9', label: '엘리베이터홀', kind: 'space' },
  space_elevator: { color: '#A9A9A9', label: '엘리베이터', kind: 'space' },
  space_dress_room: { color: '#C2255C', label: '드레스룸', kind: 'space' },
  space_ac_room: { color: '#74B816', label: '실외기실', kind: 'space' },
  space_multipurpose: { color: '#7950F2', label: '다목적실', kind: 'space' },
  space_other: { color: '#ADB5BD', label: '기타 공간', kind: 'space' }
};

const FALLBACK_STYLE: ClassStyle = { color: '#ADB5BD', label: '영역', kind: 'space' };

function styleFor(cls: string): ClassStyle {
  return CLASS_STYLE[cls] ?? FALLBACK_STYLE;
}

/** 비내력벽 후보만 철거 희망 대상으로 선택 가능(OVERLAY-002). */
function isSelectable(cls: string): boolean {
  return cls === 'wall_other';
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** payload.regions 를 방어적으로 정규화 — polygon 이 짝수 좌표(>=6)인 것만 채택. */
function normalizeRegions(raw: unknown): OverlayRegion[] {
  if (!Array.isArray(raw)) return [];
  const out: OverlayRegion[] = [];
  for (const item of raw) {
    if (!isPlainObject(item)) continue;
    const poly = item.polygon;
    const cls = item.class_name;
    const rid = item.region_id;
    if (typeof cls !== 'string' || typeof rid !== 'string') continue;
    if (
      !Array.isArray(poly) ||
      poly.length < 6 ||
      poly.length % 2 !== 0 ||
      !poly.every((n) => typeof n === 'number' && Number.isFinite(n))
    ) {
      continue;
    }
    out.push({
      region_id: rid,
      class_name: cls,
      polygon: poly as number[],
      score: typeof item.score === 'number' ? item.score : undefined,
      requires_hitl: item.requires_hitl === true
    });
  }
  return out;
}

/** flat [x1,y1,...] → SVG points "x1,y1 x2,y2". */
function toPoints(poly: number[]): string {
  const parts: string[] = [];
  for (let i = 0; i + 1 < poly.length; i += 2) {
    parts.push(`${poly[i]},${poly[i + 1]}`);
  }
  return parts.join(' ');
}

type ViewBox = { x: number; y: number; w: number; h: number };

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;

export function FloorplanOverlayCard({ payload }: { payload: FloorplanOverlayPayload }) {
  const actions = useChatActions();
  const titleId = useId();
  const sessionId = actions?.sessionId;
  const assetId = typeof payload.asset_id === 'string' ? payload.asset_id : undefined;

  const regions = useMemo(() => normalizeRegions(payload.regions), [payload.regions]);

  // 원본 이미지 크기 — 폴리곤이 이 좌표계다. payload.image 우선, 없으면 폴리곤 bbox 로 추정.
  const dims = useMemo(() => {
    const w = payload.image?.width;
    const h = payload.image?.height;
    if (typeof w === 'number' && typeof h === 'number' && w > 0 && h > 0) {
      return { w, h };
    }
    let maxX = 1;
    let maxY = 1;
    for (const r of regions) {
      for (let i = 0; i + 1 < r.polygon.length; i += 2) {
        maxX = Math.max(maxX, r.polygon[i] ?? 0);
        maxY = Math.max(maxY, r.polygon[i + 1] ?? 0);
      }
    }
    return { w: Math.ceil(maxX), h: Math.ceil(maxY) };
  }, [payload.image, regions]);

  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  // 세션이 있으면 로딩으로 시작(서명 URL/선택 복원), 없으면 로딩할 게 없다.
  const [loading, setLoading] = useState<boolean>(() => Boolean(sessionId));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  // 표시용 서명 URL 발급 + 기존 선택 복원(judgment_schema.selected_walls).
  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;
    void (async () => {
      try {
        const [url, session] = await Promise.all([
          assetId
            ? getFloorplanAssetSignedUrl(sessionId, assetId).catch(() => null)
            : Promise.resolve(null),
          getSession(sessionId).catch(() => null)
        ]);
        if (ignore) return;
        if (url) setImageUrl(url);
        else setImageFailed(true);
        const prev = session?.judgment_schema?.selected_walls;
        if (Array.isArray(prev)) {
          setSelected(new Set(prev.filter((x): x is string => typeof x === 'string')));
        }
      } catch {
        if (!ignore) setImageFailed(true);
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId, assetId]);

  // 선택 토글 → 판단스키마 영속(클릭마다, best-effort).
  const persist = useCallback(
    async (next: Set<string>) => {
      if (!sessionId) return;
      setSaving(true);
      try {
        await updateSelectedWalls(sessionId, [...next]);
      } catch {
        /* 영속 실패는 조용히 무시 — 다음 토글에서 다시 시도된다 */
      } finally {
        setSaving(false);
      }
    },
    [sessionId]
  );

  const toggle = useCallback(
    (regionId: string, cls: string) => {
      if (!isSelectable(cls)) return;
      setSelected((cur) => {
        const next = new Set(cur);
        if (next.has(regionId)) next.delete(regionId);
        else next.add(regionId);
        void persist(next);
        return next;
      });
    },
    [persist]
  );

  // 범례: 실제 등장한 클래스만, 종류(벽→공간→개구부) + 라벨 순.
  const legend = useMemo(() => {
    const seen = new Map<string, ClassStyle>();
    for (const r of regions) {
      if (!seen.has(r.class_name)) seen.set(r.class_name, styleFor(r.class_name));
    }
    const order: Record<ClassKind, number> = { wall: 0, space: 1, opening: 2 };
    return [...seen.entries()].sort(
      (a, b) => order[a[1].kind] - order[b[1].kind] || a[1].label.localeCompare(b[1].label)
    );
  }, [regions]);

  const wallOtherCount = useMemo(
    () => regions.filter((r) => r.class_name === 'wall_other').length,
    [regions]
  );

  return (
    <CardShell accent="blueprint" labelledBy={titleId}>
      <CardHeader
        icon={<IconVectorTriangle size={17} aria-hidden />}
        eyebrow="도면 분석"
        title="분석 영역을 확인하고 철거할 벽을 골라 주세요"
        titleId={titleId}
      />
      <CardRule />

      <Stack gap="sm">
        <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.55 }}>
          도면 위 색상은 AI가 <b>추정</b>한 후보예요. 초록색 <b>비내력벽 후보</b>를 눌러 철거하고
          싶은 벽을 고르면 다음 단계에서 함께 검토해 드려요. 모든 표시는 확정이 아니라 검토용
          후보입니다.
        </Text>

        {loading ? (
          <Group gap={8} align="center" wrap="nowrap" style={{ minHeight: 120 }}>
            <Loader size={16} color="coral" />
            <Text size="xs" c="var(--jippin-brand-copy)">
              도면을 불러오고 있어요…
            </Text>
          </Group>
        ) : (
          <OverlayCanvas
            key={`${dims.w}x${dims.h}:${regions.length}`}
            dims={dims}
            regions={regions}
            imageUrl={imageUrl}
            imageFailed={imageFailed}
            selected={selected}
            onToggle={toggle}
            onImageError={() => setImageFailed(true)}
          />
        )}

        {legend.length > 0 ? (
          <Group gap={10} wrap="wrap" aria-label="범례">
            {legend.map(([cls, st]) => (
              <Group key={cls} gap={5} wrap="nowrap">
                <span
                  aria-hidden
                  style={{
                    width: 11,
                    height: 11,
                    borderRadius: 3,
                    background: st.color,
                    opacity: st.kind === 'space' ? 0.55 : 0.85,
                    flexShrink: 0
                  }}
                />
                <Text size="11px" c="var(--jippin-brand-copy)">
                  {st.label}
                </Text>
              </Group>
            ))}
          </Group>
        ) : null}

        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text size="xs" c="var(--jippin-brand-copy)">
            {wallOtherCount > 0
              ? `비내력벽 후보 ${wallOtherCount}곳 · 선택 ${selected.size}곳`
              : '선택 가능한 비내력벽 후보가 없어요. 다른 도면이 필요할 수 있어요.'}
          </Text>
          {saving ? (
            <Group gap={5} wrap="nowrap">
              <Loader size={12} color="coral" />
              <Text size="11px" c="dimmed">
                저장 중…
              </Text>
            </Group>
          ) : null}
        </Group>
      </Stack>
    </CardShell>
  );
}

/** SVG 오버레이 + 줌/팬. viewBox 를 조작해 핀치/휠 줌, 드래그/스와이프 팬을 지원한다. */
function OverlayCanvas({
  dims,
  regions,
  imageUrl,
  imageFailed,
  selected,
  onToggle,
  onImageError
}: {
  dims: { w: number; h: number };
  regions: OverlayRegion[];
  imageUrl: string | null;
  imageFailed: boolean;
  selected: Set<string>;
  onToggle: (regionId: string, cls: string) => void;
  onImageError: () => void;
}) {
  // 부모가 dims/regions 변화 시 key 로 remount 하므로, view 초기값을 full 로 두면 충분하다
  // (effect 내 setState 불필요).
  const full: ViewBox = useMemo(() => ({ x: 0, y: 0, w: dims.w, h: dims.h }), [dims]);
  const [view, setView] = useState<ViewBox>(full);

  const svgRef = useRef<SVGSVGElement | null>(null);
  // 활성 포인터(핀치 감지). pointerId → 화면 좌표.
  const pointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pinchPrev = useRef<number | null>(null);
  const panMoved = useRef(false);

  const zoom = dims.w / view.w;

  const clampView = useCallback(
    (v: ViewBox): ViewBox => {
      const w = Math.min(full.w, Math.max(full.w / MAX_ZOOM, v.w));
      const h = w * (full.h / full.w);
      const x = Math.min(Math.max(0, v.x), full.w - w);
      const y = Math.min(Math.max(0, v.y), full.h - h);
      return { x, y, w, h };
    },
    [full]
  );

  const zoomAt = useCallback(
    (clientX: number, clientY: number, factor: number) => {
      setView((v) => {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return v;
        const px = (clientX - rect.left) / rect.width;
        const py = (clientY - rect.top) / rect.height;
        const focusX = v.x + px * v.w;
        const focusY = v.y + py * v.h;
        const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, (dims.w / v.w) * factor));
        const nw = dims.w / nextZoom;
        const nh = nw * (full.h / full.w);
        return clampView({ x: focusX - px * nw, y: focusY - py * nh, w: nw, h: nh });
      });
    },
    [clampView, dims.w, full.h, full.w]
  );

  const onWheel = useCallback(
    (e: React.WheelEvent<SVGSVGElement>) => {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
    },
    [zoomAt]
  );

  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    panMoved.current = false;
    pinchPrev.current = null;
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      const pts = pointers.current;
      if (!pts.has(e.pointerId)) return;
      const prev = pts.get(e.pointerId)!;
      const dx = e.clientX - prev.x;
      const dy = e.clientY - prev.y;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pts.size >= 2) {
        // 핀치 줌 — 두 포인터 거리 변화율로.
        const [a, b] = [...pts.values()];
        if (a && b) {
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (pinchPrev.current != null && pinchPrev.current > 0) {
            zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, dist / pinchPrev.current);
          }
          pinchPrev.current = dist;
        }
        panMoved.current = true;
        return;
      }
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) panMoved.current = true;
      // 단일 포인터 드래그 = 팬.
      setView((v) => {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return v;
        return clampView({
          ...v,
          x: v.x - (dx / rect.width) * v.w,
          y: v.y - (dy / rect.height) * v.h
        });
      });
    },
    [clampView, zoomAt]
  );

  const onPointerUp = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchPrev.current = null;
  }, []);

  return (
    <Box
      style={{
        position: 'relative',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid var(--jippin-brand-border)',
        background: '#fff'
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        role="img"
        aria-label="도면 분석 오버레이"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        style={{
          display: 'block',
          width: '100%',
          aspectRatio: `${dims.w} / ${dims.h}`,
          touchAction: 'none',
          cursor: zoom > 1 ? 'grab' : 'default',
          background: '#f8f9fa'
        }}
      >
        {imageUrl && !imageFailed ? (
          <image
            href={imageUrl}
            x={0}
            y={0}
            width={dims.w}
            height={dims.h}
            preserveAspectRatio="xMidYMid meet"
            onError={onImageError}
          />
        ) : null}

        {regions.map((r) => {
          const st = styleFor(r.class_name);
          const selectable = isSelectable(r.class_name);
          const isSel = selected.has(r.region_id);
          const baseOpacity = st.kind === 'space' ? 0.16 : st.kind === 'opening' ? 0.32 : 0.28;
          return (
            <polygon
              key={r.region_id}
              points={toPoints(r.polygon)}
              fill={st.color}
              fillOpacity={isSel ? 0.55 : baseOpacity}
              stroke={isSel ? '#ffffff' : st.color}
              strokeOpacity={st.kind === 'space' ? 0.5 : 0.9}
              strokeWidth={(isSel ? 3.5 : 1.5) * (view.w / dims.w)}
              style={{ cursor: selectable ? 'pointer' : 'default' }}
              onClick={() => {
                // 팬 제스처 끝의 클릭은 무시(드래그와 선택 구분).
                if (panMoved.current) return;
                onToggle(r.region_id, r.class_name);
              }}
            >
              {selectable ? (
                <title>비내력벽 후보 — 누르면 철거 대상으로 선택</title>
              ) : (
                <title>{st.label}</title>
              )}
            </polygon>
          );
        })}
      </svg>

      {/* 줌 컨트롤 + 도움말. */}
      <Group
        gap={4}
        style={{ position: 'absolute', right: 8, bottom: 8 }}
        wrap="nowrap"
      >
        <ActionIcon
          variant="default"
          size="md"
          radius="md"
          aria-label="축소"
          onClick={() => zoomAt(0, 0, 1 / 1.4)}
        >
          <IconMinus size={15} />
        </ActionIcon>
        <ActionIcon
          variant="default"
          size="md"
          radius="md"
          aria-label="확대"
          onClick={() => zoomAt(0, 0, 1.4)}
        >
          <IconPlus size={15} />
        </ActionIcon>
        <ActionIcon
          variant="default"
          size="md"
          radius="md"
          aria-label="원래 크기"
          onClick={() => setView(full)}
        >
          <IconArrowsMaximize size={15} />
        </ActionIcon>
      </Group>

      {imageFailed ? (
        <Group
          gap={6}
          wrap="nowrap"
          style={{
            position: 'absolute',
            left: 8,
            top: 8,
            padding: '4px 8px',
            borderRadius: 8,
            background: 'rgba(255,255,255,0.92)'
          }}
        >
          <IconPhotoExclamation size={14} color="var(--mantine-color-warning-7)" />
          <Text size="11px" c="var(--jippin-brand-copy)">
            도면 이미지를 못 불러와 영역만 표시해요
          </Text>
        </Group>
      ) : (
        <Tooltip label="휠/핀치로 확대, 드래그로 이동" position="left" withArrow>
          <ActionIcon
            variant="default"
            size="md"
            radius="md"
            aria-label="조작 안내"
            style={{ position: 'absolute', left: 8, top: 8 }}
            tabIndex={-1}
          >
            <IconHandFinger size={15} />
          </ActionIcon>
        </Tooltip>
      )}
    </Box>
  );
}
