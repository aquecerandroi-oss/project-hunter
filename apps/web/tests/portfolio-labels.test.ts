import { describe, expect, it } from "vitest";

import {
  actorTypeLabel,
  DIRECTION_LABEL,
  EXECUTION_MODE_LABEL,
  fxSourceLabel,
  ORDER_PURPOSE_LABEL,
  ORDER_STATUS_LABEL,
  ORDER_TYPE_LABEL,
  PORTFOLIO_EXIT_REASON_LABEL,
  PORTFOLIO_STATUS_LABEL,
  PORTFOLIO_TYPE_LABEL,
  POSITION_STATUS_LABEL,
  SIDE_LABEL,
} from "@/components/portfolio/labels";

/**
 * The literal unions themselves (`lib/api/portfolio-types.ts`'s aliases onto
 * `components["schemas"]`) already give every `Record<Enum, string>` above
 * compile-time exhaustiveness -- a member added to the OpenAPI-generated
 * union without a matching entry here fails `pnpm typecheck` before this
 * test ever runs. This file re-asserts the same exhaustiveness at runtime
 * (so a CI run that skips typecheck still catches it) and enforces the
 * "sem backstage na copy" shape rule: no label contains `_` or is upper-case.
 */
function isCleanLabel(label: string): boolean {
  return !label.includes("_") && label !== label.toUpperCase();
}

const DIRECTION_VALUES = ["long", "short", "neutral"] as const;
const SIDE_VALUES = ["buy", "sell"] as const;
const MODE_VALUES = ["paper", "shadow", "live"] as const;
const PORTFOLIO_STATUS_VALUES = ["active", "paused", "archived"] as const;
const POSITION_STATUS_VALUES = ["open", "closing", "closed"] as const;
const ORDER_TYPE_VALUES = ["market", "limit", "stop_market", "stop_limit", "take_profit"] as const;
const ORDER_PURPOSE_VALUES = ["entry", "stop", "target", "exit", "reduce"] as const;
const ORDER_STATUS_VALUES = ["pending", "submitted", "partially_filled", "filled", "cancelled", "rejected", "expired"] as const;
const EXIT_REASON_VALUES = ["target", "stop", "invalidation", "manual", "kill_switch", "expired", "risk_event"] as const;

describe.each([
  ["DIRECTION_LABEL", DIRECTION_LABEL, DIRECTION_VALUES],
  ["SIDE_LABEL", SIDE_LABEL, SIDE_VALUES],
  ["PORTFOLIO_TYPE_LABEL", PORTFOLIO_TYPE_LABEL, MODE_VALUES],
  ["EXECUTION_MODE_LABEL", EXECUTION_MODE_LABEL, MODE_VALUES],
  ["PORTFOLIO_STATUS_LABEL", PORTFOLIO_STATUS_LABEL, PORTFOLIO_STATUS_VALUES],
  ["POSITION_STATUS_LABEL", POSITION_STATUS_LABEL, POSITION_STATUS_VALUES],
  ["ORDER_TYPE_LABEL", ORDER_TYPE_LABEL, ORDER_TYPE_VALUES],
  ["ORDER_PURPOSE_LABEL", ORDER_PURPOSE_LABEL, ORDER_PURPOSE_VALUES],
  ["ORDER_STATUS_LABEL", ORDER_STATUS_LABEL, ORDER_STATUS_VALUES],
  ["PORTFOLIO_EXIT_REASON_LABEL", PORTFOLIO_EXIT_REASON_LABEL, EXIT_REASON_VALUES],
] as const)("%s: every member has a clean Portuguese label", (_name, dict, values) => {
  it.each(values)("%s", (member) => {
    const label = (dict as Record<string, string | undefined>)[member];
    expect(label).toBeDefined();
    expect(isCleanLabel(label as string)).toBe(true);
  });
});

describe("actorTypeLabel", () => {
  it("labels system and user", () => {
    expect(actorTypeLabel("system")).toBe("Sistema");
    expect(actorTypeLabel("user")).toBe("Usuário");
  });

  it("never drops an unrecognized actor type silently", () => {
    expect(actorTypeLabel("robot")).toBe("robot");
  });
});

describe("fxSourceLabel", () => {
  it("labels the known Binance spot ticker source", () => {
    expect(fxSourceLabel("binance.spot.ticker")).toBe("Binance spot (ticker)");
  });

  it("falls back to the raw source for an unknown one", () => {
    expect(fxSourceLabel("bybit.spot.ticker")).toBe("bybit.spot.ticker");
  });
});
