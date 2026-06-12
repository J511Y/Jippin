/**
 * 도메인 enum → 한국어 라벨 SSOT (CMP-DIRECT).
 * 값 자체는 supabase/migrations 0008/0009 의 check 제약이 정본이다.
 */

export const LEAD_STATUS_LABELS: Record<string, string> = {
  new: '신규',
  contacted: '연락 완료',
  in_progress: '진행중',
  closed: '종료',
  spam: '스팸'
};

export const LEAD_STATUSES = ['new', 'contacted', 'in_progress', 'closed', 'spam'] as const;
export type LeadStatus = (typeof LEAD_STATUSES)[number];

/** Vercel 풍 모노톤 — 상태만 점 컬러로 구분한다. */
export const LEAD_STATUS_DOT_CLASS: Record<string, string> = {
  new: 'bg-blue-500',
  contacted: 'bg-amber-500',
  in_progress: 'bg-violet-500',
  closed: 'bg-emerald-500',
  spam: 'bg-zinc-400'
};

export const SESSION_STATUS_LABELS: Record<string, string> = {
  draft: '초안',
  address_ready: '주소 입력',
  floorplan_selected: '도면 선택',
  analyzing: '분석중',
  awaiting_overlay: '오버레이 대기',
  collecting_info: '정보 수집',
  ready_for_rule: '판정 대기',
  report_ready: '리포트 완료',
  handoff: '상담 전환',
  expired: '만료',
  deleted: '삭제'
};

export const APPLICANT_KIND_LABELS: Record<string, string> = {
  individual: '개인',
  company: '법인/사업자'
};

export const OWNERSHIP_STATUS_LABELS: Record<string, string> = {
  in_transaction: '거래 진행중',
  owner: '소유자'
};

export const INFLOW_SOURCE_LABELS: Record<string, string> = {
  naver_search: '네이버 검색',
  blog: '블로그',
  acquaintance: '지인 소개',
  cafe: '카페',
  etc: '기타'
};

export const SOURCE_FORM_LABELS: Record<string, string> = {
  main_page: '메인 페이지(간편)',
  lead_page: '상담 신청 페이지'
};

export const UPLOAD_STATUS_LABELS: Record<string, string> = {
  uploaded: '업로드됨',
  scan_pending: '스캔 대기',
  scan_failed: '스캔 실패',
  ready_for_processing: '처리 대기',
  processing: '처리중',
  processed: '처리 완료',
  rejected: '거부됨',
  promoted_to_catalog: '카탈로그 승격'
};

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' });
}
