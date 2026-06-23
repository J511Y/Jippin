'use client';

/**
 * A2UI `address-candidates` 카드 — 주소 후보 선택 (CMP-DIRECT).
 *
 * search_address 결과가 여럿일 때 에이전트가 방출한다. 사용자가 후보를 고르면
 * `sendMessage` 로 선택을 대화에 이어 보낸다.
 *
 * payload: { candidates: Array<{ id; road_address; jibun_address?; building_name? }> }
 *
 * 보안/검증: candidates 가 배열이고 각 원소가 최소한 `id`/`road_address` string 을
 * 가졌는지 검증한다. 형태가 어긋나면 카드 렌더러가 null 을 반환해 JSON fallback 으로
 * 떨어진다. 모든 문자열은 React 텍스트 노드로만 렌더한다.
 */

import { Badge, Group, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconChevronRight, IconMapPin } from '@tabler/icons-react';
import { useChatActions } from '@/components/agent/chat-actions';

export type AddressCandidate = {
  id: string;
  road_address: string;
  jibun_address?: string;
  building_name?: string;
};

export type AddressCandidatesPayload = {
  candidates: AddressCandidate[];
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCandidate(value: unknown): value is AddressCandidate {
  if (!isPlainObject(value)) {
    return false;
  }
  const idOk = typeof value.id === 'string' && value.id.length > 0;
  const roadOk =
    typeof value.road_address === 'string' && value.road_address.length > 0;
  const jibunOk =
    value.jibun_address === undefined || typeof value.jibun_address === 'string';
  const nameOk =
    value.building_name === undefined ||
    typeof value.building_name === 'string';
  return idOk && roadOk && jibunOk && nameOk;
}

export function isAddressCandidatesPayload(
  payload: unknown
): payload is AddressCandidatesPayload {
  if (!isPlainObject(payload)) {
    return false;
  }
  const { candidates } = payload;
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return false;
  }
  return candidates.every(isCandidate);
}

export function AddressCandidatesCard({
  payload
}: {
  payload: AddressCandidatesPayload;
}) {
  const actions = useChatActions();
  const interactive = actions !== null;
  const disabled = !interactive || (actions?.busy ?? false);

  function handleSelect(candidate: AddressCandidate) {
    if (!actions) {
      return;
    }
    const detail = candidate.building_name
      ? `${candidate.road_address} (${candidate.building_name})`
      : candidate.road_address;
    void actions.sendMessage(`이 주소로 진행할게요: ${detail}`);
  }

  return (
    <Stack gap="sm">
      <Group gap="xs" wrap="nowrap">
        <IconMapPin
          size={18}
          aria-hidden
          style={{ color: 'var(--jippin-brand-professional)', flexShrink: 0 }}
        />
        <Text fw={600} size="sm" c="var(--jippin-brand-ink)">
          주소를 선택해 주세요
        </Text>
      </Group>

      <Stack gap={8} role="list">
        {payload.candidates.map((candidate) => (
          <UnstyledButton
            key={candidate.id}
            role="listitem"
            onClick={() => handleSelect(candidate)}
            disabled={disabled}
            aria-label={`주소 선택: ${candidate.road_address}`}
            style={{
              border: '1px solid var(--jippin-brand-border)',
              borderRadius: 'var(--mantine-radius-md)',
              padding: '0.625rem 0.75rem',
              background: 'var(--jippin-brand-surface)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              opacity: disabled ? 0.6 : 1,
              transition: 'border-color 120ms ease, background 120ms ease'
            }}
          >
            <Group gap="xs" wrap="nowrap" align="flex-start">
              <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                <Group gap={6} wrap="nowrap">
                  <Text
                    size="sm"
                    fw={600}
                    c="var(--jippin-brand-ink)"
                    style={{ wordBreak: 'keep-all', overflowWrap: 'anywhere' }}
                  >
                    {candidate.road_address}
                  </Text>
                  {candidate.building_name ? (
                    <Badge color="blueprint" variant="light" size="sm">
                      {candidate.building_name}
                    </Badge>
                  ) : null}
                </Group>
                {candidate.jibun_address ? (
                  <Text size="xs" c="var(--jippin-brand-copy)">
                    지번 {candidate.jibun_address}
                  </Text>
                ) : null}
              </Stack>
              <IconChevronRight
                size={16}
                aria-hidden
                style={{
                  color: 'var(--jippin-brand-copy)',
                  flexShrink: 0,
                  marginTop: 2
                }}
              />
            </Group>
          </UnstyledButton>
        ))}
      </Stack>

      {!interactive ? (
        <Text size="xs" c="var(--jippin-brand-copy)">
          대화 화면에서 주소를 선택할 수 있어요.
        </Text>
      ) : null}
    </Stack>
  );
}
