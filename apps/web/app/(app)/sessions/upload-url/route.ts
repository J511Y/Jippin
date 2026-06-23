/**
 * 세션 도면 업로드용 S3 presigned PUT URL 발급 (CMP-DIRECT) — leads/upload-url 미러.
 *
 * 경로: `POST /sessions/upload-url`. owner 폴더(object key 첫 세그먼트)는 검증된
 * Supabase 세션 uid 에서 도출하고, 두 번째 세그먼트로 session_id 를 둔다
 * (`<uid>/<sessionId>/<uuid>-<safeName>`). 백엔드(`POST /sessions/{id}/floorplan-assets`)
 * 가 Bearer user_id 로 owner-folder 를 한 번 더 검증한다.
 */

import { PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { NextResponse, type NextRequest } from 'next/server';
import { safeFileName, validateUploadRequest } from '@/lib/leads/upload-policy';
import { createRouteHandlerClient } from '@/lib/supabase/server';

// @aws-sdk 는 Node 런타임 필요(Edge 비호환).
export const runtime = 'nodejs';

const DEFAULT_BUCKET = 'session-floorplans';
const PRESIGN_TTL_SECONDS = 300;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function jsonError(code: string, message: string, status: number): NextResponse {
  return NextResponse.json({ error: { code, message } }, { status });
}

function createS3Client(): S3Client {
  const endpoint = process.env.S3_ENDPOINT;
  const region = process.env.S3_REGION;
  const accessKeyId = process.env.S3_ACCESS_KEY;
  const secretAccessKey = process.env.S3_SECRET_KEY;
  if (!endpoint || !region || !accessKeyId || !secretAccessKey) {
    throw new Error(
      'S3 자격증명(S3_ENDPOINT/S3_REGION/S3_ACCESS_KEY/S3_SECRET_KEY)이 설정되지 않았습니다.'
    );
  }
  return new S3Client({
    endpoint,
    region,
    forcePathStyle: true,
    credentials: { accessKeyId, secretAccessKey }
  });
}

export async function POST(request: NextRequest) {
  const cookieResponse = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response: cookieResponse });

  const {
    data: { user },
    error: authError
  } = await supabase.auth.getUser();
  if (authError || !user) {
    return jsonError('UNAUTHENTICATED', '업로드하려면 세션이 필요합니다.', 401);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = null;
  }
  const sessionId =
    body && typeof body === 'object' && typeof (body as { session_id?: unknown }).session_id === 'string'
      ? (body as { session_id: string }).session_id
      : '';
  if (!UUID_RE.test(sessionId)) {
    return jsonError('INVALID_SESSION_ID', 'session_id 가 올바르지 않습니다.', 422);
  }
  const parsed = validateUploadRequest(body);
  if (!parsed.ok) {
    return jsonError('INVALID_UPLOAD', parsed.message, 422);
  }

  const bucket = process.env.SESSION_FLOORPLAN_BUCKET ?? DEFAULT_BUCKET;
  // owner-folder 규약: 첫 세그먼트 = uid, 두 번째 = session_id.
  const objectPath = `${user.id}/${sessionId}/${crypto.randomUUID()}-${safeFileName(parsed.fileName)}`;

  let uploadUrl: string;
  try {
    uploadUrl = await getSignedUrl(
      createS3Client(),
      new PutObjectCommand({
        Bucket: bucket,
        Key: objectPath,
        ContentType: parsed.contentType
      }),
      { expiresIn: PRESIGN_TTL_SECONDS }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : '업로드 URL 발급에 실패했습니다.';
    return jsonError('PRESIGN_FAILED', message, 500);
  }

  const json = NextResponse.json({ upload_url: uploadUrl, object_path: objectPath, bucket });
  for (const cookie of cookieResponse.cookies.getAll()) {
    json.cookies.set(cookie);
  }
  return json;
}
