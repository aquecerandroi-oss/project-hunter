"use client";

import { usePathname, useRouter } from "next/navigation";

import { OPPORTUNITY_STAGE_VALUES } from "@/lib/api/radar-types";
import type { OpportunityStage, OpportunityStatus } from "@/lib/api/radar-types";

const STATUS_VALUES: OpportunityStatus[] = ["NORMAL", "WATCHING", "ANOMALY", "HOT", "ENTRY_CANDIDATE", "EXTENDED", "EXPIRED"];
const HOT_QUICK_FILTER: OpportunityStatus[] = ["HOT", "ENTRY_CANDIDATE"];

export interface OpportunitiesFiltersState {
  q: string;
  scoreMin: string;
  status: OpportunityStatus[];
  stage: OpportunityStage[];
  exchange: string;
}

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v) => b.includes(v));
}

/**
 * `/opportunities`'s filters -- narrower than `/radar`'s (no anomaly_type,
 * regime, volatility: `routers/opportunities.py::list_opportunities` does
 * not accept them, `.claude/state/notes-T2.6.md`). Includes a removable
 * "Só HOT/ENTRY_CANDIDATE" quick toggle instead of permanently restricting
 * the index to those statuses (Astra's T2.7 review: "ofereceria esse recorte
 * como filtro explícito, removível").
 */
export function OpportunitiesFilters({ state }: { state: OpportunitiesFiltersState }) {
  const router = useRouter();
  const pathname = usePathname();

  function navigate(next: Partial<OpportunitiesFiltersState>): void {
    const merged: OpportunitiesFiltersState = { ...state, ...next };
    const params = new URLSearchParams();
    if (merged.q) params.set("q", merged.q);
    if (merged.scoreMin) params.set("score_min", merged.scoreMin);
    for (const s of merged.status) params.append("status", s);
    for (const s of merged.stage) params.append("stage", s);
    if (merged.exchange) params.set("exchange", merged.exchange);
    router.push(`${pathname}?${params.toString()}`);
  }

  const hotOnly = sameSet(state.status, HOT_QUICK_FILTER);

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-bg-elevated p-3 text-sm">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Buscar símbolo</span>
          <input
            type="search"
            defaultValue={state.q}
            onBlur={(e) => navigate({ q: e.target.value.trim() })}
            aria-label="Buscar símbolo"
            className="h-8 w-40 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Score mínimo</span>
          <input
            type="number"
            min={0}
            max={100}
            defaultValue={state.scoreMin}
            onBlur={(e) => navigate({ scoreMin: e.target.value })}
            aria-label="Score mínimo"
            className="h-8 w-24 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Exchange</span>
          <input
            type="text"
            defaultValue={state.exchange}
            onBlur={(e) => navigate({ exchange: e.target.value.trim() })}
            aria-label="Exchange"
            className="h-8 w-28 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          />
        </label>
        <label className="flex items-center gap-1 text-xs text-fg">
          <input type="checkbox" checked={hotOnly} onChange={() => navigate({ status: hotOnly ? [] : HOT_QUICK_FILTER })} />
          Só HOT / ENTRY_CANDIDATE
        </label>
      </div>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="text-xs text-fg-muted">Status</legend>
        {STATUS_VALUES.map((s) => (
          <label key={s} className="flex items-center gap-1 text-xs text-fg">
            <input type="checkbox" checked={state.status.includes(s)} onChange={() => navigate({ status: toggle(state.status, s) })} />
            {s}
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="text-xs text-fg-muted">Estágio</legend>
        {OPPORTUNITY_STAGE_VALUES.map((s) => (
          <label key={s} className="flex items-center gap-1 text-xs text-fg">
            <input type="checkbox" checked={state.stage.includes(s)} onChange={() => navigate({ stage: toggle(state.stage, s) })} />
            {s}
          </label>
        ))}
      </fieldset>
    </div>
  );
}
