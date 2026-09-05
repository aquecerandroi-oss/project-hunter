import "server-only";

import type { Problem } from "@hunter/shared-types";
import type { components } from "@hunter/shared-types/api";

import { ApiError } from "@/lib/api-error";

/**
 * Aliases onto the OpenAPI-generated `components["schemas"]` (T09 -- see
 * `infra/scripts/dump_openapi.py` and root `pnpm gen:types`). Every response
 * shape a Server Component or Server Action needs is named here once so
 * call sites read `OrganizationOut` instead of the generated path.
 */
export type OrganizationOut = components["schemas"]["OrganizationOut"];
export type OrganizationCreated = components["schemas"]["OrganizationCreated"];
export type WorkspaceOut = components["schemas"]["WorkspaceOut"];
export type MemberOut = components["schemas"]["MemberOut"];
export type InvitationOut = components["schemas"]["InvitationOut"];
export type InvitationCreated = components["schemas"]["InvitationCreated"];
export type MeOut = components["schemas"]["MeOut"];
export type MembershipOut = components["schemas"]["MembershipOut"];
export type OnboardingState = components["schemas"]["OnboardingState"];
export type AuditEntryOut = components["schemas"]["AuditEntryOut"];
export type OrganizationRole = components["schemas"]["OrganizationRole"];
export type WorkspaceObjective = components["schemas"]["WorkspaceObjective"];
export type RiskPreset = components["schemas"]["RiskPreset"];

export type Page<T> = { items: T[]; next_cursor?: string | null };
export type ListParams = { limit?: number; cursor?: string };

/**
 * `/ready` and `/api/v1/system/info` (apps/api/hunter_api/health.py) return
 * plain dicts, not a Pydantic `response_model`, so the generated OpenAPI
 * types can't describe their shape (see the module docstring below for why
 * -- `dump_openapi.py` can't fabricate what the API itself doesn't declare).
 * These mirror `health.py`'s actual return values by hand.
 */
export interface ReadyStatus {
  database: boolean;
  redis: boolean;
  database_detail?: string;
  redis_detail?: string;
}

export interface SystemInfo {
  environment: string;
  version: string;
  git_sha: string;
  features: {
    enable_live_trading: boolean;
    enable_social_intelligence: boolean;
    enable_onchain: boolean;
    enable_stripe: boolean;
    enable_llm_analysis: boolean;
    enable_arena: boolean;
    enable_backtests: boolean;
  };
}

/**
 * Every mutation goes through a Server Action shaped like this instead of
 * throwing to the client -- a form can render `problem.detail` without a
 * try/catch, and a thrown `ApiError` never crosses the server/client
 * boundary (Next.js would otherwise turn it into an opaque digest).
 */
export type ActionResult<T = undefined> = { ok: true; data: T } | { ok: false; problem: Problem };

export function actionOk<T>(data: T): ActionResult<T> {
  return { ok: true, data };
}

export function actionError(problem: Problem): ActionResult<never> {
  return { ok: false, problem };
}

/** Turns a thrown `ApiError` (lib/api-error.ts) into the RFC 9457 shape Server Actions return. */
export function problemFromApiError(error: ApiError): Problem {
  return {
    type: error.type,
    title: error.message,
    status: error.status,
    detail: error.detail,
    instance: error.instance,
  };
}

/** A synthetic problem for a client-side (zod) validation failure -- never reaches `apps/api`. */
export function validationProblem(detail: string): Problem {
  return {
    type: "https://hunter.dev/problems/validation-error",
    title: "Validation Error",
    status: 422,
    detail,
  };
}

export { ApiError };

/**
 * Aliases onto the OpenAPI-generated `components["schemas"]` for the real
 * T1.4 market/system contract (`apps/api/hunter_api/schemas/{markets,system}.py`,
 * `pnpm gen:types`) -- same pattern as the org/workspace aliases above. T1.5's
 * H1 fix retired the hand-written mirror of this contract that used to live
 * here: it had already drifted (`base_asset`/`quote_asset` are
 * `string | null`, not the non-nullable `string` this file used to declare),
 * which crashed `markets-table.tsx`'s search filter on the first
 * not-yet-backfilled row. Every numeric field is still a `Decimal` string or
 * `null`, never a `number` -- CLAUDE.md's "money is Decimal, never float"
 * extends to the wire format here too.
 */
