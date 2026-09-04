import "server-only";

import { apiFetch } from "@/lib/server/api";

import type { MeOut } from "./types";

/** `GET /api/v1/me` (apps/api/hunter_api/routers/me.py) -- the signed-in user and their organizations. */
export async function me(): Promise<MeOut> {
  return apiFetch<MeOut>("/api/v1/me");
}
