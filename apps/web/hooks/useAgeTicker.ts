"use client";

import { useEffect, useState } from "react";

/**
 * `docs/plans/M1.md` T1.5 (joint decision): staleness ages must advance
 * visibly even when no new realtime message arrives -- a frozen "12s" next
 * to a dot that never changes reads as fresh when it is actually stuck.
 * This ticks `Date.now()` once a second so any component computing
 * `now - lastUpdate` re-renders on its own.
 */
export function useAgeTicker(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return now;
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
