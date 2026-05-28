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
