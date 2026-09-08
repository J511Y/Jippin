import { cleanup, fireEvent, render, screen, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it } from 'vitest';

import { FLOORPLAN_SAMPLES, FloorplanSampleGuide } from './FloorplanSampleGuide';

afterEach(cleanup);

describe('FloorplanSampleGuide (단위세대 평면도 예시 안내)', () => {
  it('예시 썸네일 2장과 촬영 안내를 보여 준다', () => {
    render(<FloorplanSampleGuide />);

    const thumbs = screen.getAllByRole('button', { name: /크게 보기$/ });
    expect(thumbs).toHaveLength(FLOORPLAN_SAMPLES.length);
    const imgs = screen
      .getByTestId('floorplan-sample-guide')
      .querySelectorAll('img');
    expect(Array.from(imgs).map((img) => img.getAttribute('src'))).toEqual(
      FLOORPLAN_SAMPLES.map((s) => s.thumb)
    );
    // 어떤 도면인지(단위세대 평면도) + 촬영 조건(전체·선명) 안내.
    expect(screen.getByText('이런 도면을 올려 주세요 — 단위세대 평면도')).toBeTruthy();
    expect(screen.getByText('전체가 잘리지 않게')).toBeTruthy();
    expect(screen.getByText('선명하게')).toBeTruthy();
    // 닫혀 있을 때는 라이트박스가 없다.
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('썸네일을 누르면 확대 라이트박스가 열리고, 닫기로 닫힌다', async () => {
    render(<FloorplanSampleGuide />);

    fireEvent.click(
      screen.getByRole('button', { name: `${FLOORPLAN_SAMPLES[1].label} 크게 보기` })
    );
    expect(await screen.findByRole('dialog')).toBeTruthy();
    // 확대 원본(1600px)과 캡션이 실린다.
    await waitFor(() =>
      expect(screen.getAllByAltText(FLOORPLAN_SAMPLES[1].alt).length).toBeGreaterThan(0)
    );
    expect(screen.getByText(FLOORPLAN_SAMPLES[1].description)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
