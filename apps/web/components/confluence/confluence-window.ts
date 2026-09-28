/**
 * Pure time-window logic for the confluence screen (design §4): what counts
 * as "vigente às 11:45", what counts as "já sabíamos" vs. "descobrimos
 * depois", and the ±N reading window around a cursor. No React, no chart
 * library -- Vitest-able without mocking either (design §7b's own file list).
 */
import type { DeskOrderOut, DeskPositionOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import type { RegimeOut } from "@/lib/api/regime-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";

/** design §4B: the default reading window is ±15 min around the cursor -- "esta barra e uma de cada lado" at the screen's 15m unit. The second step is ±60 min. */
export const DEFAULT_WINDOW_MINUTES = 15;
export const WIDE_WINDOW_MINUTES = 60;

export interface WindowBounds {
  since: string;
  until: string;
}

/** `[cursor - minutes, cursor + minutes]`, inclusive on both ends (a reading window, not the API's half-open fetch window). */
export function windowBounds(cursorIso: string, minutes: number): WindowBounds {
  const cursorMs = new Date(cursorIso).getTime();
  const spanMs = minutes * 60_000;
  return {
    since: new Date(cursorMs - spanMs).toISOString(),
    until: new Date(cursorMs + spanMs).toISOString(),
  };
}

/**
 * design §7a item 3 / Astra's review: a real position is "vigente às 11:45"
 * by **interval intersection**, not a point query -- one opened at 10:00 and
 * never closed (or closed after the cursor) was still held at the cursor.
 * `exit_at === null` is open; a position that exits exactly at the cursor
 * still counts (closed-at-cursor is still "held" the instant before).
 */
export function positionVigenteAtCursor(
  position: Pick<DeskPositionOut, "entry_at" | "exit_at">,
  cursorIso: string,
): boolean {
  const entry = new Date(position.entry_at).getTime();
  const cursor = new Date(cursorIso).getTime();
  if (entry > cursor) return false;
  if (position.exit_at === null) return true;
  return new Date(position.exit_at).getTime() >= cursor;
}

const SIGNAL_LIVE_TRACKING_STATES = new Set(["pending_entry", "active"]);

/**
 * design §4A: "sinais com `emitted_at <= cursor < expires_at` e
 * `tracking_state` ainda em curso". `decision_at` IS `agent_signals.emitted_at`
 * (`hunter_api/repositories/lab_common.py::DECISION_AT`). `expires_at === null`
 * (older rows, or a signal type the worker never set one for) is **not**
 * read as "already expired" -- there is simply no computed boundary to test
 * against, so only `tracking_state` decides.
 */
export function signalVigenteAtCursor(
  signal: Pick<SignalListItemOut, "decision_at" | "expires_at" | "tracking_state">,
  cursorIso: string,
): boolean {
  if (!SIGNAL_LIVE_TRACKING_STATES.has(signal.tracking_state)) return false;
  const cursor = new Date(cursorIso).getTime();
  const emitted = new Date(signal.decision_at).getTime();
  if (emitted > cursor) return false;
  if (signal.expires_at === null) return true;
  return cursor < new Date(signal.expires_at).getTime();
}

export type SignalOrderState =
  | { kind: "executed"; order: DeskOrderOut }
  | { kind: "refused"; order: DeskOrderOut }
  | { kind: "failed"; order: DeskOrderOut }
  /** Received (and, possibly, already mutated past this point by the executor) but not yet SETTLED as of the cursor -- see `orderFinalAsOfCursor`. */
  | { kind: "pending"; order: DeskOrderOut }
  | { kind: "none" };

const TERMINAL_ORDER_STATUSES = new Set(["confirmed", "refused", "failed"]);

/**
 * Astra's round-4 review of the round-3 fix, must-fix 1: `settled_at` is
 * NOT the one column every terminal row carries. `refuse_row`
 * (`spot_entry_writes.py`) and the ``status="admitted" if approved else
 * "refused"`` branch (`spot_entries.py`) both INSERT a `refused` row
 * directly -- `_INSERT_ORDER` (`spot_repo.py`) never sets `settled_at` on
 * that path, only `admitted_at` (and only when `status = 'admitted'`). A row
 * refused at birth is final the INSTANT it is received: there is no
 * admission phase for a later async mutation to race with, unlike a row that
 * WAS admitted and only later settles through `_CONFIRMED`/`_REFUSED`/
 * `_FAILED` (the only writes that ever set `settled_at`). `admitted_at`
 * being `null` is exactly the fact that tells the two apart.
 */
export function orderFinalAsOfCursor(
  order: Pick<DeskOrderOut, "settled_at" | "admitted_at" | "received_at">,
  cursorIso: string,
): boolean {
  const cursor = new Date(cursorIso).getTime();
  if (order.admitted_at === null) return new Date(order.received_at).getTime() <= cursor;
  return order.settled_at !== null && new Date(order.settled_at).getTime() <= cursor;
}

/** Whether an order's terminal outcome was already knowable at `cursorIso` -- alias kept for callers that only care about the settlement gate on an already-admitted row (block B's separate "received" vs "settled" rows, code review round 4 must-fix 3). */
export function orderSettledAsOfCursor(
  order: Pick<DeskOrderOut, "settled_at">,
  cursorIso: string,
): boolean {
  return order.settled_at !== null && new Date(order.settled_at).getTime() <= new Date(cursorIso).getTime();
}

/**
 * design §4A's "linha mais valiosa da tela": for one signal, did the desk
 * admit, refuse, or never even see it? An `attempt` can retry (a `refused`
 * row followed by an `admitted` one on a later attempt) -- the outcome that
 * actually happened wins, so `executed` is checked before `refused`/`failed`,
 * and every terminal status requires `orderFinalAsOfCursor` (code review
 * round 3 must-fix 3, round 4 must-fix 1-2): a row born `refused` is final at
 * `received_at`; an `admitted` row is only final once its OWN `settled_at`
 * had already happened by `cursorIso`. Everything else (no order at all yet,
 * or one received/admitted but not yet settled by the cursor) falls through
 * to `pending`/`none` instead of showing a status the reader could not have
 * known at that instant.
 */
export function latestOrderStateForSignal(
  orders: readonly DeskOrderOut[],
  signalId: string,
  cursorIso: string,
): SignalOrderState {
  const forSignal = orders.filter((order) => order.signal_id === signalId);
  if (forSignal.length === 0) return { kind: "none" };
  const finalByCursor = (order: DeskOrderOut) =>
    TERMINAL_ORDER_STATUSES.has(order.status) && orderFinalAsOfCursor(order, cursorIso);
  const executed = forSignal.find((order) => order.status === "confirmed" && finalByCursor(order));
  if (executed) return { kind: "executed", order: executed };
  const refused = forSignal.find((order) => order.status === "refused" && finalByCursor(order));
  if (refused) return { kind: "refused", order: refused };
  const failed = forSignal.find((order) => order.status === "failed" && finalByCursor(order));
  if (failed) return { kind: "failed", order: failed };
  // `reduce` without a seed keeps this `DeskOrderOut`, never `| undefined`
  // (`noUncheckedIndexedAccess` would force that on a sort-then-index) --
  // safe here because `forSignal.length > 0` is already checked above.
  const mostRecentReceived = forSignal.reduce((latest, order) =>
    new Date(order.received_at).getTime() > new Date(latest.received_at).getTime() ? order : latest,
  );
  return { kind: "pending", order: mostRecentReceived };
}

export type EventTiming = "known" | "later";

/**
 * design §4C: "às 11:45 não pode absorver conhecimento posterior em
 * silêncio". The only fact that decides whether we *knew* something at the
 * cursor is `ingested_at <= cursor` -- when the row reached our own database,
 * regardless of what `published_at` claims about the outside world. A
 * headline published before the cursor but ingested after it is exactly the
 * case this function must return `"later"` for (design §4C, brief case 8).
 */
export function classifyEventTiming(
  event: Pick<MarketEventOut, "ingested_at">,
  cursorIso: string,
): EventTiming {
  return new Date(event.ingested_at).getTime() <= new Date(cursorIso).getTime() ? "known" : "later";
}

/** The instant an event is placed at on the shared timeline/chart -- `published_at` when known, `observed_at` otherwise (design §3 overlay 4: an event with no `published_at` never draws on the chart, but still needs a placement for the lane/list). */
export function eventEffectiveInstant(event: Pick<MarketEventOut, "published_at" | "observed_at">): string {
  return event.published_at ?? event.observed_at;
}

/** Whether an event's effective instant falls inside `[since, until]` (inclusive), for the ±N lane/panel. */
export function eventInWindow(
  event: Pick<MarketEventOut, "published_at" | "observed_at">,
  bounds: WindowBounds,
): boolean {
  const at = new Date(eventEffectiveInstant(event)).getTime();
  return at >= new Date(bounds.since).getTime() && at <= new Date(bounds.until).getTime();
}

/**
 * Code review (round 2, must-fix 3): block B ("o que acabara de acontecer")
 * used to admit an event purely by `published_at`/`observed_at` falling in
 * the ±N window, with no check on `ingested_at` -- a headline published
 * before the cursor but only ingested well after it would render in B with
 * no caveat, even though design §4C's whole point is that such an event was
 * NOT known at the cursor and belongs in block C ("depois deste instante")
 * instead. `classifyEventTiming` is design §4C's own test for exactly that;
 * this is `eventInWindow` gated by it, so callers cannot admit one without
 * the other by accident.
 */
export function eventKnownInWindow(
  event: Pick<MarketEventOut, "published_at" | "observed_at" | "ingested_at">,
  bounds: WindowBounds,
  cursorIso: string,
): boolean {
  return eventInWindow(event, bounds) && classifyEventTiming(event, cursorIso) === "known";
}

/**
 * design §5: "Regime nunca diz 'desconhecido' como se fosse um regime — sem
 * leitura válida antes do cursor, diz 'sem leitura de regime anterior a este
 * instante'." `history` is expected newest-first (the API's own order); this
 * returns the first row whose validity interval covers the cursor.
 */
export function regimeAtCursor<T extends Pick<RegimeOut, "start_time" | "end_time">>(
  history: readonly T[],
  cursorIso: string,
): T | null {
  const cursor = new Date(cursorIso).getTime();
  for (const row of history) {
    const start = new Date(row.start_time).getTime();
    if (start > cursor) continue;
    if (row.end_time === null || row.end_time === undefined) return row;
    if (new Date(row.end_time).getTime() > cursor) return row;
  }
  return null;
}
