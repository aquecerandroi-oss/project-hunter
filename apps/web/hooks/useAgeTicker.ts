"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export interface AgeClock {
  /**
   * `Date.now()` corrected by the server offset when one is available,
   * otherwise the viewer's own clock. Ticks once a second.
   */
  now: number;
  /**
   * `false` whenever there was no `serverNowIso` to anchor on (missing or
   * unparseable) and `now` fell back to the viewer's own clock -- callers
   * render a muted "relógio local" hint in that case so the fallback stays
   * visible instead of silently trusting a clock that might be skewed.
   */
  hasServerClock: boolean;
}

/**
 * `offset = serverNow - receivedAt`, computed once per response (memoized on
 * the pair passed in). T3.16 (Everton, VPS, 2026-09-08): a viewer's own
 * clock is not trustworthy -- a browser clock ~60s ahead of the VPS turned
 * every fresh row "atrasado 1min" while every heartbeat and ticker timestamp
 * was within 1s of the server. `null` when there is no `serverNowIso` to
 * anchor on (an API build predating T3.16, or a genuinely unparseable
 * value) -- callers fall back to the viewer's own `Date.now()`.
 */
export function useServerClock(serverNowIso: string | null | undefined, receivedAtMs: number): number | null {
  return useMemo(() => {
    if (!serverNowIso) return null;
    const serverNow = new Date(serverNowIso).getTime();
    return Number.isNaN(serverNow) ? null : serverNow - receivedAtMs;
  }, [serverNowIso, receivedAtMs]);
}

/**
 * `docs/plans/M1.md` T1.5 (joint decision): staleness ages must advance
 * visibly even when no new realtime message arrives -- a frozen "12s" next
 * to a dot that never changes reads as fresh when it is actually stuck.
 * This ticks once a second so any component computing `now - lastUpdate`
 * re-renders on its own.
 *
 * T3.16: optionally anchored to the server's own clock via `serverNowIso`
 * (the API's `server_now` -- present on every response that also carries
 * `stale_after_ms`: `MarketListPage`, `MarketDetailOut`). `receivedAtMs` is
 * captured once per distinct `serverNowIso` value -- a `ref` remembers the
 * last value seen, and a plain `useEffect` (a side effect, never render
 * itself) calls `Date.now()` only the instant a *new* one arrives -- so the
 * offset in `useServerClock` above is anchored exactly once per response,
 * not on every one-second tick. `Date.now()` is otherwise never called
 * directly during render (React's purity rule): both this and the ticking
 * clock below live in `useState`'s lazy-initializer escape hatch or inside
 * an effect/interval callback, never in the render body itself. A viewer
 * clock skewed by minutes in either direction never changes the returned
 * `now` once a `serverNowIso` is present -- see `hasServerClock` for the one
 * case where it still does (no server clock to anchor on at all).
 */
export function useAgeTicker(serverNowIso?: string | null, intervalMs = 1000): AgeClock {
  const [receivedAtMs, setReceivedAtMs] = useState(() => Date.now());
  const lastServerNowIsoRef = useRef(serverNowIso);

  useEffect(() => {
    if (lastServerNowIsoRef.current === serverNowIso) return;
    lastServerNowIsoRef.current = serverNowIso;
    setReceivedAtMs(Date.now());
  }, [serverNowIso]);

  const offsetMs = useServerClock(serverNowIso, receivedAtMs);

  const [tickNow, setTickNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setTickNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return { now: offsetMs !== null ? tickNow + offsetMs : tickNow, hasServerClock: offsetMs !== null };
}

/**
 * A worker heartbeat (`WorkerHeartbeatOut`, `/system/workers`) carries both
 * its own `ts` and the server-computed `age_s` (`now - ts` at scan time) --
 * their sum is the exact instant the API's own clock read as "now" when it
 * built that row, without needing a separate `server_now` field (T3.16:
 * `/system/workers` is a bare `list[WorkerHeartbeatOut]`, not a
 * `stale_after_ms`-carrying envelope like `MarketListPage`/`MarketDetailOut`).
 * Feed the result into `useAgeTicker` instead of the worker's own `ts` alone,
 * so its age keeps advancing off the server's clock, never the viewer's.
 * `null` only when `ts` itself is unparseable.
 */
export function heartbeatServerNowIso(ts: string, ageS: number): string | null {
  const parsed = new Date(ts).getTime();
  return Number.isNaN(parsed) ? null : new Date(parsed + ageS * 1000).toISOString();
}

/** Age in ms of an ISO timestamp against `now`, or `null` when there is no timestamp at all. */
export function computeAgeMs(tsIso: string | null | undefined, now: number): number | null {
  if (!tsIso) return null;
  const ts = new Date(tsIso).getTime();
  if (Number.isNaN(ts)) return null;
  return Math.max(0, now - ts);
}

/** Short, human age: "12s", "3min", "2h" -- never more precision than the badge/label has room for. */
export function formatAge(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h`;
}
