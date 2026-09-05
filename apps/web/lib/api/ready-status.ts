import type { ReadyStatus } from "./types";

/**
 * Sentinel `*_detail` value for "the check was never attempted" (missing
 * `API_URL`) -- distinct from `"unreachable"` (attempted, the fetch itself
 * failed). Split out of `lib/api/system.ts` (H3, T1.5b fix pass): that file
 * starts with `import "server-only"`, which throws if the module ends up in
 * a client bundle -- `components/system/readiness-panel.tsx` is a `"use
 * client"` component that needs this exact classification for its
 * `StatusBadge`'s "sem verificação" state, so the pure, dependency-free part
 * lives here where a client component can safely import it. `lib/api/
 * system.ts` re-exports both names so every existing server-side caller
 * keeps working unchanged.
 */
export const READY_CHECK_NOT_CONFIGURED = "not_configured";

/** `false` means `ready()`'s check never actually ran -- see `READY_CHECK_NOT_CONFIGURED`. */
export function wasReadyCheckAttempted(status: ReadyStatus): boolean {
  return status.database_detail !== READY_CHECK_NOT_CONFIGURED;
}
