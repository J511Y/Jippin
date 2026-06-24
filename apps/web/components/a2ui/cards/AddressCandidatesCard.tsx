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

import { Group, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconBuilding, IconChevronRight, IconMapPin } from '@tabler/icons-react';
import { useId } from 'react';
import { useChatActions } from '@/components/agent/chat-actions';
import { CardHeader, CardRule, CardShell } from './CardShell';

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
  const titleId = useId();
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
    <CardShell accent="blueprint" labelledBy={titleId}>
      <CardHeader
        icon={<IconMapPin size={17} aria-hidden />}
        eyebrow="주소 확인"
        title="어느 주소인가요?"
        titleId={titleId}
      />

      <Text className="a2ui-meta" mt={6} mb="xs">
        검색된 후보 {payload.candidates.length}곳 중 하나를 선택해 주세요.
      </Text>

      <Stack gap={8} role="list">
        {payload.candidates.map((candidate, index) => (
          <UnstyledButton
            key={candidate.id}
            role="listitem"
            className="a2ui-option"
            data-disabled={disabled ? 'true' : undefined}
            disabled={disabled}
            onClick={() => handleSelect(candidate)}
            aria-label={`주소 선택: ${candidate.road_address}`}
          >
            <span className="a2ui-option__index" aria-hidden>
              {index + 1}
            </span>
            <Stack gap={3} style={{ flex: 1, minWidth: 0 }}>
              <Text
                size="sm"
                fw={600}
                c="var(--jippin-brand-ink)"
                style={{
                  lineHeight: 1.35,
                  wordBreak: 'keep-all',
                  overflowWrap: 'anywhere'
                }}
              >
                {candidate.road_address}
              </Text>
              {candidate.building_name || candidate.jibun_address ? (
                <Group gap={6} wrap="wrap">
                  {candidate.building_name ? (
                    <Group gap={4} wrap="nowrap" align="center">
                      <IconBuilding
                        size={13}
                        aria-hidden
                        style={{
                          color: 'var(--jippin-brand-professional)',
                          flexShrink: 0
                        }}
                      />
                      <Text
                        size="xs"
                        fw={500}
                        c="var(--jippin-brand-professional)"
                        style={{ wordBreak: 'keep-all' }}
                      >
                        {candidate.building_name}
                      </Text>
                    </Group>
                  ) : null}
                  {candidate.building_name && candidate.jibun_address ? (
                    <Text size="xs" c="var(--jippin-brand-border)" aria-hidden>
                      ·
                    </Text>
                  ) : null}
                  {candidate.jibun_address ? (
                    <Text size="xs" c="var(--jippin-brand-copy)">
                      지번 {candidate.jibun_address}
                    </Text>
                  ) : null}
                </Group>
              ) : null}
            </Stack>
            <IconChevronRight
              size={16}
              aria-hidden
              className="a2ui-option__chevron"
            />
          </UnstyledButton>
        ))}
      </Stack>

      {!interactive ? (
        <>
          <CardRule />
          <Text className="a2ui-meta">
            대화 화면에서 주소를 선택할 수 있어요.
          </Text>
        </>
      ) : null}
    </CardShell>
  );
}
