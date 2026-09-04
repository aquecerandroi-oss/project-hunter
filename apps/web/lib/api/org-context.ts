import "server-only";

import { me } from "./me";
import type { MembershipOut } from "./types";

/**
 * Resolves `[orgSlug]` (docs/ARCHITECTURE.md §7's URL convention) against the
 * caller's own memberships from `/api/v1/me`. There is no "get org by slug"
 * endpoint -- `/me` is already the one request the app shell makes on every
 * load (see its own docstring), so this never adds a second round trip for
 * the common case of a page needing "this org, as this caller".
 *
 * Returns `null` for a slug the caller has no membership for; every caller
 * of this function turns that into `notFound()` (never a 500) because a
 * mistyped or foreign slug must read as "page doesn't exist", not an error.
 */
export async function resolveOrgContext(orgSlug: string): Promise<MembershipOut | null> {
  const { memberships } = await me();
  return memberships.find((m) => m.organization.slug === orgSlug) ?? null;
}

export const ROLE_RANK: Record<MembershipOut["role"], number> = {
  VIEWER: 1,
  ANALYST: 2,
  TRADER: 3,
  ADMIN: 4,
  OWNER: 5,
};

/** Whether `role` meets or exceeds `minRole` -- mirrors `lib/nav-registry.ts`'s own rank table. */
export function roleAtLeast(role: MembershipOut["role"], minRole: MembershipOut["role"]): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}
