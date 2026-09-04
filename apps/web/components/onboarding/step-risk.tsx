"use client";

import { RISK_PRESET_LABELS } from "@/components/onboarding/labels";
import type { WizardData } from "@/components/onboarding/wizard-state";
import { PlannedBadge } from "@/components/layout/planned-badge";
import { RISK_LIMITS_TABLE, RISK_PRESETS } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

export interface StepRiskProps {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}

/** Onboarding step 4 (docs/PRODUCT.md §3.4) -- risk preset, limits from docs/RISK_ENGINE.md §2 shown read-only. */
export function StepRisk({ data, onChange }: StepRiskProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-fg">Perfil de risco</h2>
        <p className="mt-1 text-sm text-fg-muted">O preset é copiado para os limites de risco da sua organização.</p>
      </div>
      <div role="radiogroup" aria-label="Perfil de risco" className="grid gap-2 sm:grid-cols-4">
        {RISK_PRESETS.map((preset) => {
          const selected = data.riskPreset === preset;
          return (
            <button
              key={preset}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange({ riskPreset: preset })}
              className={cn(
                "rounded-md border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold",
                selected ? "border-gold bg-gold-soft text-fg" : "border-border bg-bg-overlay text-fg hover:border-border-strong",
              )}
            >
              {RISK_PRESET_LABELS[preset]}
            </button>
          );
        })}
      </div>

      {data.riskPreset === "custom" ? (
        <div className="flex items-center gap-2 rounded-md border border-dashed border-border p-3 text-sm text-fg-muted">
          Ajuste fino de limites por checagem individual
          <PlannedBadge milestone="M4" />
          na Risk Center. Por enquanto, o preset Customizado começa com os mesmos limites do Balanceado.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-left">
            <thead className="bg-bg-overlay text-xs text-fg-muted">
              <tr>
                <th className="h-8 px-3 font-medium">Limite</th>
                <th className="h-8 px-3 font-medium">Conservador</th>
                <th className="h-8 px-3 font-medium">Balanceado</th>
                <th className="h-8 px-3 font-medium">Agressivo</th>
              </tr>
            </thead>
            <tbody className="text-[13px]">
              {RISK_LIMITS_TABLE.map((row) => (
                <tr key={row.key} className="h-8 border-t border-border">
                  <td className="px-3 text-fg">{row.label}</td>
                  <td className={cn("num px-3", data.riskPreset === "conservative" ? "font-semibold text-fg" : "text-fg-muted")}>
                    {row.conservative}
                  </td>
                  <td className={cn("num px-3", data.riskPreset === "balanced" ? "font-semibold text-fg" : "text-fg-muted")}>
                    {row.balanced}
                  </td>
                  <td className={cn("num px-3", data.riskPreset === "aggressive" ? "font-semibold text-fg" : "text-fg-muted")}>
                    {row.aggressive}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
