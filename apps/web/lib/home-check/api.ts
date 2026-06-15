/**
 * 우리집 체크 백엔드 API 호출 (CMP-DIRECT, ADR-0008).
 *
 * `apiClient`(axios)가 `lib/auth-token` 의 Bearer 토큰을 자동 부착한다. 따라서 잡 생성/조회
 * 전에 `ensureAnonymousSession()`(leads 패턴)으로 세션을 보장해야 한다 — 잡은 익명도 허용한다.
 *
 * 응답/리포트 타입은 contracts 정본을 그대로 쓴다(직접 재정의 금지). 웹은 contracts 의 TS
 * 바인딩을 `@contracts/*` 경로 별칭(tsconfig)으로 import 한다 — 백엔드는 동일 스키마의
 * Pydantic 모델을 쓴다.
 */

import { apiClient } from '@/lib/api-client';
import type { HomeCheckJob } from '@contracts/home-check';

export type { HomeCheckJob } from '@contracts/home-check';

export interface CreateHomeCheckPayload {
  road_addr: string;
  jibun_addr?: string | null;
  dong: string;
  ho: string;
}

export interface ContinueHomeCheckPayload {
  dong?: string;
  ho?: string;
  secure_no?: string;
}

/**
 * 잡 생성. 백엔드는 즉시 202 + jobId(status=pending|querying)로 응답하고, 실제 조회는
 * 백그라운드에서 진행한다 — 호출부는 `getHomeCheck` 로 폴링한다.
 */
export async function createHomeCheck(payload: CreateHomeCheckPayload): Promise<HomeCheckJob> {
  const response = await apiClient.post<HomeCheckJob>('/home-check', payload);
  return response.data;
}

/** 잡 단건 조회(폴링). status=completed 면 `report`, needs_input 면 `needs_input`, failed 면 `error` 가 채워진다. */
export async function getHomeCheck(id: string): Promise<HomeCheckJob> {
  const response = await apiClient.get<HomeCheckJob>(`/home-check/${id}`);
  return response.data;
}

/** needs_input 폴백 재개(동·호 재선택 또는 보안문자 입력). */
export async function continueHomeCheck(
  id: string,
  payload: ContinueHomeCheckPayload
): Promise<HomeCheckJob> {
  const response = await apiClient.post<HomeCheckJob>(`/home-check/${id}/continue`, payload);
  return response.data;
}

// 내 우리집 체크 이력(`/home-check/mine`)은 로그인 필수이고 하드 리프레시 후 apiClient
// 메모리 토큰이 비어있을 수 있어, Supabase 세션 토큰을 명시적으로 싣는
// `lib/auth/account-api.ts::listMyHomeChecks` 를 사용한다(listMyLeads 와 동일 경로).
