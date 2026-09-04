import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { AuditEntryOut, Page } from "./types";

export interface AuditListParams {
  limit?: number;
  cursor?: string;
  action?: string;
  actor?: string;
  from?: string;
  to?: string;
}

function query(params: AuditListParams): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

/** `GET /api/v1/orgs/{org_id}/audit` (apps/api/hunter_api/routers/audit.py) -- ADMIN and above, append-only. */
export async function listAudit(orgId: string, params: AuditListParams = {}): Promise<Page<AuditEntryOut>> {
  return apiFetch<Page<AuditEntryOut>>(`/api/v1/orgs/${orgId}/audit${query(params)}`);
}
