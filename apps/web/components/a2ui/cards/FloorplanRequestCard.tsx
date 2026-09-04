'use client';

/**
 * A2UI `floorplan-request` 카드 — 도면 업로드 유도 (CMP-DIRECT).
 *
 * 항상 떠 있던 업로드 입력을 대체한다. 에이전트가 "도면이 필요하다"고 판단하면
 * 이 카드를 방출하고, 사용자가 카드 안에서 이미지를 골라(드래그앤드롭·클릭·모바일
 * 카메라 — `FloorplanDropInput`) 첨부하면 업로드 → asset 등록 → `sendMessage` 로
 * 분석을 이어 가게 한다.
 *
 * payload: { reason?: string, prior_asset_id?: string | null }
 *
 * `prior_asset_id` 는 서버가 카드 발행 시점의 selected_floorplan_asset_id 를 스탬프한
 * 값(#floorplan-request-prior-asset). "세션에 도면이 하나라도 있으면 첨부 완료"가 아니라
 * "이 카드 발행 **이후** 새 asset 이 붙었는가"로 완료를 판정해야, 분석 불가(벽 후보 0)
 * 등으로 에이전트가 **재업로드**를 요청한 새 카드가 뜨자마자 '받았어요'로 잠기지 않는다.
 * 스탬프가 없는 구 카드들은 종전대로 "도면이 있으면 첨부 완료"로 처리하되, '다른 도면으로
 * 다시 올리기'로 언제든 폼을 되열 수 있다(재제출 — 기존 도면은 삭제하지 않고 대체).
 *
 * 보안/검증: payload 는 LLM/서버 유래라 런타임 형태가 임의일 수 있다. `isPlainObject`
 * 로 객체임을 좁힌 뒤 `reason` 이 string 일 때만 채택한다(아니면 기본 문구). 모든
 * 사용자/LLM 문자열은 React 텍스트 노드로만 렌더해 raw HTML 주입을 막는다.
 */

import { Button, Group, Loader, Stack, Text } from '@mantine/core';
import {
  IconAlertCircle,
  IconCircleCheck,
  IconPhotoUp,
  IconUpload
} from '@tabler/icons-react';
import { useEffect, useId, useState } from 'react';
import { trackPrecheckFloorplanAttach } from '@/lib/analytics/sessions-funnel';
import { useChatActions } from '@/components/agent/chat-actions';
import { FloorplanDropInput } from '@/components/inputs/FloorplanDropInput';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { MAX_UPLOAD_BYTES } from '@/lib/leads/upload-policy';
import { createFloorplanAsset, getSession } from '@/lib/sessions/api';
import {
  deleteSessionFloorplan,
  uploadSessionFloorplan
} from '@/lib/sessions/upload';
import { CardHeader, CardRule, CardShell } from './CardShell';

