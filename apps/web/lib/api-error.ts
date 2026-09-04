/**
 * Client-safe error shape shared by `lib/server/api.ts` and any component
 * that renders API failures. The API responds with RFC 9457
 * (`application/problem+json`) per docs/ARCHITECTURE.md §9.
 */
export interface ApiErrorBody {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly type: string;
  readonly detail: string | undefined;
  readonly instance: string | undefined;

  constructor(body: ApiErrorBody) {
    super(body.title || `API error ${body.status}`);
    this.name = "ApiError";
    this.status = body.status;
    this.type = body.type;
    this.detail = body.detail;
    this.instance = body.instance;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
