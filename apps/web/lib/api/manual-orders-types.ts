/**
 * The manual paper order write path (T3.72/T3.72b/T3.72c, reconciled against
 * T3.68's landed API — `apps/api/hunter_api/routers/orders.py`,
 * `schemas/orders.py`, `.claude/state/notes-T3.68.md`). There is still no
 * generated OpenAPI type for this router (not regenerated into
 * `@hunter/shared-types/api` yet, contrast `portfolio-types.ts`, which
 * aliases the generated schema for the read routes that already exist), so
 * this file keeps hand-mirroring the real contract with `zod`. Every response
 * is `.parse()`d in `manual-orders.ts`/`manual-orders-actions.ts` before this
 * app trusts it -- a future drift on the real API's side surfaces as an
 * honest parse failure, never a silently wrong render.
 *
 * The resource lives at `.../order-requests`, not `.../orders`
 * (`routers/orders.py`'s own module docstring): `.../orders` already serves
 * `execution_orders` rows (T3.8a). `ManualOrderOut` always carries
 * `market_id`/`direction` (the router's `schemas/orders.py` docstring calls
 * these "additive" over the brief's literal shape) -- required fields below,
 * not a guess.
 *
 * `RiskDecision`/`RiskCheck`/`Sizing`/`LimitCap` mirror
 * `packages/risk-core/hunter_risk/decision.py` field for field (the pure
 * core's own shape, which `to_jsonable()` -- via `canonical_json` --
 * serializes as normalized decimal strings and ISO-8601 `Z` timestamps, so
 * every numeric field below is a `string`, never a `number` -- CLAUDE.md's
 * "money is Decimal, never float" extends to every check value/limit here
 * too, not only prices). `decision` itself is passed through by the API as
 * the raw JSONB (`schemas/orders.py`'s own docstring) -- this schema
 * re-validates that shape at the client boundary, it does not re-derive it.
 */
import { z } from "zod";

// A `Decimal`-backed field the API always sends as a string (CLAUDE.md).
// Permissive on purpose (the engine's own serializer, not user input): this
// only guards against a non-string leaking through, never re-validates the
// engine's own math.
const decimalString = z.string().min(1);

export const manualOrderDirectionSchema = z.enum(["long", "short"]);
export type ManualOrderDirection = z.infer<typeof manualOrderDirectionSchema>;

export const manualOrderRequestStatusSchema = z.enum(["pending", "decided"]);
export type ManualOrderRequestStatus = z.infer<typeof manualOrderRequestStatusSchema>;

export const checkStateSchema = z.enum(["passed", "failed", "unavailable"]);
export type CheckState = z.infer<typeof checkStateSchema>;

export const riskCheckSchema = z.object({
  name: z.string().min(1),
  state: checkStateSchema,
  value: decimalString.nullable().optional(),
  limit: decimalString.nullable().optional(),
  message: z.string().optional().default(""),
});
export type RiskCheck = z.infer<typeof riskCheckSchema>;

export const limitCapSchema = z.object({
  name: z.string().min(1),
  notional: decimalString.nullable(),
  limit: decimalString.nullable().optional(),
  detail: z.string().optional().default(""),
});
export type LimitCap = z.infer<typeof limitCapSchema>;

export const counterfactualSchema = z.object({
  name: z.string().min(1),
  qty: decimalString.nullable().optional(),
  notional: decimalString.nullable().optional(),
  unavailable_reason: z.string().nullable().optional(),
});
export type Counterfactual = z.infer<typeof counterfactualSchema>;

export const sizingSchema = z.object({
  entry_ref: decimalString,
  sizing_price: decimalString,
  stop: decimalString,
  stop_distance_pct: decimalString,
  cost_pct: decimalString,
  caps: z.array(limitCapSchema),
  binding_limit: limitCapSchema,
  binding_constraint: z.string().min(1),
  size_without_multipliers: counterfactualSchema,
  size_without_participation: counterfactualSchema,
  tied_limits: z.array(z.string()).optional().default([]),
  notional_before_multiplier: decimalString,
  kill_switch_multiplier: decimalString,
  notional_after_multiplier: decimalString,
  qty: decimalString,
  notional: decimalString,
  planned_risk_quote: decimalString,
  planned_risk_pct: decimalString,
});
export type Sizing = z.infer<typeof sizingSchema>;

const marketIdentitySchema = z.object({
  exchange: z.string(),
  symbol: z.string(),
  market_type: z.enum(["spot", "perpetual"]),
  base_asset: z.string(),
  quote_asset: z.string(),
});

const killSwitchStateSchema = z.enum(["ACTIVE", "WARNING", "TRADING_DISABLED", "EMERGENCY"]);