export type FloorplanRequestPayload = {
  reason?: string;
  /** 카드 발행 시점에 세션에 이미 선택돼 있던 asset id (서버 스탬프). null=발행
   *  시점에 도면 없음, undefined=스탬프 없는 구 카드(#floorplan-request-prior-asset). */
  prior_asset_id?: string | null;
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * floorplan-request 는 모든 필드가 optional 이라 빈 객체(`{}`)도 유효하다.
 * 객체이기만 하면 채택하고, `reason` 은 문자열일 때만 노출한다.
 */
export function isFloorplanRequestPayload(
  payload: unknown
): payload is FloorplanRequestPayload {
  if (!isPlainObject(payload)) {
    return false;
  }
  if (payload.reason !== undefined && typeof payload.reason !== 'string') {
    return false;
  }
  return (
    payload.prior_asset_id === undefined ||
    payload.prior_asset_id === null ||
    typeof payload.prior_asset_id === 'string'
  );
}

const DEFAULT_REASON =
  '정확한 판단을 위해 평면도(도면) 이미지가 필요해요. 등기상 구조와 실제 구조를 비교해 분석합니다.';

/** 업로드 실패 시 raw 에러 대신 보여 줄 친화적 문구(원인 추정으로 분기). */
function friendlyUploadError(err: unknown): string {
  // fetch 네트워크 실패는 보통 TypeError("Failed to fetch").
  if (err instanceof TypeError) {
    return '네트워크 문제로 도면을 올리지 못했어요. 연결을 확인하고 다시 시도해 주세요.';
  }
  return '도면을 올리지 못했어요. 잠시 후 다시 시도하거나 다른 이미지로 올려 주세요.';
}

export function FloorplanRequestCard({
  payload
}: {
  payload: FloorplanRequestPayload;
}) {
  const actions = useChatActions();
  const titleId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 이 카드에서 방금 업로드에 성공했는지(세션 재조회가 돌아오기 전의 낙관 상태).
  const [locallyAttached, setLocallyAttached] = useState(false);
  // '다른 도면으로 다시 올리기'를 누른 시점의 선택 asset — 그 값이 그대로인 동안은
  // 폼을 유지하고, **새로운** asset 변화(형제 카드의 업로드 포함)가 오면 다시 잠근다.
  // undefined = 되연 적 없음.
  const [reopenedAtAssetId, setReopenedAtAssetId] = useState<
    string | null | undefined
  >(undefined);

  const reason =
    typeof payload.reason === 'string' && payload.reason.trim().length > 0
      ? payload.reason
      : DEFAULT_REASON;

  const interactive = actions !== null;
  const streaming = actions?.busy ?? false;

  // 새로고침 시 이 카드(과거 메시지의 동적 컴포넌트)가 로컬 state 만으로는 첨부 여부를
  // 몰라 업로드 폼을 다시 보여 주던 문제 — 세션의 selected_floorplan_asset_id 로 영속
  // 상태와 UI 를 동기화한다. 컨텍스트 브로드캐스트(#floorplan-cards-broadcast)가 정본:
  // 형제 카드가 업로드해 값이 바뀌면 이 카드도 함께 재조정된다(한 스레드의 여러 도면
  // 카드가 서로 모순되게 남지 않게). 브로드캐스트가 없을 때(테스트 등)만 1회 자체 조회.
  const sessionId = actions?.sessionId;
  const priorAssetId = payload.prior_asset_id;
  const broadcastAssetId = actions?.selectedFloorplanAssetId;
  const [fetchedAssetId, setFetchedAssetId] = useState<string | null | undefined>(
    undefined
  );
  useEffect(() => {
    if (!sessionId || broadcastAssetId !== undefined) return;
    let ignore = false;
    void (async () => {
      try {
        const row = await getSession(sessionId);
        // await 이후의 setState — 동기 cascading render 아님(#set-state-in-effect 규약).
        if (!ignore) setFetchedAssetId(row.selected_floorplan_asset_id ?? null);
      } catch {
        /* 조회 실패 — 폼을 그대로 보여 준다(첨부는 다시 시도 가능) */
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId, broadcastAssetId]);
  const currentAssetId =
    broadcastAssetId !== undefined ? broadcastAssetId : fetchedAssetId;

  // 첨부 완료는 렌더 시 파생한다(효과로 state 미러링 금지 — react-hooks/set-state-in-effect).
  // "도면이 있다"만으로 잠그면 재업로드 요청 카드가 뜨자마자 죽는다 — 카드에 스탬프된
  // prior_asset_id(발행 시점의 asset)와 비교해 **이 카드 이후 새 asset 이 붙었을 때만**
  // 이행된 것으로 본다(#floorplan-request-prior-asset). 스탬프 없는 구 카드는 종전
  // 동작(도면 존재=첨부됨). '다시 올리기'로 되연 카드는 그 시점의 asset 이 그대로인
  // 동안 폼을 유지한다.
  const fulfilledByServer =
    currentAssetId != null &&
    (priorAssetId === undefined || currentAssetId !== priorAssetId);
  const attached =
    locallyAttached ||
    (fulfilledByServer && currentAssetId !== reopenedAtAssetId);
  // 세션에 (어떤 카드로든) 도면이 이미 존재하는지 — 폼 상태에서 "새 도면이 기존 도면을
  // 대체한다"는 안내를 붙일지 결정한다(재제출 UX).
  const hasPriorFloorplan = currentAssetId != null || locallyAttached;
  const disabled = busy || streaming || attached || !interactive;

  // 이미지 MIME·용량 검증은 드롭 입력이 한 번만 한다 — 통과한 파일만 여기로 온다.
  function handlePick(picked: File | null) {
    setError(null);
    setFile(picked);
  }

  function handleReject(message: string) {
    setFile(null);
    setError(message);
  }

  async function handleSubmit() {
    if (!actions || !file) {
      return;
    }
    if (actions.simulateUploads) {
      // 미리보기(/a2ui-preview) 전용 — 실제 세션·업로드·등록·전송 없이 성공 상태만 재현한다.
      setLocallyAttached(true);
      setFile(null);
      return;
    }
    setBusy(true);
    setError(null);
    let uploadedKey: string | null = null;
    try {
      await ensureAnonymousSession();
      const uploaded = await uploadSessionFloorplan(actions.sessionId, file);
      uploadedKey = uploaded.object_key;
      await createFloorplanAsset(actions.sessionId, {
        bucket: uploaded.bucket,
        object_key: uploaded.object_key,
        content_type: uploaded.content_type,
        byte_size: uploaded.byte_size
      });
      // 등록까지 성공 — 정리 대상 아님.
      uploadedKey = null;
      setLocallyAttached(true);
      setFile(null);
      trackPrecheckFloorplanAttach();
      await actions.refreshSession?.();
      await actions.sendMessage('도면을 첨부했어요. 분석해 주세요.');
    } catch (err) {
      if (uploadedKey) {
        // asset 등록 실패 — 방금 올린 object 를 정리(best-effort).
        await deleteSessionFloorplan(uploadedKey);
      }
      // raw 에러(예: "Request failed with status code 422", 백엔드 내부 메시지)를 그대로
      // 노출하지 않는다 — 사용자에겐 친화적 안내로 치환하고, 원인은 콘솔에만 남긴다.
      console.error('[floorplan-upload] failed', err);
      setError(friendlyUploadError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <CardShell accent={attached ? 'success' : 'blueprint'} labelledBy={titleId}>
      <CardHeader
        icon={
          attached ? (
            <IconCircleCheck size={17} aria-hidden />
          ) : (
            <IconPhotoUp size={17} aria-hidden />
          )
        }
        eyebrow={attached ? '첨부 완료' : '도면 검토'}
        title={attached ? '평면도를 받았어요' : '평면도를 올려 주세요'}
        titleId={titleId}
      />

      <CardRule />

      {attached ? (
        <Stack gap="xs">
          <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.55 }}>
            도면을 첨부했어요. 이어서 비내력벽 후보를 분석할게요.
          </Text>
          {/* 재제출 — 첨부 완료로 잠긴 카드에서도 폼을 되열어 다른 도면을 올릴 수 있다.
              기존 도면은 삭제되지 않고 새 도면이 대체한다(분석도 새 도면 기준으로 재실행).
              3차 액션이라 subtle, 단 모바일 터치 타깃 ≥44px(AGENTS.md)는 minHeight 로 보장. */}
          {interactive ? (
            <Button
              variant="subtle"
              color="jippin"
              size="sm"
              leftSection={<IconPhotoUp size={14} />}
              onClick={() => {
                // 이 시점의 asset 을 기억해 폼을 되연다 — 이후 **새** asset 변화가
                // 오면(형제 카드 업로드 등) 다시 '첨부 완료'로 잠긴다.
                setReopenedAtAssetId(currentAssetId ?? null);
                setLocallyAttached(false);
                setFile(null);
                setError(null);
              }}
              disabled={busy || streaming}
              styles={{ root: { alignSelf: 'flex-start', minHeight: 44 } }}
            >
              다른 도면으로 다시 올리기
            </Button>
          ) : null}
        </Stack>
      ) : (
        <Stack gap="sm">
          <Text
            size="sm"
            c="var(--jippin-brand-copy)"
            style={{ lineHeight: 1.55 }}
          >
            {reason}
          </Text>

          {interactive ? (
            <Stack gap="xs">
              {/* 드래그앤드롭 + 클릭/키보드 + 모바일 카메라 한 표면. 검증 거절 사유는
                  아래 error 블록으로 보여 준다. */}
              <FloorplanDropInput
                value={file}
                onChange={handlePick}
                onReject={handleReject}
                maxBytes={MAX_UPLOAD_BYTES}
                disabled={busy || streaming}
                size="sm"
              />
              {/* 재제출 안내 — 세션에 도면이 이미 있으면, 새 업로드가 기존 도면을
                  대체(재분석)함을 알린다. 기존 도면 삭제 아님. */}
              {hasPriorFloorplan ? (
                <Text size="xs" c="dimmed">
                  새 도면을 올리면 이전 도면 대신 새 도면으로 다시 분석해요.
                </Text>
              ) : null}
              {error ? (
                <Group
                  gap={8}
                  align="flex-start"
                  wrap="nowrap"
                  role="alert"
                  style={{
                    padding: '0.5rem 0.625rem',
                    borderRadius: 10,
                    background: 'var(--mantine-color-danger-0)'
                  }}
                >
                  <IconAlertCircle
                    size={15}
                    aria-hidden
                    style={{
                      color: 'var(--mantine-color-danger-6)',
                      flexShrink: 0,
                      marginTop: 1
                    }}
                  />
                  <Text size="xs" c="var(--jippin-brand-ink)">
                    {error}
                  </Text>
                </Group>
              ) : null}
              {/* 진행 표시 — 버튼 라벨이 사라지는 대신, 업로드 중임을 한 줄로 알린다. */}
              {busy ? (
                <Group gap={8} align="center" wrap="nowrap">
                  {/* 진행 표시는 상태 신호 — coral(전환 CTA 전용)이 아니라 브랜드색. */}
                  <Loader size={14} color="jippin" />
                  <Text size="xs" c="var(--jippin-brand-copy)">
                    도면을 올리고 있어요… 잠시만 기다려 주세요.
                  </Text>
                </Group>
              ) : null}
              {/* 로딩 중에도 라벨이 보이도록 Mantine loading(라벨 가림) 대신 직접 분기.
                  1차 액션(제품 기능: 도면 제출) — jippin filled. coral 은 전환 CTA 전용. */}
              <Button
                color="jippin"
                size="md"
                radius="md"
                leftSection={
                  busy ? (
                    <Loader size={16} color="white" />
                  ) : (
                    <IconUpload size={16} />
                  )
                }
                disabled={!file || disabled}
                onClick={handleSubmit}
                fullWidth
              >
                {busy ? '업로드 중…' : '도면 첨부하고 분석'}
              </Button>
            </Stack>
          ) : (
            <Text className="a2ui-meta">
              대화 화면에서 도면 이미지를 첨부할 수 있어요.
            </Text>
          )}
        </Stack>
      )}
    </CardShell>
  );
}
