'use server';

import { revalidatePath } from 'next/cache';

import { apiBaseUrl } from '@/lib/api-base-url';
import { isAdminUser } from '@/lib/auth';
import { listAdminOptions } from '@/lib/data/leads';
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

export interface AssignResult extends ActionResult {
  /** 알림톡 발송 성공 여부 — undefined 면 발송을 시도하지 않음(배정 해제 등). */
  notified?: boolean;
  notifyError?: string;
}

async function requireAdminActor() {
  const supabase = await createServerComponentClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  if (!isAdminUser(user)) {
    throw new Error('관리자 권한이 필요합니다.');
  }
  // 백엔드 위임 호출(알림톡)용 access token — 검증은 백엔드가 JWKS 로 다시 한다.
  const {
    data: { session }
  } = await supabase.auth.getSession();
  return { user, accessToken: session?.access_token ?? null };
}

/**
 * 담당자 배정 알림톡 발송 — SOLAPI 자격증명은 backend 단독 보유이므로
 * apps/api `POST /leads/{id}/assignee-notification` 에 위임한다.
 */
async function sendAssigneeNotification(
  leadId: string,
  assigneeName: string,
  accessToken: string | null
): Promise<{ notified: boolean; notifyError?: string }> {
  if (!accessToken) {
    return { notified: false, notifyError: '세션 토큰을 찾을 수 없습니다.' };
  }
  const base = apiBaseUrl();
  if (!base) {
    return {
      notified: false,
      notifyError: 'API_BASE_URL 미설정 — 비프로덕션 환경에서는 알림톡을 발송하지 않습니다.'
    };
  }
  try {
    const res = await fetch(`${base}/leads/${leadId}/assignee-notification`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify({ assignee_name: assigneeName }),
      cache: 'no-store'
    });
    if (res.status === 202) {
      return { notified: true };
    }
    const body = (await res.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    return {
      notified: false,
      notifyError: body?.error?.message ?? `알림톡 발송 실패 (HTTP ${res.status})`
    };
  } catch {
    return { notified: false, notifyError: '알림톡 발송 요청에 실패했습니다.' };
  }
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

export async function assignLead(leadId: string, adminId: string | null): Promise<AssignResult> {
  const { accessToken } = await requireAdminActor();

  // 클라이언트가 보낸 adminId 를 신뢰하지 않는다 — service_role 로 쓰기 전에
  // admin_list_admins(app_metadata.role='admin') 목록과 대조하고, 알림톡의
  // 담당자명도 서버에서 같은 목록으로 도출한다.
  let assignee: { name: string; company: string } | null = null;
  if (adminId) {
    const admins = await listAdminOptions();
    const matched = admins?.find((admin) => admin.id === adminId) ?? null;
    if (!matched) {
      return { ok: false, error: '관리자 목록에 없는 사용자입니다.' };
    }
    assignee = matched;
  }

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

  // 배정(해제 아님)일 때만 고객에게 담당자 배정 알림톡을 발송한다.
  // 배정 자체는 이미 저장됐으므로 발송 실패가 배정을 되돌리지 않는다.
  if (assignee) {
    // 알림톡 #{담당자명} = "{회사명} {이름}" (콘솔 표시는 이름만 — labels SSOT).
    const alimtalkName = [assignee.company, assignee.name].filter(Boolean).join(' ');
    const result = await sendAssigneeNotification(leadId, alimtalkName, accessToken);
    return { ok: true, ...result };
  }
  return { ok: true };
}

export async function addLeadComment(leadId: string, body: string): Promise<ActionResult> {
  const { user: actor } = await requireAdminActor();

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
