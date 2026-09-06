"use client";

import { useEffect, useState } from "react";

import { AnomalyStatusChip } from "@/components/anomalies/anomaly-status-chip";
import { EvaluationStateChip } from "@/components/anomalies/evaluation-state-chip";
import { loadAnomalyTimelineAction } from "@/lib/api/anomalies-actions";
import { DEFAULT_ANOMALY_WINDOW_HOURS } from "@/lib/api/anomalies-types";
import type { AnomalyOut } from "@/lib/api/anomalies-types";
import { formatUtc } from "@/lib/format";
import { logger } from "@/lib/logger";

type TimelineState =
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ok"; items: AnomalyOut[]; truncated: boolean; asOf: string };

// A market-detail widget, not a trading surface -- 15s is plenty to keep
// "resolved since the page opened" honest without polling as aggressively
// as the Radar table (Astra's T2.7 diff review, must-fix 8: this used to
// only ever fetch once per `marketId`, so a status/evaluation_state change
// on an already-open page never showed up).
const REFRESH_INTERVAL_MS = 15_000;

/**
 * The market-detail anomaly timeline (brief line 11): 24h window, type,
 * severity, `AnomalyStatus` (active/resolved/expired) and
 * `AnomalyEvaluationState` shown together but never merged into one label
 * (`unknown` must never read as "resolved" -- `schemas/anomalies.py`).
 * Fetched client-side via a Server Action (`lib/api/anomalies-actions.ts`)
 * since `components/markets/**` cannot import `@/lib/server/**` directly.
 */
export function AnomalyTimeline({ marketId }: { marketId: string }) {
  const [state, setState] = useState<TimelineState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        const outcome = await loadAnomalyTimelineAction(marketId, DEFAULT_ANOMALY_WINDOW_HOURS);
        if (cancelled) return;
        if (!outcome.ok) {
          setState({ status: "error", reason: outcome.reason ?? "erro desconhecido" });
          return;
        }
        setState({ status: "ok", items: outcome.page.items, truncated: outcome.page.next_cursor !== null, asOf: outcome.page.as_of });
      } catch (error) {
        if (cancelled) return;
        logger.error("anomaly_timeline_load_failed", { error: String(error) });
        setState({ status: "error", reason: "erro desconhecido" });
      }
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting to loading when `marketId` itself changes, syncing from that external prop
    setState({ status: "loading" });
    void load();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [marketId]);

  if (state.status === "loading") return <p className="text-sm text-fg-muted">Carregando anomalias...</p>;
  if (state.status === "error") return <p className="text-sm text-fg-muted">Anomalias indisponíveis: {state.reason}</p>;
  if (state.items.length === 0) {
    return (
      <p className="text-sm text-fg-muted">
        Nenhuma anomalia nas últimas {DEFAULT_ANOMALY_WINDOW_HOURS}h · verificado {formatUtc(state.asOf)}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {state.items.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-2 border-t border-border/60 py-1 text-sm first:border-0">
            <span className="text-xs text-fg-subtle">{formatUtc(a.detected_at)}</span>
            <span className="font-medium text-fg">{a.type}</span>
            <span className="font-mono text-xs tabular-nums text-fg-muted">severidade {a.severity}</span>
            <AnomalyStatusChip status={a.status} />
            <EvaluationStateChip state={a.evaluation_state} />
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-fg-subtle">
        verificado {formatUtc(state.asOf)}
        {state.truncated && " · lista truncada — mais de 200 anomalias nas 24h"}
      </p>
    </div>
  );
}
