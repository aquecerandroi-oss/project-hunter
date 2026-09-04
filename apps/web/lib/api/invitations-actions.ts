"use server";

import { invitationCreateSchema } from "@/lib/api/schemas";
import { apiFetch } from "@/lib/server/api";

import { actionError, actionOk, ApiError, problemFromApiError, validationProblem } from "./types";
import type { ActionResult, InvitationCreated } from "./types";

/**
 * `POST /api/v1/orgs/{org_id}/invitations` -- ADMIN and above. The API
 * itself rejects a role above the inviter's own (`RoleAboveInviterError`,
 * services/invitations.py); the UI only offers roles up to the caller's own
 * as a courtesy, never as the actual guarantee.
 *
 * The token in the response is shown to the caller exactly once
 * (apps/api/hunter_api/schemas/invitations.py) -- it is never returned by
 * `listInvitations` afterwards, because only its SHA-256 hash is stored.
 */
export async function createInvitation(
  orgId: string,
  input: { email: string; role: string },
): Promise<ActionResult<InvitationCreated>> {
  const parsed = invitationCreateSchema.safeParse(input);
  if (!parsed.success) return actionError(validationProblem(parsed.error.issues[0]?.message ?? "Dados inválidos"));

  try {
    const invitation = await apiFetch<InvitationCreated>(`/api/v1/orgs/${orgId}/invitations`, {
      method: "POST",
      body: JSON.stringify(parsed.data),
    });
    return actionOk(invitation);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}

/** `DELETE /api/v1/orgs/{org_id}/invitations/{invitation_id}` -- ADMIN and above. */
export async function revokeInvitation(orgId: string, invitationId: string): Promise<ActionResult<undefined>> {
  try {
    await apiFetch<undefined>(`/api/v1/orgs/${orgId}/invitations/${invitationId}`, { method: "DELETE" });
    return actionOk(undefined);
  } catch (error) {
    if (error instanceof ApiError) return actionError(problemFromApiError(error));
    throw error;
  }
}
