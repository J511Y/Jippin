/**
 * 평면도 업로드용 S3 presigned PUT URL 발급 (CMP-DIRECT).
 *
 * 경로: `POST /leads/upload-url`. Vercel(Next.js 서버)이 환경별 S3 자격증명
 * (`S3_ENDPOINT`/`S3_REGION`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`)으로 Supabase Storage
 * S3 엔드포인트에 대한 presigned PUT URL 을 발급한다. 브라우저는 받은 URL 로 파일을
 * 직접 PUT 하므로 서버 함수 본문 용량 제한(Vercel ~4.5MB)을 우회한다.
 *
 * 소유 폴더(object key 의 첫 세그먼트)는 **검증된 Supabase 세션**에서 도출한다 —
 * 클라이언트가 임의 uid 를 주입해 타인 폴더로 업로드하지 못하게 한다. 백엔드
 * (`POST /leads`)도 Bearer 토큰의 user_id 로 owner-folder 를 한 번 더 검증한다.
 *
 * `/api/*` 는 next.config 가 FastAPI 로 rewrite 하므로 본 라우트는 `/leads` 하위에 둔다.
 */

import { PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { NextResponse, type NextRequest } from 'next/server';
import { buildLeadObjectPath, validateUploadRequest } from '@/lib/leads/upload-policy';
import { createRouteHandlerClient } from '@/lib/supabase/server';

// @aws-sdk 는 Node 런타임 필요(Edge 비호환).
export const runtime = 'nodejs';

const DEFAULT_BUCKET = 'lead-floorplans';
const PRESIGN_TTL_SECONDS = 300;

function jsonError(code: string, message: string, status: number): NextResponse {
  return NextResponse.json({ error: { code, message } }, { status });
}

function createS3Client(): S3Client {
  const endpoint = process.env.S3_ENDPOINT;
  const region = process.env.S3_REGION;
  const accessKeyId = process.env.S3_ACCESS_KEY;
  const secretAccessKey = process.env.S3_SECRET_KEY;
  if (!endpoint || !region || !accessKeyId || !secretAccessKey) {
    throw new Error('S3 자격증명(S3_ENDPOINT/S3_REGION/S3_ACCESS_KEY/S3_SECRET_KEY)이 설정되지 않았습니다.');
  }
  return new S3Client({
    endpoint,
    region,
    forcePathStyle: true, // Supabase Storage S3 호환 엔드포인트는 path-style 필요.
    credentials: { accessKeyId, secretAccessKey }
  });
}

export async function POST(request: NextRequest) {
  // 세션 쿠키 갱신을 누적할 단일 response. getUser 가 토큰을 회전하면 여기 Set-Cookie 가 쌓인다.
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
  const parsed = validateUploadRequest(body);
  if (!parsed.ok) {
    return jsonError('INVALID_UPLOAD', parsed.message, 422);
  }

  const bucket = process.env.LEAD_FLOORPLAN_BUCKET ?? DEFAULT_BUCKET;
  const objectPath = buildLeadObjectPath(user.id, parsed.fileName);

  let uploadUrl: string;
  try {
    uploadUrl = await getSignedUrl(
      createS3Client(),
      new PutObjectCommand({ Bucket: bucket, Key: objectPath, ContentType: parsed.contentType }),
      { expiresIn: PRESIGN_TTL_SECONDS }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : '업로드 URL 발급에 실패했습니다.';
    return jsonError('PRESIGN_FAILED', message, 500);
  }

  const json = NextResponse.json({ upload_url: uploadUrl, object_path: objectPath, bucket });
  // getUser 가 갱신한 세션 쿠키를 응답에 전달.
  for (const cookie of cookieResponse.cookies.getAll()) {
    json.cookies.set(cookie);
  }
  return json;
}
