/**
 * 평면도 첨부 업로드 (CMP-DIRECT).
 *
 * 흐름: (1) `POST /leads/upload-url` 로 presigned PUT URL 발급(서버가 검증된 세션에서
 * owner 폴더 도출 + S3 자격증명 사용) → (2) 받은 URL 로 Supabase Storage S3 엔드포인트에
 * 파일을 직접 PUT → (3) object metadata 를 `POST /leads` 의 attachments 로 전달.
 *
 * 직접 PUT 이므로 Vercel 함수 본문 용량 제한을 우회한다. 사전: 호출 전에
 * `ensureAnonymousSession()` 으로 세션 쿠키가 설정돼 있어야 한다(서버가 uid 를 읽음).
 */

export interface UploadedAttachment {
  bucket: string;
  object_path: string;
  file_name: string;
  content_type: string;
  byte_size: number;
}

interface PresignResponse {
  upload_url: string;
  object_path: string;
  bucket: string;
}

async function requestPresignedUrl(file: File, contentType: string): Promise<PresignResponse> {
  const response = await fetch('/leads/upload-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_name: file.name,
      content_type: contentType,
      byte_size: file.size
    })
  });
  if (!response.ok) {
    let message = '업로드 준비에 실패했습니다.';
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

export async function uploadFloorplan(file: File): Promise<UploadedAttachment> {
  const contentType = file.type || 'application/octet-stream';
  const { upload_url, object_path, bucket } = await requestPresignedUrl(file, contentType);

  const put = await fetch(upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: file
  });
  if (!put.ok) {
    throw new Error(`평면도 업로드에 실패했습니다 (HTTP ${put.status}).`);
  }

  return {
    bucket,
    object_path,
    file_name: file.name,
    content_type: contentType,
    byte_size: file.size
  };
}
