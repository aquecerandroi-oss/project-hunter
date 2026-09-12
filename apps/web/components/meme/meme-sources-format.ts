/**
 * Pure helpers for the "Fontes" panel (brief T4.3b): one chip per source
 * with its tone decided by rule, the three honest gauges of
 * `GET /meme/sources` (progress covered, tape covered, discovery blindness)
 * and the radar's own state -- every number next to its `observed_at`, every
 * absence "sem leitura: motivo", never a 0. No React, no fetch --
 * `tests/meme-sources-format.test.ts`.
 *
 * Tolerant to an older API by design: a field the payload does not carry at
 * all (`undefined`) reads "o worker não informou este número", distinct from
 * a `null` the worker wrote on purpose (which has its own reason).
 */
import type { MemeSourceOut, MemeSources } from "@/lib/api/meme-types";
import { formatBrasiliaShort } from "@/lib/time";

import { memeFeedSourceLabel, memeRadarStatusLabel, memeSourceStatusLabel } from "./labels";

export const BLINDNESS_SENTENCE = "moedas de outros launchpads que o radar não vê por construção";
export const NOT_REPORTED = "o worker não informou este número";

export type SourceTone = "green" | "amber" | "red" | "grey";

export interface SourceChip {
  name: string;
  tone: SourceTone;
  /** Full state sentence ("atrasada há 1 min", "sem leitura: nunca observou ..."). */
  state: string;
  /** The state's first words, for the one-line variant ("sem leitura", "com erro"). */
  short: string;
  /** "atraso 1.2 s · 30/60 req/min". */
  detail: string;
  /** Everything the chip knows, one fact per line, for `title`. */
  title: string;
  observedAt: string | null;
}

export interface Gauge {
  key: "progress" | "tape" | "blindness";
  label: string;
  short: string;
  value: string | null;
  reason: string | null;
  detail: string | null;
  observedAt: string | null;
  /** What `observedAt` is: the folded minute for coverage, the heartbeat for blindness. */
  observedLabel: string;
}

