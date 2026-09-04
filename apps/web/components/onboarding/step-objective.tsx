"use client";

import { OBJECTIVE_LABELS } from "@/components/onboarding/labels";
import type { WizardData } from "@/components/onboarding/wizard-state";
import { OBJECTIVES } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

export interface StepObjectiveProps {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}

/** Onboarding step 2 (docs/PRODUCT.md §3.2). */
export function StepObjective({ data, onChange }: StepObjectiveProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-fg">Qual é o seu objetivo?</h2>
        <p className="mt-1 text-sm text-fg-muted">Isso ajusta os presets e destaca itens de navegação relevantes.</p>
      </div>
      <div role="radiogroup" aria-label="Objetivo" className="grid gap-2 sm:grid-cols-2">
        {OBJECTIVES.map((objective) => {
          const selected = data.objective === objective;
          const label = OBJECTIVE_LABELS[objective];
          return (
            <button
              key={objective}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange({ objective })}
              className={cn(
                "rounded-md border p-3 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold",
                selected ? "border-gold bg-gold-soft" : "border-border bg-bg-overlay hover:border-border-strong",
              )}
            >
              <div className="font-medium text-fg">{label.title}</div>
              <div className="mt-1 text-xs text-fg-muted">{label.description}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
