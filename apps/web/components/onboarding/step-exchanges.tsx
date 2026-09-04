"use client";

import type { WizardData } from "@/components/onboarding/wizard-state";
import { EXCHANGE_CODES, EXCHANGE_LABELS } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

export interface StepExchangesProps {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}

/**
 * Onboarding step 5 (docs/PRODUCT.md §3.5). M0 has no `/exchanges` listing
 * endpoint (docs/ARCHITECTURE.md §7's `markets` router lands in M1), so this
 * offers exactly the two exchange codes `infra/scripts/seed.py` inserts --
 * hardcoded here on purpose, not fetched.
 */
export function StepExchanges({ data, onChange }: StepExchangesProps) {
  function toggle(code: string): void {
    const next = data.monitoredExchanges.includes(code)
      ? data.monitoredExchanges.filter((c) => c !== code)
      : [...data.monitoredExchanges, code];
    onChange({ monitoredExchanges: next });
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-fg">Exchanges monitoradas</h2>
        <p className="mt-1 text-sm text-fg-muted">
          Filtro de preferência para o radar (a partir do Milestone 1/2). Sem endpoint de exchanges no M0 -- lista fixa das
          duas exchanges semeadas.
        </p>
      </div>
      <div className="flex flex-col gap-2">
        {EXCHANGE_CODES.map((code) => {
          const checked = data.monitoredExchanges.includes(code);
          return (
            <label
              key={code}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-sm transition-colors",
                checked ? "border-gold bg-gold-soft" : "border-border bg-bg-overlay hover:border-border-strong",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(code)}
                className="size-4 accent-[var(--color-gold)]"
              />
              <span className="font-medium text-fg">{EXCHANGE_LABELS[code]}</span>
            </label>
          );
        })}
      </div>
      {data.monitoredExchanges.length === 0 && (
        <p className="text-xs text-fg-muted">Nenhuma selecionada ainda -- você pode ajustar isso depois em Settings.</p>
      )}
    </div>
  );
}
