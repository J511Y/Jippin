import { notifications } from '@mantine/notifications';
import {
  MutationCache,
  QueryCache,
  QueryClient,
  defaultShouldDehydrateQuery,
  isServer
} from '@tanstack/react-query';
import { resolveErrorContent } from '@/lib/api/error-content';

/**
 * TanStack Query SSR-safe 팩토리.
 *
 * - 서버에서는 매 요청마다 새 QueryClient를 만들어야 캐시 누수가 없다.
 * - 브라우저는 React tree 재구성 시 동일 인스턴스를 재사용 (Strict Mode/Fast Refresh 대응).
 * - dehydrate 정책: pending 상태도 직렬화하여 streaming SSR 폴백 대응.
 *
 * 참조: https://tanstack.com/query/v5/docs/framework/react/guides/advanced-ssr
 */

/** axios(`error.response.status`) / ApiError(`error.status`) 양쪽 형태에서 HTTP status 추출. */
function getErrorStatus(error: unknown): number | undefined {
  const e = error as { status?: number; response?: { status?: number } } | null;
  return e?.status ?? e?.response?.status;
}

/** 전역 에러 토스트. 클라이언트에서만 노출한다. */
function showErrorToast(error: unknown): void {
  if (isServer) return;
  const { title, message } = resolveErrorContent(error);
  notifications.show({ color: 'red', title, message });
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    // 백그라운드 refetch 실패(이미 캐시 데이터가 있어 error 경계가 안 뜨는 경우)만 토스트.
    // 최초 로드 실패는 컴포넌트/`error.tsx` 가 처리하므로 중복 노출을 피한다(TkDodo 패턴).
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.state.data !== undefined) showErrorToast(error);
      }
    }),
    // mutation 은 보통 error 경계가 없으므로 항상 토스트.
    // 단, 개별 mutation 이 자체 onError 를 정의하면 그 의도를 존중해 전역 토스트를 건너뛴다.
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        if (mutation.options.onError) return;
        showErrorToast(error);
      }
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (failureCount >= 2) return false;
          const status = getErrorStatus(error);
          if (status && status >= 400 && status < 500) return false;
          return true;
        }
      },
      dehydrate: {
        shouldDehydrateQuery: (query) =>
          defaultShouldDehydrateQuery(query) || query.state.status === 'pending'
      }
    }
  });
}

let browserQueryClient: QueryClient | undefined;

export function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient();
  }
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}
