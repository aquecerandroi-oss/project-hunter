"use server";

import { onboardingCreateOrgSchema, organizationNameSchema } from "@/lib/api/schemas";
import { apiFetch } from "@/lib/server/api";

import { actionError, actionOk, ApiError, problemFromApiError, validationProblem } from "./types";
import type { ActionResult, OrganizationCreated, OrganizationOut } from "./types";

/**
 * `POST /api/v1/orgs` -- sign-up (apps/api/hunter_api/routers/organizations.py).
 * Onboarding step 1: creates the organization and its first workspace in one
 * call. `objective` is left at the API's default (`explore`); the real
 * choice from onboarding step 2 is persisted later by `putOnboarding`, which
 * is idempotent and safe to call last.
 */
export async function createOrganization(input: {
  name: string;
  workspaceName?: string | undefined;
}): Promise<ActionResult<OrganizationCreated>> {
  const parsed = onboardingCreateOrgSchema.safeParse(input);
  if (!parsed.success) return actionError(validationProblem(parsed.error.issues[0]?.message ?? "Dados inválidos"));

  try {
    const created = await apiFetch<OrganizationCreated>("/api/v1/orgs", {
      method: "POST",
      body: JSON.stringify({
        name: parsed.data.name,
        workspace_name: parsed.data.workspaceName ?? null,
      }),
    });
    return actionOk(created);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}

/**
 * `PATCH /api/v1/orgs/{org_id}` -- rename, ADMIN and above
 * (apps/api/hunter_api/schemas/organizations.py: name is the only mutable field in M0).
 */
export async function updateOrganization(orgId: string, name: string): Promise<ActionResult<OrganizationOut>> {
  const parsed = organizationNameSchema.safeParse(name);
  if (!parsed.success) return actionError(validationProblem(parsed.error.issues[0]?.message ?? "Nome inválido"));

  try {
    const updated = await apiFetch<OrganizationOut>(`/api/v1/orgs/${orgId}`, {
      method: "PATCH",
      body: JSON.stringify({ name: parsed.data }),
    });
    return actionOk(updated);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
