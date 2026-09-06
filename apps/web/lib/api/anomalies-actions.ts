"use server";

import { isApiError } from "@/lib/api-error";
import { getServerSession } from "@/lib/server/auth";

import { listAnomalies } from "./anomalies";
import { DEFAULT_ANOMALY_WINDOW_HOURS, MAX_ANOMALY_WINDOW_HOURS, buildAnomaliesAggregate, unavailableAnomaliesAggregate } from "./anomalies-types";
import type { AnomaliesAggregate, AnomalyPage } from "./anomalies-types";

export interface AnomalyTimelineOutcome {
  ok: boolean;
  page: AnomalyPage;
  reason?: string;
}

function emptyPage(): AnomalyPage {
  return { items: [], next_cursor: null, as_of: new Date().toISOString(), window_start: new Date().toISOString() };
}

/**
 * Behind `components/anomalies/anomaly-timeline.tsx` (the market-detail
 * timeline, brief line 11): `lib/api/anomalies.ts` is `"server-only"`, so
 * the client widget cannot call `listAnomalies` directly. One market, one
 * 24h window by default (`DEFAULT_ANOMALY_WINDOW_HOURS`) -- the brief's own
 * scope for this widget.
 */
export async function loadAnomalyTimelineAction(
  marketId: string,
  windowHours: number = DEFAULT_ANOMALY_WINDOW_HOURS,
): Promise<AnomalyTimelineOutcome> {
  const session = await getServerSession();
  if (!session) return { ok: false, page: emptyPage(), reason: "unauthenticated" };

  try {
    const page = await listAnomalies({ market_id: marketId, window_hours: windowHours, limit: 200 });
    return { ok: true, page };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    return { ok: false, page: emptyPage(), reason };
  }
}

/**
 * Behind `hooks/useRadarPage.ts`'s reconciliation: the Radar table's
 * "anomalias ativas" column aggregate (`components/radar/anomaly-count-cell.tsx`),
 * refetched on the same 5s cadence as the radar rows so it carries its own,
 * currently-true `as_of` instead of one frozen at the page's initial SSR
 * load (Astra's T2.7 diff review, must-fix 3). Shares `buildAnomaliesAggregate`
 * with `radar/page.tsx`'s initial server-side read so the two never compute
 * the grouping differently.
 */
export async function loadRadarAnomaliesAggregateAction(): Promise<AnomaliesAggregate> {
  const session = await getServerSession();
  if (!session) return unavailableAnomaliesAggregate();

  try {
    const page = await listAnomalies({ status: "active", window_hours: MAX_ANOMALY_WINDOW_HOURS, limit: 200 });
    return buildAnomaliesAggregate(page);
  } catch {
    return unavailableAnomaliesAggregate();
  }
}
