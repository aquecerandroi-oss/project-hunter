/**
 * Defensive adapter over `opportunities.decomposition`/`explanation`/
 * `feature_snapshot` (`dict[str, Any]` on the wire -- `schemas/opportunities.py`
 * module docstring: their shape is owned by `hunter_indicators.opportunity`
 * and the scanner-worker, not this API contract). Reads the REAL, current
 * shape from the source of truth on disk today
 * (`packages/indicators/hunter_indicators/opportunity/{model,explanation,envelope}.py`
 * -- `ScoreResult.decomposition()`, `explain()`, `opportunity_envelope()`),
 * never a guessed one, per Astra's T2.7 review ("não inventaria um formato
 * reconhecível"). Every parser fails closed to `{recognized: false, raw}`
 * instead of throwing or fabricating zeros -- a producer-format drift shows
 * the raw JSON, never a silently wrong chart.
 */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | null {
  return typeof value === "string" ? value : typeof value === "number" ? String(value) : null;
}

function bool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function num(value: unknown, fallback: number): number {
  return typeof value === "number" ? value : fallback;
}

export interface ParsedInputScore {
  feature: string;
  available: boolean;
  value: string | null;
  baseline: string | null;
  deviation: string | null;
  severity: string | null;
  maturity: string | null;
  direction: string;
  reason: string | null;
}

function parseInput(raw: unknown): ParsedInputScore | null {
  if (!isRecord(raw) || typeof raw.feature !== "string") return null;
  return {
    feature: raw.feature,
    available: bool(raw.available, false),
    value: str(raw.value),
    baseline: str(raw.baseline),
    deviation: str(raw.deviation),
    severity: str(raw.severity),
    maturity: str(raw.maturity),
    direction: str(raw.direction) ?? "neutral",
    reason: str(raw.reason),
  };
}

export interface ParsedComponent {
  name: string;
  kind: string;
  weight: string;
  raw: string | null;
  normalized: string | null;
  contribution: string;
  confidence: string;
  direction: string;
  expected: number;
  used: number;
  available: boolean;
  reason: string | null;
  inputs: ParsedInputScore[];
  notImplemented: Record<string, string>;
}

/**
 * `weight`/`contribution`/`confidence` are never absent on a real
 * `ComponentScore.as_wire()` (`opportunity/model.py:201`) -- unlike
 * `raw`/`normalized`, which are legitimately `None` for an unavailable
 * component. A component object missing any of the three is not a real
 * component in an unusual state, it is a producer-format drift: this
 * returns `null` for it rather than inventing `"0"`, which would render an
 * incompatible payload as if it were a real, zero-weighted component
 * (Astra's T2.7 diff review, must-fix 5).
 */
function parseComponent(raw: unknown): ParsedComponent | null {
  if (!isRecord(raw) || typeof raw.name !== "string") return null;
  if (typeof raw.weight !== "string" || typeof raw.contribution !== "string" || typeof raw.confidence !== "string") return null;
  const inputs = Array.isArray(raw.inputs) ? raw.inputs.map(parseInput).filter((v): v is ParsedInputScore => v !== null) : [];
  const notImplemented: Record<string, string> = {};
  if (isRecord(raw.not_implemented)) {
    for (const [k, v] of Object.entries(raw.not_implemented)) if (typeof v === "string") notImplemented[k] = v;
  }
  return {
    name: raw.name,
    kind: str(raw.kind) ?? "mad",
    weight: raw.weight,
    raw: str(raw.raw),
    normalized: str(raw.normalized),
    contribution: raw.contribution,
    confidence: raw.confidence,
    direction: str(raw.direction) ?? "neutral",
    expected: num(raw.expected, 0),
    used: num(raw.used, 0),
    available: bool(raw.available, false),
    reason: str(raw.reason),
    inputs,
    notImplemented,
  };
}

export interface ParsedEarlyMovement {
  e: number;
  magnitude: string;
  contribution: string;
  stage: string;
  stageDirection: string;
  reason: string | null;
}

function parseEarlyMovement(raw: unknown): ParsedEarlyMovement {
  if (!isRecord(raw)) return { e: 0, magnitude: "0", contribution: "0", stage: "NONE", stageDirection: "neutral", reason: null };
  return {
    e: num(raw.e, 0),
    magnitude: str(raw.magnitude) ?? "0",
    contribution: str(raw.contribution) ?? "0",
    stage: str(raw.stage) ?? "NONE",
    stageDirection: str(raw.stage_direction) ?? "neutral",
    reason: str(raw.reason),
  };
}

