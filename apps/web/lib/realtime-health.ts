import type { RealtimeCloseInfo, RealtimeStatus } from "@/lib/ws";

/**
 * T3.44d: `RealtimeClient` (`lib/ws.ts`) already retries a dropped
 * connection on its own exponential backoff -- most closes it observes
 * (server-initiated 44xx, an idle proxy, or the browser tearing the socket
 * down on a hard navigation the VPS `ws_closed` evidence turned out to be
 * mostly this) resolve within a few seconds, without the viewer ever
 * touching the page. Flipping the topbar's "(tempo real do navegador
 * interrompido)" note the INSTANT `status` leaves `"open"` turned every one
 * of those routine blips into a visible alarm, and gave a caller who missed
 * the recovery no way to tell "still reconnecting" apart from "gave up".
 *
 * `deriveConnectionHealth` is the pure decision the topbar (`live-status.tsx`)
 * renders from: `live` stays `true` through a disconnection shorter than
 * `graceMs` (the reconnect is trusted to land), and only reads `false` once
 * the CURRENT disconnection has outlasted it. `since`/`lastCloseLabel` are
 * carried through unconditionally for the tooltip, which shows the honest
 * detail (when the current state began, what the last close actually was)
 * regardless of whether the headline reads "ao vivo" or not.
 */
export interface ConnectionHealth {
  /** `true` renders as "ao vivo" -- a disconnection still inside `graceMs` is trusted to self-heal, never flashed as an alarm. */
  live: boolean;
  /** `Date.now()` the CURRENT status began, or `null` before the client's first transition. Brasília-formatted by the caller (`lib/time.ts`). */
  since: number | null;
  /** `"<reason> (<code>)"`, or `null` before this client has ever closed a socket. */
  lastCloseLabel: string | null;
}

/**
 * Long enough to cover the client's own first few reconnect attempts
 * (`baseBackoffMs` defaults to 500ms, doubling) without hiding a connection
 * that is genuinely stuck -- short enough that a real outage still reads as
 * "interrompido" well inside the 15s topbar polling cadence it sits next to.
 */
export const RECONNECT_GRACE_MS = 8_000;

/**
 * T3.44e: `session.py`'s `WS_IDLE_TIMEOUT_CODE` -- the server's own 15-minute
 * idle close, kept here (not imported; this file has no server dependency)
 * as the one close code `closeLabel` below names in plain Portuguese instead
 * of echoing the server's raw English reason string ("idle timeout"). This
 * is the ONE close the visible-tab keepalive (`lib/ws.ts`'s `KEEPALIVE_MS`)
 * exists specifically to prevent for a visible tab, so a viewer who still
 * sees it deserves the plainest possible explanation.
 */
export const IDLE_TIMEOUT_CLOSE_CODE = 4409;

function closeLabel(lastClose: RealtimeCloseInfo | null): string | null {
  if (!lastClose) return null;
  if (lastClose.code === IDLE_TIMEOUT_CLOSE_CODE) return "encerrado por ociosidade (15 min)";
  const reason = lastClose.reason || "sem motivo informado";
  return `${reason} (${lastClose.code})`;
}

export function deriveConnectionHealth(input: {
  status: RealtimeStatus;
  since: number | null;
  now: number;
  lastClose: RealtimeCloseInfo | null;
  graceMs?: number;
}): ConnectionHealth {
  const lastCloseLabel = closeLabel(input.lastClose ?? null);
  // Loose fallback on purpose: a caller (or an older test double predating
  // this module, e.g. a plain `{ status: "closed", messages: {} }` mock of
  // `useMarketChannels`) that omits `since` entirely hands this `undefined`,
  // not `null` -- `undefined - number` is `NaN`, and `NaN < graceMs` is
  // `false`, which would have silently built a Date from `undefined`
  // downstream instead of the honest "never connected" reading.
  const since = input.since ?? null;
  if (input.status === "open") {
    return { live: true, since, lastCloseLabel };
  }
  const graceMs = input.graceMs ?? RECONNECT_GRACE_MS;
  const disconnectedForMs = since !== null ? Math.max(0, input.now - since) : Infinity;
  return { live: disconnectedForMs < graceMs, since, lastCloseLabel };
}
