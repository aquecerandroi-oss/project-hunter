import { describe, expect, it } from "vitest";

import {
  manualOrderDetailSchema,
  manualOrderListPageSchema,
  manualOrderOutSchema,
  manualOrderRequestBodySchema,
  manualOrdersPath,
  riskDecisionSchema,
} from "@/lib/api/manual-orders-types";

const APPROVED_DECISION = {
  approved: true,
  kind: "entry",
  proposal_id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000001",
  portfolio_id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000002",
  market: { exchange: "binance", symbol: "BTCUSDT", market_type: "spot", base_asset: "BTC", quote_asset: "USDT" },
  limits_profile: "paper_v1",
  effective_kill_switch: "ACTIVE",
  cancel_pending: false,
  shadow_only: false,
  checks: [{ name: "kill_switch", state: "passed", value: null, limit: null, message: "" }],
  sizing: {
    entry_ref: "65000.0000000000",
    sizing_price: "65000.0000000000",
    stop: "63700.0000000000",
    stop_distance_pct: "0.0200000000",
    cost_pct: "0.0010000000",
    caps: [{ name: "risk_per_trade", notional: "1000.0000000000", limit: "0.0025000000", detail: "risco ..." }],
    binding_limit: { name: "risk_per_trade", notional: "1000.0000000000", limit: "0.0025000000", detail: "risco ..." },
    binding_constraint: "risk_per_trade",
    size_without_multipliers: { name: "sem_multiplicadores", qty: "0.015", notional: "975.00" },
    size_without_participation: { name: "sem_participacao", qty: "0.02", notional: "1300.00" },
    tied_limits: [],
    notional_before_multiplier: "1000.0000000000",
    kill_switch_multiplier: "1.0000000000",
    notional_after_multiplier: "1000.0000000000",
    qty: "0.0153800000",
    notional: "999.7000000000",
    planned_risk_quote: "25.0000000000",
    planned_risk_pct: "0.0025000000",
  },
};

describe("riskDecisionSchema: mirrors packages/risk-core/hunter_risk/decision.py", () => {
  it("parses a real approved entry decision shape", () => {
    const result = riskDecisionSchema.safeParse(APPROVED_DECISION);
    expect(result.success).toBe(true);
  });

  it("parses a refused decision with no sizing", () => {
    const refused = {
      ...APPROVED_DECISION,
      approved: false,
      sizing: null,
      checks: [
        { name: "kill_switch", state: "passed", message: "" },
        { name: "stop_distance", state: "failed", value: "0.05", limit: "0.03", message: "fora do teto" },
      ],
    };
    const result = riskDecisionSchema.safeParse(refused);
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.sizing).toBeNull();
  });

  it("rejects a decision missing a required field (proposal_id)", () => {
    const broken: Record<string, unknown> = { ...APPROVED_DECISION };
    delete broken.proposal_id;
    expect(riskDecisionSchema.safeParse(broken).success).toBe(false);
  });
});

const MARKET_ID = "3f6b3b9a-6b1a-4e6a-9c1a-000000000003";

const REAL_OUTCOME = {
  id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000004",
  market_id: MARKET_ID,
  side: "buy",
  type: "market",
  purpose: "entry",
  execution_mode: "paper",
  status: "filled",
  qty: "0.0153800000",
  price: "65010.0000000000",
  stop_price: null,
  filled_qty: "0.0153800000",
  avg_fill_price: "65010.0000000000",
  created_at: "2026-09-10T12:00:05Z",
  completed_at: "2026-09-10T12:00:05Z",
};

describe("manualOrderOutSchema / manualOrderDetailSchema", () => {
  it("parses a pending 202 body with a null decision (market_id/direction always present, T3.68)", () => {
    const body = { request_id: "req-1", market_id: MARKET_ID, direction: "long", status: "pending", filed_at: "2026-09-10T12:00:00Z", decision: null };
    expect(manualOrderOutSchema.safeParse(body).success).toBe(true);
  });

  it("rejects a body missing market_id -- ManualOrderOut always carries it (schemas/orders.py)", () => {
    const body = { request_id: "req-1", direction: "long", status: "pending", filed_at: "2026-09-10T12:00:00Z", decision: null };
    expect(manualOrderOutSchema.safeParse(body).success).toBe(false);
  });

  it("parses a decided body carrying a real decision", () => {
    const body = { request_id: "req-1", market_id: MARKET_ID, direction: "long", status: "decided", filed_at: "2026-09-10T12:00:00Z", decision: APPROVED_DECISION };
    expect(manualOrderOutSchema.safeParse(body).success).toBe(true);
  });

  it("the detail schema parses a real OrderOut-shaped outcome (ManualOrderDetailOut.outcome, T3.68)", () => {
    const body = {
      request_id: "req-1",
      market_id: MARKET_ID,
      direction: "long",
      status: "decided",
      filed_at: "2026-09-10T12:00:00Z",
      decision: APPROVED_DECISION,
      outcome: REAL_OUTCOME,
    };
    const result = manualOrderDetailSchema.safeParse(body);
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.outcome).toEqual(REAL_OUTCOME);
  });

  it("the detail schema parses a null outcome (pending/rejected/expired/not-yet-picked-up)", () => {
    const body = {
      request_id: "req-1",
      market_id: MARKET_ID,
      direction: "long",
      status: "pending",
      filed_at: "2026-09-10T12:00:00Z",
      decision: null,
      outcome: null,
    };
    expect(manualOrderDetailSchema.safeParse(body).success).toBe(true);
  });
});

describe("manualOrderRequestBodySchema", () => {
  it("accepts a well-formed request with no notional cap", () => {
    const body = { market_id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000001", direction: "long", stop: "63700.00", requested_notional: null };
    expect(manualOrderRequestBodySchema.safeParse(body).success).toBe(true);
  });

  it("rejects a non-uuid market_id", () => {
    const body = { market_id: "btcusdt", direction: "long", stop: "63700.00", requested_notional: null };
    expect(manualOrderRequestBodySchema.safeParse(body).success).toBe(false);
  });
});

describe("manualOrderListPageSchema", () => {
  it("parses an empty page", () => {
    expect(manualOrderListPageSchema.safeParse({ items: [], next_cursor: null }).success).toBe(true);
  });

  it("parses a page whose item is exactly ManualOrderOut's shape, passing through an extra real API field", () => {
    const page = {
      items: [
        {
          request_id: "req-1",
          market_id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000003",
          direction: "long",
          status: "decided",
          filed_at: "2026-09-10T12:00:00Z",
          decision: null,
          extra_field_from_a_newer_api: 42,
        },
      ],
      next_cursor: null,
    };
    const result = manualOrderListPageSchema.safeParse(page);
    expect(result.success).toBe(true);
    if (result.success) expect((result.data.items[0] as Record<string, unknown>).extra_field_from_a_newer_api).toBe(42);
  });
});

describe("manualOrdersPath", () => {
  it("builds the org-scoped order-requests path this app's real routing uses (T3.68: .../orders already means execution orders)", () => {
    expect(manualOrdersPath("org-1", "wallet-1")).toBe("/api/v1/orgs/org-1/portfolios/wallet-1/order-requests");
  });
});