export interface ParsedDecomposition {
  recognized: true;
  scorerVersion: string | null;
  weightsVersion: string | null;
  eligible: boolean;
  reason: string | null;
  score: string | null;
  confidence: string;
  direction: string;
  directionReason: string | null;
  /** `ScoreResult.agreement: Decimal | None` (`opportunity/model.py:256`) -- `null` means "nothing to agree on", a fact distinct from `"0"` (a real standoff). Never fabricated. */
  agreement: string | null;
  earlyMovement: ParsedEarlyMovement;
  components: ParsedComponent[];
  baselineIds: string[];
}

export type DecompositionResult = ParsedDecomposition | { recognized: false; raw: Record<string, unknown> };

/**
 * `ScoreResult.decomposition()` (`opportunity/model.py:268`) -- fails closed
 * to `{recognized: false}` when `components` is missing/not an array, OR
 * when any single component in it fails to parse (Astra's T2.7 diff review,
 * must-fix 5): a partially-malformed decomposition is not a real one with a
 * gap, it is a format the UI does not understand, and showing the components
 * that happen to parse would understate the picture without saying so.
 */
export function parseDecomposition(raw: Record<string, unknown>): DecompositionResult {
  if (!Array.isArray(raw.components)) return { recognized: false, raw };
  const parsed = raw.components.map(parseComponent);
  if (parsed.some((c) => c === null)) return { recognized: false, raw };
  const components = parsed as ParsedComponent[];
  return {
    recognized: true,
    scorerVersion: str(raw.scorer_version),
    weightsVersion: str(raw.weights_version),
    eligible: bool(raw.eligible, true),
    reason: str(raw.reason),
    score: str(raw.score),
    confidence: str(raw.confidence) ?? "0",
    direction: str(raw.direction) ?? "neutral",
    directionReason: str(raw.direction_reason),
    agreement: str(raw.agreement),
    earlyMovement: parseEarlyMovement(raw.early_movement),
    components,
    baselineIds: Array.isArray(raw.baseline_ids) ? raw.baseline_ids.filter((v): v is string => typeof v === "string") : [],
  };
}

export interface ParsedSentence {
  codigo: string;
  texto: string;
}

export interface ParsedExplanation {
  recognized: true;
  resumo: string;
  frases: ParsedSentence[];
}

export type ExplanationResult = ParsedExplanation | { recognized: false; raw: Record<string, unknown> };

/** `explain()` (`opportunity/explanation.py:217`) -- pt-BR sentences, verbatim from the API, never re-translated here. */
export function parseExplanation(raw: Record<string, unknown>): ExplanationResult {
  if (typeof raw.resumo !== "string" || !Array.isArray(raw.frases)) return { recognized: false, raw };
  const frases: ParsedSentence[] = raw.frases
    .filter(isRecord)
    .filter((f): f is Record<string, unknown> & { codigo: string; texto: string } => typeof f.codigo === "string" && typeof f.texto === "string")
    .map((f) => ({ codigo: f.codigo, texto: f.texto }));
  return { recognized: true, resumo: raw.resumo, frases };
}

export interface ParsedFeature {
  key: string;
  value: string | null;
  quality: string;
  reason: string | null;
}

export type FeatureSnapshotResult =
  | { recognized: true; features: ParsedFeature[]; source: "vector" | "features" }
  | { recognized: false; raw: Record<string, unknown> };

/**
 * `null` when `values` itself isn't a record, or the moment any single entry
 * in it isn't (Astra's T2.7 diff review, must-fix 5) -- an incompatible
 * entry used to be silently skipped, which could turn a genuinely broken
 * vector into an empty-but-"recognized" table instead of the honest
 * unrecognized-format fallback.
 */
function parseValuesMap(values: unknown): ParsedFeature[] | null {
  if (!isRecord(values)) return null;
  const out: ParsedFeature[] = [];
  for (const [key, entry] of Object.entries(values)) {
    if (!isRecord(entry)) return null;
    out.push({ key, value: str(entry.value), quality: str(entry.quality) ?? "unavailable", reason: str(entry.reason) });
  }
  return out;
}

/**
 * `opportunities.feature_snapshot` -- tries the REAL shape written by
 * `opportunity_envelope()` (`feature_snapshot.vector.values`,
 * `FeatureVector.as_wire()`) first, then the shape
 * `.claude/state/notes-T2.6.md` assumed while T2.4 was still in flight
 * (`feature_snapshot.features.values`), so this keeps working whichever one
 * the scanner-worker ends up writing. Neither present: raw JSON, never a
 * fabricated empty table.
 */
export function parseFeatureSnapshot(raw: Record<string, unknown>): FeatureSnapshotResult {
  if (isRecord(raw.vector)) {
    const features = parseValuesMap(raw.vector.values);
    if (features) return { recognized: true, features, source: "vector" };
  }
  if (isRecord(raw.features)) {
    const features = parseValuesMap(raw.features.values);
    if (features) return { recognized: true, features, source: "features" };
  }
  return { recognized: false, raw };
}