export const riskDecisionSchema = z.object({
  approved: z.boolean(),
  kind: z.enum(["entry", "exit"]),
  proposal_id: z.string(),
  portfolio_id: z.string(),
  market: marketIdentitySchema,
  limits_profile: z.string(),
  effective_kill_switch: killSwitchStateSchema,
  cancel_pending: z.boolean(),
  shadow_only: z.boolean(),
  checks: z.array(riskCheckSchema),
  sizing: sizingSchema.nullable().optional(),
  // Never populated by a manual ENTRY order, kept nullable so a decision
  // fetched by id never fails to parse just because this reads as an exit.
  exit_plan: z.record(z.string(), z.unknown()).nullable().optional(),
});
export type RiskDecision = z.infer<typeof riskDecisionSchema>;

/** `POST .../order-requests` body -- mirrors `ManualOrderCreate` (`schemas/orders.py`) field for field. */
export const manualOrderRequestBodySchema = z.object({
  market_id: z.string().uuid(),
  direction: manualOrderDirectionSchema,
  stop: decimalString,
  requested_notional: decimalString.nullable(),
});
export type ManualOrderRequestBody = z.infer<typeof manualOrderRequestBodySchema>;

/** `OrderSide`/`OrderType`/`OrderPurpose`/`ExecutionMode`/`OrderStatus` -- `packages/core/hunter_core/domain/enums.py`, the same string values `schemas/portfolio_lists.py`'s `OrderOut` already serializes for the (today always-empty) `.../orders` read. */
const orderSideSchema = z.enum(["buy", "sell"]);
const orderTypeSchema = z.enum(["market", "limit", "stop_market", "stop_limit", "take_profit"]);
const orderPurposeSchema = z.enum(["entry", "stop", "target", "exit", "reduce"]);
const executionModeSchema = z.enum(["paper", "shadow", "live"]);
const orderStatusSchema = z.enum([
  "pending",
  "submitted",
  "partially_filled",
  "filled",
  "cancelled",
  "rejected",
  "expired",
]);

/** `ManualOrderDetailOut.outcome` -- the `OrderOut` row this request's approval turned into, verbatim (`services/orders.py::_load_outcome`), or `null` (pending/rejected/expired/approved-not-yet-picked-up). Not yet rendered anywhere in this app (no UI names an execution order today) -- typed for the parse boundary regardless, so a real value never silently fails to validate. */
export const manualOrderOutcomeSchema = z.object({
  id: z.string(),
  market_id: z.string(),
  side: orderSideSchema,
  type: orderTypeSchema,
  purpose: orderPurposeSchema,
  execution_mode: executionModeSchema,
  status: orderStatusSchema,
  qty: decimalString,
  price: decimalString.nullable(),
  stop_price: decimalString.nullable(),
  filled_qty: decimalString,
  avg_fill_price: decimalString.nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});
export type ManualOrderOutcome = z.infer<typeof manualOrderOutcomeSchema>;

/** `202` response shape (`ManualOrderOut`, `schemas/orders.py`), and the base of the `GET .../order-requests/{id}` shape below. */
export const manualOrderOutSchema = z.object({
  request_id: z.string(),
  market_id: z.string(),
  direction: manualOrderDirectionSchema,
  status: manualOrderRequestStatusSchema,
  filed_at: z.string(),
  decision: riskDecisionSchema.nullable(),
});
export type ManualOrderOut = z.infer<typeof manualOrderOutSchema>;

/** `GET .../order-requests/{request_id}` (`ManualOrderDetailOut`) -- `ManualOrderOut` plus `outcome`. */
export const manualOrderDetailSchema = manualOrderOutSchema.extend({
  outcome: manualOrderOutcomeSchema.nullable(),
});
export type ManualOrderDetail = z.infer<typeof manualOrderDetailSchema>;

/**
 * One row of `GET .../order-requests` (list) -- the same shape as
 * `ManualOrderOut` (`routers/orders.py::list_manual_orders_route`'s
 * `response_model=CursorPage[ManualOrderOut]`; the list carries no `outcome`,
 * only the single-request `GET` does). `.passthrough()` kept so a real,
 * additional field a future API version adds is preserved on the parsed
 * object rather than silently stripped by this client's own shape.
 */
export const manualOrderListItemSchema = manualOrderOutSchema.passthrough();
export type ManualOrderListItem = z.infer<typeof manualOrderListItemSchema>;

export const manualOrderListPageSchema = z.object({
  items: z.array(manualOrderListItemSchema),
  next_cursor: z.string().nullable().optional(),
});
export type ManualOrderListPage = z.infer<typeof manualOrderListPageSchema>;

/** `/api/v1/orgs/{org_id}/portfolios/{portfolio_id}/order-requests` -- shared by the server-only GET module and the "use server" write actions, matching the org-scoped convention every other portfolio route already uses (`lib/api/portfolio.ts`'s own `portfoliosBase`). Deviates from the brief's literal `.../orders` path: that path already serves `execution_orders` rows (`routers/portfolio.py`, T3.8a) -- see `routers/orders.py`'s module docstring and `.claude/state/notes-T3.68.md`. */
export function manualOrdersPath(orgId: string, portfolioId: string): string {
  return `/api/v1/orgs/${orgId}/portfolios/${portfolioId}/order-requests`;
}
