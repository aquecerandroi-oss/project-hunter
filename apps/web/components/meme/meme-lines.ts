/**
 * T4.10b: the trend lines of a meme's bonding curve as the screen reads them
 * -- pure, unit-tested in `tests/meme-lines.test.ts`. The backend computes
 * the lines as features (`meme_features_v3`, brief T4.10 §Contrato: support
 * through the last two local lows, the 15-minute high, breakout against the
 * *previous* window, `higher_lows`, `line_reason` when null); this module only
 * turns those columns into segments in data space (time in ms, mcap in SOL)
 * for `meme-curve-chart.tsx` to scale, and into the sentences the brief asks
 * for. Nothing here draws a line the backend did not compute.
 *
 * Tolerance: the columns land in parallel with this screen, so every field
 * is read by key. A payload without any of them is `absent` ("linha: sem
 * leitura") -- distinct from `untraceable` (the columns exist, the line does
 * not, and `line_reason` says why).
 */
import type { MemeFeaturePoint } from "@/lib/api/meme-types";
import { formatPct } from "@/lib/format";

import { MEME_HYPE_NO_READING, MEME_LINE_NO_READING, memeHypeMissingText, memeHypeReasonLabel, memeLineUntraceableText } from "./labels";
import { formatRatio, formatSol } from "./meme-format";

/** W = 15 minutes (contract): the window the lows, the high and the slope are measured over. */
export const LINE_WINDOW_MS = 15 * 60_000;
const MINUTE_MS = 60_000;

const LINE_KEYS = [
  "support_line_sol",
  "support_line_slope",
  "high_15m_sol",
  "low_15m_sol",
  "breakout_15m",
  "higher_lows",
  "distance_to_support_pct",
  "line_points",
  "line_reason",
  "mcap_slope_5m",
  "mcap_slope_15m",
] as const;

export interface LineFields {
  /** Any of the contract's line columns exists on the row (even as null). */
  present: boolean;
  supportLineSol: string | null;
  /** SOL per minute. */
  supportLineSlope: string | null;
  high15mSol: string | null;
  low15mSol: string | null;
  breakout15m: boolean | null;
  higherLows: boolean | null;
  distanceToSupportPct: string | null;
  linePoints: number | null;
  lineReason: string | null;
  mcapSlope5m: string | null;
  mcapSlope15m: string | null;
}

function field(row: object, key: string): unknown {
  return (row as Record<string, unknown>)[key];
}