export type MarketDataQuality = components["schemas"]["DataQuality"];
/** A single component's own freshness -- narrower than `MarketDataQuality`, which also knows `degraded`/`unavailable` (market-wide, not one component's). */
export type ComponentQuality = components["schemas"]["ComponentQuality"];

/** `ticker`/`book`/`mark` -- the three required components. */
export type ComponentStatus = components["schemas"]["ComponentStatusOut"];
/** `open_interest` -- not required, so it carries no `quality`. */
export type OptionalComponentStatus = components["schemas"]["OptionalComponentStatusOut"];
export type FundingComponentStatus = components["schemas"]["FundingComponentStatusOut"];
export type MarketComponents = components["schemas"]["MarketComponentsOut"];

/** One row of `GET /api/v1/markets` (`MarketOut`) -- named `MarketRow` here because every call site reads it as a table row. */
export type MarketRow = components["schemas"]["MarketOut"];
export type MarketsSummary = components["schemas"]["MarketsSummary"];
/** `GET /api/v1/markets`'s full page shape (`MarketListPage`), including `stale_after_ms` (H2) and `summary`. */
export type MarketsListResponse = components["schemas"]["MarketListPage"];

/** `{price, qty}`, both `Decimal` strings. */
export type OrderBookLevel = components["schemas"]["BookLevelOut"];
export type MarketBook = components["schemas"]["OrderBookOut"];
export type RecentTrade = components["schemas"]["TradeOut"];

/**
 * `GET /api/v1/markets/{exchange}/{symbol}` (`MarketDetailOut`). Carries
 * `hot_state_ok` (H3): `false` means the Redis hot-state read itself failed
 * and `book`/`recent_trades` are `null` because the API *could not ask*, not
 * because there is no book/no trades -- render an outage, never "no book"/"no
 * recent trades", whenever this is `false`. See the generated type's own
 * docstring in `packages/shared-types/src/generated/api.d.ts` for the full
 * contract.
 */
export type MarketDetail = components["schemas"]["MarketDetailOut"];

/** `GET .../candles` -- final candles only (`is_final = true`), never a partial one. */
export type Candle = components["schemas"]["CandleOut"];

export type WorkerStatus = components["schemas"]["WorkerLivenessStatus"];
/**
 * `GET /api/v1/system/workers` -- one row per `hb:{role}:{instance}` key.
 * The `market` role's rows (`instance` = exchange code) additionally carry
 * the exchange fields below; every other role has them `null`, never fabricated.
 */
export type WorkerHeartbeat = components["schemas"]["WorkerHeartbeatOut"];

export type ExchangeStatus = components["schemas"]["MarketStatusExchangeOut"];
/** `GET /api/v1/system/market-status`. */
export type MarketStatusResponse = components["schemas"]["MarketStatusOut"];

/**
 * `rt:market:{exchange}:{symbol}` payload (docs/ARCHITECTURE.md §5.2,
 * `services/market-worker/hunter_market_worker/ingest.py::build_tick_payload`).
 * Not part of the OpenAPI document (it's a Redis pub/sub message, not an HTTP
 * response), so it stays hand-typed. `price_ts`/`book_ts` (H4) track the
 * timestamp of the event kind that actually owns each value -- `ts` is only
 * the coalesced aggregate (bumped on ANY event, price or book), so using it
 * to age the price lets a book-only update republish a frozen price under a
 * fresh-looking age. Compare/display the price's age against `price_ts` and
 * the book's against `book_ts`; never fall back to `ts` when one of these is
 * missing (a worker that hasn't shipped them yet must read as "no signal",
 * not as fresh).
 */
export interface RtMarketMessage {
  exchange: string;
  symbol: string;
  price: string | null;
  bid: string | null;
  ask: string | null;
  volume_delta: string | null;
  trades_count: number | null;
  book_imbalance_5: string | null;
  ts: string;
  price_ts: string | null;
  book_ts: string | null;
}

/** `rt:system` payload -- one exchange's status per message. */
export interface RtSystemMessage {
  type: "market_status";
  exchange: string;
  ws_state: string;
  last_event_at: string | null;
  markets_monitored: number;
  open_gaps: number;
  ts: string;
}
