/**
 * The overview strip (brief T4.3): coins created 24h/7d, Mayhem active,
 * graduations 24h -- each with its own `observed_at`/source, per
 * `MemeOverviewOut`'s two possible shapes. Never a fabricated number: a
 * `null` count renders "sem dado" with why, not a blank or a `0`.
 */
import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { MemeOverview } from "@/lib/api/meme-types";

function Stat({ label, value, footnote }: { label: string; value: string; footnote?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-fg-muted">{label}</span>
      <span className="text-2xl font-semibold tabular-nums text-fg">{value}</span>
      {footnote && <span className="text-[11px] text-fg-subtle">{footnote}</span>}
    </div>
  );
}

function countLabel(value: number | null): string {
  return value === null ? "sem dado" : value.toLocaleString("pt-BR");
}

export interface MemeOverviewStripProps {
  overview: MemeOverview;
}

export function MemeOverviewStrip({ overview }: MemeOverviewStripProps) {
  const sourceNote =
    overview.source === "meme_tokens"
      ? `fonte: seu radar (${overview.graduations_24h.tracked_tokens} token(s) rastreado(s))`
      : "fonte: pump.fun (mercado inteiro, não é o seu radar)";

  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs text-fg-muted">
          Só monitoramento — sem execução. {sourceNote}, consultado em <BrasiliaInstant iso={overview.observed_at} />.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Criados (24h)" value={countLabel(overview.coins_created_24h)} />
        <Stat label="Criados (7d)" value={countLabel(overview.coins_created_7d)} />
        <Stat label="Mayhem ativos" value={countLabel(overview.mayhem_active_coins)} />
        <Stat
          label="Graduações (24h)"
          value={countLabel(overview.graduations_24h.count)}
          footnote={
            overview.graduations_24h.reason
              ? `sem dado: ${overview.graduations_24h.reason}`
              : `de ${overview.graduations_24h.tracked_tokens} rastreado(s)`
          }
        />
      </div>
      {overview.coins_created_by_mode && (
        <p className="text-[11px] text-fg-subtle">
          Por modo (pump.fun, mercado inteiro): auto {overview.coins_created_by_mode.auto.last_24h.toLocaleString("pt-BR")} · manual{" "}
          {overview.coins_created_by_mode.manual.last_24h.toLocaleString("pt-BR")} (24h)
        </p>
      )}
    </section>
  );
}
