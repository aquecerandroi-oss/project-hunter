/**
 * `GET /api/v1/system/latency` (brief T3.79, frozen contract in
 * `.claude/state/notes-T3.79.md` §4, backed by
 * `apps/api/hunter_api/schemas/latency.py`). Hand-mirrored with `zod`, same
 * convention as `lab-daily-goal-types.ts`/`manual-orders-types.ts` -- this
 * router has not been through `pnpm gen:types` yet, so there is no generated
 * OpenAPI type to alias.
 *
 * `p50_s`/`p95_s` are plain JSON numbers in seconds, NOT `Decimal` strings:
 * `hunter_api.schemas.latency.LatencyHopOut` types them `float | None` and
 * the frozen contract's own worked example sends `"p50_s": 0.09` -- unlike
 * the `Decimal`-string convention money fields use elsewhere
 * (`lab_daily_goal.py`, `manual_orders.py`), this endpoint is not money, so
 * it is not `NUMERIC(28,10)`-backed and the API never encodes it as a
 * string. `null` is a real, honest value here (a hop with no reading yet),
 * never coerced to `0` -- `.parse()` is the boundary that turns a real drift
 * in that contract into a loud failure instead of a silently wrong render.
 */
import { z } from "zod";

export const LATENCY_SLO_STATUS_VALUES = ["ok", "warn", "critical", "unknown"] as const;
export const latencySloStatusSchema = z.enum(LATENCY_SLO_STATUS_VALUES);
export type LatencySloStatus = z.infer<typeof latencySloStatusSchema>;

export const latencyHopSchema = z.object({
  hop: z.string(),
  p50_s: z.number().nullable(),
  p95_s: z.number().nullable(),
  target_p50_s: z.number(),
  target_p95_s: z.number(),
  status: latencySloStatusSchema,
});
export type LatencyHop = z.infer<typeof latencyHopSchema>;

export const latencyOutSchema = z.object({
  hops: z.array(latencyHopSchema),
  end_to_end: latencyHopSchema,
  generated_at: z.string(),
});
export type LatencyOut = z.infer<typeof latencyOutSchema>;
