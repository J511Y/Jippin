/**
 * 세션 도면 업로드 (CMP-DIRECT) — leads/upload.ts 패턴 미러.
 *
 * (1) `POST /sessions/upload-url` 로 presigned PUT URL 발급(서버가 세션 uid + session_id
 * 로 owner 폴더 도출) → (2) Supabase Storage S3 로 직접 PUT → (3) object metadata 를
 * `POST /sessions/{id}/floorplan-assets` 로 등록(백엔드가 다시 owner-folder 검증).
 *
 * 사전: 호출 전에 `ensureAnonymousSession()` 으로 세션 쿠키가 설정돼 있어야 한다.
 */

export interface UploadedFloorplan {
  bucket: string;
  object_key: string;
  content_type: string;
  byte_size: number;
}

interface PresignResponse {
  upload_url: string;
  object_path: string;
  bucket: string;
}

async function requestPresignedUrl(
  sessionId: string,
  file: File,
  contentType: string
): Promise<PresignResponse> {
  const response = await fetch('/sessions/upload-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      file_name: file.name,
      content_type: contentType,
      byte_size: file.size
    })
  });
  if (!response.ok) {
    let message = '도면 업로드 준비에 실패했습니다.';
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(message);
  }
  return (await response.json()) as PresignResponse;
}

export async function uploadSessionFloorplan(
  sessionId: string,
  file: File
): Promise<UploadedFloorplan> {
  const contentType = file.type || 'application/octet-stream';
  const { upload_url, object_path, bucket } = await requestPresignedUrl(
    sessionId,
    file,
    contentType
  );

  const put = await fetch(upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: file
  });
  if (!put.ok) {
    throw new Error(`도면 업로드에 실패했습니다 (HTTP ${put.status}).`);
  }

  return {
    bucket,
    object_key: object_path,
    content_type: contentType,
    byte_size: file.size
  };
}

/**
 * 업로드된 도면 정리(best-effort). asset 등록 실패 시 방금 올린 object 를 지워
 * orphan PII 파일을 남기지 않는다. 실패해도 throw 하지 않는다(원래 에러 흐름 유지).
 */
export async function deleteSessionFloorplan(objectKey: string): Promise<void> {
  try {
    await fetch('/sessions/upload-url', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ object_path: objectKey })
    });
  } catch {
    // 정리는 best-effort — 서버측 cleanup 잡이 최종 안전망.
  }
}
