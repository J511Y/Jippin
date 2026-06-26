'use client';

/**
 * 진행 계획 패널 (CMP-DIRECT 대화형 에이전트).
 *
 * deepagents 가 write_todos 로 세운 계획(단계 목록 + 각 단계 상태)을 응답 대기 중
 * 실시간으로 보여 준다. plan 은 useAgentStream 이 SSE tool_step.todos 로 갱신한다.
 *
 * - 데스크톱: 채팅 좌측 사이드바에 전체 단계를 상태와 함께 세로로 나열(SessionChat 이
 *   `.plan-sidebar` 로 위치를 잡고, 여기서는 `visibleFrom="sm"` 표현만 렌더).
 * - 모바일: 현재 단계 한 줄(아이콘 + content + chevron + "N/M")만 접힘으로 보여 주고,
 *   클릭하면 Collapse 로 전체 목록을 펼친다(`hiddenFrom="sm"`).
 *
 * 색은 전부 브랜드 토큰. plan 이 비면 null 을 반환해 패널 자체를 렌더하지 않는다.
 */

import { Box, Collapse, Group, Loader, Stack, Text, UnstyledButton } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconCheck, IconChevronDown } from '@tabler/icons-react';

import type { PlanTodo } from '@/lib/agent/useAgentStream';

type StepState = 'pending' | 'in_progress' | 'completed';

/** 알 수 없는 status 문자열은 'pending' 으로 취급한다(하위호환). */
function normalizeStatus(status: string): StepState {
  if (status === 'completed' || status === 'in_progress') return status;
  return 'pending';
}

/** 현재 진행 단계 인덱스 — in_progress 우선, 없으면 첫 pending, 그것도 없으면 -1. */
function currentIndex(steps: StepState[]): number {
  const inProgress = steps.findIndex((s) => s === 'in_progress');
  if (inProgress >= 0) return inProgress;
  const firstPending = steps.findIndex((s) => s === 'pending');
  return firstPending;
}

/** 단계 상태 아이콘 — completed=체크(success), in_progress=스피너/현재 점, pending=빈 원.
 *
 * ``animated=false`` 면 진행 중 단계에 스피너 대신 정적 '현재' 점을 쓴다(PC 계획 패널은
 * 끊임없이 도는 스피너가 산만해 제거 — 굵게·강조색으로 현재 단계를 표시). */
function StepIcon({ state, animated = true }: { state: StepState; animated?: boolean }) {
  if (state === 'completed') {
    return <IconCheck size={16} color="var(--mantine-color-success-6)" aria-hidden />;
  }
  if (state === 'in_progress') {
    if (animated) {
      return <Loader size={14} color="jippin" aria-hidden />;
    }
    // 정적 현재 마커 — 채워진 점(jippin)으로 진행 단계를 스피너 없이 표시.
    return (
      <Box
        aria-hidden
        style={{
          width: 12,
          height: 12,
          borderRadius: 999,
          background: 'var(--mantine-color-jippin-6)',
          boxSizing: 'border-box'
        }}
      />
    );
  }
  return (
    <Box
      aria-hidden
      style={{
        width: 14,
        height: 14,
        borderRadius: 999,
        border: '2px solid var(--jippin-brand-border)',
        boxSizing: 'border-box'
      }}
    />
  );
}

function statusLabel(state: StepState): string {
  if (state === 'completed') return '완료';
  if (state === 'in_progress') return '진행 중';
  return '대기';
}

/** 단계 한 줄(번호 + 아이콘 + content). 현재 단계는 ink 색·굵게 강조. */
function StepRow({
  index,
  content,
  state,
  current,
  animated = true
}: {
  index: number;
  content: string;
  state: StepState;
  current: boolean;
  animated?: boolean;
}) {
  return (
    <Group
      gap={8}
      wrap="nowrap"
      align="flex-start"
      role="listitem"
      aria-label={`${index + 1}단계: ${content} (${statusLabel(state)})`}
    >
      <Box style={{ flex: '0 0 auto', width: 16, display: 'grid', placeItems: 'center', marginTop: 1 }}>
        <StepIcon state={state} animated={animated} />
      </Box>
      <Text
        size="sm"
        c={state === 'completed' ? 'dimmed' : current ? undefined : 'dimmed'}
        fw={current ? 600 : 400}
        style={{
          wordBreak: 'keep-all',
          overflowWrap: 'break-word',
          color: current ? 'var(--jippin-brand-ink)' : undefined,
          textDecoration: state === 'completed' ? 'line-through' : undefined
        }}
      >
        {content}
      </Text>
    </Group>
  );
}

