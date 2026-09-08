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

/**
 * Fail-closed guard for a Server Action about to call `apiFetch`
 * (T3.28c, security-reviewer T3.28a finding 1). `/` is public in
 * `middleware.ts`, so an unauthenticated POST carrying a `Next-Action` id
 * still reaches every exported action -- `apiFetch` only sets `Authorization`
 * `if (session?.token)`, so it used to issue the outbound API request
 * regardless (the API correctly answered 401, but the request had already
 * spent the web peer's shared rate-limit bucket, 6 000/min after T3.28a).
 * A thin, intent-revealing alias over `getServerSession` on purpose: every
 * action that calls `apiFetch` must call this FIRST and return on `null`
 * without ever calling `apiFetch` -- same pattern
 * `markets-actions.ts::searchMarketsAction` already used before this
 * existed; that file is unchanged (docs/SECURITY.md §5).
 */
export async function requireSession(): Promise<ServerSession | null> {
  return getServerSession();
}
