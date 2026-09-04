import "server-only";

import { ApiError, type ApiErrorBody } from "@/lib/api-error";
import { logger } from "@/lib/logger";
import { getServerSession } from "@/lib/server/auth";

async function buildHeaders(init: RequestInit): Promise<Headers> {
  const session = await getServerSession();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (session?.token) headers.set("Authorization", `Bearer ${session.token}`);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

async function readErrorBody(response: Response, isJson: boolean, payload: unknown): Promise<ApiErrorBody> {
  if (isJson && payload !== null && typeof payload === "object") {
    return payload as ApiErrorBody;
  }
  return { type: "about:blank", title: response.statusText, status: response.status };
}

/**
 * Server-only fetch wrapper for `apps/api` (docs/ARCHITECTURE.md §9): adds
 * the Clerk bearer token and a request id, and turns a non-2xx
 * `application/problem+json` body into an `ApiError`. Only ever call this
 * from Server Components / route handlers -- `import "server-only"` plus
 * the ESLint boundary rules stop `components/**`/`hooks/**` from importing
 * it directly.
 *
 * `API_URL` (not `NEXT_PUBLIC_API_URL`) on purpose: this call happens on the
 * server, so the internal/service URL is used, never the public one meant
 * for the browser.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const baseUrl = process.env.API_URL;
  if (!baseUrl) throw new Error("API_URL is not configured");

  const headers = await buildHeaders(init);
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;

  const isJson = (response.headers.get("content-type") ?? "").includes("json");
  const payload: unknown = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const body = await readErrorBody(response, isJson, payload);
    logger.error("api_request_failed", { path, status: response.status, type: body.type });
    throw new ApiError(body);
  }

  return payload as T;
}
