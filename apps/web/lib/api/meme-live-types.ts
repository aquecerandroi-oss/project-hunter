/**
 * TypeScript aliases onto the OpenAPI-generated `components["schemas"]` for
 * the real executor (T4.14/T4.17, `apps/api/hunter_api/{routers,schemas}/meme_live.py`)
 * -- same pattern as `lib/api/meme-desk-types.ts`. Every SOL amount stays a
 * `Decimal` string here, never a `number` (CLAUDE.md: money is never a float).
 */
import type { components } from "@hunter/shared-types/api";

import { memeDeskBase } from "./meme-desk-types";

export type MemeLive = components["schemas"]["MemeLiveOut"];
export type LiveExecutor = components["schemas"]["LiveExecutorOut"];
export type LiveOrder = components["schemas"]["LiveOrderOut"];
export type LivePosition = components["schemas"]["LivePositionOut"];
export type SellNowResult = components["schemas"]["SellNowOut"];

export type ExecutorStatus = "alive" | "stalled" | "never" | "heartbeat_missing" | "redis_unavailable";
export const EXECUTOR_STATUSES: readonly ExecutorStatus[] = ["alive", "stalled", "never", "heartbeat_missing", "redis_unavailable"];

export function isExecutorStatus(value: string): value is ExecutorStatus {
  return (EXECUTOR_STATUSES as readonly string[]).includes(value);
}

export type LiveOrderStatus = "admitted" | "refused" | "simulated" | "submitted_unconfirmed" | "confirmed" | "failed";
export const LIVE_ORDER_STATUSES: readonly LiveOrderStatus[] = ["admitted", "refused", "simulated", "submitted_unconfirmed", "confirmed", "failed"];

export function isLiveOrderStatus(value: string): value is LiveOrderStatus {
  return (LIVE_ORDER_STATUSES as readonly string[]).includes(value);
}

export type LivePositionStatus = "open" | "closed";
export const LIVE_POSITION_STATUSES: readonly LivePositionStatus[] = ["open", "closed"];

export function isLivePositionStatus(value: string): value is LivePositionStatus {
  return (LIVE_POSITION_STATUSES as readonly string[]).includes(value);
}

/** Mirrors `hunter_api.schemas.meme_live.MEME_LIVE_LABEL` -- the permanent, red label carried by every real payload. */
export const MEME_LIVE_LABEL =
  "REAL — transações assinadas na carteira Solana dedicada; a chave vive só no meme-executor, a API nunca assina";

/** `/api/v1/orgs/{org_id}/meme/live` -- shared by the server-only GET module, the "use server" write action and the desk's approve-REAL flow. */
export function memeLiveBase(orgId: string): string {
  return `${memeDeskBase(orgId)}/live`;
}

/**
 * The panel's three states (brief T4.17 §1): `ausente` (the executor process
 * itself never proved it is up -- any non-`alive` heartbeat status, whatever
 * the reason), `desligado` (alive, but the executor's own copy of
 * `ENABLE_MEME_LIVE_TRADING` is off), `ligado` (alive and the executor's flag
 * is on -- the only state where the desk may render every REAL number).
 * Read off the heartbeat alone; the API's own `api_live_enabled` is a
 * separate fact (whether the API itself would accept `mode: "live"`) and is
 * combined separately by `realActionsAvailable` below.
 */
export type ExecutorPanelState = "ausente" | "desligado" | "ligado";

export function executorPanelState(executor: LiveExecutor): ExecutorPanelState {
  if (executor.status !== "alive") return "ausente";
  return executor.live_enabled ? "ligado" : "desligado";
}

/**
 * `true` only when the executor is up, its own flag is on, AND the API's
 * copy of the flag is also on -- every gate the desk needs before it may
 * render "Aprovar (REAL)" / "Vender agora (REAL)". A `false` here means the
 * button must say why, never just disappear.
 */
export function realActionsAvailable(live: MemeLive): boolean {
  return live.api_live_enabled && executorPanelState(live.executor) === "ligado";
}
