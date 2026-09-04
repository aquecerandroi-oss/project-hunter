import {
  monitoredExchangesSchema,
  objectiveSchema,
  organizationNameSchema,
  riskPresetSchema,
  virtualCapitalSchema,
  type Objective,
  type RiskPresetValue,
} from "@/lib/api/schemas";

/**
 * Pure state machine for the six-step onboarding wizard (docs/PRODUCT.md §3).
 * No React, no fetch -- `app/(onboarding)/onboarding/[[...step]]/page.tsx` and
 * `components/onboarding/wizard.tsx` are the only things that touch the
 * network; this module is fully unit-tested in isolation
 * (tests/wizard-state.test.ts).
 *
 * Step order:
 *   1. organization + workspace name  -> createOrganization
 *   2. objective
 *   3. virtual capital
 *   4. risk profile
 *   5. exchanges to monitor
 *   6. summary                        -> putOnboarding
 */
export const STEP_COUNT = 6 as const;
export type WizardStep = 1 | 2 | 3 | 4 | 5 | 6;

export interface WizardData {
  orgName: string;
  workspaceName: string;
  objective: Objective;
  virtualCapital: string;
  riskPreset: RiskPresetValue;
  monitoredExchanges: string[];
}

export interface OrgIdentity {
  orgSlug: string;
  orgId: string;
  workspaceId: string;
}

export interface WizardState {
  step: WizardStep;
  /** The lowest step `goBack` may reach -- 2 when resumed via `?org=`, since step 1 (create the org) no longer applies. */
  minStep: WizardStep;
  org: OrgIdentity | null;
  data: WizardData;
}

export const DEFAULT_DATA: WizardData = {
  orgName: "",
  workspaceName: "",
  objective: "explore",
  virtualCapital: "10000",
  riskPreset: "balanced",
  monitoredExchanges: [],
};

/** `resume` is set when the onboarding page was loaded with `?org=<slug>` and the org/workspace already exist. */
export function createInitialState(resume?: OrgIdentity): WizardState {
  return {
    step: resume ? 2 : 1,
    minStep: resume ? 2 : 1,
    org: resume ?? null,
    data: { ...DEFAULT_DATA },
  };
}

/** Validation error messages for `step`'s own fields; empty means the step may advance. */
export function validateStep(step: WizardStep, data: WizardData): string[] {
  switch (step) {
    case 1: {
      const result = organizationNameSchema.safeParse(data.orgName);
      return result.success ? [] : result.error.issues.map((i) => i.message);
    }
    case 2: {
      const result = objectiveSchema.safeParse(data.objective);
      return result.success ? [] : ["Selecione um objetivo"];
    }
    case 3: {
      const result = virtualCapitalSchema.safeParse(data.virtualCapital);
      return result.success ? [] : result.error.issues.map((i) => i.message);
    }
    case 4: {
      const result = riskPresetSchema.safeParse(data.riskPreset);
      return result.success ? [] : ["Selecione um perfil de risco"];
    }
    case 5: {
      // Monitoring zero exchanges is valid (OnboardingUpdate.monitored_exchanges defaults to []).
      const result = monitoredExchangesSchema.safeParse(data.monitoredExchanges);
      return result.success ? [] : result.error.issues.map((i) => i.message);
    }
    case 6:
      return [];
  }
}

export function canAdvance(state: WizardState): boolean {
  return validateStep(state.step, state.data).length === 0;
}

export function goNext(state: WizardState): WizardState {
  if (!canAdvance(state) || state.step >= STEP_COUNT) return state;
  return { ...state, step: (state.step + 1) as WizardStep };
}

export function goBack(state: WizardState): WizardState {
  if (state.step <= state.minStep) return state;
  return { ...state, step: (state.step - 1) as WizardStep };
}

export function updateData(state: WizardState, patch: Partial<WizardData>): WizardState {
  return { ...state, data: { ...state.data, ...patch } };
}

/**
 * Called once `createOrganization` (step 1) succeeds; advances to step 2 and
 * raises `minStep` to 2 -- exactly like a `?org=` resume. Step 1 calls a real,
 * side-effecting mutation (it creates a row), so once it has run, going back
 * to it and pressing "next" again must not be possible: that would silently
 * create a second, orphaned organization rather than editing the first one.
 */
export function setOrgCreated(state: WizardState, org: OrgIdentity): WizardState {
  return { ...state, org, step: 2, minStep: 2 };
}
