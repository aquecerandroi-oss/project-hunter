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
 * One executable SPOT candidate for the "Nova ordem paper" market picker
 * (T3.72): the 50M floor (`min_liquidity_usd_24h`, docs/RISK_ENGINE.md §2) is
 * shown as a real, computed fact from `quote_volume_24h` -- never a second
 * source of truth for the universe decision itself, which stays
 * `is_monitored` (D12's exit hysteresis can leave a monitored market briefly
 * under 50M; this label says so rather than contradicting `is_monitored`).
 */
export interface SpotMarketOption {
  id: string;
  exchange: string;
  symbol: string;
  status: string;
  is_monitored: boolean;
  quote_asset: string | null;
  last_price: string | null;
  volume_24h: string | null;
}

export interface SpotMarketSearchOutcome {
  ok: boolean;
  results: SpotMarketOption[];
  reason?: string;
}

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

/**
 * Server Action behind `manual-order-market-field.tsx`'s SPOT picker
 * (T3.72): `?market_type=spot` (`routers/markets.py`, T3.0c) -- the tradable
 * spot universe, never the perpetual default this file's other search
 * already uses. Same fail-closed session gate and query-length bound as
 * `searchMarketsAction` above; not restricted to `monitored: true` on
 * purpose -- an unmonitored/status!=active row still needs to render (and be
 * refused with a real reason) rather than silently vanish from the picker.
 */
export async function searchSpotMarketsAction(q: string): Promise<SpotMarketSearchOutcome> {
  const trimmed = q.trim();
  if (trimmed.length === 0) return { ok: true, results: [] };
  if (trimmed.length > MARKET_SEARCH_MAX_LENGTH) {
    return { ok: false, results: [], reason: "consulta muito longa" };
  }

  const session = await getServerSession();
  if (!session) return { ok: false, results: [], reason: "unauthenticated" };

  try {
    const page = await listMarkets({ q: trimmed, marketType: "spot", limit: SEARCH_LIMIT });
    return {
      ok: true,
      results: page.items.map((item) => ({
        id: item.id,
        exchange: item.exchange,
        symbol: item.symbol,
        status: item.status,
        is_monitored: item.is_monitored,
        quote_asset: item.quote_asset ?? null,
        last_price: item.last_price ?? null,
        volume_24h: item.volume_24h ?? null,
      })),
    };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, results: [], reason };
  }
}
