'use client';

import { Button, Card, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';

import { isOxQuiz, type QuizItem } from '@/lib/quiz';

/**
 * 대기 화면 퀴즈 카드 — O/X·객관식 두 렌더 변형(판별은 데이터만으로, `isOxQuiz`).
 *
 * 상태기계: answering → (선택지 탭) → revealed(정답/오답 + 해설 + 점수) → "다음 문제"
 * → … → finished("다시 풀기" = 재셔플). 자동 넘김은 두지 않는다 — 해설(규정 교육)이
 * 이 카드의 제품 가치이고, 읽는 속도는 사람마다 다르다. 상태는 클라이언트 휘발성.
 *
 * a11y: 정답 공개 후에도 선택지 버튼을 `disabled` 하지 않는다(키보드/SR 포커스 유지)
 * — 클릭만 무시하고 `data-*` 로 시각 상태를 표현한다. 피드백은 role="status".
 */

type QuizPhase = 'answering' | 'revealed' | 'finished';

/** Fisher-Yates 사본 셔플 — 재방문/다시 풀기마다 문항 순서가 달라진다. */
function shuffle<T>(source: readonly T[]): T[] {
  const out = [...source];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = out[i] as T;
    out[i] = out[j] as T;
    out[j] = tmp;
  }
  return out;
}

export function QuizCard({ items }: { items: QuizItem[] }) {
  const [order, setOrder] = useState<QuizItem[]>(() => shuffle(items));
  const [cursor, setCursor] = useState(0);
  const [phase, setPhase] = useState<QuizPhase>('answering');
  const [picked, setPicked] = useState<number | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [correctCount, setCorrectCount] = useState(0);

  // 퀴즈 데이터가 비어도(전체 비공개 등) 대기 화면 자체는 깨지지 않는다.
  const item = order[cursor];
  if (!item) return null;

  const ox = isOxQuiz(item);
  const isCorrect = picked === item.answer_index;

  const pick = (index: number) => {
    if (phase !== 'answering') return; // 공개 후 재탭 무시(disabled 대신).
    setPicked(index);
    setPhase('revealed');
    setAnsweredCount((n) => n + 1);
    if (index === item.answer_index) setCorrectCount((n) => n + 1);
  };

  const next = () => {
    if (cursor + 1 < order.length) {
      setCursor((c) => c + 1);
      setPicked(null);
      setPhase('answering');
    } else {
      setPhase('finished');
    }
  };

  const restart = () => {
    setOrder(shuffle(items));
    setCursor(0);
    setPicked(null);
    setAnsweredCount(0);
    setCorrectCount(0);
    setPhase('answering');
  };

  if (phase === 'finished') {
    return (
      <Card withBorder radius="lg" padding="xl" className="hc-quiz">
        <Stack gap="sm" align="center" ta="center">
          <span className="hc-quiz__eyebrow">기다리는 동안 · 집 상식 퀴즈</span>
          <Text fw={700} style={{ wordBreak: 'keep-all' }}>
            퀴즈를 다 풀었어요! {answeredCount}문제 중 {correctCount}개 맞혔어요.
          </Text>
          <Button variant="light" color="jippin" radius="md" onClick={restart}>
            다시 풀기
          </Button>
        </Stack>
      </Card>
    );
  }

  /** 선택지의 reveal 상태 — 정답 항목은 correct, 오답으로 고른 항목은 incorrect. */
  const revealOf = (index: number): 'correct' | 'incorrect' | undefined => {
    if (phase !== 'revealed') return undefined;
    if (index === item.answer_index) return 'correct';
    if (index === picked) return 'incorrect';
    return undefined;
  };

  return (
    <Card withBorder radius="lg" padding="xl" className="hc-quiz">
      <Stack gap="md">
        <div>
          <span className="hc-quiz__eyebrow">
            기다리는 동안 · 집 상식 퀴즈 {cursor + 1}/{order.length}
          </span>
          <p className="hc-quiz__question">{item.question}</p>
        </div>

        {ox ? (
          <div className="hc-ox" role="group" aria-label="O X 선택">
            <button
              type="button"
              className="hc-ox__btn"
              data-picked={picked === 0 || undefined}
              data-reveal={revealOf(0)}
              aria-label="O — 맞아요"
              onClick={() => pick(0)}
            >
              O
            </button>
            <button
              type="button"
              className="hc-ox__btn"
              data-picked={picked === 1 || undefined}
              data-reveal={revealOf(1)}
              aria-label="X — 아니에요"
              onClick={() => pick(1)}
            >
              X
            </button>
          </div>
        ) : (
          <Stack gap="xs" role="group" aria-label="선택지">
            {item.choices.map((choice, index) => (
              <button
                key={choice}
                type="button"
                className="hc-quiz-choice"
                data-picked={picked === index || undefined}
                data-reveal={revealOf(index)}
                onClick={() => pick(index)}
              >
                {choice}
              </button>
            ))}
          </Stack>
        )}

        {phase === 'revealed' && (
          <div role="status" className="hc-quiz__feedback" data-tone={isCorrect ? 'correct' : 'incorrect'}>
            <Text fw={700} className="hc-quiz__verdict">
              {isCorrect
                ? '정답이에요!'
                : ox
                  ? `아쉬워요, 정답은 ${item.choices[item.answer_index]}예요`
                  : `아쉬워요, 정답은 '${item.choices[item.answer_index]}'예요`}
            </Text>
            <div className="hc-quiz__explanation">
              <ReactMarkdown>{item.explanation}</ReactMarkdown>
            </div>
            <div className="hc-quiz__footer">
              <Text size="sm" c="dimmed">
                {answeredCount}문제 중 {correctCount}개 맞혔어요
              </Text>
              <Button variant="light" color="jippin" radius="md" size="sm" onClick={next}>
                {cursor + 1 < order.length ? '다음 문제' : '결과 보기'}
              </Button>
            </div>
          </div>
        )}
      </Stack>
    </Card>
  );
}
