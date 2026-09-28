import "server-only";

import { apiFetch } from "@/lib/server/api";

import { marketDeskOrgBase } from "./market-desk-types";
import type { MarketEventsOut } from "./market-events-types";

export interface GetMarketEventsParams {
  since?: string;
  until?: string;
}

function eventsQuery(params: GetMarketEventsParams): string {
  const search = new URLSearchParams();
  if (params.since !== undefined) search.set("since", params.since);
  if (params.until !== undefined) search.set("until", params.until);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/events` (T4.82,
 * `routers/market_desk.py`) -- headlines recorded for this market, newest
 * first. An empty list means "nothing recorded in this period", never "this
 * market has no news" (today's only source is the plantão's own hand,
 * design §8).
 */
export async function getMarketEvents(
  orgId: string,
  exchange: string,
  symbol: string,
  params: GetMarketEventsParams = {},
): Promise<MarketEventsOut> {
  return apiFetch<MarketEventsOut>(
    `${marketDeskOrgBase(orgId)}/${encodeURIComponent(exchange)}/${encodeURIComponent(symbol)}/events${eventsQuery(params)}`,
  );
}
