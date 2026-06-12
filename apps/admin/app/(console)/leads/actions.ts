'use server';

import { revalidatePath } from 'next/cache';

import { isAdminUser } from '@/lib/auth';
import { LEAD_STATUSES, type LeadStatus } from '@/lib/labels';
import { createServerComponentClient } from '@/lib/supabase/server';
import { createServiceRoleClient } from '@/lib/supabase/service-role';

/**
 * 상담 리드 변경 서버 액션 (CMP-DIRECT).
 *
 * service_role 사용 전 액션마다 세션 사용자의 admin 클레임을 재검증한다
 * (proxy 게이트만 믿지 않는다 — service-role.ts docstring 봉인).
 */

interface ActionResult {
  ok: boolean;
  error?: string;
}

async function requireAdminActor() {
  const supabase = await createServerComponentClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  if (!isAdminUser(user)) {
    throw new Error('관리자 권한이 필요합니다.');
  }
  return user;
}

function revalidateLead(leadId: string): void {
  revalidatePath('/leads');
  revalidatePath(`/leads/${leadId}`);
}

export async function updateLeadStatus(leadId: string, status: string): Promise<ActionResult> {
  await requireAdminActor();
  if (!LEAD_STATUSES.includes(status as LeadStatus)) {
    return { ok: false, error: '허용되지 않은 상태입니다.' };
  }

  const supabase = createServiceRoleClient();
  const { error } = await supabase
    .from('consultation_leads')
    .update({ status, updated_at: new Date().toISOString() })
    .eq('id', leadId);
  if (error) {
    return { ok: false, error: `상태 변경 실패: ${error.message}` };
  }
  revalidateLead(leadId);
  return { ok: true };
}

export async function assignLead(leadId: string, adminId: string | null): Promise<ActionResult> {
  await requireAdminActor();

  const supabase = createServiceRoleClient();
  const { error } = await supabase
    .from('consultation_leads')
    .update({
      assigned_admin_id: adminId,
      assigned_at: adminId ? new Date().toISOString() : null,
      updated_at: new Date().toISOString()
    })
    .eq('id', leadId);
  if (error) {
    return { ok: false, error: `담당자 배정 실패: ${error.message}` };
  }
  revalidateLead(leadId);
  return { ok: true };
}

export async function addLeadComment(leadId: string, body: string): Promise<ActionResult> {
  const actor = await requireAdminActor();

  const trimmed = body.trim();
  if (!trimmed) {
    return { ok: false, error: '댓글 내용을 입력해 주세요.' };
  }
  if (trimmed.length > 4000) {
    return { ok: false, error: '댓글은 4000자 이내로 입력해 주세요.' };
  }

  const supabase = createServiceRoleClient();
  const { error } = await supabase.from('consultation_lead_comments').insert({
    lead_id: leadId,
    author_id: actor.id,
    author_email: actor.email ?? 'unknown',
    body: trimmed
  });
  if (error) {
    return { ok: false, error: `댓글 작성 실패: ${error.message}` };
  }
  revalidateLead(leadId);
  return { ok: true };
}
