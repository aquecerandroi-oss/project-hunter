import { REGIME_LABEL } from "@/components/radar/labels";
import { BrasiliaInstant, BrasiliaShort } from "@/components/time/brasilia-instant";
import { Badge } from "@/components/ui/badge";
import { isApiError } from "@/lib/api-error";
import { getCurrentRegime } from "@/lib/api/regime";
import { REGIME_SCOPE_LABELS } from "@/lib/api/regime-types";
import type { RegimeComponentOut, RegimeOut } from "@/lib/api/regime-types";
import { BRASILIA_LABEL } from "@/lib/time";
import { logger } from "@/lib/logger";

export type RegimeTileLoad = { ok: true; items: RegimeOut[]; asOf: string } | { ok: false };

/** T3.43b's five-line decomposition, pt-BR (D19: no raw component name on screen). */
const COMPONENT_LABEL: Record<string, string> = {
  trend: "Tendência",
  breadth: "Amplitude",
  volatility: "Volatilidade",
  drawdown: "Drawdown",
  funding: "Funding",
};

function componentLabel(name: string): string {
  return COMPONENT_LABEL[name] ?? name;
}

/** "62" from the API's "62.00" -- the tile shows a whole number over 100, never a fabricated extra decimal. `null`/`undefined` (a `regime_v0` row, or the engine could not score the hour) stays `null`, never "0". */
function formatScore(score: string | null | undefined): string | null {
  if (score == null) return null;
  const value = Number(score);
  return Number.isFinite(value) ? String(Math.round(value)) : null;
}

/** pt-BR comma, 1-2 fraction digits: "0.8000" -> "0,8", "0.7500" -> "0,75" (D17). */
function formatConfidencePtBr(value: string | null | undefined): string | null {
  if (value == null) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 }).format(num);
}

/** A component's contribution, in the score's own 0-100 points -- pt-BR, one decimal. `null`/`undefined` (no usable input that hour) is never displayed as "0". */
function formatContribution(value: string | null | undefined): string | null {
  if (value == null) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(num);
}

/** "35%" from the version's fixed weight (0.35) -- always a round tens figure in `regime_hourly_v1`, so zero fraction digits never rounds away real precision. */
function formatWeightPct(value: string): string | null {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 0 }).format(num);
}

/**
 * "há 12min" since `iso` -- a static read at render time (this tile is a
 * Server Component; unlike Radar/Markets' ticking freshness labels, a
 * dashboard summary re-rendering on the page's own refresh is enough, and
 * pulling in `hooks/useAgeTicker.ts`'s client boundary for one static number
 * is not worth it). `null` on a missing/unparseable/future timestamp --
 * never a negative or garbage age.
 */
function formatAgeSince(iso: string | null | undefined): string | null {
  if (iso == null) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const ms = Date.now() - then;
  if (ms < 0) return null;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h`;
}

/**
 * "Regime atual" (brief line 12) -- one row per `RegimeScope`
 * (`global`/`btc`, `.claude/state/notes-T2.6.md`), each with its own
 * `is_stale`. `MarketRegime.UNKNOWN` is a real classification (classifier
 * warm-up), never hidden or confused with a missing value.
 *
 * T3.43b: a row whose `identity` is set (`regime_hourly_v1…`) carries the
 * hourly engine's own score/confidence/five-component decomposition, on top
 * of the same `scope`/`regime`/`is_stale` every row already had --
 * `identity`/`score`/`components`/`as_of` are `null`/`[]` for `regime_v0`
 * (`global`), never fabricated.
 */
export async function loadRegimeTile(): Promise<RegimeTileLoad> {
  try {
    const current = await getCurrentRegime();
    return { ok: true, items: current.items, asOf: current.as_of };
  } catch (error) {
    const reason = isApiError(error) ? (error.detail ?? error.message) : "erro desconhecido";
    logger.error("dashboard_regime_tile_failed", { error: reason });
    return { ok: false };
  }
}

function RegimeComponentsDetail({ components }: { components: RegimeComponentOut[] }) {
  if (components.length === 0) return null;
  return (
    <details className="mt-1 rounded-md border border-border/60 bg-bg-overlay/50">
      <summary className="cursor-pointer px-2 py-1 text-[11px] text-fg-muted">
        {components.length} componentes do score
      </summary>
      <ul className="flex flex-col gap-1 px-2 pb-2 text-xs">
        {components.map((component) => {
          const contribution = formatContribution(component.contribution);
          const weight = formatWeightPct(component.weight);
          return (
            <li key={component.name} className="flex items-center justify-between gap-3">
              <span className="text-fg-muted">{componentLabel(component.name)}</span>
              <span className="font-mono tabular-nums text-fg-subtle">
                {contribution !== null ? `${contribution} pts` : "sem leitura"}
                {weight !== null && <span className="ml-1">(peso {weight})</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

/** "score 62/100 · confiança 0,8" -- either half may be absent (a `regime_v0` row has neither; an hourly row the engine could not score has no `score` but keeps `confidence`), so this renders only the halves it actually has. */
function RegimeScoreConfidence({ score, confidence }: { score: string | null; confidence: string | null }) {
  if (score === null && confidence === null) return null;
  const parts = [score !== null ? `score ${score}/100` : null, confidence !== null ? `confiança ${confidence}` : null];
  return <span className="font-mono tabular-nums text-xs text-fg-muted">{parts.filter(Boolean).join(" · ")}</span>;
}

/** "hora 15:00 Brasília · atualizado há 12min" -- only for the hourly engine's own rows (`identity` set), whose `as_of` is the hour itself. */
function RegimeHourLine({ asOf }: { asOf: string }) {
  const age = formatAgeSince(asOf);
  return (
    <p className="text-[11px] text-fg-subtle">
      hora <BrasiliaShort iso={asOf} className="font-mono tabular-nums" /> {BRASILIA_LABEL}
      {age !== null && ` · atualizado há ${age}`}
    </p>
  );
}

function RegimeRow({ item }: { item: RegimeOut }) {
  const regimeLabel = REGIME_LABEL[item.regime] ?? item.regime;
  const isHourly = item.identity != null;
  const score = isHourly ? formatScore(item.score) : null;
  const confidence = isHourly ? formatConfidencePtBr(item.confidence) : null;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-xs text-fg-muted">{REGIME_SCOPE_LABELS[item.scope]}</span>
        <span className="font-medium text-fg">{regimeLabel}</span>
        <RegimeScoreConfidence score={score} confidence={confidence} />
        {item.is_stale && <Badge variant="warning">stale</Badge>}
      </div>
      {isHourly && item.as_of != null && <RegimeHourLine asOf={item.as_of} />}
      {isHourly && <RegimeComponentsDetail components={item.components} />}
    </div>
  );
}

export function RegimeTile({ result }: { result: RegimeTileLoad }) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Regime atual</h2>
      {!result.ok ? (
        <p className="mt-1 text-sm text-fg-muted">sem verificação</p>
      ) : result.items.length === 0 ? (
        <p className="mt-1 text-sm text-fg-muted">
          0 regimes classificados · verificado <BrasiliaInstant iso={result.asOf} />
        </p>
      ) : (
        <div className="mt-1 flex flex-col gap-2">
          {result.items.map((item) => (
            <RegimeRow key={item.id} item={item} />
          ))}
          <p className="mt-1 text-[11px] text-fg-subtle">
            verificado <BrasiliaInstant iso={result.asOf} />
          </p>
        </div>
      )}
    </section>
  );
}
