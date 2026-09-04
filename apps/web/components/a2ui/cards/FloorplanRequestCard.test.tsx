import { cleanup, fireEvent, render, screen, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatActionsProvider } from '@/components/agent/chat-actions';

const apiMocks = vi.hoisted(() => ({
  getSession: vi.fn(() =>
    Promise.resolve({ selected_floorplan_asset_id: null as string | null })
  ),
  createFloorplanAsset: vi.fn(() => Promise.resolve({}))
}));

vi.mock('@/lib/sessions/api', () => apiMocks);
const uploadMocks = vi.hoisted(() => ({
  uploadSessionFloorplan: vi.fn(),
  deleteSessionFloorplan: vi.fn()
}));
vi.mock('@/lib/sessions/upload', () => uploadMocks);
vi.mock('@/lib/leads/ensure-anonymous-session', () => ({
  ensureAnonymousSession: vi.fn(() => Promise.resolve())
}));
vi.mock('@/lib/analytics/sessions-funnel', () => ({
  trackPrecheckFloorplanAttach: vi.fn()
}));

import {
  FloorplanRequestCard,
  isFloorplanRequestPayload,
  type FloorplanRequestPayload
} from './FloorplanRequestCard';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function Card({ payload }: { payload: FloorplanRequestPayload }) {
  return (
    <ChatActionsProvider
      value={{ sessionId: 'session-1', busy: false, sendMessage: vi.fn() }}
    >
      <FloorplanRequestCard payload={payload} />
    </ChatActionsProvider>
  );
}

describe('FloorplanRequestCard 재업로드 판정 (#floorplan-request-prior-asset)', () => {
  it('스탬프 없는 구 카드는 세션에 도면이 있으면 첨부 완료로 잠긴다(종전 동작)', async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1'
    });
    render(<Card payload={{}} />);

    await waitFor(() =>
      expect(screen.getByText('평면도를 받았어요')).toBeTruthy()
    );
    // 잠겨도 재제출 탈출구는 항상 있다.
    expect(
      screen.getByRole('button', { name: '다른 도면으로 다시 올리기' })
    ).toBeTruthy();
  });

  it('prior_asset_id 가 현재 asset 과 같으면(재요청 카드) 업로드 폼을 유지한다', async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1'
    });
    render(<Card payload={{ prior_asset_id: 'asset-1', reason: '다른 도면 필요' }} />);

    await waitFor(() => expect(apiMocks.getSession).toHaveBeenCalledTimes(1));
    expect(screen.getByText('평면도를 올려 주세요')).toBeTruthy();
    expect(screen.queryByText('평면도를 받았어요')).toBeNull();
    // 세션에 도면이 이미 있으니 "새 도면이 기존 도면을 대체" 안내가 붙는다.
    await waitFor(() =>
      expect(
        screen.getByText('새 도면을 올리면 이전 도면 대신 새 도면으로 다시 분석해요.')
      ).toBeTruthy()
    );
  });

  it('prior_asset_id 이후 새 asset 이 붙었으면 첨부 완료로 전환된다', async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-2'
    });
    render(<Card payload={{ prior_asset_id: 'asset-1' }} />);

    await waitFor(() =>
      expect(screen.getByText('평면도를 받았어요')).toBeTruthy()
    );
  });

  it('prior_asset_id=null(첫 요청 카드)은 도면이 붙는 순간 첨부 완료가 된다', async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1'
    });
    render(<Card payload={{ prior_asset_id: null }} />);

    await waitFor(() =>
      expect(screen.getByText('평면도를 받았어요')).toBeTruthy()
    );
  });

  it("'다른 도면으로 다시 올리기'를 누르면 업로드 폼이 다시 열린다(재제출)", async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1'
    });
    render(<Card payload={{}} />);

    const reopen = await screen.findByRole('button', {
      name: '다른 도면으로 다시 올리기'
    });
    fireEvent.click(reopen);

    expect(screen.getByText('평면도를 올려 주세요')).toBeTruthy();
    expect(
      screen.getByText('새 도면을 올리면 이전 도면 대신 새 도면으로 다시 분석해요.')
    ).toBeTruthy();
  });
});

describe('FloorplanRequestCard 형제 카드 동기화 (#floorplan-cards-broadcast)', () => {
  function BroadcastCard({
    assetId,
    payload
  }: {
    assetId: string | null;
    payload: FloorplanRequestPayload;
  }) {
    return (
      <ChatActionsProvider
        value={{
          sessionId: 'session-1',
          busy: false,
          sendMessage: vi.fn(),
          selectedFloorplanAssetId: assetId
        }}
      >
        <FloorplanRequestCard payload={payload} />
      </ChatActionsProvider>
    );
  }

  it('컨텍스트가 asset 을 주면 자체 세션 조회 없이 그 값으로 판정한다', async () => {
    render(<BroadcastCard assetId="asset-1" payload={{ prior_asset_id: 'asset-1' }} />);

    // 재요청 카드(prior == current) — 폼 유지, 자체 getSession 호출 없음.
    await waitFor(() =>
      expect(
        screen.getByText('새 도면을 올리면 이전 도면 대신 새 도면으로 다시 분석해요.')
      ).toBeTruthy()
    );
    expect(screen.getByText('평면도를 올려 주세요')).toBeTruthy();
    expect(apiMocks.getSession).not.toHaveBeenCalled();
  });

  it('형제 카드가 올린 새 asset 이 브로드캐스트되면 폼 상태 카드도 첨부 완료로 재조정된다', async () => {
    const view = render(
      <BroadcastCard assetId="asset-1" payload={{ prior_asset_id: 'asset-1' }} />
    );
    expect(screen.getByText('평면도를 올려 주세요')).toBeTruthy();

    // 다른 카드의 업로드 → refreshSession → 컨텍스트 값이 asset-2 로 갱신.
    view.rerender(
      <BroadcastCard assetId="asset-2" payload={{ prior_asset_id: 'asset-1' }} />
    );
    await waitFor(() =>
      expect(screen.getByText('평면도를 받았어요')).toBeTruthy()
    );
    expect(apiMocks.getSession).not.toHaveBeenCalled();
  });
});

