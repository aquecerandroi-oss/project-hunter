/**
 * Client- and server-safe validation for the "Nova ordem paper" form
 * (T3.72). No `"server-only"` on purpose -- `manual-order-form.tsx` runs
 * this in the browser for inline errors before ever calling the Server
 * Action, same convention as `lib/api/schemas.ts`'s onboarding schemas.
 *
 * Two different kinds of check live here, deliberately kept apart:
 * - **shape** (`manualOrderFormShapeSchema`): is this a UUID, a positive
 *   decimal string, a supported direction -- mirrors the wire contract
 *   (`manual-orders-types.ts`), zod-checked.
 * - **market-dependent** (`validateStopAgainstMarket`): needs the market's
 *   own last price, which zod's static schema does not carry. This can only
 *   ever be a client-side *hint* for the hard geometry rule
 *   (docs/RISK_ENGINE.md §3.1 check 7: "o stop está abaixo do preço
 *   observado" for a LONG) -- the real check also runs against
 *   `sizing_price` (the worse of `entry_ref` and the observed price, §4),
 *   which this form does not compute, so this never blocks a distance-%
 *   warning the way it blocks the wrong-side-of-price case. The engine's own
 *   `RiskDecision` is the only authority for whether a stop was actually
 *   accepted.
 */
import { z } from "zod";

import { manualOrderDirectionSchema } from "@/lib/api/manual-orders-types";
import { compareDecimalStrings } from "@/lib/format";

const DECIMAL_RE = /^\d+(\.\d+)?$/;

export const positiveDecimalSchema = z
  .string()
  .trim()
  .regex(DECIMAL_RE, "Use um número decimal positivo (ex.: 65000.50)")
  .refine((value) => Number(value) > 0, "Deve ser maior que zero");

/** Optional notional: empty string means "sem teto" (`requested_notional: null` on the wire), never `0`. */
export const optionalNotionalSchema = z.union([
  z.literal(""),
  z
    .string()
    .trim()
    .regex(DECIMAL_RE, "Use um número decimal positivo (ex.: 500.00)")
    .refine((value) => Number(value) > 0, "Deve ser maior que zero"),
]);

export const manualOrderFormShapeSchema = z.object({
  marketId: z.string().uuid("Selecione um mercado"),
  direction: manualOrderDirectionSchema,
  stop: positiveDecimalSchema,
  requestedNotional: optionalNotionalSchema,
});
export type ManualOrderFormShape = z.infer<typeof manualOrderFormShapeSchema>;

export interface StopValidation {
  ok: boolean;
  message?: string;
  /** `null` when the last price is not known yet -- distance cannot be computed, never shown as `0%`. */
  distancePct: number | null;
  /** `true` when `distancePct` exceeds the profile's `max_stop_distance_pct` -- informational only (see module docstring), never blocks submission on its own. */
  overCap: boolean;
}

/**
 * The hard, unambiguous half of check 7 (stop on the correct side of the
 * observed price for a LONG) plus the informational stop-distance-%-vs-cap
 * hint. `lastPrice`/`maxStopDistancePct` absent -> distance cannot be shown,
 * never guessed as `0%` (CLAUDE.md: `null` never becomes 0).
 */
export function validateStopAgainstMarket(
  stop: string,
  lastPrice: string | null,
  maxStopDistancePct: string | null,
): StopValidation {
  const stopValue = Number(stop);
  if (!Number.isFinite(stopValue) || stopValue <= 0) {
    return { ok: false, message: "Stop inválido.", distancePct: null, overCap: false };
  }
  if (lastPrice === null) {
    return { ok: true, distancePct: null, overCap: false };
  }
  const lastPriceValue = Number(lastPrice);
  if (!Number.isFinite(lastPriceValue) || lastPriceValue <= 0) {
    return { ok: true, distancePct: null, overCap: false };
  }
  // Exact string comparison (not `Number()`) -- the wire values are `Decimal`
  // strings, and a float round-trip could flip this side-of-price check for
  // two very close/very large prices (CLAUDE.md: `Decimal` never goes
  // through `float`).
  if (compareDecimalStrings(stop, lastPrice) >= 0) {
    return {
      ok: false,
      message: "O stop precisa ficar abaixo do último preço (SPOT só compra -- geometria de uma posição comprada).",
      distancePct: null,
      overCap: false,
    };
  }
  const distancePct = (lastPriceValue - stopValue) / lastPriceValue;
  const cap = maxStopDistancePct !== null ? Number(maxStopDistancePct) : null;
  const overCap = cap !== null && Number.isFinite(cap) && distancePct > cap;
  return { ok: true, distancePct, overCap };
}
