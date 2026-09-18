/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * "Carteira real" (T4.57, `apps/api/hunter_api/{routers,schemas}/meme_live_wallet.py`)
 * -- same pattern as `lib/api/meme-live-types.ts`. Every SOL/USD/BRL amount
 * stays a `Decimal` string here, never a `number` (CLAUDE.md: money is never
 * a float).
 */
import type { components } from "@hunter/shared-types/api";

import { memeLiveBase } from "./meme-live-types";

export type WalletSummary = components["schemas"]["WalletSummaryOut"];
export type WalletNow = components["schemas"]["WalletNowOut"];
export type WalletToday = components["schemas"]["WalletTodayOut"];
export type WalletAllTime = components["schemas"]["WalletAllTimeOut"];
export type WalletFx = components["schemas"]["WalletFxOut"];
export type WalletBestWorst = components["schemas"]["WalletBestWorstOut"];
export type WalletClosedPosition = components["schemas"]["WalletClosedPositionOut"];
export type WalletOpenPosition = components["schemas"]["WalletOpenPositionOut"];

/** `/api/v1/orgs/{org_id}/meme/live/wallet-summary` -- the endpoint `wallet-summary-panel.tsx` polls every 10 s. */
export function memeLiveWalletSummaryPath(orgId: string): string {
  return `${memeLiveBase(orgId)}/wallet-summary`;
}
