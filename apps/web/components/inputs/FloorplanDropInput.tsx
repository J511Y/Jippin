'use client';

/**
 * 도면 이미지 드롭 입력 (CMP-DIRECT).
 *
 * 기존 Mantine `FileInput` 은 클릭 → 파일 대화상자만 지원해 PC 에서 탐색기/사진 앱의
 * 도면 사진을 끌어다 놓을 수 없었다. 본 컴포넌트는 **드래그앤드롭 + 클릭/키보드 선택
 * + 모바일 카메라·갤러리(accept=image/*)** 를 한 표면으로 제공한다. 외부 의존성 없이
 * 네이티브 DataTransfer 만 쓴다(@mantine/dropzone 미도입 — react-dropzone 피어 의존과
 * 번들 증가 회피).
 *
 * 검증(이미지 MIME·용량 상한)은 여기서 한 번만 한다 — 통과한 파일만 `onChange` 로
 * 올리고, 거절 사유는 `onReject` 로 생활어 한 문장을 돌려준다(호출부가 폼 에러로
 * 노출). 서버(presign 라우트·백엔드 HEAD 검증)가 최종 관문이라 여기 검증은 UX 용이다.
 *
 * 값 계약은 `value: File | null` + `onChange(file | null)` — 기존 FileInput 과 같아
 * 카드/폼의 상태 코드를 바꾸지 않고 교체된다. 접근성: 컨테이너는 드롭·클릭 편의 표면일
 * 뿐이고, 키보드/스크린리더 경로는 안의 실제 버튼("이미지 선택"/"바꾸기", "첨부 취소")
 * 이다(중첩 버튼 회피). 점선 테두리 = "여기에 놓을 수 있음" 어포던스(색 단독 아님).
 */

import { Box, Button, CloseButton, Group, Input, Stack, Text } from '@mantine/core';
import { IconPhotoUp } from '@tabler/icons-react';
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type MouseEvent,
  type ReactNode
} from 'react';

import { MAX_UPLOAD_BYTES } from '@/lib/leads/upload-policy';

export interface FloorplanDropInputProps {
  value: File | null;
  onChange: (file: File | null) => void;
  /** 거절(비이미지·용량 초과) 사유 — 생활어 한 문장. 호출부가 error 로 노출한다. */
  onReject?: (message: string) => void;
  disabled?: boolean;
  /** 용량 상한(바이트). 기본은 presign 정책과 같은 50MB. */
  maxBytes?: number;
  label?: ReactNode;
  description?: ReactNode;
  error?: ReactNode;
  withAsterisk?: boolean;
  /** 빈 상태 안내 문구. */
  prompt?: string;
  /** 빈 상태 보조 힌트(형식·용량). 기본: 형식 + 용량 상한. */
  hint?: string;
  /** 다루는 대상 이름 — 래퍼 label 이 없는 사용처(카드)에서 선택/바꾸기 버튼의 접근성 이름을
   *  "<subject> 선택"/"<subject> 바꾸기" 로 짓는다. label 이 있으면 label 로 이름 짓는다. */
  subject?: string;
  /** 시각 밀도 — 카드 안에서는 sm. */
  size?: 'sm' | 'md';
}

