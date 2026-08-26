'use client';

/**
 * 세션 채팅 컨테이너 (CMP-DIRECT 채팅 UX 재설계).
 *
 * ChatGPT/Gemini 식 UX 의 정점. activeId 가 없으면(=/sessions 진입) 중앙 인사말 + 단일
 * 입력창 + 예시 칩(compose)을 보여 주고, 첫 전송 시 익명 세션 보장 → createSession →
 * `history.replaceState` 로 URL 만 교체(리마운트 없음) → 대화 레이아웃으로 부드럽게 전환한다.
 * activeId 가 있으면 곧장 대화 레이아웃(Conversation)을 마운트한다.
 */

import { ActionIcon, Box, Loader, Stack, Text } from '@mantine/core';
import { IconArrowDown } from '@tabler/icons-react';
import Image from 'next/image';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

import { ChatActionsProvider } from '@/components/agent/chat-actions';
import { trackPrecheckSessionStart } from '@/lib/analytics/sessions-funnel';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { useAgentStream } from '@/lib/agent/useAgentStream';
import { createSession, getSession, warmupSegmentation } from '@/lib/sessions/api';

import { MessageComposer } from './MessageComposer';
import { MessageThread } from './MessageThread';
import { PlanPanel } from './PlanPanel';

const AGENT_ENABLED = process.env.NEXT_PUBLIC_AGENT_ENABLED === 'true';

const EXAMPLE_QUESTIONS = [
  '우리집 거실 벽을 철거할 수 있는지 확인해줘',
  '내력벽인지 아닌지 도면으로 봐줄 수 있어?',
  '확장 공사를 하려는데 가능한 구조인지 봐줘'
];

const GREETING = '우리집 구조, 무엇이든 물어보세요';
const SUBGREETING =
  '주소와 도면을 바탕으로 벽 철거·확장 같은 리모델링 가능성을 함께 확인해 드려요.';

// 도면 추론 엔드포인트 keep-alive 재핑 간격 — 서버 scale-to-zero idle(15분)보다 짧게
// 잡아 세션이 활성인 동안 잠들지 않게 한다(백엔드 /health 핑이 idle 타이머를 리셋).
const WARMUP_KEEPALIVE_INTERVAL_MS = 10 * 60 * 1000;