/** A `Decimal` arrives as a string (CLAUDE.md); a number is tolerated as its text, never re-rounded. */
function decimalOf(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function boolOf(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function intOf(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function textOf(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function readLineFields(row: object): LineFields {
  return {
    present: LINE_KEYS.some((key) => Object.hasOwn(row, key)),
    supportLineSol: decimalOf(field(row, "support_line_sol")),
    supportLineSlope: decimalOf(field(row, "support_line_slope")),
    high15mSol: decimalOf(field(row, "high_15m_sol")),
    low15mSol: decimalOf(field(row, "low_15m_sol")),
    breakout15m: boolOf(field(row, "breakout_15m")),
    higherLows: boolOf(field(row, "higher_lows")),
    distanceToSupportPct: decimalOf(field(row, "distance_to_support_pct")),
    linePoints: intOf(field(row, "line_points")),
    lineReason: textOf(field(row, "line_reason")),
    mcapSlope5m: decimalOf(field(row, "mcap_slope_5m")),
    mcapSlope15m: decimalOf(field(row, "mcap_slope_15m")),
  };
}

export type LineReading =
  | { kind: "absent" }
  | { kind: "untraceable"; reason: string | null }
  | {
      kind: "traced";
      /** The API's decimal string, for display -- never re-rendered from the float below. */
      supportLineSol: string;
      /** The same value as a number, for geometry only. */
      supportSol: number;
      slopePerMinute: number;
      higherLows: boolean | null;
      breakout: boolean | null;
      distanceToSupportPct: string | null;
      linePoints: number | null;
    };

function numberOf(value: string | null): number | null {
  if (value === null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function lineReading(fields: LineFields): LineReading {
  if (!fields.present) return { kind: "absent" };
  const supportSol = numberOf(fields.supportLineSol);
  if (supportSol === null || fields.supportLineSol === null) return { kind: "untraceable", reason: fields.lineReason };
  return {
    kind: "traced",
    supportLineSol: fields.supportLineSol,
    supportSol,
    slopePerMinute: numberOf(fields.supportLineSlope) ?? 0,
    higherLows: fields.higherLows,
    breakout: fields.breakout15m,
    distanceToSupportPct: fields.distanceToSupportPct,
    linePoints: fields.linePoints,
  };
}

function yesNo(value: boolean | null): string {
  if (value === null) return "sem leitura";
  return value ? "sim" : "não";
}

/** One sentence per state -- the caption under the chart and the collapsed cell in the table. */
export function lineReadingText(reading: LineReading): string {
  if (reading.kind === "absent") return MEME_LINE_NO_READING;
  if (reading.kind === "untraceable") return memeLineUntraceableText(reading.reason);
  const parts = [`suporte ${formatSol(reading.supportLineSol)}`];
  if (reading.distanceToSupportPct !== null) parts.push(`distância ao suporte ${formatPct(reading.distanceToSupportPct, { signed: true })}`);
  parts.push(`fundos ascendentes: ${yesNo(reading.higherLows)}`);
  parts.push(`rompimento 15 min: ${yesNo(reading.breakout)}`);
  return parts.join(" · ");
}

export interface ChartSpan {
  minX: number;
  maxX: number;
}

export interface SupportSegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  higherLows: boolean | null;
}

/**
 * The line through the last two lows, as the backend fixed it at the latest
 * minute (`support_line_sol` at `end_time`, `support_line_slope` in SOL/min),
 * drawn from the window's edge and projected to the chart's now:
 * `y(t) = support + slope × (t − end_time) / 1 min`.
 */
export function supportSegment(fields: LineFields, endMs: number, span: ChartSpan): SupportSegment | null {
  const support = numberOf(fields.supportLineSol);
  if (support === null) return null;
  const slope = numberOf(fields.supportLineSlope) ?? 0;
  const x1 = Math.max(span.minX, endMs - LINE_WINDOW_MS);
  const x2 = span.maxX;
  if (x1 >= x2) return null;
  const at = (t: number): number => support + (slope * (t - endMs)) / MINUTE_MS;
  return { x1, y1: at(x1), x2, y2: at(x2), higherLows: fields.higherLows };
}

export interface HorizontalLine {
  x1: number;
  x2: number;
  y: number;
  /** The API's decimal string of `y`, for display. */
  yText: string;
}

/** `high_15m_sol` of the *previous* minute -- the level `breakout_15m` compares against (the contract excludes the current minute). */
export function previousHighLine(previous: LineFields | null, previousEndMs: number | null, span: ChartSpan): HorizontalLine | null {
  if (previous === null || previousEndMs === null) return null;
  const y = numberOf(previous.high15mSol);
  if (y === null || previous.high15mSol === null) return null;
  const x1 = Math.max(span.minX, previousEndMs - LINE_WINDOW_MS);
  const x2 = span.maxX;
  if (x1 >= x2) return null;
  return { x1, x2, y, yText: previous.high15mSol };
}

export interface BreakoutMark {
  x: number;
  /** The minute's mcap, else the broken high; `null` with `unplaced` when neither exists. */
  y: number | null;
  unplaced: boolean;
}

export function breakoutMark(row: Pick<MemeFeaturePoint, "mcap_sol">, fields: LineFields, endMs: number, previousHigh: HorizontalLine | null): BreakoutMark | null {
  if (fields.breakout15m !== true) return null;
  const y = numberOf(row.mcap_sol) ?? previousHigh?.y ?? null;
  return { x: endMs, y, unplaced: y === null };
}

export interface LatestTwo {
  latest: MemeFeaturePoint | null;
  previous: MemeFeaturePoint | null;
}

/** The API sends newest-first; a caller may have reversed it. Sort by `end_time` instead of trusting either. */
export function latestTwo(features: readonly MemeFeaturePoint[]): LatestTwo {
  const sorted = [...features].sort((a, b) => Date.parse(b.end_time) - Date.parse(a.end_time));
  return { latest: sorted[0] ?? null, previous: sorted[1] ?? null };
}

export interface HypeReading {
  present: boolean;
  score: string | null;
  reason: string | null;
}

export function readHype(row: object): HypeReading {
  return {
    present: Object.hasOwn(row, "hype_score") || Object.hasOwn(row, "hype_reason"),
    score: decimalOf(field(row, "hype_score")),
    reason: textOf(field(row, "hype_reason")),
  };
}

/** "hype 0.72", "hype 0.60 · só uma das duas fontes (fita ou board)", "sem hype: <motivo>", "hype: sem leitura". */
export function hypeText(hype: HypeReading): string {
  if (hype.score !== null) {
    const base = `hype ${formatRatio(hype.score)}`;
    return hype.reason ? `${base} · ${memeHypeReasonLabel(hype.reason)}` : base;
  }
  if (!hype.present) return MEME_HYPE_NO_READING;
  return memeHypeMissingText(hype.reason);
}

export interface LineOverlay {
  reading: LineReading;
  support: SupportSegment | null;
  previousHigh: HorizontalLine | null;
  breakout: BreakoutMark | null;
  higherLows: boolean | null;
  hype: HypeReading;
}

/** Everything the chart draws and captions, from the feature series alone; `span` is the chart's drawn time range (`null` when the curve itself cannot be drawn). */
export function lineOverlay(features: readonly MemeFeaturePoint[], span: ChartSpan | null): LineOverlay {
  const { latest, previous } = latestTwo(features);
  if (latest === null) return { reading: { kind: "absent" }, support: null, previousHigh: null, breakout: null, higherLows: null, hype: { present: false, score: null, reason: null } };
  const fields = readLineFields(latest);
  const reading = lineReading(fields);
  const hype = readHype(latest);
  if (span === null) return { reading, support: null, previousHigh: null, breakout: null, higherLows: fields.higherLows, hype };
  const endMs = Date.parse(latest.end_time);
  const previousHigh = previousHighLine(previous ? readLineFields(previous) : null, previous ? Date.parse(previous.end_time) : null, span);
  return {
    reading,
    support: supportSegment(fields, endMs, span),
    previousHigh,
    breakout: breakoutMark(latest, fields, endMs, previousHigh),
    higherLows: fields.higherLows,
    hype,
  };
}