describe('isFloorplanRequestPayload', () => {
  it('prior_asset_id 는 string/null/생략만 허용한다', () => {
    expect(isFloorplanRequestPayload({})).toBe(true);
    expect(isFloorplanRequestPayload({ prior_asset_id: null })).toBe(true);
    expect(isFloorplanRequestPayload({ prior_asset_id: 'asset-1' })).toBe(true);
    expect(isFloorplanRequestPayload({ prior_asset_id: 7 })).toBe(false);
    expect(isFloorplanRequestPayload({ reason: 7 })).toBe(false);
  });
});

describe('FloorplanRequestCard 드래그앤드롭 업로드', () => {
  function DropCard({ sendMessage }: { sendMessage: ReturnType<typeof vi.fn> }) {
    return (
      <ChatActionsProvider
        value={{
          sessionId: 'session-1',
          busy: false,
          sendMessage,
          selectedFloorplanAssetId: null
        }}
      >
        <FloorplanRequestCard payload={{ prior_asset_id: null }} />
      </ChatActionsProvider>
    );
  }
  const drop = (file: File) =>
    fireEvent.drop(screen.getByTestId('floorplan-dropzone'), {
      dataTransfer: { types: ['Files'], files: [file] }
    });

  it('드롭존에 이미지를 놓고 제출하면 업로드 → asset 등록 → 분석 요청으로 이어진다', async () => {
    const sendMessage = vi.fn();
    uploadMocks.uploadSessionFloorplan.mockResolvedValueOnce({
      bucket: 'session-floorplans',
      object_key: 'u/session-1/k.png',
      content_type: 'image/png',
      byte_size: 1
    });
    render(<DropCard sendMessage={sendMessage} />);
    const file = new File(['x'], 'plan.png', { type: 'image/png' });
    drop(file);
    expect(screen.getByText('plan.png')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '도면 첨부하고 분석' }));
    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith('도면을 첨부했어요. 분석해 주세요.')
    );
    expect(uploadMocks.uploadSessionFloorplan).toHaveBeenCalledWith('session-1', file);
    expect(apiMocks.createFloorplanAsset).toHaveBeenCalledWith('session-1', {
      bucket: 'session-floorplans',
      object_key: 'u/session-1/k.png',
      content_type: 'image/png',
      byte_size: 1
    });
    await waitFor(() => expect(screen.getByText('평면도를 받았어요')).toBeTruthy());
  });

  it('이미지가 아닌 파일을 놓으면 생활어 사유를 보여 주고 제출 버튼은 잠긴다', () => {
    render(<DropCard sendMessage={vi.fn()} />);
    drop(new File(['x'], 'plan.pdf', { type: 'application/pdf' }));
    expect(screen.getByRole('alert').textContent).toContain('이미지 파일만 첨부할 수 있어요');
    expect(
      (screen.getByRole('button', { name: '도면 첨부하고 분석' }) as HTMLButtonElement).disabled
    ).toBe(true);
    expect(uploadMocks.uploadSessionFloorplan).not.toHaveBeenCalled();
  });
});

describe('FloorplanRequestCard 미리보기 스텁 (simulateUploads)', () => {
  it('simulateUploads 면 실제 업로드·등록·전송 없이 첨부 완료 상태만 재현한다', async () => {
    const sendMessage = vi.fn();
    render(
      <ChatActionsProvider
        value={{
          sessionId: 'preview',
          busy: false,
          sendMessage,
          selectedFloorplanAssetId: null,
          simulateUploads: true
        }}
      >
        <FloorplanRequestCard payload={{ prior_asset_id: null }} />
      </ChatActionsProvider>
    );
    fireEvent.drop(screen.getByTestId('floorplan-dropzone'), {
      dataTransfer: { types: ['Files'], files: [new File(['x'], 'plan.png', { type: 'image/png' })] }
    });
    fireEvent.click(screen.getByRole('button', { name: '도면 첨부하고 분석' }));

    await waitFor(() => expect(screen.getByText('평면도를 받았어요')).toBeTruthy());
    expect(uploadMocks.uploadSessionFloorplan).not.toHaveBeenCalled();
    expect(apiMocks.createFloorplanAsset).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });
});
