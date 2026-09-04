import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { ListParams, MemberOut, Page } from "./types";

function query(params: ListParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/orgs/{org_id}/members` (apps/api/hunter_api/routers/members.py) -- VIEWER and above. */
export async function listMembers(orgId: string, params: ListParams = {}): Promise<Page<MemberOut>> {
  return apiFetch<Page<MemberOut>>(`/api/v1/orgs/${orgId}/members${query(params)}`);
}
