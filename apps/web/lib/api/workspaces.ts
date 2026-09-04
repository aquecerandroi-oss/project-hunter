import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { ListParams, Page, WorkspaceOut } from "./types";

function query(params: ListParams): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor !== undefined) search.set("cursor", params.cursor);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/orgs/{org_id}/workspaces` (apps/api/hunter_api/routers/workspaces.py) -- VIEWER and above. */
export async function listWorkspaces(orgId: string, params: ListParams = {}): Promise<Page<WorkspaceOut>> {
  return apiFetch<Page<WorkspaceOut>>(`/api/v1/orgs/${orgId}/workspaces${query(params)}`);
}
