'use client';

/**
 * 도면 업로드 카드의 **단위세대 평면도 예시 안내** (CMP-DIRECT).
 *
 * 운영 세션에서 부동산 앱(네이버 등)의 작은 평면도·단지 배치도처럼 벽이 선 하나로만
 * 그려진 그림이나 흐릿한 사진을 올리는 사용자가 반복됐다 — 세그멘테이션이 벽 두께를
 * 읽지 못해 후보 0 / 평면도 아님으로 끝난다. 글로만 "단위세대 평면도"를 설명하면
 * 와닿지 않아, 실제 예시 사진 2장을 썸네일로 보여 주고(클릭 → 확대·핀치줌 라이트박스)
 * 촬영 조건(전체가 보이게·선명하게)을 함께 안내한다.
 *
 * 라이트박스는 yet-another-react-lightbox(+zoom/captions 플러그인) — 핀치·휠·더블탭 줌,
 * 키보드(Esc/←→), 포커스 트랩을 갖춘 가벼운 MIT 라이브러리. 이미지는 public 정적
 * 자산(썸네일 긴 변 640px / 확대 1600px)이라 세션·서명 URL 과 무관하고, 별도 요청 없이
 * 카드마다 같은 예시를 보여 준다.
 */

import { List, Stack, Text } from '@mantine/core';
import { IconZoomIn } from '@tabler/icons-react';
import { useState } from 'react';
import Lightbox from 'yet-another-react-lightbox';
import Captions from 'yet-another-react-lightbox/plugins/captions';
import Zoom from 'yet-another-react-lightbox/plugins/zoom';
import 'yet-another-react-lightbox/styles.css';
import 'yet-another-react-lightbox/plugins/captions.css';

export interface FloorplanSample {
  /** 확대(라이트박스) 이미지 — 긴 변 1600px. */
  src: string;
  /** 카드 썸네일 — 긴 변 640px(2x DPR 의 ~300px 표시 폭까지 선명). */
  thumb: string;
  width: number;
  height: number;
  /** 썸네일 아래 짧은 라벨(= 버튼 접근성 이름의 앞부분). */
  label: string;
  /** 라이트박스 이미지 대체 텍스트. */
  alt: string;
  /** 라이트박스 캡션 — 이 예시의 어떤 점이 좋은지. */
  description: string;
}

/** 예시 도면 — 운영자가 고른 실제 단위세대 평면도 2장(public 정적 자산). */
export const FLOORPLAN_SAMPLES: readonly FloorplanSample[] = [
  {
    src: '/precheck/floorplan-samples/unit-plan-1.jpg',
    thumb: '/precheck/floorplan-samples/unit-plan-1-thumb.jpg',
    width: 1600,
    height: 1127,
    label: '예시 1 · 인쇄 도면을 찍은 사진',
    alt: '인쇄된 단위세대 평면도를 찍은 사진. 벽 두께와 치수, 방 이름이 또렷하고 도면 전체가 들어와 있다.',
    description:
      '벽의 두께·치수·방 이름이 읽힐 만큼 선명하고, 도면 전체가 잘리지 않게 찍혔어요.'
  },
  {
    src: '/precheck/floorplan-samples/unit-plan-2.jpg',
    thumb: '/precheck/floorplan-samples/unit-plan-2-thumb.jpg',
    width: 1600,
    height: 1172,
    label: '예시 2 · 청사진 도면',
    alt: '청사진으로 된 단위세대 평면도. 한 세대의 방·거실·발코니 배치와 벽 두께가 그려져 있다.',
    description:
      '한 세대의 방·거실·발코니와 벽 두께가 그려진 단위세대 평면도예요. 오래된 청사진도 전체가 보이면 괜찮아요.'
  }
];

/** 라이트박스 컨트롤 라벨 — 기본 영문(Close/Next…)을 생활어로. */
const LIGHTBOX_LABELS = {
  Previous: '이전 예시',
  Next: '다음 예시',
  Close: '닫기',
  'Zoom in': '확대',
  'Zoom out': '축소',
  Lightbox: '평면도 예시 크게 보기',
  'Photo gallery': '평면도 예시',
  Slide: '예시',
  Carousel: '예시 목록',
  '{index} of {total}': '{total}장 중 {index}번째'
};

