"use server";

import { isApiError } from "@/lib/api-error";
import { getServerSession } from "@/lib/server/auth";

import { listRadar } from "./radar";
import type { RadarPage, RadarParams } from "./radar-types";

export interface RadarActionOutcome {
  ok: boolean;
  page: RadarPage;
  reason?: string;
}

function emptyPage(): RadarPage {
  return { items: [], next_cursor: null, as_of: new Date().toISOString(), org_scoped: false };
}

/**
 * Server Action behind `components/radar/radar-table.tsx`: `lib/api/radar.ts`
 * is `"server-only"`, so a client component cannot call `listRadar` directly
 * (ESLint boundary: `components/**` never imports `@/lib/server/**`). Used
 * for both "load more" (cursor, same filters) and the periodic/`rt:radar`
 * driven reconciliation -- a fresh call with `cursor` omitted replaces the
 * currently-loaded page 1 rather than merging an assumed partial payload
 * shape, since no real publisher exists yet for `rt:radar`
 * (`.claude/state/notes-T2.7.md` records this as the explicit, disclosed
 * assumption to reconcile once T2.5 lands a producer).
 */
export async function loadRadarAction(params: RadarParams): Promise<RadarActionOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, page: emptyPage(), reason: "unauthenticated" };

  try {
    const page = await listRadar(params);
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, page: emptyPage(), reason };
  }
}
