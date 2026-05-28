import {
  QueryClient,
  defaultShouldDehydrateQuery,
  isServer
} from '@tanstack/react-query';

/**
 * TanStack Query SSR-safe 팩토리.
 *
 * - 서버에서는 매 요청마다 새 QueryClient를 만들어야 캐시 누수가 없다.
 * - 브라우저는 React tree 재구성 시 동일 인스턴스를 재사용 (Strict Mode/Fast Refresh 대응).
 * - dehydrate 정책: pending 상태도 직렬화하여 streaming SSR 폴백 대응.
 *
 * 참조: https://tanstack.com/query/v5/docs/framework/react/guides/advanced-ssr
 */

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (failureCount >= 2) return false;
          const status = (error as { response?: { status?: number } })?.response?.status;
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
