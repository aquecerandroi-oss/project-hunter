"use server";

import { ready } from "./system";
import type { ReadyStatus } from "./types";

/**
 * Server Action wrapping `ready()` (lib/api/system.ts) so the System page's
 * client-side refresh button can re-run a *real* check instead of only
 * relying on `export const revalidate` -- a manual click always reflects the
 * current state of Postgres/Redis, not a stale up-to-15s-old render.
 */
export async function refreshReadiness(): Promise<ReadyStatus> {
  return ready();
}
