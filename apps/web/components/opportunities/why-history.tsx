"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { loadOpportunityDetailAction } from "@/lib/api/opportunities-actions";
import { MAX_ENVELOPE_HISTORY_LIMIT } from "@/lib/api/opportunities-types";
import type { OpportunityHistoryPointOut } from "@/lib/api/opportunities-types";
import { formatUtc } from "@/lib/format";

function toNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** A calm, discrete sparkline -- no chart library, matches docs/DESIGN.md §2's "movimento calmo". Chronological left-to-right (`points` is newest-first from the API, reversed here). */
function Sparkline({ points }: { points: OpportunityHistoryPointOut[] }) {
  if (points.length < 2) return null;
  const chronological = [...points].reverse();
  const scores = chronological.map((p) => toNumber(p.score));
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const span = max - min || 1;
  const width = 240;
  const height = 32;
  const step = width / (chronological.length - 1);
  const coords = scores.map((s, i) => `${i * step},${height - ((s - min) / span) * height}`).join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label={`Histórico de score, de ${min} a ${max}`} className="text-fg-muted">
      <polyline points={coords} fill="none" stroke="currentColor" strokeWidth={1.5} />
    </svg>
  );
}

export interface WhyHistoryProps {
  opportunityId: string;
  orgId: string | undefined;
  history: OpportunityHistoryPointOut[];
}

/**
 * Score history (brief line 10: "sparkline discreta + lista", envelope sob
 * demanda, limite 50). The initial page load never ships an envelope per
 * point (`include_envelope=false` -- MF-3, `schemas/opportunities.py`); this
 * button re-fetches the detail with it, capped at
 * `MAX_ENVELOPE_HISTORY_LIMIT`.
 */
export function WhyHistory({ opportunityId, orgId, history }: WhyHistoryProps) {
  const [points, setPoints] = useState(history);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedEnvelope, setLoadedEnvelope] = useState(false);

  async function loadEnvelope(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const limit = Math.min(points.length || MAX_ENVELOPE_HISTORY_LIMIT, MAX_ENVELOPE_HISTORY_LIMIT);
      const params: Parameters<typeof loadOpportunityDetailAction>[1] = { include_envelope: true, history_limit: limit };
      if (orgId !== undefined) params.org_id = orgId;
      const outcome = await loadOpportunityDetailAction(opportunityId, params);
      if (!outcome.ok || !outcome.detail) {
        setError(outcome.reason ?? "erro desconhecido");
        return;
      }
      setPoints(outcome.detail.history);
      setLoadedEnvelope(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Histórico do score (últimas {points.length} amostras)</h2>
        <Button type="button" variant="outline" size="sm" onClick={() => void loadEnvelope()} disabled={loading}>
          {loading ? "Carregando..." : loadedEnvelope ? `Envelope carregado (≤ ${MAX_ENVELOPE_HISTORY_LIMIT})` : `Carregar envelope (≤ ${MAX_ENVELOPE_HISTORY_LIMIT})`}
        </Button>
      </div>
      {error && <p className="mt-1 text-xs text-red">{error}</p>}
      <div className="mt-3">
        <Sparkline points={points} />
      </div>
      <ul className="mt-2 flex max-h-48 flex-col gap-1 overflow-y-auto text-xs">
        {points.map((p) => (
          <li key={p.ts} className="flex flex-wrap items-center gap-2 border-t border-border/60 py-1 first:border-0">
            <span className="text-fg-subtle">{formatUtc(p.ts)}</span>
            <span className="font-mono tabular-nums text-fg">{p.score}</span>
            <span className="text-fg-muted">{p.status}</span>
            <span className="text-fg-muted">{p.stage}</span>
            {p.envelope !== null && p.envelope !== undefined && (
              <details className="ml-auto">
                <summary className="cursor-pointer text-fg-muted">envelope</summary>
                <pre className="max-w-md overflow-x-auto text-[10px] text-fg-subtle">{JSON.stringify(p.envelope, null, 2)}</pre>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