export interface PlanPanelProps {
  plan: PlanTodo[];
  busy?: boolean;
}

export function PlanPanel({ plan, busy }: PlanPanelProps) {
  const [opened, { toggle }] = useDisclosure(false);

  if (!plan || plan.length === 0) return null;

  const states = plan.map((t) => normalizeStatus(t.status));
  const active = currentIndex(states);
  const completedCount = states.filter((s) => s === 'completed').length;
  const total = plan.length;
  // 모바일 접힘 줄에 보여 줄 현재 단계(없으면 마지막 단계로 폴백).
  const headIndex = active >= 0 ? active : total - 1;
  const headState = states[headIndex] ?? 'pending';
  const headContent = plan[headIndex]?.content ?? '';

  // animated=false 면 진행 단계 스피너 대신 정적 점(PC 패널). 모바일은 기존대로 스피너.
  const renderList = (animated: boolean) => (
    <Stack gap={10} role="list">
      {plan.map((todo, i) => (
        <StepRow
          key={`${i}-${todo.content}`}
          index={i}
          content={todo.content}
          state={states[i] ?? 'pending'}
          current={i === active}
          animated={animated}
        />
      ))}
    </Stack>
  );

  return (
    <>
      {/* 데스크톱: 좌측 사이드바 세로 목록 — 진행 '단계' 스피너는 제거(정적 점)하고,
          패널 헤더의 busy 표시(전체 응답 대기)는 유지한다. */}
      <Box className="plan-desktop" visibleFrom="sm">
        <Stack gap="sm">
          <Group justify="space-between" align="center" gap="xs" wrap="nowrap">
            <Group gap={6} wrap="nowrap">
              {busy ? <Loader size={13} color="jippin" aria-hidden /> : null}
              <Text size="sm" fw={700} c="var(--jippin-brand-ink)">
                진행 계획
              </Text>
            </Group>
            <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }}>
              {completedCount}/{total}
            </Text>
          </Group>
          {renderList(false)}
        </Stack>
      </Box>

      {/* 모바일: 접힘 = 현재 단계 한 줄, 클릭 시 전체 펼침 */}
      <Box className="plan-mobile" hiddenFrom="sm">
        <UnstyledButton
          onClick={toggle}
          aria-expanded={opened}
          aria-label="진행 계획 펼치기"
          style={{ width: '100%', display: 'block' }}
        >
          <Group gap={8} wrap="nowrap" align="center" style={{ width: '100%' }}>
            <Box style={{ flex: '0 0 auto', width: 16, display: 'grid', placeItems: 'center' }}>
              <StepIcon state={headState} />
            </Box>
            <Text
              size="sm"
              fw={600}
              c="var(--jippin-brand-ink)"
              style={{ flex: 1, minWidth: 0, wordBreak: 'keep-all', overflowWrap: 'break-word' }}
              lineClamp={1}
            >
              {headContent}
            </Text>
            <Text size="xs" c="dimmed" style={{ flex: '0 0 auto' }}>
              {completedCount}/{total}
            </Text>
            <IconChevronDown
              size={16}
              aria-hidden
              style={{
                flex: '0 0 auto',
                color: 'var(--jippin-brand-copy)',
                transform: opened ? 'rotate(180deg)' : 'none',
                transition: 'transform 160ms ease'
              }}
              className="plan-chevron"
            />
          </Group>
        </UnstyledButton>
        <Collapse expanded={opened}>
          <Box pt="sm">{renderList(true)}</Box>
        </Collapse>
      </Box>
    </>
  );
}
