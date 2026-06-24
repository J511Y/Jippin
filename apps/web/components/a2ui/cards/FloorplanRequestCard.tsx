'use client';

/**
 * A2UI `floorplan-request` 카드 — 도면 업로드 유도 (CMP-DIRECT).
 *
 * 항상 떠 있던 업로드 입력을 대체한다. 에이전트가 "도면이 필요하다"고 판단하면
 * 이 카드를 방출하고, 사용자가 카드 안에서 이미지를 골라 첨부하면 업로드 →
 * asset 등록 → `sendMessage` 로 분석을 이어 가게 한다.
 *
 * payload: { reason?: string }
 *
 * 보안/검증: payload 는 LLM/서버 유래라 런타임 형태가 임의일 수 있다. `isPlainObject`
 * 로 객체임을 좁힌 뒤 `reason` 이 string 일 때만 채택한다(아니면 기본 문구). 모든
 * 사용자/LLM 문자열은 React 텍스트 노드로만 렌더해 raw HTML 주입을 막는다.
 */

import { Button, FileInput, Group, Loader, Stack, Text } from '@mantine/core';
import {
  IconAlertCircle,
  IconCircleCheck,
  IconPhotoUp,
  IconUpload
} from '@tabler/icons-react';
import { useId, useState } from 'react';
import { useChatActions } from '@/components/agent/chat-actions';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { createFloorplanAsset } from '@/lib/sessions/api';
import {
  deleteSessionFloorplan,
  uploadSessionFloorplan
} from '@/lib/sessions/upload';
import { CardHeader, CardRule, CardShell } from './CardShell';

/** 50MB — 백엔드 presign 한도와 정합. */
const MAX_BYTES = 50 * 1024 * 1024;

export type FloorplanRequestPayload = {
  reason?: string;
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
  return payload.reason === undefined || typeof payload.reason === 'string';
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
  const [attached, setAttached] = useState(false);

  const reason =
    typeof payload.reason === 'string' && payload.reason.trim().length > 0
      ? payload.reason
      : DEFAULT_REASON;

  const interactive = actions !== null;
  const streaming = actions?.busy ?? false;
  const disabled = busy || streaming || attached || !interactive;

  function handlePick(picked: File | null) {
    setError(null);
    if (picked && picked.size > MAX_BYTES) {
      setFile(null);
      setError('이미지 용량은 50MB 이하여야 합니다.');
      return;
    }
    setFile(picked);
  }

  async function handleSubmit() {
    if (!actions || !file) {
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
      setAttached(true);
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
        <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.55 }}>
          도면을 첨부했어요. 이어서 비내력벽 후보를 분석할게요.
        </Text>
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
              <FileInput
                value={file}
                onChange={handlePick}
                accept="image/*"
                placeholder="이미지 파일 선택 (최대 50MB)"
                clearable
                disabled={busy || streaming}
                leftSection={<IconPhotoUp size={16} />}
                aria-label="평면도 이미지 선택"
              />
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
                  <Loader size={14} color="coral" />
                  <Text size="xs" c="var(--jippin-brand-copy)">
                    도면을 올리고 있어요… 잠시만 기다려 주세요.
                  </Text>
                </Group>
              ) : null}
              {/* 로딩 중에도 라벨이 보이도록 Mantine loading(라벨 가림) 대신 직접 분기. */}
              <Button
                color="coral"
                size="sm"
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