function isNum(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** "12 s" | "1 min" | "1 h" -- whole units, a space before the unit (DESIGN-5). */
export function formatAgeS(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h`;
}

export function formatBudget(used: number | null | undefined, limit: number | null | undefined): string {
  if (!isNum(used)) return "orçamento: sem leitura";
  if (!isNum(limit)) return `${used}/min (sem limite declarado)`;
  return `${used}/${limit} req/min`;
}

/** Fraction of the per-minute limit in use; `null` when either side is unknown or the limit is zero (never a division by zero, never a guess). */
export function budgetShare(used: number | null | undefined, limit: number | null | undefined): number | null {
  if (!isNum(used) || !isNum(limit) || limit <= 0) return null;
  return used / limit;
}

function formatLag(lag: number | null | undefined): string {
  return isNum(lag) ? `atraso ${lag.toFixed(1)} s` : "atraso: sem leitura";
}

// The worker's own reason words (`services/meme_sources.py`'s `source_status`), in plain Portuguese.
const SOURCE_REASON: Record<string, string> = {
  disabled: "desligada por chave",
  never_observed: "nunca observou nada desde que o worker subiu",
  never_connected: "nunca conectou desde que o worker subiu",
  heartbeat_missing: "o heartbeat não traz esta fonte",
};

function sourceReasonText(reason: string | null | undefined): string {
  if (!reason) return "motivo não informado";
  return SOURCE_REASON[reason] ?? reason.replace(/_/g, " ");
}

function chipState(source: MemeSourceOut, stalledAfterS: number): { tone: SourceTone; state: string; short: string } {
  const label = memeSourceStatusLabel(source.status);
  switch (source.status) {
    case "disabled":
      return { tone: "grey", state: label, short: label };
    case "unknown":
      return { tone: "grey", state: `${label}: ${sourceReasonText(source.reason)}`, short: label };
    case "disconnected":
      return { tone: "red", state: label, short: label };
    case "erroring":
      return { tone: "red", state: isNum(source.errors_1h) ? `${label} · ${source.errors_1h} na hora` : label, short: label };
    default:
      break;
  }
  const errors = isNum(source.errors_1h) ? source.errors_1h : 0;
  if (errors > 0) return { tone: "red", state: `${errors} erro(s) na hora`, short: "com erro" };
  if (isNum(source.age_s) && source.age_s > stalledAfterS) return { tone: "amber", state: `atrasada há ${formatAgeS(source.age_s)}`, short: "atrasada" };
  const share = budgetShare(source.used_60s, source.budget_60s);
  if (share !== null && share >= 0.9) return { tone: "amber", state: `orçamento ${Math.round(share * 100)}%`, short: "orçamento" };
  return { tone: "green", state: label, short: label };
}

function databaseWitness(source: MemeSourceOut): string {
  if (source.row_reason === "no_table") return "banco: esta fonte não escreve tabela própria";
  if (source.last_row_observed_at) return `banco: última linha observada em ${source.last_row_observed_at} (UTC)`;
  return "banco: nenhuma linha ainda";
}

function chipTitle(name: string, state: string, detail: string, source: MemeSourceOut): string {
  const lines = [`${name} — ${state}`, detail, `último dado observado (UTC): ${source.last_observed_at ?? "sem leitura"}`];
  if (isNum(source.errors_1h)) lines.push(`erros na última hora: ${source.errors_1h}`);
  if (source.last_error) lines.push(`último erro: ${source.last_error}${source.last_error_at ? ` (${source.last_error_at})` : ""}`);
  lines.push(databaseWitness(source));
  return lines.join("\n");
}

/** `stalledAfterS` is the radar's own threshold (`stalled_after_s`), so "atrasada" means the same thing the API means by "stale". */
export function sourceChip(source: MemeSourceOut, stalledAfterS: number): SourceChip {
  const name = memeFeedSourceLabel(source.name);
  const { tone, state, short } = chipState(source, stalledAfterS);
  const detail = `${formatLag(source.lag_s)} · ${formatBudget(source.used_60s, source.budget_60s)}`;
  return { name, tone, state, short, detail, title: chipTitle(name, state, detail, source), observedAt: source.last_observed_at ?? null };
}

/** `scale` 1 for a 0..100 percentage, 100 for a 0..1 share -- both print as "43.3%". */
function pctValue(value: number | null | undefined, scale: 1 | 100): string | null {
  return isNum(value) ? `${(value * scale).toFixed(1)}%` : null;
}

function coverageReason(payload: MemeSources, pct: number | null | undefined): string | null {
  if (pct === undefined) return `sem leitura: ${NOT_REPORTED}`;
  if (pct !== null) return null;
  if (payload.radar_status !== "alive") return `sem leitura: ${memeRadarStatusLabel(payload.radar_status)}`;
  if (payload.fold_minute === null || payload.fold_minute === undefined) return "sem leitura: nenhum minuto dobrado desde que o worker subiu";
  if (payload.fold_rows === 0) return "sem leitura: o último minuto dobrado não tem linhas";
  return `sem leitura: ${NOT_REPORTED}`;
}

export function progressGauge(payload: MemeSources): Gauge {
  const parts: string[] = [];
  if (isNum(payload.fold_rows)) parts.push(`${payload.fold_rows} linha(s) no minuto`);
  if (isNum(payload.mayhem_pending)) parts.push(`${payload.mayhem_pending} Mayhem sem denominador`);
  return {
    key: "progress",
    label: "Progresso coberto",
    short: "progresso",
    value: pctValue(payload.progress_coverage_pct, 1),
    reason: coverageReason(payload, payload.progress_coverage_pct),
    detail: parts.length ? parts.join(" · ") : null,
    observedAt: payload.fold_minute ?? null,
    observedLabel: "minuto dobrado",
  };
}

export function tapeGauge(payload: MemeSources): Gauge {
  const parts: string[] = [];
  if (isNum(payload.tape_covered_mints) && isNum(payload.tape_tracked_mints)) parts.push(`${payload.tape_covered_mints} de ${payload.tape_tracked_mints} mints com fita`);
  if (isNum(payload.tape_cycle_s)) parts.push(`ciclo ${payload.tape_cycle_s.toFixed(1)} s`);
  if (isNum(payload.tape_deferred_60s)) parts.push(`${payload.tape_deferred_60s} adiado(s)/min`);
  if (isNum(payload.tape_never_pulled)) parts.push(`${payload.tape_never_pulled} nunca puxado(s)`);
  return {
    key: "tape",
    label: "Fita coberta",
    short: "fita",
    value: pctValue(payload.tape_coverage_pct, 1),
    reason: coverageReason(payload, payload.tape_coverage_pct),
    detail: parts.length ? parts.join(" · ") : null,
    observedAt: payload.fold_minute ?? null,
    observedLabel: "minuto dobrado",
  };
}

function blindnessReason(payload: MemeSources): string | null {
  const share = payload.discovery_blind_share_1h;
  if (share === undefined) return `sem leitura: ${NOT_REPORTED}`;
  if (share !== null) return null;
  if (payload.radar_status !== "alive") return `sem leitura: ${memeRadarStatusLabel(payload.radar_status)}`;
  if (payload.discovery_new_board_entries_1h === 0) return "sem leitura: o board new não listou nada na última hora";
  return `sem leitura: ${NOT_REPORTED}`;
}

/** Share of the `new` board's listings in the last hour whose program is not pump -- declared, never corrected (T4.2d). */
export function blindnessGauge(payload: MemeSources): Gauge {
  const entries = payload.discovery_new_board_entries_1h;
  const nonPump = payload.discovery_non_pump_entries_1h;
  return {
    key: "blindness",
    label: "Cegueira da descoberta",
    short: "cegueira",
    value: pctValue(payload.discovery_blind_share_1h, 100),
    reason: blindnessReason(payload),
    detail: isNum(nonPump) && isNum(entries) && entries > 0 ? `${nonPump} de ${entries} entradas do board new na hora` : null,
    observedAt: payload.sources_at ?? null,
    observedLabel: "heartbeat",
  };
}

export function sourceGauges(payload: MemeSources): Gauge[] {
  return [progressGauge(payload), tapeGauge(payload), blindnessGauge(payload)];
}

export interface RadarState {
  tone: "green" | "red" | "grey";
  label: string;
}

/** "radar vivo · heartbeat há N s" ≠ "radar parado desde dd/mm hh:mm" ≠ "radar: sem leitura (motivo)" -- three facts, never one. */
export function radarStateLabel(payload: MemeSources): RadarState {
  const label = memeRadarStatusLabel(payload.radar_status);
  switch (payload.radar_status) {
    case "alive":
      return { tone: "green", label: isNum(payload.heartbeat_age_s) ? `${label} · heartbeat há ${formatAgeS(payload.heartbeat_age_s)}` : label };
    case "stale": {
      const since = payload.sources_at ? formatBrasiliaShort(payload.sources_at) : null;
      return { tone: "red", label: since ? `${label} desde ${since}` : label };
    }
    default:
      return { tone: "grey", label: `radar: sem leitura (${label})` };
  }
}

export function trackedLabel(tracked: number | null | undefined): string {
  return isNum(tracked) ? `${tracked.toLocaleString("pt-BR")} mints rastreados` : "rastreados: sem leitura";
}

/** Gaps and malformed socket messages in the last minute -- only when there were any (a real 0 is not a warning). */
export function minuteFlags(payload: MemeSources): string[] {
  const flags: string[] = [];
  if (isNum(payload.gaps_60s) && payload.gaps_60s > 0) flags.push(`${payload.gaps_60s} gap(s) no último minuto`);
  if (isNum(payload.ws_malformed_60s) && payload.ws_malformed_60s > 0) flags.push(`${payload.ws_malformed_60s} mensagem(ns) malformada(s) no último minuto`);
  return flags;
}

/**
 * T4.16: the 15-second clock's own counters and the loop's decision→fill
 * latency (Everton's priority #1 -- median < 5 s, p95 < 20 s) plus the
 * running count of `indeterminate` closes. `null` (never an empty card) when
 * an older worker has not started reporting any of these yet.
 */
export function fastLaneLine(payload: MemeSources): string | null {
  const parts: string[] = [];
  if (isNum(payload.fast_lane_mints)) parts.push(`${payload.fast_lane_mints} moedas < 5 min no relógio de 15 s`);
  if (isNum(payload.fast_lane_reads_60s)) parts.push(`${payload.fast_lane_reads_60s} leituras por minuto (15 s)`);
  if (isNum(payload.fast_lane_calls_60s)) parts.push(`${payload.fast_lane_calls_60s} chamadas por minuto (15 s)`);
  if (isNum(payload.fast_lane_cycle_s)) parts.push(`ciclo do relógio de 15 s ${payload.fast_lane_cycle_s.toFixed(1)} s`);
  if (isNum(payload.lab_decision_to_fill_s_p50)) parts.push(`decisão → fill p50 (medido) ${payload.lab_decision_to_fill_s_p50.toFixed(1)} s`);
  if (isNum(payload.lab_decision_to_fill_s_p95)) parts.push(`decisão → fill p95 (medido) ${payload.lab_decision_to_fill_s_p95.toFixed(1)} s`);
  if (isNum(payload.lab_bets_indeterminate_total)) parts.push(`${payload.lab_bets_indeterminate_total} indeterminadas (total)`);
  return parts.length ? parts.join(" · ") : null;
}
