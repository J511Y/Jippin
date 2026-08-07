/**
 * 업로드 도면 모아보기 데이터 로더 (CMP-DIRECT).
 *
 * 도면이 들어오는 곳은 두 갈래다:
 *  1) 상담 신청 첨부 — Supabase Storage `lead-floorplans` 버킷
 *     (consultation_lead_attachments, ADR-0007). signed URL 미리보기 가능.
 *  2) 사전검토 세션 업로드 — floorplan_assets (0008). 정본 버킷은 Supabase Storage
 *     `session-floorplans` 로, 상담 첨부와 같은 signed URL 패턴으로 미리보기한다.
 *     (floorplan_uploads 는 클라이언트가 쓰지 않는 dead 테이블 — 읽지 않는다.)
 */

import 'server-only';

import { deriveAssetFileName } from '@/lib/data/sessions';
import { createServiceRoleClient } from '@/lib/supabase/service-role';

export interface LeadAttachmentCard {
  id: string;
  lead_id: string;
  applicant_name: string | null;
  file_name: string | null;
  content_type: string | null;
  byte_size: number | null;
  created_at: string;
  signedUrl: string | null;
}

export interface SessionUploadCard {
  id: string;
  session_id: string;
  scan_status: string;
  /** object_key 에서 유도한 표시용 파일명. */
  file_name: string;
  content_type: string | null;
  byte_size: number | null;
  created_at: string;
  signedUrl: string | null;
}

export async function listLeadAttachmentCards(limit = 60): Promise<LeadAttachmentCard[]> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('consultation_lead_attachments')
    .select('id, lead_id, bucket, object_path, file_name, content_type, byte_size, created_at, consultation_leads(applicant_name)')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error || !data) return [];

  return Promise.all(
    data.map(async (row) => {
      const record = row as Record<string, unknown>;
      const lead = record.consultation_leads as { applicant_name?: string } | Array<{ applicant_name?: string }> | null;
      const applicantName = Array.isArray(lead)
        ? (lead[0]?.applicant_name ?? null)
        : (lead?.applicant_name ?? null);
      const { data: signed } = await supabase.storage
        .from(record.bucket as string)
        .createSignedUrl(record.object_path as string, 60 * 60);
      return {
        id: record.id as string,
        lead_id: record.lead_id as string,
        applicant_name: applicantName,
        file_name: (record.file_name as string | null) ?? null,
        content_type: (record.content_type as string | null) ?? null,
        byte_size: (record.byte_size as number | null) ?? null,
        created_at: record.created_at as string,
        signedUrl: signed?.signedUrl ?? null
      };
    })
  );
}

/** 미리보기(서명 URL)를 만들지 않는 스캔 상태 — API 세그멘테이션과 같은 경계.
 * infected/failed 오브젝트를 관리자 브라우저에 로드하지 않는다(메타데이터만 표시). */
export const PREVIEW_BLOCKED_SCAN_STATUSES = new Set(['infected', 'failed']);

export async function listSessionUploadCards(limit = 60): Promise<SessionUploadCard[]> {
  const supabase = createServiceRoleClient();
  // session_id 는 catalog 스코프 asset 에서 null — 세션 업로드 갤러리는 세션 귀속
  // 행만 다룬다(null 이 섞이면 session_id.slice() 렌더가 페이지를 깨뜨린다).
  const { data, error } = await supabase
    .from('floorplan_assets')
    .select('id, session_id, bucket, object_key, content_type, byte_size, scan_status, created_at')
    .not('session_id', 'is', null)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error || !data) return [];

  return Promise.all(
    data.map(async (row) => {
      const record = row as Record<string, unknown>;
      const scanStatus = record.scan_status as string;
      // 버킷은 행 메타데이터를 따른다(session-floorplans) — 서명 실패 시 미리보기 없이 렌더.
      const { data: signed } = PREVIEW_BLOCKED_SCAN_STATUSES.has(scanStatus)
        ? { data: null }
        : await supabase.storage
            .from(record.bucket as string)
            .createSignedUrl(record.object_key as string, 60 * 60);
      return {
        id: record.id as string,
        session_id: record.session_id as string,
        scan_status: scanStatus,
        file_name: deriveAssetFileName(record.object_key as string),
        content_type: (record.content_type as string | null) ?? null,
        byte_size: (record.byte_size as number | null) ?? null,
        created_at: record.created_at as string,
        signedUrl: signed?.signedUrl ?? null
      };
    })
  );
}
