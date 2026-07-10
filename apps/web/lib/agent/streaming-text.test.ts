import { describe, expect, it } from 'vitest';

import { maskStreamingJson } from './streaming-text';

describe('maskStreamingJson', () => {
  it('일반 생활어 본문은 그대로 둔다', () => {
    const text = '도면에서 초록색 비내력벽 후보를 눌러 골라 주세요.';
    expect(maskStreamingJson(text)).toBe(text);
  });

  it('중괄호+따옴표 키로 시작하는 JSON 덤프를 가린다', () => {
    const text = '분석이 끝났어요. {"is_floorplan":true,"confidence":0.7,"notes":["…"]';
    expect(maskStreamingJson(text)).toBe('분석이 끝났어요.');
  });

  it('pretty-print JSON(중괄호 뒤 개행)도 가린다', () => {
    const text = '결과입니다.\n{\n  "reclassifications": []';
    expect(maskStreamingJson(text)).toBe('결과입니다.');
  });

  it('```json 코드펜스를 가린다', () => {
    const text = '아래 결과를 확인해 주세요.\n```json\n{"verdict": "ALLOW"}';
    expect(maskStreamingJson(text)).toBe('아래 결과를 확인해 주세요.');
  });

  it('본문 전체가 JSON 이면 빈 문자열이 된다(타이핑 인디케이터 폴백)', () => {
    expect(maskStreamingJson('{"is_floorplan": true}')).toBe('');
  });

  it('중괄호가 있어도 JSON 형태가 아니면 그대로 둔다', () => {
    const text = '수식 {x} 표기는 마스킹하지 않아요.';
    expect(maskStreamingJson(text)).toBe(text);
  });
});
