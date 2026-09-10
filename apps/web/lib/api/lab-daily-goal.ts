import "server-only";

import { apiFetch } from "@/lib/server/api";

import { dailyGoalOutSchema, type DailyGoalOut } from "./lab-daily-goal-types";

export interface LabDailyGoalParams {
  /** `YYYY-MM-DD`, a Brasília calendar day (`lib/time.ts::BRASILIA_TIME_ZONE`). Omitted -> the API's own default, today in America/Sao_Paulo. */
  day?: string;
}

function dailyGoalQuery(params: LabDailyGoalParams): string {
  const search = new URLSearchParams();
  if (params.day !== undefined) search.set("day", params.day);
  const value = search.toString();
  return value ? `?${value}` : "";
}

/**
 * `GET /api/v1/orgs/{org_id}/lab/daily-goal` (brief T3.78, VIEWER+, frozen in
 * `.claude/state/notes-T3.78.md`). Read-only and `"server-only"` like the
 * rest of `lib/api/*.ts` (ESLint boundary stops `components/**`/`hooks/**`
 * from importing this directly). `.parse()`s the response before this app
 * trusts it -- same reasoning as `manual-orders.ts`: this router has no
 * generated OpenAPI type yet, so a real shape drift must surface as an
 * honest parse failure here, never a silently wrong render.
 */
export async function getLabDailyGoal(orgId: string, params: LabDailyGoalParams = {}): Promise<DailyGoalOut> {
  const raw = await apiFetch<unknown>(`/api/v1/orgs/${orgId}/lab/daily-goal${dailyGoalQuery(params)}`);
  return dailyGoalOutSchema.parse(raw);
}
