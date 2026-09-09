/**
 * `/radar` and `/opportunities`' "Estado do Radar" strip (T3.46 quant study
 * -- the Radar has never scored a market past `NORMAL`, covers a fraction of
 * the monitored universe and most baselines are still warming up). Pure
 * formatting/derivation only -- no fetch, no JSX -- so it is unit-testable
 * without a DOM. Every number traces back to `GET /api/v1/radar/coverage`
 * (`lib/api/radar-coverage-types.ts`); nothing here is invented.
 */
import type { RadarCoverageOut, RadarDetectorOut } from "@/lib/api/radar-coverage-types";
import { formatBrasiliaShort } from "@/lib/time";

export const WATCHING_THRESHOLD = 40;
/**
 * docs/PIPELINE.md §5: "Status: `NORMAL` (< 40) -> `WATCHING` (40-60) -> ...".
 * A pipeline-wide constant, not a per-organization setting or a value the
 * API exposes on its own -- there is nowhere else to read it from, so it is
 * named here rather than guessed inline every time the copy needs it.
 */

export const REOPEN_BASELINE_GATE_TARGET_PCT = 60;
export const REOPEN_MARKETS_TARGET = 150;
export const REOPEN_HISTORY_DAYS_TARGET = 14;
/**
 * The three reopen conditions the T3.46 quant study recommended, together:
 * >= 60% of `feature_baselines` rows passing the v2 gate, anomalies covering
 * >= 150 markets, >= 14 days of series. Product decision constants from that
 * study, not derived from any live field -- there is no endpoint for "the
 * threshold a past study recommended".
 */

const PT_BR_INT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const PT_BR_1_DECIMAL = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** "38.33" -> "38" (whole points, same convention as the dashboard's regime score, `regime-tile.tsx::formatScore`). `null` stays `null`, never a fabricated 0. */
export function formatScoreWhole(value: string | null | undefined): string | null {
  const n = toNumber(value);
  return n === null ? null : PT_BR_INT.format(Math.round(n));
}

/** pt-BR comma, one decimal: `8.08` -> "8,1". `null` stays `null` (no active gate / no baseline row yet -- distinct from a fabricated "0%"). */
export function formatPctPtBr(value: string | number | null | undefined): string | null {
  const n = toNumber(value);
  return n === null ? null : PT_BR_1_DECIMAL.format(n);
}

export interface BootstrapPointerParts {
  symbol: string;
  progress: string;
}

const BOOTSTRAP_POINTER_RE = /^bootstrapping\s+(\S+)\s+\((\d+\/\d+)\)$/;

/**
 * The scanner's raw `baselines_state` heartbeat sentence (e.g.
 * `"bootstrapping 1000FLOKIUSDT (4/200)"`) parsed into its two parts for the
 * strip's own wording. An unrecognized shape (a future scanner message this
 * regex was never updated for) still renders verbatim -- `progress: ""` --
 * rather than being silently dropped.
 */
export function parseBootstrapPointer(raw: string | null | undefined): BootstrapPointerParts | null {
  if (!raw) return null;
  const match = BOOTSTRAP_POINTER_RE.exec(raw.trim());
  if (!match) return { symbol: raw.trim(), progress: "" };
  return { symbol: match[1] ?? "", progress: match[2] ?? "" };
}

export type DetectorState = "producing" | "disarmed" | "silent";

/**
 * `rows_31d > 0` always wins (it produced real rows, whatever the heartbeat
 * says); zero rows with a declared reason is `disarmed` (by design); zero
 * rows with no declared reason is `silent` -- the defect T3.46 flagged
 * (`ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE`, `TRADE_VELOCITY_SPIKE`
 * today) and the one state this page must never quietly hide.
 */
export function classifyDetector(detector: RadarDetectorOut): DetectorState {
  if (detector.rows_31d > 0) return "producing";
  if (detector.disarmed_reason) return "disarmed";
  return "silent";
}

export const DETECTOR_STATE_LABEL: Record<DetectorState, string> = {
  producing: "Produzindo",
  disarmed: "Desarmado",
  silent: "Silencioso — sem motivo declarado",
};

/**
 * Known `detectors_disarmed` reason codes
 * (`services/scanner-worker/hunter_scanner_worker/health.py::write_heartbeat`'s
 * own vocabulary) translated to plain Portuguese (D19: no raw snake_case on
 * screen). An unrecognized reason still renders -- with its raw code
 * alongside, never hidden -- since a future disarm reason must be visible on
 * day one, not wait for this dictionary to catch up.
 */
const DISARM_REASON_LABEL: Record<string, string> = {
  single_exchange_until_m1b: "só há uma exchange conectada até o M1b (comparar entre exchanges ainda não é possível)",
  funding_unavailable: "funding indisponível para este mercado",
  feature_not_implemented: "a feature que este detector precisa ainda não foi implementada",
  deriv_history_unavailable: "sem histórico de open interest para este mercado",
  // T3.46b: as três classes que o scanner passou a declarar por avaliação, e
  // não mais só por capacidade do deploy.
  baselines_under_construction: "a baseline deste mercado e hora ainda não passa o portão de maturidade",
  baseline_absent: "nenhuma baseline foi escrita ainda para este mercado e hora",
  baseline_version_mismatch: "a baseline existente é de outra versão da feature",
  baseline_without_dispersion: "a baseline não tem dispersão (MAD zero): não há escala para medir o desvio",
  data_degraded: "o dado deste minuto está degradado e o pipeline não o usa para anomalia",
  feature_after_cut: "o livro de ofertas chega depois do corte de cobertura da avaliação",
  feature_missing_input: "falta a entrada que esta feature precisa",
  feature_warmup: "a feature ainda está aquecendo (histórico insuficiente)",
  feature_insufficient_coverage: "a cobertura da janela não pôde ser provada",
  feature_insufficient_sample: "menos observações do que a definição exige",
  feature_gap: "há lacuna de dados na janela desta feature",
  feature_corrupt_input: "a entrada chegou corrompida e foi recusada inteira",
  feature_zero_divisor: "o divisor desta feature é zero: o valor é indefinido",
  feature_stale_input: "uma entrada está mais velha que o orçamento de frescor",
  feature_misaligned: "o corte pedido não cai numa fronteira de barra",
  feature_not_in_vector: "esta feature não existe no vetor deste build",
  no_data: "nada chegou deste mercado neste minuto",
  undeclared: "o detector não declarou motivo (isto é defeito, não estado)",
};

export function disarmReasonLabel(reason: string): string {
  return DISARM_REASON_LABEL[reason] ?? `motivo técnico: ${reason}`;
}

export interface ReopenCondition {
  id: "baselines" | "coverage" | "history";
  label: string;
  currentText: string;
  pct: number;
  met: boolean;
}

function clampPct(value: number): number {
  return Math.max(0, Math.min(100, value));
}

/** Whole days between two ISO instants, never negative -- `null` when `startIso` is absent (no anomaly has ever fired). */
export function daysBetween(startIso: string | null | undefined, endIso: string): number | null {
  if (!startIso) return null;
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 86_400_000);
}

