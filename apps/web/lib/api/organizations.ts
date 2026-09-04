import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { OrganizationOut } from "./types";

/** `GET /api/v1/orgs/{org_id}` (apps/api/hunter_api/routers/organizations.py) -- VIEWER and above. */
export async function getOrganization(orgId: string): Promise<OrganizationOut> {
  return apiFetch<OrganizationOut>(`/api/v1/orgs/${orgId}`);
}
