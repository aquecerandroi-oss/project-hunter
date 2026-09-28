/**
 * Pure builders for blocks B ("o que acabara de acontecer", ±N) and C
 * ("depois deste instante") of the confluence screen's "Neste instante"
 * panel (design §4B/§4C). Split out of `confluence-instant-panel.tsx`
 * (Astra's round-4 review pushed that file over the 350-line budget) -- no
 * React here, so every branch is Vitest-able without mounting anything,
 * which is also how `confluence-window.ts` stays test-covered.
 */
import type { DeskOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";

import { deskOrderStatusLabel, MARKET_EVENT_CONFIDENCE_LABEL, MARKET_EVENT_KIND_LABEL, ORDER_PENDING_LABEL, spotOrderReasonLabel } from "./labels";
import { classifyEventTiming, eventEffectiveInstant, eventKnownInWindow, type WindowBounds } from "./confluence-window";

export interface TimelineRow {
  key: string;
  iso: string;
  text: string;
}

export function formatR(value: string | null): string {
  if (value === null) return "sem R calculado";
  const n = Number(value);
  return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(2)}R` : `${value}R`;
}

/** The final outcome's own line -- shared by block B's "settled" row and block C's "discovered later" one, never attributed to a different instant than the settlement itself (Astra's round-4 review, must-fix 3). */
function orderOutcomeText(order: DeskOut["orders"][number]): string {
  return order.status === "refused" ? `Recusa: ${spotOrderReasonLabel(order.reason)}` : `Ordem ${deskOrderStatusLabel(order.status)}`;
}

/**
 * Astra's round-4 review, must-fix 3: `received_at` and the order's eventual
 * OUTCOME are two different facts with two different instants -- retrodating
 * a settlement onto `received_at` (received 11:46, inside ±15, confirmed
 * 13:00, an hour past the window) misattributes a result that was not even
 * knowable within the displayed window. Each gets its own row here, at its
 * own timestamp: "recebida" always shows the truth of that instant (a row
 * born `refused` -- `admitted_at === null` -- is final immediately, no
 * separate outcome to wait for); a settlement is a *second*, independent row,
 * added only when ITS OWN instant also falls in the window. A settlement
 * outside the window never appears here -- it surfaces in block C instead
 * (`buildBlockCRows`).
 */
function pushOrderRows(rows: TimelineRow[], order: DeskOut["orders"][number], bounds: WindowBounds): void {
  const since = new Date(bounds.since).getTime();
  const until = new Date(bounds.until).getTime();
  const receivedAt = new Date(order.received_at).getTime();
  if (receivedAt >= since && receivedAt <= until) {
    const text = order.admitted_at === null ? `Recusa: ${spotOrderReasonLabel(order.reason)}` : `Ordem recebida, ${ORDER_PENDING_LABEL}`;
    rows.push({ key: `order-received-${order.id}`, iso: order.received_at, text });
  }
  if (order.admitted_at !== null && order.settled_at !== null) {
    const settledAt = new Date(order.settled_at).getTime();
    if (settledAt >= since && settledAt <= until) {
      rows.push({ key: `order-settled-${order.id}`, iso: order.settled_at, text: orderOutcomeText(order) });
    }
  }
}

export function buildBlockBRows(cursorIso: string, bounds: WindowBounds, signals: SignalListItemOut[], events: MarketEventOut[], desk: DeskOut | null): TimelineRow[] {
  const rows: TimelineRow[] = [];
  for (const signal of signals) {
    if (new Date(signal.decision_at) >= new Date(bounds.since) && new Date(signal.decision_at) <= new Date(bounds.until)) {
      rows.push({ key: `signal-${signal.signal_id}`, iso: signal.decision_at, text: `Sinal ${signal.direction} emitido` });
    }
  }
  for (const event of events) {
    // Code review (round 2, must-fix 3): a headline published/observed
    // inside ±N but only INGESTED after the cursor was not knowable at that
    // instant -- `eventKnownInWindow` excludes it from B; it still surfaces,
    // labelled as such, in block C (`buildBlockCRows` below).
    if (eventKnownInWindow(event, bounds, cursorIso)) {
      rows.push({ key: `event-${event.id}`, iso: eventEffectiveInstant(event), text: `Notícia (${MARKET_EVENT_KIND_LABEL[event.kind as keyof typeof MARKET_EVENT_KIND_LABEL] ?? event.kind}): ${event.title}` });
    }
  }
  for (const order of desk?.orders ?? []) pushOrderRows(rows, order, bounds);
  return rows.sort((a, b) => new Date(b.iso).getTime() - new Date(a.iso).getTime());
}

/**
 * Astra's round-4 review, must-fix 4: the old condition only caught the one
 * narrow "published before cursor, ingested after" case (design §4C's own
 * example) -- `eventKnownInWindow` (block B) now excludes EVERY event not
 * known by the cursor, including ones with no `published_at` at all or one
 * that itself falls after the cursor, so this catch-all must admit every one
 * of them too, or they vanish from both blocks in silence.
 */
function laterEventRowText(event: MarketEventOut, cursor: number): string {
  const knownPublishedBeforeCursor = event.published_at !== null && new Date(event.published_at).getTime() <= cursor;
  const confidenceLabel = MARKET_EVENT_CONFIDENCE_LABEL[event.confidence as keyof typeof MARKET_EVENT_CONFIDENCE_LABEL] ?? event.confidence;
  return knownPublishedBeforeCursor
    ? `Notícia publicada antes, ingerida depois: ${event.title} (${confidenceLabel})`
    : `Notícia ingerida depois deste instante: ${event.title} (${confidenceLabel})`;
}

export function buildBlockCRows(cursorIso: string, signals: SignalListItemOut[], events: MarketEventOut[], desk: DeskOut | null): TimelineRow[] {
  const rows: TimelineRow[] = [];
  const cursor = new Date(cursorIso).getTime();
  for (const signal of signals) {
    if (signal.exit_ts !== null && new Date(signal.exit_ts).getTime() > cursor && signal.result !== "open") {
      rows.push({ key: `exit-${signal.signal_id}`, iso: signal.exit_ts, text: `Desfecho do sinal: ${signal.result}${signal.r_multiple !== null ? ` (${formatR(signal.r_multiple)})` : ""}` });
    }
  }
  for (const event of events) {
    if (classifyEventTiming(event, cursorIso) === "later") {
      rows.push({ key: `later-event-${event.id}`, iso: event.ingested_at, text: laterEventRowText(event, cursor) });
    }
  }
  for (const order of desk?.orders ?? []) {
    // Astra's round-4 review, must-fix 3: a settlement whose OWN instant
    // falls after the cursor is exactly "descobrimos depois", regardless of
    // whether it also happens to sit inside the ±N window (block B keeps its
    // own, window-scoped copy of the same fact -- design §4C is not windowed
    // to begin with, same as the signal exits above).
    if (order.admitted_at !== null && order.settled_at !== null && new Date(order.settled_at).getTime() > cursor) {
      rows.push({ key: `order-outcome-${order.id}`, iso: order.settled_at, text: orderOutcomeText(order) });
    }
  }
  return rows.sort((a, b) => new Date(b.iso).getTime() - new Date(a.iso).getTime());
}
