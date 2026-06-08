import { type ApiError, parseApiError } from './error';

/**
 * 에러 → 사용자 노출 카피 매핑.
 *
 * `error.tsx`(라우트 경계)와 전역 토스트(query-client)가 동일한 한국어 문구를 쓰도록
 * 한 곳에서 정의한다. React/Mantine 의존이 없는 순수 함수이므로 `global-error` 등
 * 어디서든 재사용할 수 있다.
 *
 * `kind` 는 호출부가 어떤 CTA(로그인/재시도/홈)를 노출할지 결정하는 데 쓴다.
 */

export type ErrorKind = 'auth' | 'notfound' | 'network' | 'server' | 'client';

export type ErrorContent = {
  /** 정규화된 원본 에러 (status/code/requestId 접근용). */
  apiError: ApiError;
  kind: ErrorKind;
  title: string;
  message: string;
  /** reset()/refetch 로 복구 시도가 의미 있는 에러인지. */
  retryable: boolean;
};

function classify(status: number | undefined, code: string): ErrorKind {
  if (status === 401 || status === 403) return 'auth';
  if (status === 404) return 'notfound';
  if (
    code === 'NETWORK_ERROR' ||
    code === 'NETWORK_TIMEOUT' ||
    status === 408 ||
    status === 504
  ) {
    return 'network';
  }
  if (status !== undefined && status >= 500) return 'server';
  return 'client';
}

export function resolveErrorContent(error: unknown): ErrorContent {
  const apiError = parseApiError(error);
  const { status, code } = apiError;
  const kind = classify(status, code);

  switch (true) {
    case status === 401:
      return {
        apiError,
        kind,
        title: '로그인이 필요해요',
        message: '세션이 만료되었거나 로그인이 필요합니다. 다시 로그인해 주세요.',
        retryable: false
      };
    case status === 403:
      return {
        apiError,
        kind,
        title: '접근 권한이 없어요',
        message: '이 페이지나 작업에 대한 권한이 없습니다. 계정을 확인해 주세요.',
        retryable: false
      };
    case status === 404:
      return {
        apiError,
        kind,
        title: '찾을 수 없어요',
        message: '요청하신 페이지나 데이터를 찾을 수 없습니다.',
        retryable: false
      };
    case kind === 'network':
      return {
        apiError,
        kind,
        title: '네트워크 연결을 확인해 주세요',
        message: '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.',
        retryable: true
      };
    case status === 409:
      return {
        apiError,
        kind,
        title: '요청이 충돌했어요',
        message: '다른 작업과 충돌이 발생했습니다. 새로고침 후 다시 시도해 주세요.',
        retryable: true
      };
    case status === 422:
      return {
        apiError,
        kind,
        title: '입력값을 확인해 주세요',
        message: apiError.message || '요청 내용에 문제가 있습니다. 입력값을 다시 확인해 주세요.',
        retryable: false
      };
    case status === 429:
      return {
        apiError,
        kind,
        title: '요청이 너무 많아요',
        message: '잠시 후 다시 시도해 주세요.',
        retryable: true
      };
    case kind === 'server':
      return {
        apiError,
        kind,
        title: '일시적인 오류가 발생했어요',
        message: '서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.',
        retryable: true
      };
    default:
      return {
        apiError,
        kind,
        title: '문제가 발생했어요',
        message: '예기치 못한 오류가 발생했습니다. 다시 시도해 주세요.',
        retryable: true
      };
  }
}
