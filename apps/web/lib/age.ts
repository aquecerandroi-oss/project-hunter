/**
 * Pure age arithmetic shared by Client and Server Components.
 *
 * These three helpers used to live in `hooks/useAgeTicker.ts`, a `"use client"`
 * module. A Server Component that imports a function from a client module gets a
 * client *reference*, not the function — calling it throws at render time
 * ("Attempted to call computeAgeMs() from the server but computeAgeMs is on the
 * client"). That is exactly what took `/meme/mesa` down on 16/09/2026 12:2x BRT:
 * the "Executor real" panel is a Server Component and formatted the heartbeat's
 * age with `computeAgeMs`. The hook module re-exports these so every client
 * caller keeps its import; Server Components import from here.
 */

/**
 * The instant the heartbeat was *read*, derived from the ticker's own timestamp
 * plus the age the reader measured — the server clock a client ticker needs.
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