/**
 * The three reopen conditions T3.46 wrote down, each with its own real
 * current value -- never all-or-nothing, since a viewer needs to see which
 * one is closest.
 */
export function buildReopenConditions(coverage: RadarCoverageOut): ReopenCondition[] {
  const gatePct = toNumber(coverage.baseline_gate_v2_pct);
  const days = daysBetween(coverage.first_anomaly_at, coverage.as_of);

  return [
    {
      id: "baselines",
      label: `Baselines passando o gate v2 (≥ ${REOPEN_BASELINE_GATE_TARGET_PCT} %)`,
      currentText: gatePct === null ? "sem gate ativo" : `${formatPctPtBr(gatePct)} %`,
      pct: gatePct === null ? 0 : clampPct((gatePct / REOPEN_BASELINE_GATE_TARGET_PCT) * 100),
      met: gatePct !== null && gatePct >= REOPEN_BASELINE_GATE_TARGET_PCT,
    },
    {
      id: "coverage",
      label: `Mercados com alguma anomalia (≥ ${REOPEN_MARKETS_TARGET})`,
      currentText: `${PT_BR_INT.format(coverage.markets_with_anomaly)} de ${REOPEN_MARKETS_TARGET}`,
      pct: clampPct((coverage.markets_with_anomaly / REOPEN_MARKETS_TARGET) * 100),
      met: coverage.markets_with_anomaly >= REOPEN_MARKETS_TARGET,
    },
    {
      id: "history",
      label: `Dias de histórico (≥ ${REOPEN_HISTORY_DAYS_TARGET})`,
      currentText: days === null ? "sem histórico ainda" : `${formatPctPtBr(days)} de ${REOPEN_HISTORY_DAYS_TARGET}`,
      pct: days === null ? 0 : clampPct((days / REOPEN_HISTORY_DAYS_TARGET) * 100),
      met: days !== null && days >= REOPEN_HISTORY_DAYS_TARGET,
    },
  ];
}

/**
 * The strip's one headline sentence -- every clause a real field,
 * `formatBrasiliaShort` for the "desde ..." clause (Brasília-first,
 * `lib/time.ts`). Renders an honest fallback clause instead of a fabricated
 * number whenever a field is `null` (no heartbeat, no episode scored yet, no
 * anomaly yet).
 */
export function buildHeadline(coverage: RadarCoverageOut): string {
  const pointer = parseBootstrapPointer(coverage.bootstrap_pointer);
  const pointerText = pointer
    ? pointer.progress
      ? `bootstrap em ordem alfabética: ${pointer.symbol} ${pointer.progress}`
      : `bootstrap: ${pointer.symbol}`
    : "sem heartbeat do scanner no momento";
  const baselinesTotal = coverage.baselines_usable + coverage.baselines_under_construction;
  const baselinesPct = baselinesTotal > 0 ? (coverage.baselines_usable / baselinesTotal) * 100 : null;
  const score = formatScoreWhole(coverage.max_score_ever);
  const since = coverage.first_anomaly_at ? formatBrasiliaShort(coverage.first_anomaly_at) : null;

  const parts = [
    `Radar em construção — cobre ${PT_BR_INT.format(coverage.markets_with_anomaly)} de ${PT_BR_INT.format(coverage.markets_monitored)} mercados (${pointerText})`,
    baselinesPct === null ? "baselines: sem leitura do scanner" : `baselines prontas ${formatPctPtBr(baselinesPct)} %`,
    score === null ? "nenhum episódio pontuado ainda" : `maior score já visto ${score} (primeiro degrau ${WATCHING_THRESHOLD})`,
    since === null ? "nenhuma anomalia registrada ainda" : `nenhum mercado passou de NORMAL desde ${since} Brasília`,
  ];
  return parts.join(" · ");
}
