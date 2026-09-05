import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { Candle, MarketDetail, MarketsListResponse } from "./types";

export interface ListMarketsParams {
  exchange?: string;
  q?: string;
  monitored?: boolean;
  limit?: number;
  cursor?: string;
}

function listQuery(params: ListMarketsParams): string {
  const search = new URLSearchParams();
  if (params.exchange !== undefined) search.set("exchange", params.exchange);
  if (params.q !== undefined) search.set("q", params.q);
  if (params.monitored !== undefined) search.set("monitored", String(params.monitored));
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/markets` (apps/api/hunter_api/routers/markets.py, T1.4) -- the monitored universe with hot-state pricing. */
export async function listMarkets(params: ListMarketsParams = {}): Promise<MarketsListResponse> {
  return apiFetch<MarketsListResponse>(`/api/v1/markets${listQuery(params)}`);
}

/** Path segments come straight from the Next.js dynamic route, already
 * URL-decoded by the router, so they are fully caller-controlled. Without
 * escaping, `symbol = "x/../../../metrics"` is normalized by WHATWG URL
 * parsing *before* the request leaves the server, and `apiFetch` sends it to
 * `API_URL` -- the internal service address the browser is deliberately not
 * meant to reach (see `lib/server/api.ts`), carrying the caller's own bearer
 * token. `#` and `?` are injectable the same way. Found by the security
 * review of the T1.6b proof, 2026-09-05; non-ASCII symbols (Binance lists
 * perpetuals written in Chinese) made this route's escaping load-bearing. */
function marketPath(exchange: string, symbol: string): string {
  return `/api/v1/markets/${encodeURIComponent(exchange)}/${encodeURIComponent(symbol)}`;
}

/** `GET /api/v1/markets/{exchange}/{symbol}` -- row + top-20 book + recent trades. 404 when the pair doesn't exist. */
export async function getMarket(exchange: string, symbol: string): Promise<MarketDetail> {
  return apiFetch<MarketDetail>(marketPath(exchange, symbol));
}

export interface CandlesParams {
  timeframe?: string;
  limit?: number;
}

function candlesQuery(params: CandlesParams): string {
  const search = new URLSearchParams();
  if (params.timeframe !== undefined) search.set("timeframe", params.timeframe);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/markets/{exchange}/{symbol}/candles` -- a bare array (`schemas/markets.py`'s `list[CandleOut]`), default `timeframe=1m`, `limit=500`, final candles only. */
export async function getCandles(exchange: string, symbol: string, params: CandlesParams = {}): Promise<Candle[]> {
  return apiFetch<Candle[]>(`${marketPath(exchange, symbol)}/candles${candlesQuery(params)}`);
}
