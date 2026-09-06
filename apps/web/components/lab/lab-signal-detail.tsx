"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { loadLabSignalEnvelopeAction } from "@/lib/api/lab-actions";
import { logger } from "@/lib/logger";

export interface LabSignalDetailProps {
  signalId: string;
  market: string;
  strategyVersionId: string;
  cohort: string;
}

type EnvelopeState =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "loaded"; envelope: Record<string, unknown> | null }
  | { status: "error"; reason: string };

/**
 * On-demand envelope panel (brief S3b: "painel lateral/expansível com o
 * envelope (`include=envelope`) sob demand em JSON legível"). Fetched only
 * when the user asks for one row's envelope, never prefetched for the whole
 * page -- `supporting_features` can be large (SHADOW-LAB.md §2) and is
 * redundant for the rest of the table (contract-S3-lab.md).
 */
export function LabSignalDetail({ signalId, market, strategyVersionId, cohort }: LabSignalDetailProps) {
  const [state, setState] = useState<EnvelopeState>({ status: "closed" });

  async function toggle(): Promise<void> {
    if (state.status === "loaded" || state.status === "loading") {
      setState({ status: "closed" });
      return;
    }
    setState({ status: "loading" });
    try {
      const outcome = await loadLabSignalEnvelopeAction(signalId, market, strategyVersionId, cohort);
      if (!outcome.ok) {
        setState({ status: "error", reason: outcome.reason ?? "erro desconhecido" });
        return;
      }
      setState({ status: "loaded", envelope: outcome.envelope });
    } catch (error) {
      logger.error("lab_signal_envelope_load_failed", { signalId, error: String(error) });
      setState({ status: "error", reason: "falha ao buscar o envelope" });
    }
  }

  return (
    <div>
      <Button type="button" variant="ghost" size="sm" onClick={() => void toggle()} aria-expanded={state.status === "loaded"}>
        {state.status === "loaded" ? "Ocultar envelope" : "Ver envelope"}
      </Button>
      {state.status === "loading" && <p className="mt-1 text-xs text-fg-muted">Carregando envelope...</p>}
      {state.status === "error" && <p className="mt-1 text-xs text-red">Envelope indisponível: {state.reason}</p>}
      {state.status === "loaded" && (
        <pre className="mt-2 max-h-96 overflow-auto rounded-md border border-border bg-bg-overlay p-3 text-[11px] text-fg">
          {state.envelope ? JSON.stringify(state.envelope, null, 2) : "envelope vazio"}
        </pre>
      )}
    </div>
  );
}
