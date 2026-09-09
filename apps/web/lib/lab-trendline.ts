/**
 * Pure geometry math for the Shadow Lab's trend-line overlay (brief T3.49,
 * Everton 2026-09-08 19:45/19:50: "quero conferir visualmente se a linha
 * estava certa"). Parses `trendline_breakout_v1`'s decision envelope
 * (`agent_signals.supporting_features`, written by
 * `packages/core/hunter_core/strategies/tl_setup.py::_line_features` --
 * every Decimal field travels as a string) and re-derives the exact line the
 * decision drew. No I/O, no `lightweight-charts` import -- testable without a
 * DOM (`.claude/state/notes-T3.34c.md` §8 is the proof this data exists and
 * is complete on every one of this version's 47 real decisions).
 *
 * Any other strategy's envelope has no `line_id` at all -- `present: false`
 * below is the honest "esta versão não lê linhas" case, not an error.
 */

export interface TrendlineGeometry {
  lineKind: string | null;
  lineId: string | null;
  slopePerBar: number | null;
  touches: number | null;
  violations: number | null;
  firstIdx: number | null;
  lastIdx: number | null;
  validFromIdx: number | null;
  priceAtDecision: number | null;
  eventKind: string | null;
  eventDistanceAtr: number | null;
  pivotLowPrice: number | null;
  pivotLowIdx: number | null;
  patternBars: number | null;
  patternPivots: number | null;
  patternLines: number | null;
  patternRetiredLines: number | null;
  /** `null` exactly when `channelAvailable` is `false` (no channel found -- `unavailable_reason: "no_channel"`, a real, honest state, not a missing field). */
  channelWidthAtr: number | null;
  channelAvailable: boolean;
  patternParams: Record<string, unknown> | null;
  patternParamsRaw: string | null;
}

export interface TrendlineGeometryResult {
  /** `false` when the envelope carries no `line_id` -- this strategy version does not draw lines at all. */
  present: boolean;
  geometry: TrendlineGeometry | null;
  /** Portuguese labels of any field required to redraw the line that is absent or unparseable (brief: "no fabricated points" -- render without that element and say which one is missing). Excludes `channel_width_atr`, whose own absence is a legitimate value (`channelAvailable`). */
  missing: string[];
}

/** Every field `_line_features` always emits when `present` is true -- used both to build `TrendlineGeometry` and to report which of them failed to parse, in Portuguese. */
const TRENDLINE_FIELD_LABELS: Record<string, string> = {
  line_kind: "tipo da linha",
  line_slope_per_bar: "inclinação por barra",
  line_touches: "toques",
  line_violations: "violações",
  line_first_idx: "primeiro índice",
  line_last_idx: "último índice",
  line_valid_from_idx: "válida desde (índice)",
  line_price_at_decision: "preço da linha na decisão",
  event_kind: "tipo do evento",
  event_distance_atr: "distância do evento (ATR)",
  pivot_low_price: "preço do pivô",
  pivot_low_idx: "índice do pivô",
  pattern_bars: "barras do padrão",
};

/** One `FeatureEvidence.to_jsonable()` entry -- only `name`/`value` matter here (mirrors the SQL's own `jsonb_object_agg(name, value)`, T3.34c q05). */
interface RawFeatureEntry {
  name?: unknown;
  value?: unknown;
}

/** `{features: [{name, value}, ...]}` -> `{name -> raw value}`. `value` can legitimately be `null` (e.g. `channel_width_atr` with no channel) -- kept as `null`, never coerced. `null`/non-array input (no envelope fetched yet, or a strategy that never carries a `features` array) yields `null`, distinct from an empty map. */
export function parseFeatureMap(supportingFeatures: Record<string, unknown> | null): Map<string, unknown> | null {
  if (!supportingFeatures) return null;
  const features = supportingFeatures.features;
  if (!Array.isArray(features)) return null;
  const map = new Map<string, unknown>();
  for (const entry of features as RawFeatureEntry[]) {
    if (entry && typeof entry === "object" && typeof entry.name === "string") {
      map.set(entry.name, entry.value);
    }
  }
  return map;
}

function rawStr(map: Map<string, unknown>, key: string): string | null {
  const v = map.get(key);
  return typeof v === "string" ? v : null;
}

