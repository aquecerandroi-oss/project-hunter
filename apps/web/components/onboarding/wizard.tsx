"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { OnboardingProgress } from "@/components/onboarding/progress";
import { StepCapital } from "@/components/onboarding/step-capital";
import { StepExchanges } from "@/components/onboarding/step-exchanges";
import { StepObjective } from "@/components/onboarding/step-objective";
import { StepOrganization } from "@/components/onboarding/step-organization";
import { StepRisk } from "@/components/onboarding/step-risk";
import { StepSummary } from "@/components/onboarding/step-summary";
import {
  canAdvance,
  createInitialState,
  goBack,
  goNext,
  setOrgCreated,
  updateData,
  type OrgIdentity,
  type WizardStep,
} from "@/components/onboarding/wizard-state";
import { Button } from "@/components/ui/button";
import { createOrganization } from "@/lib/api/organizations-actions";
import { putOnboarding } from "@/lib/api/workspaces-actions";

export interface OnboardingWizardProps {
  initialOrg: OrgIdentity | null;
  initialStep?: WizardStep | undefined;
}

function clampStep(step: WizardStep | undefined, minStep: WizardStep): WizardStep {
  if (step === undefined) return minStep;
  return step < minStep ? minStep : step;
}

export function OnboardingWizard({ initialOrg, initialStep }: OnboardingWizardProps) {
  const router = useRouter();
  const [state, setState] = useState(() => {
    const base = createInitialState(initialOrg ?? undefined);
    return { ...base, step: clampStep(initialStep, base.minStep) };
  });
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleChange(patch: Parameters<typeof updateData>[1]): void {
    setState((s) => updateData(s, patch));
  }

  function handleBack(): void {
    setError(null);
    setState((s) => goBack(s));
  }

  function handleNext(): void {
    setError(null);
    if (state.step === 1) {
      startTransition(async () => {
        const result = await createOrganization({
          name: state.data.orgName,
          workspaceName: state.data.workspaceName || undefined,
        });
        if (!result.ok) {
          setError(result.problem.detail ?? result.problem.title);
          return;
        }
        setState((s) =>
          setOrgCreated(s, {
            orgSlug: result.data.slug,
            orgId: result.data.id,
            workspaceId: result.data.workspace_id,
          }),
        );
      });
      return;
    }
    if (state.step === 6) {
      const org = state.org;
      if (!org) {
        setError("Organização não encontrada -- volte ao passo 1.");
        return;
      }
      startTransition(async () => {
        const result = await putOnboarding(org.orgId, org.workspaceId, {
          objective: state.data.objective,
          virtualCapital: state.data.virtualCapital,
          riskPreset: state.data.riskPreset,
          monitoredExchanges: state.data.monitoredExchanges,
        });
        if (!result.ok) {
          setError(result.problem.detail ?? result.problem.title);
          return;
        }
        router.push(`/${org.orgSlug}/dashboard`);
      });
      return;
    }
    setState((s) => goNext(s));
  }

  const canNext = canAdvance(state);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <OnboardingProgress step={state.step} />
      <div className="rounded-lg border border-border bg-bg-elevated p-6">
        {state.step === 1 && <StepOrganization data={state.data} onChange={handleChange} />}
        {state.step === 2 && <StepObjective data={state.data} onChange={handleChange} />}
        {state.step === 3 && <StepCapital data={state.data} onChange={handleChange} />}
        {state.step === 4 && <StepRisk data={state.data} onChange={handleChange} />}
        {state.step === 5 && <StepExchanges data={state.data} onChange={handleChange} />}
        {state.step === 6 && <StepSummary org={state.org} data={state.data} />}

        {error && (
          <p role="alert" className="mt-4 rounded-md border border-red/30 bg-red/10 px-3 py-2 text-sm text-red">
            {error}
          </p>
        )}

        <div className="mt-6 flex items-center justify-between">
          <Button type="button" variant="outline" onClick={handleBack} disabled={state.step <= state.minStep || pending}>
            Voltar
          </Button>
          <Button type="button" onClick={handleNext} disabled={!canNext || pending}>
            {pending ? "Salvando..." : state.step === 6 ? "Finalizar" : "Avançar"}
          </Button>
        </div>
      </div>
    </div>
  );
}
