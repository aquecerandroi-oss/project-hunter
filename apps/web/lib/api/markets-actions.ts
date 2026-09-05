"use server";

import { isApiError } from "@/lib/api-error";
import { listMarkets } from "@/lib/api/markets";
import { MARKET_SEARCH_MAX_LENGTH } from "@/lib/api/markets-search";
import { getServerSession } from "@/lib/server/auth";

export interface MarketSearchResult {
  exchange: string;
  symbol: string;
}

export interface MarketSearchOutcome {
  ok: boolean;
  results: MarketSearchResult[];
  reason?: string;
}

const SEARCH_LIMIT = 8;

/**
 * Server Action behind `components/layout/command-palette.tsx` (T1.5b joint
 * decision #7): a real `GET /api/v1/markets?q=...` call, not a filter over
 * whatever page happened to load client-side -- `lib/api/markets.ts` is
 * `"server-only"`, so a client component cannot call `listMarkets` directly
 * (ESLint boundary: `components/**` cannot import `@/lib/server/**`, and
 * this file's transitive `apiFetch` lives there). Still bounded to the
 * *monitored* universe the API tracks, never "every symbol that ever
 * existed" -- the palette's own copy says so.
 *
 * M7 (security): a Server Action is a public POST endpoint. `listMarkets`
 * used to be called unconditionally regardless of session -- `lib/server/
 * api.ts` only sets `Authorization` `if (session?.token)`, so an
 * unauthenticated caller still issued the outbound API request (which the
 * API then rejected). Fails closed HERE, before ever touching `listMarkets`,
 * using the same `getServerSession` helper `lib/server/api.ts` itself uses.
 */
export async function searchMarketsAction(q: string): Promise<MarketSearchOutcome> {
  const trimmed = q.trim();
  if (trimmed.length === 0) return { ok: true, results: [] };
  if (trimmed.length > MARKET_SEARCH_MAX_LENGTH) {
    return { ok: false, results: [], reason: "consulta muito longa" };
  }

  const session = await getServerSession();
  if (!session) return { ok: false, results: [], reason: "unauthenticated" };

  try {
    const page = await listMarkets({ q: trimmed, monitored: true, limit: SEARCH_LIMIT });
    return { ok: true, results: page.items.map((item) => ({ exchange: item.exchange, symbol: item.symbol })) };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, results: [], reason };
  }
}
