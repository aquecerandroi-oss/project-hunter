/**
 * Aliases onto the T4.82 confluence-screen contract
 * (`apps/api/hunter_api/{routers,schemas}/market_events.py`) -- the news lane.
 * Same convention as `lib/api/anomalies-types.ts`.
 */
import type { components } from "@hunter/shared-types/api";

export type MarketEventOut = components["schemas"]["MarketEventOut"];
export type MarketEventsOut = components["schemas"]["MarketEventsOut"];

/** `market_events.source` (`packages/core/hunter_core/db/models/market_events.py`). */
export type MarketEventSource = "baha" | "manual" | "plantao" | "exchange_notice";

/** `market_events.kind`. */
export type MarketEventKind =
  | "listing"
  | "delisting"
  | "upgrade"
  | "incident"
  | "macro"
  | "company"
  | "narrative";

/** `market_events.confidence` -- rendered as a shape, never a colour (design §3, overlay 4). */
export type MarketEventConfidence = "confirmed" | "reported" | "rumor";
