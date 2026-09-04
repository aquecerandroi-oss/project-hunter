"use client";

import type { WizardData } from "@/components/onboarding/wizard-state";
import { CAPITAL_PRESETS, MIN_VIRTUAL_CAPITAL, virtualCapitalSchema } from "@/lib/api/schemas";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface StepCapitalProps {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}

/** Onboarding step 3 (docs/PRODUCT.md §3.3) -- virtual capital, ≥ 1000, presets + custom. */
export function StepCapital({ data, onChange }: StepCapitalProps) {
  const valid = virtualCapitalSchema.safeParse(data.virtualCapital).success;
  const isPreset = (CAPITAL_PRESETS as readonly number[]).includes(Number(data.virtualCapital));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Capital virtual</h2>
        <p className="mt-1 text-sm text-muted">
          Vira o capital inicial padrão dos portfolios paper (a partir do Milestone 3). Mínimo de{" "}
          {formatMoney(MIN_VIRTUAL_CAPITAL, { currency: "USD" })}.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {CAPITAL_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => onChange({ virtualCapital: String(preset) })}
            className={cn(
              "rounded-md border px-3 py-2 text-sm font-medium tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isPreset && Number(data.virtualCapital) === preset
                ? "border-accent bg-surface-3 text-foreground"
                : "border-border bg-surface-2 text-foreground hover:bg-surface-3",
            )}
          >
            {formatMoney(preset, { decimals: 0 })}
          </button>
        ))}
      </div>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Ou um valor customizado (USDT)</span>
        <input
          inputMode="decimal"
          value={data.virtualCapital}
          onChange={(e) => onChange({ virtualCapital: e.target.value })}
          placeholder="10000"
          className={cn(
            "num rounded-md border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring",
            valid ? "border-border" : "border-negative",
          )}
        />
        {!valid && <span className="text-xs text-negative">Use um número ≥ {MIN_VIRTUAL_CAPITAL} (ex.: 10000 ou 10000.50)</span>}
      </label>
    </div>
  );
}
