/**
 * 상담 리드 백엔드 API 호출 (CMP-DIRECT).
 *
 * `apiClient`(axios)가 `lib/auth-token` 의 Bearer 토큰을 자동 부착한다. 따라서
 * `createLead` 호출 전에 `ensureAnonymousSession()` 으로 세션을 보장해야 한다.
 * 주소 검색은 공개 프록시라 토큰이 없어도 동작한다.
 */

import { apiClient } from '@/lib/api-client';
import type { UploadedAttachment } from './upload';

// 'property_check' = 우리집 체크(ADR-0008) 결과에서 인입된 상담. DB CHECK · contracts ·
// 본 유니온 3곳이 함께 변경된다(백엔드가 enum 반영을 담당).
export type SourceForm = 'main_page' | 'lead_page' | 'property_check';
export type ApplicantKind = 'individual' | 'company';
export type OwnershipStatus = 'in_transaction' | 'owner';
export type InflowSource = 'naver_search' | 'blog' | 'acquaintance' | 'cafe' | 'etc';

export interface LeadPayload {
  source_form: SourceForm;
  applicant_kind: ApplicantKind;
  applicant_name: string;
  applicant_phone: string;
  road_addr_part1?: string | null;
  road_addr_part2?: string | null;
  road_addr_detail?: string | null;
  expansion_location?: string | null;
  ownership_status?: OwnershipStatus | null;
  construction_start_date?: string | null;
  construction_end_date?: string | null;
  inflow_source?: InflowSource | null;
  message?: string | null;
  /** 우리집 체크 인입이면 원천 잡 id — 백엔드가 home_checks.consultation_lead_id 를 채운다. */
  home_check_id?: string | null;
  attachments?: UploadedAttachment[];
}

export interface LeadResponse {
  id: string;
  source_form: SourceForm;
  status: string;
  created_at: string;
}

export async function createLead(payload: LeadPayload): Promise<LeadResponse> {
  const response = await apiClient.post<LeadResponse>('/leads', payload);
  return response.data;
}

export interface AddressItem {
  road_addr: string;
  road_addr_part1: string;
  road_addr_part2: string;
  jibun_addr: string | null;
  zip_no: string | null;
  bd_nm: string | null;
  si_nm: string | null;
  sgg_nm: string | null;
  emd_nm: string | null;
}

export interface AddressSearchResult {
  total_count: number;
  page: number;
  per_page: number;
  items: AddressItem[];
}

export async function searchAddress(keyword: string, page = 1): Promise<AddressSearchResult> {
  const response = await apiClient.get<AddressSearchResult>('/leads/address/search', {
    params: { keyword, page }
  });
  return response.data;
}
