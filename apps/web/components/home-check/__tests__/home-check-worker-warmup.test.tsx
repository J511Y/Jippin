import { cleanup, render, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

const warmHomeCheckWorker = vi.hoisted(() => vi.fn(() => Promise.resolve()));

vi.mock('@/lib/home-check/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/home-check/api')>();
  return { ...actual, warmHomeCheckWorker };
});

import { HomeCheckWorkerWarmup } from '../HomeCheckWorkerWarmup';

afterEach(() => {
  cleanup();
  warmHomeCheckWorker.mockClear();
});

describe('HomeCheckWorkerWarmup', () => {
  it('마운트 시 worker warm-up을 한 번 요청한다', async () => {
    render(<HomeCheckWorkerWarmup />);

    await waitFor(() => expect(warmHomeCheckWorker).toHaveBeenCalledTimes(1));
  });

  it('미리보기에서는 실제 worker를 깨우지 않는다', () => {
    render(<HomeCheckWorkerWarmup disabled />);

    expect(warmHomeCheckWorker).not.toHaveBeenCalled();
  });
});