/** 사람이 읽는 용량 표기(50MB, 2.7MB, 512KB). */
export function formatBytes(bytes: number): string {
  const mb = 1024 * 1024;
  if (bytes >= mb) {
    const value = bytes / mb;
    return `${value >= 10 ? Math.round(value) : Math.round(value * 10) / 10}MB`;
  }
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${bytes}B`;
}

/** 이미지 MIME + 용량 상한 검증. 통과하면 null, 아니면 사용자에게 보여 줄 사유. */
export function validateFloorplanFile(
  file: File,
  maxBytes: number = MAX_UPLOAD_BYTES
): string | null {
  if (!file.type.startsWith('image/')) {
    return '이미지 파일만 첨부할 수 있어요. (JPG, PNG 등)';
  }
  if (file.size > maxBytes) {
    return `이미지 용량은 ${formatBytes(maxBytes)} 이하여야 해요.`;
  }
  return null;
}

function transferHasFiles(event: DragEvent<HTMLElement>): boolean {
  const types = event.dataTransfer?.types;
  return types ? Array.from(types).includes('Files') : false;
}

export function FloorplanDropInput({
  value,
  onChange,
  onReject,
  disabled = false,
  maxBytes = MAX_UPLOAD_BYTES,
  label,
  description,
  error,
  withAsterisk,
  prompt = '평면도 이미지를 여기에 끌어다 놓거나, 눌러서 선택하세요',
  hint,
  subject = '평면도 이미지',
  size = 'md'
}: FloorplanDropInputProps) {
  const inputId = useId();
  // 접근성: 래퍼의 label/description/error 와 안의 실제 포커스 대상(이미지 선택·바꾸기 버튼)을
  // aria-labelledby/-describedby 로 잇는다 — 숨은 file input 대신 버튼이 유일한 키보드·
  // 스크린리더 경로라, 어느 파일 필드인지와 거절 사유를 버튼에서 들을 수 있어야 한다.
  const labelId = useId();
  const descriptionId = useId();
  const errorId = useId();
  const hintId = useId();
  const pickerId = useId();
  const changeId = useId();
  const describedBy =
    [description != null ? descriptionId : null, error ? errorId : null, value ? null : hintId]
      .filter(Boolean)
      .join(' ') || undefined;
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  // dragenter/dragleave 는 자식 요소를 지날 때마다 쌍으로 발생한다 — 깊이를 세어 컨테이너를
  // 완전히 벗어났을 때만 하이라이트를 끈다(깜빡임 방지).
  const depthRef = useRef(0);

  const resolvedHint = hint ?? `JPG·PNG 등 이미지 파일, 최대 ${formatBytes(maxBytes)}`;

  // 선택된 이미지 미리보기. object URL 은 렌더(useMemo)가 아니라 effect 에서 만든다 —
  // StrictMode/동시 렌더가 커밋되지 않은 렌더의 URL 을 만들면 cleanup 이 그 URL 을 모르고
  // 최대 50MB 블롭이 남는다. 같은 effect 의 cleanup 이 정확히 그 URL 을 해제한다.
  // (effect 안 setState 는 브라우저 리소스 수명 관리의 표준 패턴이라 규약 예외로 둔다.)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!value || typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') {
      return undefined;
    }
    let url: string;
    try {
      url = URL.createObjectURL(value);
    } catch {
      // 미리보기는 부가 기능 — 환경(테스트 jsdom/Node URL 등)이 이 File 을 거부하면 건너뛴다.
      return undefined;
    }
    /* eslint-disable react-hooks/set-state-in-effect */
    setPreviewUrl(url);
    return () => {
      setPreviewUrl(null);
      if (typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url);
    };
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [value]);

  function pick(file: File | null | undefined) {
    if (!file) return;
    const problem = validateFloorplanFile(file, maxBytes);
    if (problem) {
      onReject?.(problem);
      return;
    }
    onChange(file);
  }

  function openPicker() {
    if (disabled) return;
    inputRef.current?.click();
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null;
    // 같은 파일을 다시 골라도 change 가 나도록 값을 비운다.
    event.currentTarget.value = '';
    pick(file);
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (disabled || !transferHasFiles(event)) return;
    depthRef.current += 1;
    setDragging(true);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    // preventDefault 가 없으면 브라우저가 드롭을 거부하고 파일을 새 탭으로 연다.
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = disabled ? 'none' : 'copy';
    }
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (depthRef.current > 0) depthRef.current -= 1;
    if (depthRef.current === 0) setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    depthRef.current = 0;
    setDragging(false);
    if (disabled) return;
    // 여러 장을 놓아도 첫 장만 — 도면은 한 장 단위로 분석한다.
    pick(event.dataTransfer?.files?.[0]);
  }

  function handleClear(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation();
    onChange(null);
  }

  const zone = (
    <Box
      className="jippin-dropzone"
      data-testid="floorplan-dropzone"
      data-size={size}
      data-dragging={dragging || undefined}
      data-filled={value ? true : undefined}
      data-disabled={disabled || undefined}
      onClick={openPicker}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept="image/*"
        hidden
        disabled={disabled}
        onChange={handleInputChange}
      />
      {value ? (
        <Group gap="sm" wrap="nowrap" align="center">
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- 로컬 object URL 미리보기(next/image 비대상)
            <img src={previewUrl} alt="" className="jippin-dropzone__thumb" />
          ) : (
            <span className="jippin-dropzone__icon" aria-hidden>
              <IconPhotoUp size={18} />
            </span>
          )}
          <Stack gap="xs" style={{ minWidth: 0, flex: 1 }}>
            <Text size="sm" fw={600} truncate="end" c="var(--jippin-brand-ink)">
              {value.name}
            </Text>
            <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
              {formatBytes(value.size)} · 다른 이미지를 끌어다 놓거나 눌러서 바꿀 수 있어요
            </Text>
          </Stack>
          {/* 버튼 자체 핸들러 없음 — 클릭이 컨테이너로 버블돼 파일 대화상자가 열린다.
              모바일 터치 타깃 ≥44px(AGENTS.md §4.8.1): 두 컨트롤 모두 44px 로 맞춘다.
              특히 '첨부 취소' 는 빗나가면 컨테이너가 파일 대화상자를 여는 정정 동작이라
              작으면 안 된다. */}
          <Button
            type="button"
            id={changeId}
            variant="subtle"
            color="jippin"
            size="sm"
            disabled={disabled}
            aria-label={label == null ? `${subject} 바꾸기` : undefined}
            aria-labelledby={label != null ? `${labelId} ${changeId}` : undefined}
            aria-describedby={describedBy}
            styles={{ root: { minHeight: 44 } }}
          >
            바꾸기
          </Button>
          <CloseButton
            aria-label="첨부 취소"
            size={44}
            iconSize={18}
            disabled={disabled}
            onClick={handleClear}
          />
        </Group>
      ) : (
        <Stack gap="xs" align="center">
          <span className="jippin-dropzone__icon" aria-hidden>
            <IconPhotoUp size={20} />
          </span>
          <Text
            size="sm"
            fw={600}
            ta="center"
            c="var(--jippin-brand-ink)"
            style={{ wordBreak: 'keep-all' }}
          >
            {dragging ? '여기에 놓으면 첨부돼요' : prompt}
          </Text>
          <Text id={hintId} size="xs" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
            {resolvedHint}
          </Text>
          {/* 키보드/스크린리더 경로 — 컨테이너 클릭과 같은 동작(버블링). 모바일 터치 타깃
              ≥44px 은 minHeight 로 보장. 래퍼 label 이 있으면 "<label> 이미지 선택" 으로
              이름 짓고 description/힌트/거절 사유를 describedby 로 잇는다. */}
          <Button
            type="button"
            id={pickerId}
            variant="light"
            color="jippin"
            size="sm"
            disabled={disabled}
            aria-label={label == null ? `${subject} 선택` : undefined}
            aria-labelledby={label != null ? `${labelId} ${pickerId}` : undefined}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            styles={{ root: { minHeight: 44 } }}
          >
            이미지 선택
          </Button>
        </Stack>
      )}
    </Box>
  );

  if (label == null && description == null && !error) {
    return zone;
  }
  // 라벨 클릭도 숨은 file input(id)으로 이어져 파일 대화상자가 열린다.
  return (
    <Input.Wrapper
      id={inputId}
      label={label}
      description={description}
      error={error}
      withAsterisk={withAsterisk}
      labelProps={{ id: labelId }}
      descriptionProps={{ id: descriptionId }}
      errorProps={{ id: errorId }}
    >
      {zone}
    </Input.Wrapper>
  );
}
