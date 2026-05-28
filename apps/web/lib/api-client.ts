import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig
} from 'axios';
import { clearAccessToken, getAccessToken, setAccessToken } from '@/lib/auth-token';

/**
 * 백엔드(`apps/api`) 호출 클라이언트.
 *
 * 정책 (CMP-529 / ADR-0001 §2):
 *   1) Authorization 자동 주입: `lib/auth-token` 메모리 저장소에서 Bearer 토큰을 부착.
 *   2) 401 처리: 단일 refresh 큐로 직렬화하여 동시 갱신 폭주를 막고, 갱신 성공 시 원 요청 재시도.
 *   3) refresh 자체가 401 또는 네트워크 실패 → 토큰 폐기 후 호출부에 에러 propagate.
 *   4) refresh 엔드포인트는 HttpOnly 쿠키 기반(`withCredentials: true`)으로 본 클라이언트가
 *      별도 토큰 본문을 들고 다니지 않는다.
 *
 * 본 모듈은 **클라이언트 사이드 호출 전용** 이다.
 *   - 서버 컴포넌트/Route Handler 의 백엔드 호출은 별도 server-fetch 헬퍼에서 다룬다 (후속 이슈).
 *   - 그 이유: RSC 환경의 토큰 컨텍스트는 쿠키/헤더 기반이라 인터셉터 모델이 부적합.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const REFRESH_PATH = '/auth/refresh';

type RetriableRequest = InternalAxiosRequestConfig & { _retry?: boolean };

let refreshInflight: Promise<string | null> | null = null;

async function performRefresh(client: AxiosInstance): Promise<string | null> {
  try {
    const response = await client.post<{ access_token: string }>(
      REFRESH_PATH,
      {},
      { withCredentials: true, _retry: true } as AxiosRequestConfig & { _retry: boolean }
    );
    const next = response.data?.access_token ?? null;
    setAccessToken(next);
    return next;
  } catch {
    clearAccessToken();
    return null;
  }
}

export function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: API_BASE_URL,
    timeout: 15_000,
    withCredentials: true,
    headers: {
      Accept: 'application/json'
    }
  });

  client.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token && !(config as RetriableRequest)._retry) {
      config.headers.set('Authorization', `Bearer ${token}`);
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (!axios.isAxiosError(error) || !error.response || !error.config) {
        return Promise.reject(error);
      }

      const original = error.config as RetriableRequest;
      const status = error.response.status;

      const isRefreshCall = original.url?.endsWith(REFRESH_PATH);
      if (status !== 401 || original._retry || isRefreshCall) {
        return Promise.reject(error);
      }

      original._retry = true;
      refreshInflight ??= performRefresh(client).finally(() => {
        refreshInflight = null;
      });

      const nextToken = await refreshInflight;
      if (!nextToken) {
        return Promise.reject(error);
      }

      original.headers.set('Authorization', `Bearer ${nextToken}`);
      return client.request(original);
    }
  );

  return client;
}

export const apiClient = createApiClient();
