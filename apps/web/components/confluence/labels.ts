/**
 * The confluence screen's own small vocabularies -- design §7b: "dicionário
 * de status de ordem, motivo de recusa, kind e confidence de evento — regra
 * 'sem enum cru na tela'". `Record<Union, string>` is typed against the exact
 * union below, so the TS compiler itself refuses to build once a new member
 * of any of these value sets has no label; `tests/confluence-labels.test.ts`
 * is the same guarantee at run time, over the arrays below (the source of
 * truth mirrors the Postgres `CHECK` constraints, which is where a new
 * member would first appear).
 *
 * Refusal/failure *reasons* are not this file's job -- `spot_orders.reason`
 * reuses `components/meme-live/refusal-labels.ts`'s `executorRefusalLabel`
 * unchanged (design §7b), since `spot/1` and the meme executor share one
 * refusal vocabulary and its "recusa: <code>" fallback already satisfies
 * DESIGN-5 for a code this file has never heard of.
 */
import { executorRefusalLabel } from "@/components/meme-live/refusal-labels";
import type { DeskOrderStatus } from "@/lib/api/market-desk-types";
import type {
  MarketEventConfidence,
  MarketEventKind,
  MarketEventSource,
} from "@/lib/api/market-events-types";

/**
 * `spot_orders.reason` layers a small vocabulary of its own (`parity_above_cap`,
 * `spot_max_open_reached`, `below_ticket:<profile>`) on top of
 * `executorRefusalLabel`'s meme-executor checks -- Astra's review of T4.82
 * (must-fix 10) found the shared dictionary falls through to its own
 * `"recusa: <code>"` fallback for every one of these, which then doubled up
 * with this screen's own "Recusada:" prefix into "Recusada: recusa: …".
 * This is the single call site the panel and the period list both use, so
 * the two can never disagree on the wording.
 */
const SPOT1_REASON_LABEL: Record<string, string> = {
  parity_above_cap: "paridade da curva acima do teto",
  spot_max_open_reached: "teto de posições abertas da mesa spot/1 atingido",
};

export function spotOrderReasonLabel(reason: string | null): string {
  if (reason === null) return "motivo não registrado";
  const known = SPOT1_REASON_LABEL[reason];
  if (known !== undefined) return known;
  if (reason.startsWith("below_ticket:")) return `abaixo do tamanho mínimo do ticket (${reason.slice("below_ticket:".length)})`;
  return executorRefusalLabel(reason) ?? `recusa: ${reason}`;
}

export const DESK_ORDER_STATUSES: readonly DeskOrderStatus[] = [
  "admitted",
  "confirmed",
  "refused",
  "failed",
];

/** `spot_orders.status`'s full `CHECK` set includes `simulated`/`submitted_unconfirmed` too -- kept as `string` fallbacks below rather than widening `DeskOrderStatus` (the confluence screen's own three-answer read, design §4A, only distinguishes executed/refused/none; the other two are in-flight states no `spot/1` row observed at rest has ever carried in production as of T4.82). */
export const DESK_ORDER_STATUS_LABEL: Record<DeskOrderStatus, string> = {
  admitted: "admitida",
  confirmed: "confirmada",
  refused: "recusada",
  failed: "falhou",
};

export function deskOrderStatusLabel(status: string): string {
  if (status === "simulated") return "simulada";
  if (status === "submitted_unconfirmed") return "enviada, sem confirmação";
  return (DESK_ORDER_STATUS_LABEL as Record<string, string>)[status] ?? `status: ${status}`;
}

/**
 * Code review (round 3, must-fix 3): `spot_orders.status`/`settled_at`
 * mutate in place, so a row's CURRENT status can be knowledge from strictly
 * after the cursor being read. Whenever `latestOrderStateForSignal`/the block
 * B order loop find a received-but-not-yet-settled-by-cursor row, this is the
 * one label both show -- deliberately generic (never a specific in-flight
 * status like "simulada"/"enviada, sem confirmação") because none of those
 * intermediate values were necessarily true at the cursor either; only that
 * it had been admitted and had not yet settled.
 */
export const ORDER_PENDING_LABEL = "admitida, aguardando confirmação";

export const MARKET_EVENT_KINDS: readonly MarketEventKind[] = [
  "listing",
  "delisting",
  "upgrade",
  "incident",
  "macro",
  "company",
  "narrative",
];

export const MARKET_EVENT_KIND_LABEL: Record<MarketEventKind, string> = {
  listing: "listagem",
  delisting: "deslistagem",
  upgrade: "upgrade",
  incident: "incidente",
  macro: "macro",
  company: "empresa",
  narrative: "narrativa",
};

export const MARKET_EVENT_CONFIDENCES: readonly MarketEventConfidence[] = [
  "confirmed",
  "reported",
  "rumor",
];

export const MARKET_EVENT_CONFIDENCE_LABEL: Record<MarketEventConfidence, string> = {
  confirmed: "confirmado",
  reported: "reportado",
  rumor: "rumor",
};

export const MARKET_EVENT_SOURCES: readonly MarketEventSource[] = [
  "baha",
  "manual",
  "plantao",
  "exchange_notice",
];

export const MARKET_EVENT_SOURCE_LABEL: Record<MarketEventSource, string> = {
  baha: "baha.com",
  manual: "registro manual",
  plantao: "plantão",
  exchange_notice: "aviso da corretora",
};
