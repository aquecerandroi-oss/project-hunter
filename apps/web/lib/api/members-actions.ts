"use server";

import { memberRoleSchema } from "@/lib/api/schemas";
import { apiFetch } from "@/lib/server/api";

import { actionError, actionOk, ApiError, problemFromApiError, validationProblem } from "./types";
import type { ActionResult, MemberOut } from "./types";

/**
 * `PATCH /api/v1/orgs/{org_id}/members/{user_id}` -- OWNER only
 * (apps/api/hunter_api/routers/members.py: promoting/demoting is kept at
 * OWNER rather than "ADMIN except for OWNER rows"). The UI only hides the
 * control for a non-OWNER; the API is what actually enforces this.
 */
export async function updateMemberRole(
  orgId: string,
  userId: string,
  role: string,
): Promise<ActionResult<MemberOut>> {
  const parsed = memberRoleSchema.safeParse(role);
  if (!parsed.success) return actionError(validationProblem("Papel inválido"));

  try {
    const member = await apiFetch<MemberOut>(`/api/v1/orgs/${orgId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role: parsed.data }),
    });
    return actionOk(member);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}

/** `DELETE /api/v1/orgs/{org_id}/members/{user_id}` -- OWNER only. */
export async function removeMember(orgId: string, userId: string): Promise<ActionResult<undefined>> {
  try {
    await apiFetch<undefined>(`/api/v1/orgs/${orgId}/members/${userId}`, { method: "DELETE" });
    return actionOk(undefined);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
