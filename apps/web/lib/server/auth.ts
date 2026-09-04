import "server-only";

import { auth } from "@clerk/nextjs/server";

/**
 * Server-only session wrapper (docs/SECURITY.md §1). `import "server-only"`
 * makes it a build error for `components/**`/`hooks/**` to pull this into
 * the client bundle; `packages/config`'s `quality/no-direct-data-access`
 * plus `import-x/no-restricted-paths` enforce the same boundary at lint time.
 *
 * We don't use Clerk Organizations (roles live in our own Postgres via the
 * `api`, loaded per-request from org membership) -- so this only exposes
 * identity and the bearer token, never a role. Role-aware nav gating lands
 * once T06/T09 wire the orgs API.
 */
export interface ServerSession {
  userId: string;
  token: string | null;
}

export async function getServerSession(): Promise<ServerSession | null> {
  const { userId, getToken } = await auth();
  if (!userId) return null;
  const token = await getToken();
  return { userId, token };
}