export function FloorplanSampleGuide() {
  // 열려 있는 예시의 index. -1 = 닫힘.
  const [index, setIndex] = useState(-1);

  return (
    <Stack gap="xs" data-testid="floorplan-sample-guide">
      <Text size="xs" fw={600} c="var(--jippin-brand-ink)" style={{ wordBreak: 'keep-all' }}>
        이런 도면을 올려 주세요 — 단위세대 평면도
      </Text>
      <div className="a2ui-samples__grid">
        {FLOORPLAN_SAMPLES.map((sample, i) => (
          // 썸네일 전체가 버튼(터치 타깃 ≥44px). 이름은 라벨 + '크게 보기' — 그림 설명(alt)은
          // 라이트박스 이미지에 싣는다(버튼 이름이 길어지지 않게).
          <button
            key={sample.src}
            type="button"
            className="a2ui-sample"
            onClick={() => setIndex(i)}
            aria-label={`${sample.label} 크게 보기`}
          >
            <span className="a2ui-sample__frame">
              {/* 즉시 로드(lazy 아님) — 카드는 보통 스레드 맨 아래 화면 안에 뜨는데, lazy 면
                  첫 페인트에서 1~2초 빈 프레임이 보였다. 썸네일 2장 ≈95KB 이고 같은 URL 이라
                  이후 카드는 캐시로 무료. */}
              {/* eslint-disable-next-line @next/next/no-img-element -- public 정적 썸네일 2장(고정 크기, next/image 최적화 불필요) */}
              <img
                src={sample.thumb}
                alt=""
                width={640}
                height={Math.round((640 * sample.height) / sample.width)}
                decoding="async"
                className="a2ui-sample__img"
              />
              <span className="a2ui-sample__zoom" aria-hidden>
                <IconZoomIn size={14} />
              </span>
            </span>
            <Text
              component="span"
              size="xs"
              c="var(--jippin-brand-copy)"
              style={{ wordBreak: 'keep-all' }}
            >
              {sample.label}
            </Text>
          </button>
        ))}
      </div>
      <List size="xs" spacing={2} c="var(--jippin-brand-copy)" style={{ wordBreak: 'keep-all' }}>
        <List.Item>
          <strong>단위세대 평면도</strong>: 우리 집 한 세대의 방·거실·발코니와{' '}
          <strong>벽 두께</strong>가 그려진 도면이에요. 관리사무소 또는 건축물현황도
          도면이나, 예시처럼 인쇄된 도면을 찍은 사진이 좋아요.
        </List.Item>
        <List.Item>
          부동산 앱의 작은 평면도처럼 벽이 선 하나로만 그려진 그림이나 단지 배치도는 벽
          구조를 알아보기 어려워요.
        </List.Item>
        <List.Item>
          사진으로 찍을 땐 도면 <strong>전체가 잘리지 않게</strong>, 글자가 읽힐 만큼{' '}
          <strong>선명하게</strong> 찍어 주세요.
        </List.Item>
      </List>
      <Lightbox
        open={index >= 0}
        index={index < 0 ? 0 : index}
        close={() => setIndex(-1)}
        slides={FLOORPLAN_SAMPLES.map((s) => ({
          src: s.src,
          alt: s.alt,
          width: s.width,
          height: s.height,
          title: s.label,
          description: s.description
        }))}
        plugins={[Zoom, Captions]}
        // 핀치·휠·더블탭 줌. 확대 원본이 1600px 이라 픽셀비 4 까지 허용한다.
        zoom={{ maxZoomPixelRatio: 4, scrollToZoom: true }}
        carousel={{ finite: true }}
        controller={{ closeOnBackdropClick: true }}
        captions={{ descriptionTextAlign: 'start' }}
        labels={LIGHTBOX_LABELS}
      />
    </Stack>
  );
}
