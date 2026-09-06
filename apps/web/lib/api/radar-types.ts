/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * the T2.6 radar contract (`apps/api/hunter_api/routers/radar.py`,
 * `schemas/radar.py`) -- same pattern as `lib/api/types.ts`'s aliases. Kept
 * in this file (not `lib/api/types.ts`) because the brief's allowed-files
 * glob for this task is `lib/api/{radar,opportunities,anomalies,regime}*.ts`.
 */
import type { components } from "@hunter/shared-types/api";

export type RadarItemOut = components["schemas"]["RadarItemOut"];
export type RadarPage = components["schemas"]["RadarPage"];
export type RadarStatusFilter = components["schemas"]["RadarStatusFilter"];
export type OpportunityStage = components["schemas"]["OpportunityStage"];
export type OpportunityStatus = components["schemas"]["OpportunityStatus"];
export type MarketRegimeValue = components["schemas"]["MarketRegime"];
export type AnomalyTypeValue = components["schemas"]["AnomalyType"];
export type TradeDirectionValue = components["schemas"]["TradeDirection"];

export type RadarSortKey = "score" | "change" | "volume" | "age";
export type RadarSortOrder = "asc" | "desc";

/** Every status token `?status=` accepts (`RadarStatusFilter`), grouped for the filter UI. */
export const RADAR_STATUS_VALUES: RadarStatusFilter[] = [
  "NORMAL",
  "WATCHING",
  "ANOMALY",
  "HOT",
  "ENTRY_CANDIDATE",
  "EXTENDED",
  "EXPIRED",
  "IN_POSITION",
  "RISK_BLOCKED",
];

/** Statuses only meaningful once an `org_id` derived them (`RadarPage.org_scoped`). */
export const RADAR_ORG_ONLY_STATUS_VALUES: RadarStatusFilter[] = ["IN_POSITION", "RISK_BLOCKED"];

export const OPPORTUNITY_STAGE_VALUES: OpportunityStage[] = ["EARLY", "DEVELOPING", "EXTENDED", "NONE"];

export const MARKET_REGIME_VALUES: MarketRegimeValue[] = [
  "BTC_BULL",
  "BTC_BEAR",
  "SIDEWAYS",
  "HIGH_VOLATILITY",
  "LOW_VOLATILITY",
  "RISK_ON",
  "RISK_OFF",
  "ALT_EXPANSION",
  "PANIC",
  "LIQUIDITY_CONTRACTION",
];

export const ANOMALY_TYPE_VALUES: AnomalyTypeValue[] = [
  "VOLUME_SPIKE",
  "PRICE_ACCELERATION",
  "VOLATILITY_EXPANSION",
  "ORDERBOOK_IMBALANCE",
  "OPEN_INTEREST_SPIKE",
  "FUNDING_ANOMALY",
  "LIQUIDATION_CLUSTER",
  "CROSS_EXCHANGE_DIVERGENCE",
  "TRADE_VELOCITY_SPIKE",
  "MOMENTUM_SHIFT",
];

export interface RadarParams {
  org_id?: string;
  score_min?: string;
  status?: RadarStatusFilter[];
  stage?: OpportunityStage[];
  exchange?: string;
  anomaly_type?: AnomalyTypeValue;
  regime?: MarketRegimeValue;
  volatility_min?: string;
  volatility_max?: string;
  q?: string;
  sort?: RadarSortKey;
  order?: RadarSortOrder;
  limit?: number;
  cursor?: string;
}
