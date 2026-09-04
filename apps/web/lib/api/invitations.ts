import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { InvitationOut, ListParams, Page } from "./types";

function query(params: ListParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/orgs/{org_id}/invitations` (apps/api/hunter_api/routers/invitations.py)
 * -- ADMIN and above. Never carries the token; only `createInvitation`'s
 * response does, once.
 */
export async function listInvitations(orgId: string, params: ListParams = {}): Promise<Page<InvitationOut>> {
  return apiFetch<Page<InvitationOut>>(`/api/v1/orgs/${orgId}/invitations${query(params)}`);
}
