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

/**
 * 도면 사진의 EXIF 방향을 굽혀(upright) 재인코딩한다 — 정렬 정합의 핵심.
 *
 * 폰 사진은 EXIF orientation 으로 회전 정보를 담는다. 브라우저는 표시 시 EXIF 를
 * 적용(upright)하지만, 세그멘테이션 모델(PIL, raw 픽셀)은 EXIF 를 무시한 원본 방향을
 * 분석해 좌표를 낸다. 그 결과 오버레이 폴리곤이 표시 이미지와 90° 어긋나고 영역을
 * 벗어난다. 업로드 전에 createImageBitmap(imageOrientation:'from-image')로 EXIF 를
 * 적용한 픽셀을 canvas 에 다시 그려 **방향이 굽힌(EXIF 없는) upright 이미지**로 저장하면,
 * 모델과 브라우저가 같은 좌표계를 보게 되어 오버레이가 정확히 겹친다.
 *
 * 실패(미지원/디코드 오류)하면 원본을 그대로 올린다(최소 동작 보장).
 */
async function normalizeImageOrientation(file: File): Promise<File> {
  if (
    typeof window === 'undefined' ||
    typeof createImageBitmap !== 'function' ||
    !file.type.startsWith('image/')
  ) {
    return file;
  }
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      bitmap.close();
      return file;
    }
    ctx.drawImage(bitmap, 0, 0);
    bitmap.close();
    // 선화/표가 많은 도면은 PNG 무손실, 사진은 JPEG(용량). 원본이 PNG 면 PNG 유지.
    const outType = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, outType, outType === 'image/jpeg' ? 0.92 : undefined)
    );
    if (!blob) return file;
    const base = file.name.replace(/\.[^.]+$/, '');
    const ext = outType === 'image/png' ? '.png' : '.jpg';
    return new File([blob], `${base}${ext}`, { type: outType });
  } catch {
    return file;
  }
}

export async function uploadSessionFloorplan(
  sessionId: string,
  file: File
): Promise<UploadedFloorplan> {
  // 방향 정규화 후 정규화된 파일로 presign/PUT/등록한다(모델·표시 좌표 일치).
  const normalized = await normalizeImageOrientation(file);
  const contentType = normalized.type || 'application/octet-stream';
  const { upload_url, object_path, bucket } = await requestPresignedUrl(
    sessionId,
    normalized,
    contentType
  );

  const put = await fetch(upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: normalized
  });
  if (!put.ok) {
    throw new Error(`도면 업로드에 실패했습니다 (HTTP ${put.status}).`);
  }

  return {
    bucket,
    object_key: object_path,
    content_type: contentType,
    byte_size: normalized.size
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
