import "server-only";

import { apiFetch } from "@/lib/server/api";

import { manualOrderListPageSchema, manualOrdersPath, type ManualOrderListPage } from "./manual-orders-types";

export interface ListManualOrdersParams {
  limit?: number;
  cursor?: string;
}

function listQuery(params: ListManualOrdersParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET .../order-requests` (T3.72/T3.68/T3.72c) -- the wallet's manual paper
 * requests, newest first. Read-only and `"server-only"` like
 * `lib/api/portfolio.ts`; the write half (`POST`, plus the single-request
 * poll) is a Server Action (`manual-orders-actions.ts`), never this file --
 * a client component cannot import this module (ESLint boundary), and a
 * mutation triggered from a form has no business being a plain SSR read
 * anyway.
 *
 * `.parse()`s the response before this app trusts it: there is still no
 * generated OpenAPI type for this router (`manual-orders-types.ts`'s own
 * docstring), so a real shape drift must surface as an honest parse failure
 * here, never a silently wrong render.
 */
export async function listManualOrders(
  orgId: string,
  portfolioId: string,
  params: ListManualOrdersParams = {},
): Promise<ManualOrderListPage> {
  const raw = await apiFetch<unknown>(`${manualOrdersPath(orgId, portfolioId)}${listQuery(params)}`);
  return manualOrderListPageSchema.parse(raw);
}
