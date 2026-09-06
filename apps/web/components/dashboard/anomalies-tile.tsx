import { isApiError } from "@/lib/api-error";
import { listAnomalies } from "@/lib/api/anomalies";
import { MAX_ANOMALY_WINDOW_HOURS } from "@/lib/api/anomalies-types";
import { formatUtc } from "@/lib/format";
import { logger } from "@/lib/logger";

export type AnomaliesTileLoad = { ok: true; count: number; atLeast: boolean; asOf: string } | { ok: false };

/**
 * "Anomalias agora" (brief line 12). "Agora" is honestly the last 30 days of
 * `status=active` (the widest window the API accepts -- an `active +
 * unknown` anomaly can be arbitrarily older, `schemas/anomalies.py`), never
 * presented as a live, instantaneous count.
 *
 * A plain async function, called and awaited by `dashboard/page.tsx`
 * (mirroring that page's own `loadWorkspace`/`loadMembers`) rather than an
 * async Server Component embedded in JSX -- this file's `AnomaliesTile`
 * presentational component below stays a plain, synchronously-testable
 * function of an already-resolved result.
 */
export async function loadAnomaliesTile(): Promise<AnomaliesTileLoad> {
  try {
    const page = await listAnomalies({ status: "active", window_hours: MAX_ANOMALY_WINDOW_HOURS, limit: 200 });
    return { ok: true, count: page.items.length, atLeast: page.next_cursor !== null, asOf: page.as_of };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("dashboard_anomalies_tile_failed", { error: reason });
    return { ok: false };
  }
}

/**
 * Two distinct zero states (CLAUDE.md, brief line 12): a **failed check**
 * ("sem verificação") is never conflated with a **verified, genuinely
 * empty** result ("0 com as_of").
 */
export function AnomaliesTile({ result }: { result: AnomaliesTileLoad }) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Anomalias agora</h2>
      {!result.ok ? (
        <p className="mt-1 text-sm text-fg-muted">sem verificação</p>
      ) : (
        <>
          <p className="num mt-1 text-[28px] font-semibold text-fg">{result.atLeast ? `${result.count}+` : result.count}</p>
          <p className="mt-1 text-[11px] text-fg-subtle">ativas, últimos {MAX_ANOMALY_WINDOW_HOURS / 24}d · verificado {formatUtc(result.asOf)}</p>
        </>
      )}
    </section>
  );
}
