import axios from 'axios';

/**
 * 백엔드 표준 에러 응답 파서 (AGENTS.md §4.5).
 *
 *   {
 *     "error": {
 *       "code": "INSUFFICIENT_DATA",
 *       "message": "...",
 *       "request_id": "...",
 *       "timestamp": "..."
 *     }
 *   }
 *
 * 본 모듈은 axios 에러를 받아 위 포맷으로 정규화한다. 네트워크/타임아웃/취소 등
 * 비-HTTP 에러는 합리적인 합성 코드로 대체.
 */

export type ApiErrorShape = {
  code: string;
  message: string;
  requestId?: string;
  timestamp?: string;
  status?: number;
  cause?: unknown;
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | undefined;
  readonly requestId: string | undefined;
  readonly timestamp: string | undefined;

  constructor(shape: ApiErrorShape) {
    super(shape.message);
    this.name = 'ApiError';
    this.code = shape.code;
    this.status = shape.status;
    this.requestId = shape.requestId;
    this.timestamp = shape.timestamp;
    if (shape.cause !== undefined) {
      (this as { cause?: unknown }).cause = shape.cause;
    }
  }
}

type RawErrorBody = {
  error?: {
    code?: unknown;
    message?: unknown;
    request_id?: unknown;
    timestamp?: unknown;
  };
};

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

export function parseApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isAxiosError(error)) {
    if (error.code === 'ECONNABORTED') {
      return new ApiError({
        code: 'NETWORK_TIMEOUT',
        message: error.message || '요청이 시간 초과되었습니다.',
        cause: error
      });
    }
    if (!error.response) {
      return new ApiError({
        code: 'NETWORK_ERROR',
        message: error.message || '네트워크에 연결할 수 없습니다.',
        cause: error
      });
    }
    const body = error.response.data as RawErrorBody | undefined;
    const inner = body?.error;
    return new ApiError({
      code: asString(inner?.code) ?? `HTTP_${error.response.status}`,
      message: asString(inner?.message) ?? error.message,
      requestId: asString(inner?.request_id),
      timestamp: asString(inner?.timestamp),
      status: error.response.status,
      cause: error
    });
  }

  if (error instanceof Error) {
    return new ApiError({ code: 'UNKNOWN_ERROR', message: error.message, cause: error });
  }

  return new ApiError({ code: 'UNKNOWN_ERROR', message: String(error) });
}

/**
 * 사용자에게 노출해도 안전한 한국어 메시지로 정규화한다.
 *
 * 백엔드 원문(`error.message`)은 내부 구현(예: "Supabase bearer token is required.")을
 * 드러내고 영어라 그대로 화면에 띄우면 안 된다(#no-raw-error-leak). 인증/권한/없음만
 * 의미 단위로 안내하고, 나머지는 호출부가 준 `fallback` 으로 일반화한다.
 *
 * 소유권 가드상 403/404 는 "없음"과 "권한 없음"을 구분하지 않는다(백엔드가 열거 누수
 * 방지로 둘 다 같은 코드로 합침) — 메시지도 합쳐 자원 존재 여부를 흘리지 않는다.
 */
export function friendlyApiMessage(
  error: unknown,
  fallback = '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.'
): string {
  const status = parseApiError(error).status;
  if (status === 401) return '로그인이 필요해요. 본인 계정으로 로그인 후 다시 시도해 주세요.';
  if (status === 403 || status === 404) return '찾을 수 없거나 접근 권한이 없어요.';
  return fallback;
}
