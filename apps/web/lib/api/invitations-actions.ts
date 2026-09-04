"use server";

import { getOrganization } from "@/lib/api/organizations";
import { invitationCreateSchema, invitationTokenSchema } from "@/lib/api/schemas";
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

/** The raw response of `POST /api/v1/invitations/{token}/accept` -- a plain dict, not a schema (routers/invitations.py returns `dict[str, str]`), so it isn't in `@hunter/shared-types`. */
interface InvitationAcceptResponse {
  organization_id: string;
  user_id: string;
  role: string;
}

export interface AcceptedInvitation {
  orgSlug: string;
}

/**
 * `POST /api/v1/invitations/{token}/accept` (apps/api/hunter_api/routers/invitations.py)
 * -- accepted *by* the signed-in caller, not scoped to an org the caller is
 * already a member of (there is no membership yet). The endpoint's own
 * response carries only `organization_id` (see `InvitationAcceptResponse`
 * above), never a slug, so a second read -- `getOrganization`, VIEWER and
 * above -- resolves the `/<slug>/dashboard` redirect the caller actually
 * needs; it succeeds because the membership row was written inside the
 * same accept transaction (services/invitations.py's `accept_invitation`).
 *
 * Error mapping is deliberate, not a passthrough: a 404 (bad token, expired,
 * or already used -- `InvitationNotFoundError` collapses all three on
 * purpose, see its own docstring) always shows the same generic message, so
 * this endpoint never becomes an oracle for which tokens once existed. A 403
 * (`InvitationEmailMismatchError`) shows the API's own detail -- the caller
 * already knows which email they're signed in as, so naming the mismatch
 * isn't a leak.
 */
export async function acceptInvitation(token: string): Promise<ActionResult<AcceptedInvitation>> {
  const parsed = invitationTokenSchema.safeParse(token);
  if (!parsed.success) {
    return actionError(validationProblem(parsed.error.issues[0]?.message ?? "Convite inválido, expirado ou já usado."));
  }

  try {
    const accepted = await apiFetch<InvitationAcceptResponse>(`/api/v1/invitations/${parsed.data}/accept`, {
      method: "POST",
    });
    const organization = await getOrganization(accepted.organization_id);
    return actionOk({ orgSlug: organization.slug });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) {
        return actionError({
          type: error.type,
          title: error.message,
          status: error.status,
          detail: "Convite inválido, expirado ou já usado.",
        });
      }
      return actionError(problemFromApiError(error));
    }
    throw error;
  }
}
