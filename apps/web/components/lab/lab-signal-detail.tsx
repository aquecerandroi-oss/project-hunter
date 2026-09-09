"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { LabTrendlineGeometry } from "@/components/lab/lab-trendline-geometry";
import { LabTrendlineOverlay } from "@/components/lab/lab-trendline-overlay";
import { loadLabSignalEnvelopeAction, loadLabTrendlineCandlesAction } from "@/lib/api/lab-actions";
import type { OutcomeResult } from "@/lib/api/lab-types";
import type { Candle } from "@/lib/api/types";
import { computeCandleWindow, extractTrendlineGeometry, type TrendlineGeometry } from "@/lib/lab-trendline";
import { logger } from "@/lib/logger";

export interface LabSignalDetailProps {
  signalId: string;
  market: string;
  strategyVersionId: string;
  cohort: string;
  /** `source_bar_close` -- the decision bar's own close, the anchor every `idx` in the geometry is measured from. */
  decisionBarClose: string;
  entryPrice: string | null;
  entryTs: string | null;
  stop: string | null;
  target1: string | null;
  exitPrice: string | null;
  exitTs: string | null;
  result: OutcomeResult;
}

type EnvelopeState =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "loaded"; envelope: Record<string, unknown> | null }
  | { status: "error"; reason: string };

type TrendlineState =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "no_line" }
  | { status: "loaded"; geometry: TrendlineGeometry; missing: string[]; candles: Candle[]; derived: boolean }
  | { status: "error"; reason: string };

/** The whole "envelope -> geometry -> candles" chain, returning the final `TrendlineState` directly rather than setting it -- split out of `toggleTrendline` purely to stay under the statement-count lint budget. Never throws on an API failure (each step maps to its own `"error"`/`"no_line"` state); only a genuinely unexpected exception escapes, for the caller's own `catch`. */
async function fetchTrendlineState(props: LabSignalDetailProps): Promise<TrendlineState> {
  const { signalId, market, strategyVersionId, cohort } = props;
  const envelopeOutcome = await loadLabSignalEnvelopeAction(signalId, market, strategyVersionId, cohort);
  if (!envelopeOutcome.ok) return { status: "error", reason: envelopeOutcome.reason ?? "erro desconhecido" };

  const { present, geometry, missing } = extractTrendlineGeometry(envelopeOutcome.envelope);
  if (!present || !geometry) return { status: "no_line" };

  const window = computeCandleWindow(props.decisionBarClose, geometry.patternBars ?? 96, props.exitTs);
  const candlesOutcome = await loadLabTrendlineCandlesAction(market, window.beforeIso, window.limit);
  if (!candlesOutcome.ok) return { status: "error", reason: candlesOutcome.reason ?? "erro desconhecido" };

  return { status: "loaded", geometry, missing, candles: candlesOutcome.candles, derived: candlesOutcome.derived };
}

/**
 * On-demand envelope panel (brief S3b: "painel lateral/expansível com o
 * envelope (`include=envelope`) sob demand em JSON legível"). Fetched only
 * when the user asks for one row's envelope, never prefetched for the whole
 * page -- `supporting_features` can be large (SHADOW-LAB.md §2) and is
 * redundant for the rest of the table (contract-S3-lab.md).
 *
 * T3.49 (2026-09-08, Everton: "quero conferir visualmente se a linha estava
 * certa") adds a second, independent on-demand section beside the raw JSON
 * toggle: fetches the same envelope, and -- only when it carries a trend
 * line -- a real 15m candle window, to draw the overlay chart plus the
 * "Geometria" panel. Kept as its own toggle (not folded into the JSON one)
 * so every pre-existing envelope test keeps its exact "click once, one
 * fetch" behavior.
 */
export function LabSignalDetail(props: LabSignalDetailProps) {
  const { signalId, market, strategyVersionId, cohort } = props;
  const [state, setState] = useState<EnvelopeState>({ status: "closed" });
  const [trendline, setTrendline] = useState<TrendlineState>({ status: "closed" });

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

  async function toggleTrendline(): Promise<void> {
    if (trendline.status !== "closed") {
      setTrendline({ status: "closed" });
      return;
    }
    setTrendline({ status: "loading" });
    try {
      setTrendline(await fetchTrendlineState(props));
    } catch (error) {
      logger.error("lab_signal_trendline_load_failed", { signalId, error: String(error) });
      setTrendline({ status: "error", reason: "falha ao buscar a linha de tendência" });
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <Button type="button" variant="ghost" size="sm" onClick={() => void toggleTrendline()} aria-expanded={trendline.status === "loaded"}>
          {trendline.status === "closed" ? "Ver linha de tendência" : "Ocultar linha de tendência"}
        </Button>
        {trendline.status === "loading" && <p className="mt-1 text-xs text-fg-muted">Carregando linha de tendência...</p>}
        {trendline.status === "error" && <p className="mt-1 text-xs text-red">Linha indisponível: {trendline.reason}</p>}
        {trendline.status === "no_line" && (
          <p className="mt-1 text-xs text-fg-muted">Esta versão não lê linhas de tendência (só `trendline_breakout v1` persiste geometria de linha).</p>
        )}
        {trendline.status === "loaded" && (
          <div className="mt-2 flex flex-col gap-2">
            {trendline.derived && (
              <p className="text-[11px] text-fg-subtle">
                Candles agregadas de 1m real (o sistema ainda não grava 15m nativo em `candles`); só baldes com os 15 minutos completos entram, os parciais nas pontas ficam de fora.
              </p>
            )}
            <LabTrendlineOverlay
              candles={trendline.candles}
              geometry={trendline.geometry}
              decisionBarClose={props.decisionBarClose}
              entryPrice={props.entryPrice}
              entryTs={props.entryTs}
              stop={props.stop}
              target1={props.target1}
              exitPrice={props.exitPrice}
              exitTs={props.exitTs}
              result={props.result}
            />
            <LabTrendlineGeometry geometry={trendline.geometry} missing={trendline.missing} />
          </div>
        )}
      </div>
      <div>
        <Button type="button" variant="ghost" size="sm" onClick={() => void toggle()} aria-expanded={state.status === "loaded"}>
          {state.status === "loaded" ? "Ocultar dados brutos (JSON)" : "Ver dados brutos (JSON)"}
        </Button>
        {state.status === "loading" && <p className="mt-1 text-xs text-fg-muted">Carregando envelope...</p>}
        {state.status === "error" && <p className="mt-1 text-xs text-red">Envelope indisponível: {state.reason}</p>}
        {state.status === "loaded" && (
          <pre className="mt-2 max-h-96 overflow-auto rounded-md border border-border bg-bg-overlay p-3 text-[11px] text-fg">
            {state.envelope ? JSON.stringify(state.envelope, null, 2) : "envelope vazio"}
          </pre>
        )}
      </div>
    </div>
  );
}
