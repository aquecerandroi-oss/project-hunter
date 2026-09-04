"use server";

import { onboardingUpdateSchema } from "@/lib/api/schemas";
import { apiFetch } from "@/lib/server/api";

import { actionError, actionOk, ApiError, problemFromApiError, validationProblem } from "./types";
import type { ActionResult, WorkspaceOut } from "./types";

/**
 * `PUT /api/v1/orgs/{org_id}/workspaces/{workspace_id}/onboarding` -- the
 * onboarding wizard's final step (apps/api/hunter_api/routers/workspaces.py).
 * Idempotent server-side: re-submitting never rewrites the first
 * `onboarding_completed_at` (services/workspaces.py), so a settings screen
 * can safely call this again later to change objective/capital/risk/exchanges.
 */
export async function putOnboarding(
  orgId: string,
  workspaceId: string,
  input: {
    objective: string;
    virtualCapital: string;
    riskPreset: string;
    monitoredExchanges: string[];
  },
): Promise<ActionResult<WorkspaceOut>> {
  const parsed = onboardingUpdateSchema.safeParse(input);
  if (!parsed.success) return actionError(validationProblem(parsed.error.issues[0]?.message ?? "Dados inválidos"));

  try {
    const workspace = await apiFetch<WorkspaceOut>(
      `/api/v1/orgs/${orgId}/workspaces/${workspaceId}/onboarding`,
      {
        method: "PUT",
        body: JSON.stringify({
          objective: parsed.data.objective,
          virtual_capital: parsed.data.virtualCapital,
          risk_preset: parsed.data.riskPreset,
          monitored_exchanges: parsed.data.monitoredExchanges,
        }),
      },
    );
    return actionOk(workspace);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