/** 활성 세션의 대화 레이아웃 — useAgentStream 을 소비한다. key={sessionId} 로 마운트. */
function Conversation({
  sessionId,
  pendingFirstMessage,
  onConsumePending
}: {
  sessionId: string;
  pendingFirstMessage?: string | null;
  onConsumePending?: () => void;
}) {
  const { messages, streamingText, activity, plan, status, error, send } =
    useAgentStream(sessionId);
  const [hasReport, setHasReport] = useState(false);
  // 선택 도면 asset — 컨텍스트로 카드들에 브로드캐스트한다(#floorplan-cards-broadcast).
  // undefined = 아직 조회 전(카드가 자체 조회로 폴백).
  const [selectedFloorplanAssetId, setSelectedFloorplanAssetId] = useState<
    string | null | undefined
  >(undefined);

  const busy = status === 'streaming';
  const hasPlan = plan.length > 0;

  // 스크롤이 최하단이 아닐 때만 "맨 아래로" 플로팅 버튼을 노출한다(모바일/PC 공통).
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [atBottom, setAtBottom] = useState(true);
  const recomputeAtBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    // 임계값 80px — 거의 바닥이면 버튼을 숨겨 깜빡임을 막는다.
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }, []);
  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, []);
  // 새 메시지/스트리밍으로 높이가 바뀌면 바닥 여부를 재계산한다.
  useEffect(() => {
    recomputeAtBottom();
  }, [messages, streamingText, activity, recomputeAtBottom]);

  // 마운트 시 보관된 첫 메시지를 1회 전송한다.
  // StrictMode(개발)의 mount→unmount→remount 동안 첫 send 의 fetch 가 useAgentStream
  // 히스토리 effect cleanup 의 abort 에 걸려 취소되고 재전송되지 않던 레이스를 피한다 —
  // setTimeout(0) 으로 마운트가 안정된 뒤(가짜 unmount 이후) 1회만 전송하고, 가짜
  // unmount 시도는 clearTimeout 으로 취소한다. 혹시 중복 전송돼도 send 의 409(이미 활성
  // 런) 경로가 resume 으로 흡수한다.
  useEffect(() => {
    if (!pendingFirstMessage) return;
    const msg = pendingFirstMessage;
    const timer = window.setTimeout(() => {
      void send(msg);
      onConsumePending?.();
    }, 0);
    return () => window.clearTimeout(timer);
    // onConsumePending 은 매 렌더 새 함수라 deps 에서 제외(재스케줄 루프 방지) —
    // 전송 후 pendingFirstMessage 가 null 이 되어 재진입은 막힌다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingFirstMessage, send]);

  // 겹친 세션 조회의 역전 방어 — 늦게 시작한 조회가 먼저 저장된 뒤, 먼저 시작한(더
  // 낡은) 응답이 나중에 도착해 브로드캐스트를 되감지 않게 시퀀스로 최신 요청만 반영한다
  // (#session-refresh-sequencing). 카드 두 장이 연달아 업로드하면 refreshSession 이
  // 겹칠 수 있다.
  const sessionFetchSeq = useRef(0);
  const applySessionRow = useCallback(
    (seq: number, row: Awaited<ReturnType<typeof getSession>>) => {
      if (seq !== sessionFetchSeq.current) return; // 더 새 조회가 이미 시작됨 — 폐기.
      setHasReport(row.has_report);
      setSelectedFloorplanAssetId(row.selected_floorplan_asset_id ?? null);
    },
    []
  );

  const refreshSession = useCallback(async () => {
    const seq = ++sessionFetchSeq.current;
    try {
      const row = await getSession(sessionId);
      applySessionRow(seq, row);
    } catch {
      /* 조용히 무시 — 헤더 링크·카드 브로드캐스트만 영향 */
    }
  }, [sessionId, applySessionRow]);

  // has_report·선택 도면을 조용히 조회한다(리포트 링크 + 카드 브로드캐스트용). setState
  // 는 await 이후라 cascading render 가 아니다 — effect 안에서 inline 으로 처리해 lint
  // 규약도 만족한다.
  useEffect(() => {
    let ignore = false;
    const seq = ++sessionFetchSeq.current;
    void (async () => {
      try {
        const row = await getSession(sessionId);
        if (ignore) return;
        applySessionRow(seq, row);
      } catch {
        /* 조용히 무시 — 헤더 링크·카드 브로드캐스트만 영향 */
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId, applySessionRow]);

  return (
    <ChatActionsProvider
      value={{
        sessionId,
        sendMessage: send,
        busy,
        refreshSession,
        selectedFloorplanAssetId
      }}
    >
      <Box className="chat-shell">
        <Box className="chat-main">
          {hasReport ? (
            <Box className="chat-report-link">
              {/* 내부 내비게이션은 next/link — 클라이언트 컴포넌트라 RSC 제약 없음. */}
              <Text
                component={Link}
                href={`/sessions/${sessionId}/report`}
                size="sm"
                c="jippin.7"
                fw={600}
              >
                리포트 보기 →
              </Text>
            </Box>
          ) : null}

          <Box className="chat-scroll" ref={scrollRef} onScroll={recomputeAtBottom}>
            <Box className="chat-column">
              {/* 진행 계획은 모바일에서만 접이식으로 노출한다. PC에서는 채팅 폭을
                  온전히 사용하도록 부모와 PlanPanel 양쪽에서 숨긴다. */}
              {hasPlan ? (
                <Box className="plan-mobile-bar">
                  <PlanPanel plan={plan} />
                </Box>
              ) : null}

              <MessageThread
                messages={messages}
                streamingText={streamingText}
                activity={activity}
                streaming={busy}
                error={error}
              />
            </Box>
          </Box>

          <Box className="chat-dock">
            {!atBottom ? (
              <ActionIcon
                className="chat-scroll-btn"
                onClick={scrollToBottom}
                radius="xl"
                size={38}
                variant="default"
                aria-label="맨 아래로 이동"
              >
                <IconArrowDown size={18} />
              </ActionIcon>
            ) : null}
            <Box className="chat-column">
              <MessageComposer
                onSend={send}
                busy={busy}
                variant="dock"
                placeholder="메시지를 입력하세요 (예: 우리집 내력벽 확인해줘)"
              />
              <Text size="xs" c="dimmed" ta="center" mt={6}>
                집핀은 참고용 정보를 제공해요. 실제 시공 전 전문가 확인이 필요합니다.
              </Text>
            </Box>
          </Box>
        </Box>
      </Box>
    </ChatActionsProvider>
  );
}

/** 비활성(compose) 단계 — 중앙 인사말 + 큰 입력창 + 예시 칩. */
function Compose({
  onFirstSend,
  starting
}: {
  onFirstSend: (text: string, entry: 'example' | 'typed') => void | Promise<void>;
  starting: boolean;
}) {
  return (
    <Box className="chat-shell">
      <Box className="chat-compose">
        <Stack className="chat-column" gap="xl" align="center">
          <Stack gap="xs" align="center">
            {/* 브랜드 마크 — MessageThread 아바타와 같은 로고(public/logo.png)로 통일.
                '집' 글자 원형은 임시 마크였다. */}
            <Box
              aria-hidden
              style={{
                width: 52,
                height: 52,
                borderRadius: 999,
                display: 'grid',
                placeItems: 'center',
                background: 'var(--jippin-brand-surface-alt, #FFFFFF)',
                border: '1px solid var(--jippin-brand-border)',
                boxShadow: '0 1px 2px rgba(13, 27, 42, 0.10)',
                overflow: 'hidden',
                marginBottom: 4
              }}
            >
              <Image src="/logo.png" alt="" width={32} height={32} style={{ display: 'block' }} />
            </Box>
            {/* 원-퀘스천 헤딩 — display 토큰(판정·대화형 헤딩 전용 단계)만 쓴다. */}
            <Text
              fz="var(--jippin-fz-display)"
              fw={700}
              ta="center"
              style={{ wordBreak: 'keep-all' }}
            >
              {GREETING}
            </Text>
            <Text c="dimmed" ta="center" maw={440} style={{ wordBreak: 'keep-all' }}>
              {SUBGREETING}
            </Text>
          </Stack>

          <Box style={{ width: '100%' }}>
            <MessageComposer
              onSend={(text) => onFirstSend(text, 'typed')}
              onExample={(text) => onFirstSend(text, 'example')}
              busy={starting}
              variant="compose"
              placeholder="무엇이든 물어보세요"
              examples={EXAMPLE_QUESTIONS}
            />
          </Box>
        </Stack>
      </Box>
    </Box>
  );
}

export function SessionChat({ sessionId }: { sessionId?: string }) {
  const [activeId, setActiveId] = useState<string | null>(sessionId ?? null);
  const [pendingFirstMessage, setPendingFirstMessage] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // /sessions/* 진입 시 도면 추론 엔드포인트를 미리 깨운다(콜드스타트 ~26초 체감 제거).
  // 세션이 활성인 동안(대화 화면 + 탭이 보이는 동안)은 10분 간격으로 재핑해 scale-to-
  // zero(15분)로 잠들지 않게 유지한다 — 깨어 있는 시간이 곧 GPU 과금 시간이라 숨김
  // 탭에서는 보내지 않고, 세션을 떠나면(언마운트) 중단해 15분 뒤 자연히 잠들게 한다.
  // best-effort + 백엔드 스로틀. HF 토큰은 백엔드만 가진다(브라우저 비노출).
  useEffect(() => {
    const ping = () => {
      if (document.visibilityState !== 'hidden') void warmupSegmentation();
    };
    ping(); // 진입/세션 시작 시 1회
    if (activeId == null) return undefined; // compose 화면: 진입 핑만, keep-alive 없음
    const intervalId = window.setInterval(ping, WARMUP_KEEPALIVE_INTERVAL_MS);
    // 백그라운드에 있다가 돌아오면 다음 interval 을 기다리지 않고 즉시 재핑 — 자리를
    // 비운 사이 잠들었어도 도면을 만지기 시작할 때는 이미 웨이크가 진행 중이도록.
    document.addEventListener('visibilitychange', ping);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', ping);
    };
  }, [activeId]);

  // 첫 전송: 익명 세션 보장 → 세션 생성 → URL 교체(리마운트 없음) → 대화 전환.
  const handleFirstSend = useCallback(
    async (text: string, entry: 'example' | 'typed' = 'typed') => {
    setStarting(true);
    setStartError(null);
    try {
      // 퍼널: 사전검토 세션 시작(예시칩/직접입력). createSession 직전에 발화.
      trackPrecheckSessionStart(entry);
      await ensureAnonymousSession();
      const session = await createSession();
      // Next 라우터 네비게이션을 트리거하지 않고 URL 만 교체한다(부드러운 전환 유지).
      if (typeof window !== 'undefined') {
        window.history.replaceState(null, '', `/sessions/${session.id}`);
      }
      setPendingFirstMessage(text);
      setActiveId(session.id);
    } catch {
      setStartError('대화를 시작하지 못했어요. 잠시 후 다시 시도해 주세요.');
      setStarting(false);
    }
  }, []);

  if (!AGENT_ENABLED) {
    return (
      <Box className="chat-shell">
        <Box className="chat-compose">
          <Stack className="chat-column" gap="sm" align="center">
            <Text fw={600} ta="center">
              AI 도우미는 현재 준비 중이에요.
            </Text>
            <Text c="dimmed" size="sm" ta="center" maw={420} style={{ wordBreak: 'keep-all' }}>
              곧 대화형 사전검토를 만나보실 수 있어요. 조금만 기다려 주세요.
            </Text>
          </Stack>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      className="chat-root"
      data-mode={activeId == null ? 'compose' : 'conversation'}
    >
      {activeId == null ? (
        <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
          <Compose onFirstSend={handleFirstSend} starting={starting} />
          {startError ? (
            <Text c="danger.7" size="sm" ta="center">
              {startError}
            </Text>
          ) : null}
          {starting ? (
            <Box ta="center">
              <Loader size="sm" color="jippin" />
            </Box>
          ) : null}
        </Stack>
      ) : (
        <Conversation
          key={activeId}
          sessionId={activeId}
          pendingFirstMessage={pendingFirstMessage}
          onConsumePending={() => setPendingFirstMessage(null)}
        />
      )}
    </Box>
  );
}
