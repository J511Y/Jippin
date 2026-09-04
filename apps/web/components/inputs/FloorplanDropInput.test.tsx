import { cleanup, fireEvent, render, screen } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  FloorplanDropInput,
  formatBytes,
  validateFloorplanFile
} from './FloorplanDropInput';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function imageFile(name = 'plan.png', type = 'image/png'): File {
  return new File(['x'], name, { type });
}

/** 큰 파일은 실제 바이트를 만들지 않고 size 만 흉내낸다. */
function sizedFile(name: string, size: number, type = 'image/jpeg'): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

const dt = (files: File[]) => ({ dataTransfer: { types: ['Files'], files } });

describe('FloorplanDropInput 드래그앤드롭', () => {
  it('이미지를 드롭하면 onChange 로 파일을 올리고 하이라이트를 끈다', () => {
    const onChange = vi.fn();
    const onReject = vi.fn();
    render(
      <FloorplanDropInput
        value={null}
        onChange={onChange}
        onReject={onReject}
        aria-label="평면도 이미지 선택"
      />
    );
    const zone = screen.getByTestId('floorplan-dropzone');
    const file = imageFile();

    fireEvent.dragEnter(zone, dt([file]));
    expect(zone.getAttribute('data-dragging')).toBe('true');
    expect(screen.getByText('여기에 놓으면 첨부돼요')).toBeTruthy();

    fireEvent.drop(zone, dt([file]));
    expect(onChange).toHaveBeenCalledWith(file);
    expect(onReject).not.toHaveBeenCalled();
    expect(zone.getAttribute('data-dragging')).toBeNull();
  });

  it('여러 장을 놓으면 첫 장만 받는다', () => {
    const onChange = vi.fn();
    render(<FloorplanDropInput value={null} onChange={onChange} />);
    const first = imageFile('a.png');
    fireEvent.drop(screen.getByTestId('floorplan-dropzone'), dt([first, imageFile('b.png')]));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(first);
  });

  it('이미지가 아닌 파일은 거절 사유를 돌려주고 onChange 를 부르지 않는다', () => {
    const onChange = vi.fn();
    const onReject = vi.fn();
    render(<FloorplanDropInput value={null} onChange={onChange} onReject={onReject} />);
    fireEvent.drop(
      screen.getByTestId('floorplan-dropzone'),
      dt([new File(['x'], 'plan.pdf', { type: 'application/pdf' })])
    );
    expect(onChange).not.toHaveBeenCalled();
    expect(onReject).toHaveBeenCalledWith('이미지 파일만 첨부할 수 있어요. (JPG, PNG 등)');
  });

  it('용량 상한을 넘는 이미지는 거절한다(기본 50MB)', () => {
    const onChange = vi.fn();
    const onReject = vi.fn();
    render(<FloorplanDropInput value={null} onChange={onChange} onReject={onReject} />);
    fireEvent.drop(
      screen.getByTestId('floorplan-dropzone'),
      dt([sizedFile('big.jpg', 50 * 1024 * 1024 + 1)])
    );
    expect(onChange).not.toHaveBeenCalled();
    expect(onReject).toHaveBeenCalledWith('이미지 용량은 50MB 이하여야 해요.');
  });

  it('disabled 면 드롭을 무시한다', () => {
    const onChange = vi.fn();
    render(<FloorplanDropInput value={null} onChange={onChange} disabled />);
    const zone = screen.getByTestId('floorplan-dropzone');
    fireEvent.dragEnter(zone, dt([imageFile()]));
    expect(zone.getAttribute('data-dragging')).toBeNull();
    fireEvent.drop(zone, dt([imageFile()]));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('FloorplanDropInput 클릭/키보드 선택', () => {
  it('파일 대화상자로 고른 파일도 같은 검증을 거친다', () => {
    const onChange = vi.fn();
    const onReject = vi.fn();
    const { container } = render(
      <FloorplanDropInput value={null} onChange={onChange} onReject={onReject} />
    );
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.getAttribute('accept')).toBe('image/*');

    fireEvent.change(input, {
      target: { files: [new File(['x'], 'x.txt', { type: 'text/plain' })] }
    });
    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();

    const file = imageFile();
    fireEvent.change(input, { target: { files: [file] } });
    expect(onChange).toHaveBeenCalledWith(file);
  });

  it('"이미지 선택" 버튼(키보드 경로)이 숨은 file input 을 연다', () => {
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {});
    render(
      <FloorplanDropInput value={null} onChange={vi.fn()} aria-label="평면도 이미지 선택" />
    );
    fireEvent.click(screen.getByRole('button', { name: '평면도 이미지 선택' }));
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('선택된 파일은 이름·용량을 보여 주고 "첨부 취소" 로 비울 수 있다', () => {
    const onChange = vi.fn();
    render(<FloorplanDropInput value={sizedFile('plan.jpg', 2_855_891)} onChange={onChange} />);
    expect(screen.getByText('plan.jpg')).toBeTruthy();
    expect(screen.getByText('2.7MB', { exact: false })).toBeTruthy();
    expect(screen.getByTestId('floorplan-dropzone').getAttribute('data-filled')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: '첨부 취소' }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('label/description/error 를 주면 Input.Wrapper 로 감싸 폼 필드처럼 보인다', () => {
    render(
      <FloorplanDropInput
        value={null}
        onChange={vi.fn()}
        label="단위세대 평면도 첨부"
        description="촬영해 첨부해 주세요."
        error="이미지 파일만 첨부할 수 있어요. (JPG, PNG 등)"
      />
    );
    expect(screen.getByText('단위세대 평면도 첨부')).toBeTruthy();
    expect(screen.getByText('촬영해 첨부해 주세요.')).toBeTruthy();
    expect(screen.getByText('이미지 파일만 첨부할 수 있어요. (JPG, PNG 등)')).toBeTruthy();
  });
});

describe('validateFloorplanFile / formatBytes', () => {
  it('이미지 MIME 이 아니면 거절, 상한 이내 이미지는 통과', () => {
    expect(validateFloorplanFile(imageFile())).toBeNull();
    expect(validateFloorplanFile(new File(['x'], 'a', { type: '' }))).not.toBeNull();
    expect(validateFloorplanFile(sizedFile('a.jpg', 11), 10)).toBe(
      '이미지 용량은 10B 이하여야 해요.'
    );
  });

  it('formatBytes 는 MB/KB/B 로 보기 좋게 줄인다', () => {
    expect(formatBytes(50 * 1024 * 1024)).toBe('50MB');
    expect(formatBytes(2_855_891)).toBe('2.7MB');
    expect(formatBytes(512 * 1024)).toBe('512KB');
    expect(formatBytes(900)).toBe('900B');
  });
});

describe('FloorplanDropInput 미리보기 object URL', () => {
  it('선택 시 URL 을 만들고 비우면 정확히 그 URL 을 revoke 한다', () => {
    const create = vi.fn(() => 'blob:preview-1');
    const revoke = vi.fn();
    // jsdom 에는 없어 직접 심는다(테스트 뒤 제거).
    const url = URL as unknown as Record<string, unknown>;
    url.createObjectURL = create;
    url.revokeObjectURL = revoke;
    try {
      const file = imageFile('plan.png');
      const view = render(<FloorplanDropInput value={file} onChange={vi.fn()} />);
      expect(create).toHaveBeenCalledTimes(1);
      expect(create).toHaveBeenCalledWith(file);
      expect(view.container.querySelector('img')?.getAttribute('src')).toBe('blob:preview-1');

      view.rerender(<FloorplanDropInput value={null} onChange={vi.fn()} />);
      expect(revoke).toHaveBeenCalledWith('blob:preview-1');
      expect(view.container.querySelector('img')).toBeNull();
    } finally {
      delete url.createObjectURL;
      delete url.revokeObjectURL;
    }
  });
});

describe('FloorplanDropInput 접근성 연결', () => {
  it('label 이 있으면 선택 버튼 이름에 label 이 들어가고 description·힌트·거절 사유가 describedby 로 이어진다', () => {
    render(
      <FloorplanDropInput
        value={null}
        onChange={vi.fn()}
        label="단위세대 평면도 첨부"
        description="촬영해 첨부해 주세요."
        error="이미지 파일만 첨부할 수 있어요. (JPG, PNG 등)"
      />
    );
    const button = screen.getByRole('button', { name: /단위세대 평면도 첨부/ });
    expect(button.textContent).toContain('이미지 선택');
    expect(button.getAttribute('aria-invalid')).toBe('true');
    const described = (button.getAttribute('aria-describedby') ?? '')
      .split(' ')
      .map((id) => document.getElementById(id)?.textContent ?? '')
      .join(' ');
    expect(described).toContain('촬영해 첨부해 주세요.');
    expect(described).toContain('이미지 파일만 첨부할 수 있어요');
    expect(described).toContain('최대 50MB');
  });

  it('label 이 없으면(카드) aria-label 이 그대로 이름이 된다', () => {
    render(<FloorplanDropInput value={null} onChange={vi.fn()} aria-label="평면도 이미지 선택" />);
    const button = screen.getByRole('button', { name: '평면도 이미지 선택' });
    expect(button.getAttribute('aria-invalid')).toBeNull();
  });
});
