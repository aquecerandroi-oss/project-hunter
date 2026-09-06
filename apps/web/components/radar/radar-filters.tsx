"use client";

import { usePathname, useRouter } from "next/navigation";

import {
  ANOMALY_TYPE_VALUES,
  MARKET_REGIME_VALUES,
  OPPORTUNITY_STAGE_VALUES,
  RADAR_STATUS_VALUES,
} from "@/lib/api/radar-types";
import type { AnomalyTypeValue, MarketRegimeValue, OpportunityStage, RadarStatusFilter } from "@/lib/api/radar-types";

export interface RadarFiltersState {
  q: string;
  scoreMin: string;
  status: RadarStatusFilter[];
  stage: OpportunityStage[];
  exchange: string;
  anomalyType: AnomalyTypeValue | "";
  regime: MarketRegimeValue | "";
  volatilityMin: string;
  volatilityMax: string;
}

export interface RadarFiltersProps {
  state: RadarFiltersState;
  hasOrg: boolean;
}

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * `/radar`'s server-side filters (brief line 9), URL-driven exactly like
 * `lab-filters.tsx`: state lives in the query string, shareable and
 * back-button-safe. Every navigation drops `cursor` (Astra's T2.7 review,
 * nice-to-have) -- a changed filter/sort invalidates whatever page the
 * trader had scrolled to.
 */
export function RadarFilters({ state, hasOrg }: RadarFiltersProps) {
  const router = useRouter();
  const pathname = usePathname();

  function navigate(next: Partial<RadarFiltersState>): void {
    const merged: RadarFiltersState = { ...state, ...next };
    const params = new URLSearchParams();
    if (merged.q) params.set("q", merged.q);
    if (merged.scoreMin) params.set("score_min", merged.scoreMin);
    for (const s of merged.status) params.append("status", s);
    for (const s of merged.stage) params.append("stage", s);
    if (merged.exchange) params.set("exchange", merged.exchange);
    if (merged.anomalyType) params.set("anomaly_type", merged.anomalyType);
    if (merged.regime) params.set("regime", merged.regime);
    if (merged.volatilityMin) params.set("volatility_min", merged.volatilityMin);
    if (merged.volatilityMax) params.set("volatility_max", merged.volatilityMax);
    router.push(`${pathname}?${params.toString()}`);
  }

  const statusOptions = hasOrg ? RADAR_STATUS_VALUES : RADAR_STATUS_VALUES.filter((s) => s !== "IN_POSITION" && s !== "RISK_BLOCKED");

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-bg-elevated p-3 text-sm">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Buscar símbolo</span>
          <input
            type="search"
            defaultValue={state.q}
            onBlur={(e) => navigate({ q: e.target.value.trim() })}
            aria-label="Buscar símbolo no radar"
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
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Regime</span>
          <select
            value={state.regime}
            onChange={(e) => navigate({ regime: e.target.value as MarketRegimeValue | "" })}
            className="h-8 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          >
            <option value="">Todos</option>
            {MARKET_REGIME_VALUES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Tipo de anomalia</span>
          <select
            value={state.anomalyType}
            onChange={(e) => navigate({ anomalyType: e.target.value as AnomalyTypeValue | "" })}
            className="h-8 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          >
            <option value="">Todos</option>
            {ANOMALY_TYPE_VALUES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Volatilidade min</span>
          <input
            type="number"
            step="0.01"
            defaultValue={state.volatilityMin}
            onBlur={(e) => navigate({ volatilityMin: e.target.value })}
            aria-label="Volatilidade mínima"
            className="h-8 w-24 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-fg-muted">Volatilidade max</span>
          <input
            type="number"
            step="0.01"
            defaultValue={state.volatilityMax}
            onBlur={(e) => navigate({ volatilityMax: e.target.value })}
            aria-label="Volatilidade máxima"
            className="h-8 w-24 rounded-md border border-border bg-bg-overlay px-2 text-[13px] text-fg"
          />
        </label>
      </div>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="text-xs text-fg-muted">Status</legend>
        {statusOptions.map((s) => (
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
