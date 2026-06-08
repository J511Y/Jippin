/**
 * 평면도 업로드 정책 — 서버 Route Handler(`/leads/upload-url`)와 공유하는 순수 검증
 * 로직 (CMP-DIRECT). 테스트 가능하도록 부수효과를 분리한다.
 *
 * object key 규약: `<userId>/<uuid>-<safeName>`. 첫 세그먼트가 업로더 uid 여야
 * 백엔드(`POST /leads`)의 owner-folder 검증과 Storage RLS 규약에 정합한다.
 */

// Supabase Storage `lead-floorplans` 버킷 file_size_limit(config.toml)와 정합한 상한.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024; // 50 MiB
const ALLOWED_CONTENT_TYPE_PREFIX = 'image/';

export function safeFileName(name: string): string {
  return (name ?? '').replace(/[^\w.\-]+/g, '_').slice(0, 120) || 'upload';
}

export function buildLeadObjectPath(userId: string, fileName: string): string {
  return `${userId}/${crypto.randomUUID()}-${safeFileName(fileName)}`;
}

export type ParsedUpload =
  | { ok: true; fileName: string; contentType: string; byteSize: number }
  | { ok: false; message: string };

export function validateUploadRequest(body: unknown): ParsedUpload {
  if (typeof body !== 'object' || body === null) {
    return { ok: false, message: '요청 본문이 올바르지 않습니다.' };
  }
  const { file_name, content_type, byte_size } = body as Record<string, unknown>;

  if (typeof file_name !== 'string' || file_name.trim().length === 0) {
    return { ok: false, message: '파일명이 필요합니다.' };
  }
  if (typeof content_type !== 'string' || !content_type.startsWith(ALLOWED_CONTENT_TYPE_PREFIX)) {
    return { ok: false, message: '이미지 파일만 첨부할 수 있습니다.' };
  }
  if (typeof byte_size !== 'number' || !Number.isFinite(byte_size) || byte_size <= 0) {
    return { ok: false, message: '파일 크기가 올바르지 않습니다.' };
  }
  if (byte_size > MAX_UPLOAD_BYTES) {
    return { ok: false, message: '파일이 너무 큽니다. (최대 50MB)' };
  }
  return { ok: true, fileName: file_name, contentType: content_type, byteSize: byte_size };
}
