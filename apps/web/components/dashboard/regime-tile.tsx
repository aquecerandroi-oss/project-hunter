import { Badge } from "@/components/ui/badge";
import { isApiError } from "@/lib/api-error";
import { getCurrentRegime } from "@/lib/api/regime";
import { REGIME_SCOPE_LABELS } from "@/lib/api/regime-types";
import type { RegimeOut } from "@/lib/api/regime-types";
import { formatUtc } from "@/lib/format";
import { logger } from "@/lib/logger";

export type RegimeTileLoad = { ok: true; items: RegimeOut[]; asOf: string } | { ok: false };

/**
 * "Regime atual" (brief line 12) -- one row per `RegimeScope`
 * (`global`/`btc`, `.claude/state/notes-T2.6.md`), each with its own
 * `is_stale`. `MarketRegime.UNKNOWN` is a real classification (classifier
 * warm-up), never hidden or confused with a missing value.
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

export function RegimeTile({ result }: { result: RegimeTileLoad }) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4 transition-colors hover:border-border-strong">
      <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Regime atual</h2>
      {!result.ok ? (
        <p className="mt-1 text-sm text-fg-muted">sem verificação</p>
      ) : result.items.length === 0 ? (
        <p className="mt-1 text-sm text-fg-muted">0 regimes classificados · verificado {formatUtc(result.asOf)}</p>
      ) : (
        <div className="mt-1 flex flex-col gap-1">
          {result.items.map((item) => (
            <div key={item.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-xs text-fg-muted">{REGIME_SCOPE_LABELS[item.scope]}</span>
              <span className="font-medium text-fg">{item.regime}</span>
              {item.is_stale && <Badge variant="warning">stale</Badge>}
            </div>
          ))}
          <p className="mt-1 text-[11px] text-fg-subtle">verificado {formatUtc(result.asOf)}</p>
        </div>
      )}
    </section>
  );
}
