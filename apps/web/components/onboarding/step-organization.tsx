"use client";

import type { WizardData } from "@/components/onboarding/wizard-state";

export interface StepOrganizationProps {
  data: WizardData;
  onChange: (patch: Partial<WizardData>) => void;
}

/** Onboarding step 1 (docs/PRODUCT.md §3.1) -- organization name creates the org; workspace name is optional. */
export function StepOrganization({ data, onChange }: StepOrganizationProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Crie sua organização</h2>
        <p className="mt-1 text-sm text-muted">O slug da organização é derivado do nome automaticamente.</p>
      </div>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Nome da organização</span>
        <input
          autoFocus
          value={data.orgName}
          onChange={(e) => onChange({ orgName: e.target.value })}
          placeholder="Acme Capital"
          maxLength={120}
          className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Nome do workspace (opcional)</span>
        <input
          value={data.workspaceName}
          onChange={(e) => onChange({ workspaceName: e.target.value })}
          placeholder="Main"
          maxLength={120}
          className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </label>
    </div>
  );
}
