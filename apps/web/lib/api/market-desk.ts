import "server-only";

import { apiFetch } from "@/lib/server/api";

import { type DeskOut, marketDeskOrgBase } from "./market-desk-types";

export interface GetMarketDeskParams {
  since?: string;
  until?: string;
}

function deskQuery(params: GetMarketDeskParams): string {
  const search = new URLSearchParams();
  if (params.since !== undefined) search.set("since", params.since);
  if (params.until !== undefined) search.set("until", params.until);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/desk` (T4.82,
 * `routers/market_desk.py`) -- the `spot/1` desk's orders and positions for
 * this market. `"server-only"` like `lib/api/meme-desk.ts`; this confluence
 * screen has no write action at all (design §6, "Sem POST").
 */
export async function getMarketDesk(
  orgId: string,
  exchange: string,
  symbol: string,
  params: GetMarketDeskParams = {},
): Promise<DeskOut> {
  return apiFetch<DeskOut>(
    `${marketDeskOrgBase(orgId)}/${encodeURIComponent(exchange)}/${encodeURIComponent(symbol)}/desk${deskQuery(params)}`,
  );
}
