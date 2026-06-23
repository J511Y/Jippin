import { describe, expect, it } from 'vitest';

import { parseSseFrame, splitSseBuffer } from './sse';

describe('splitSseBuffer', () => {
  it('완성된 프레임만 떼고 나머지는 rest 로 남긴다', () => {
    const { frames, rest } = splitSseBuffer(
      'event: token\ndata: {"a":1}\n\nevent: done\ndata: {"b":2}\n\npartial',
    );
    expect(frames).toHaveLength(2);
    expect(rest).toBe('partial');
  });

  it('\\r\\n 을 정규화한다', () => {
    const { frames } = splitSseBuffer('event: token\r\ndata: {"a":1}\r\n\r\n');
    expect(frames).toHaveLength(1);
  });
});

describe('parseSseFrame', () => {
  it('event 와 JSON data 를 파싱한다', () => {
    const frame = parseSseFrame('event: message\ndata: {"type":"message","content":"안녕"}');
    expect(frame?.event).toBe('message');
    expect((frame?.data as { content: string }).content).toBe('안녕');
  });

  it('하트비트 주석은 null', () => {
    expect(parseSseFrame(': heartbeat')).toBeNull();
  });

  it('깨진 JSON 은 null', () => {
    expect(parseSseFrame('event: x\ndata: {bad')).toBeNull();
  });

  it('data 가 없으면 null', () => {
    expect(parseSseFrame('event: ping')).toBeNull();
  });
});
