"use client";

import { OBJECTIVE_LABELS, RISK_PRESET_LABELS } from "@/components/onboarding/labels";
import type { OrgIdentity, WizardData } from "@/components/onboarding/wizard-state";
import { EXCHANGE_LABELS } from "@/lib/api/schemas";
import { formatMoney } from "@/lib/format";

export interface StepSummaryProps {
  org: OrgIdentity | null;
  data: WizardData;
}

/** Onboarding step 6 (docs/PRODUCT.md §3.6) -- recap before `putOnboarding`. */
export function StepSummary({ org, data }: StepSummaryProps) {
  const rows: { label: string; value: string }[] = [
    { label: "Organização", value: org?.orgSlug ?? "--" },
    { label: "Objetivo", value: OBJECTIVE_LABELS[data.objective].title },
    { label: "Capital virtual", value: formatMoney(data.virtualCapital) },
    { label: "Perfil de risco", value: RISK_PRESET_LABELS[data.riskPreset] },
    {
      label: "Exchanges monitoradas",
      value: data.monitoredExchanges.length > 0
        ? data.monitoredExchanges.map((c) => EXCHANGE_LABELS[c as keyof typeof EXCHANGE_LABELS] ?? c).join(", ")
        : "Nenhuma",
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Confirme e finalize</h2>
        <p className="mt-1 text-sm text-muted">Você pode alterar tudo isso depois em Settings.</p>
      </div>
      <dl className="divide-y divide-border rounded-md border border-border">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 px-3 py-2 text-sm">
            <dt className="text-muted">{row.label}</dt>
            <dd className="num text-right font-medium text-foreground">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