function rawNum(map: Map<string, unknown>, key: string): number | null {
  const v = rawStr(map, key);
  if (v === null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fieldIsUsable(map: Map<string, unknown>, key: string): boolean {
  if (key === "line_kind" || key === "event_kind") return rawStr(map, key) !== null;
  return rawNum(map, key) !== null;
}

function parsePatternParams(raw: string | null): Record<string, unknown> | null {
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** The overlay/Geometria panel's single entry point: does this decision carry a trend line, and if so, what is it (plus what could not be parsed)? */
export function extractTrendlineGeometry(supportingFeatures: Record<string, unknown> | null): TrendlineGeometryResult {
  const map = parseFeatureMap(supportingFeatures);
  if (!map || !map.has("line_id") || rawStr(map, "line_id") === null) {
    return { present: false, geometry: null, missing: [] };
  }

  const patternParamsRaw = rawStr(map, "pattern_params");
  const channelAvailable = map.has("channel_width_atr") && map.get("channel_width_atr") !== null;

  const geometry: TrendlineGeometry = {
    lineKind: rawStr(map, "line_kind"),
    lineId: rawStr(map, "line_id"),
    slopePerBar: rawNum(map, "line_slope_per_bar"),
    touches: rawNum(map, "line_touches"),
    violations: rawNum(map, "line_violations"),
    firstIdx: rawNum(map, "line_first_idx"),
    lastIdx: rawNum(map, "line_last_idx"),
    validFromIdx: rawNum(map, "line_valid_from_idx"),
    priceAtDecision: rawNum(map, "line_price_at_decision"),
    eventKind: rawStr(map, "event_kind"),
    eventDistanceAtr: rawNum(map, "event_distance_atr"),
    pivotLowPrice: rawNum(map, "pivot_low_price"),
    pivotLowIdx: rawNum(map, "pivot_low_idx"),
    patternBars: rawNum(map, "pattern_bars"),
    patternPivots: rawNum(map, "pattern_pivots"),
    patternLines: rawNum(map, "pattern_lines"),
    patternRetiredLines: rawNum(map, "pattern_retired_lines"),
    channelWidthAtr: channelAvailable ? rawNum(map, "channel_width_atr") : null,
    channelAvailable,
    patternParams: parsePatternParams(patternParamsRaw),
    patternParamsRaw,
  };

  const missing = Object.entries(TRENDLINE_FIELD_LABELS)
    .filter(([key]) => !fieldIsUsable(map, key))
    .map(([, label]) => label);

  return { present: true, geometry, missing };
}

export function lineKindLabel(kind: string | null): string {
  if (kind === "support") return "suporte";
  if (kind === "resistance") return "resistência";
  return kind ?? "desconhecido";
}

export function eventKindLabel(kind: string | null): string {
  if (kind === "bounce") return "repique";
  if (kind === "breakout") return "rompimento";
  return kind ?? "desconhecido";
}

/** `pattern_bars − 1` -- the decision bar's own index inside the pattern window (`tl_setup.py`: "`as_of = pattern_bars − 1` is the decision bar"). */
export function asOfFromPatternBars(patternBars: number): number {
  return patternBars - 1;
}

/** `idx -> bar time`, ms since epoch (T3.34c §"Data that exists": `idx → bar time = decision_bar_close − (as_of − idx) × 15 min`). `decisionBarCloseIso` is the signal's `source_bar_close`/the envelope's `observation_ts`. */
export function lineTimeMsForIdx(decisionBarCloseIso: string, asOf: number, idx: number, timeframeMinutes = 15): number {
  return new Date(decisionBarCloseIso).getTime() - (asOf - idx) * timeframeMinutes * 60_000;
}

/** The line's own price at a bar index (T3.34c §"Data that exists": `price(i) = line_price_at_decision + line_slope_per_bar × (i − as_of)`). */
export function linePriceAtIdx(priceAtDecision: number, slopePerBar: number, idx: number, asOf: number): number {
  return priceAtDecision + slopePerBar * (idx - asOf);
}

export interface LinearLine {
  priceAtDecision: number;
  slopePerBar: number;
}

/** Same rule as `linePriceAtIdx`, continuous in time rather than restricted to an integer bar index -- what the dashed continuation past the decision bar (never itself an observed touch) is drawn with. */
export function linePriceAtTimeMs(line: LinearLine, decisionBarCloseIso: string, timeMs: number, timeframeMinutes = 15): number {
  const bars = (timeMs - new Date(decisionBarCloseIso).getTime()) / (timeframeMinutes * 60_000);
  return line.priceAtDecision + line.slopePerBar * bars;
}

export interface CandleWindow {
  /** `GET .../candles?before=` -- strictly-less-than, so it must land one bar past whichever anchor (exit, or the decision bar itself) needs to stay inside the page. */
  beforeIso: string;
  limit: number;
}

/** `apps/api/hunter_api/routers/markets.py::MAX_CANDLES_LIMIT` -- kept in sync by name, not imported (that module is Python). */
const MAX_CANDLES_LIMIT = 1500;
const FORWARD_BUFFER_BARS_WITH_EXIT = 4;
const FORWARD_BUFFER_BARS_NO_EXIT = 8;

/**
 * The `?before=&limit=` window that covers the whole pattern (`patternBars`
 * bars ending at the decision bar) through the operation's own exit, with a
 * small margin so the last relevant candle is never the very last point on
 * screen. When the operation never got an exit (open/no_entry/censored), the
 * window instead extends a fixed, small amount past the decision bar itself
 * -- never "now" (which could be weeks away from a replay decision and would
 * silently fetch an irrelevant, huge page).
 */
export function computeCandleWindow(decisionBarCloseIso: string, patternBars: number, exitTsIso: string | null, timeframeMinutes = 15): CandleWindow {
  const decisionMs = new Date(decisionBarCloseIso).getTime();
  const anchorMs = exitTsIso ? new Date(exitTsIso).getTime() : decisionMs;
  const forwardBars = exitTsIso ? FORWARD_BUFFER_BARS_WITH_EXIT : FORWARD_BUFFER_BARS_NO_EXIT;
  const barMs = timeframeMinutes * 60_000;
  const beforeMs = anchorMs + (forwardBars + 1) * barMs;
  const barsFromDecisionToAnchor = Math.max(0, Math.ceil((anchorMs - decisionMs) / barMs));
  const limit = Math.max(patternBars, 1) + barsFromDecisionToAnchor + forwardBars + 2;
  return { beforeIso: new Date(beforeMs).toISOString(), limit: Math.min(limit, MAX_CANDLES_LIMIT) };
}
