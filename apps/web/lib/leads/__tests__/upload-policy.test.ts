import { describe, expect, it } from 'vitest';
import {
  buildLeadObjectPath,
  MAX_UPLOAD_BYTES,
  safeFileName,
  validateUploadRequest
} from '@/lib/leads/upload-policy';

describe('safeFileName', () => {
  it('replaces unsafe characters and path separators', () => {
    // 연속된 비허용 문자(한글/공백/괄호)는 하나의 '_' 로 축약된다.
    expect(safeFileName('내 도면 (1).png')).toBe('_1_.png');
    expect(safeFileName('a/b\\c.png')).toBe('a_b_c.png');
    // 경로 구분자가 제거돼 owner-folder 규약을 깨지 않는다.
    expect(safeFileName('a/b\\c.png')).not.toContain('/');
  });

  it('falls back to a default for empty names', () => {
    expect(safeFileName('')).toBe('upload');
  });
});

describe('buildLeadObjectPath', () => {
  it('prefixes the object key with the owner uid folder', () => {
    const uid = '11111111-2222-3333-4444-555555555555';
    const path = buildLeadObjectPath(uid, 'plan.png');
    expect(path.startsWith(`${uid}/`)).toBe(true);
    expect(path.endsWith('-plan.png')).toBe(true);
    expect(path.split('/')[0]).toBe(uid);
  });
});

describe('validateUploadRequest', () => {
  it('accepts a valid image upload request', () => {
    const result = validateUploadRequest({
      file_name: 'plan.png',
      content_type: 'image/png',
      byte_size: 1024
    });
    expect(result).toEqual({ ok: true, fileName: 'plan.png', contentType: 'image/png', byteSize: 1024 });
  });

  it('rejects non-image content types', () => {
    const result = validateUploadRequest({ file_name: 'a.pdf', content_type: 'application/pdf', byte_size: 10 });
    expect(result.ok).toBe(false);
  });

  it('rejects missing file name', () => {
    expect(validateUploadRequest({ content_type: 'image/png', byte_size: 10 }).ok).toBe(false);
  });

  it('rejects oversized files', () => {
    const result = validateUploadRequest({
      file_name: 'big.jpg',
      content_type: 'image/jpeg',
      byte_size: MAX_UPLOAD_BYTES + 1
    });
    expect(result.ok).toBe(false);
  });

  it('rejects non-object bodies', () => {
    expect(validateUploadRequest(null).ok).toBe(false);
    expect(validateUploadRequest('nope').ok).toBe(false);
  });
});
