import { describe, expect, it } from "vitest";

import {
  checkStateLabel,
  limitCapLabel,
  manualOrderProblemMessage,
  riskCheckLabel,
} from "@/components/portfolio/manual-order-labels";
import type { CheckState } from "@/lib/api/manual-orders-types";

describe("riskCheckLabel: docs/RISK_ENGINE.md §3 vocabulary, never a raw enum on screen", () => {
  it("labels every check name from §3.1/§3.2 in Portuguese", () => {
    const names = [
      "kill_switch",
      "portfolio_status",
      "modality",
      "data_quality",
      "market_gap",
      "market_in_universe",
      "signal_validity",
      "stop_distance",
      "liquidity_24h",
      "spread",
      "book_depth",
      "beta_validity",
      "concurrent_positions",
      "duplicate_position",
      "aggregate_risk_budget",
      "daily_loss",
      "drawdown",
      "sizing",
      "participation",
      "slippage_estimate",
      "cash",
      "exposure_after",
    ];
    for (const name of names) {
      expect(riskCheckLabel(name)).not.toBe(name);
    }
  });

  it("falls back to the raw name for an unrecognized check, never throws", () => {
    expect(riskCheckLabel("a_future_check_nobody_named_yet")).toBe("a_future_check_nobody_named_yet");
  });
});

describe("limitCapLabel: docs/RISK_ENGINE.md §4's nine ceilings", () => {
  it("labels every ceiling name sizing.py builds", () => {
    const names = [
      "requested",
      "risk_per_trade",
      "aggregate_risk",
      "market_participation",
      "book_depth",
      "asset_exposure",
      "total_exposure",
      "beta_exposure",
      "cash",
    ];
    for (const name of names) {
      expect(limitCapLabel(name)).not.toBe(name);
    }
  });
});

describe("checkStateLabel", () => {
  it("labels all three states", () => {
    const states: CheckState[] = ["passed", "failed", "unavailable"];
    for (const state of states) {
      expect(checkStateLabel(state)).toBeTruthy();
    }
  });
});

describe("manualOrderProblemMessage: never a raw code, always a Portuguese sentence", () => {
  it("maps the real 409 slugs (services/admission.py: OrderReplayConflictError/WalletNotOpenError)", () => {
    expect(manualOrderProblemMessage({ type: "https://hunter.dev/problems/idempotency-key-conflict", title: "x", status: 409 })).toMatch(
      /chave de envio/i,
    );
    expect(manualOrderProblemMessage({ type: "https://hunter.dev/problems/wallet-not-open", title: "x", status: 409 })).toMatch(
      /não está aberta/i,
    );
  });

  it("maps insufficient-role (403, auth/rbac.py) to the Trader-or-above sentence", () => {
    expect(manualOrderProblemMessage({ type: "https://hunter.dev/problems/insufficient-role", title: "x", status: 403 })).toMatch(/trader/i);
  });

  it("maps order-refused (422) by the reason embedded in detail (services/orders_derive.py)", () => {
    const marketNotSpot = manualOrderProblemMessage({
      type: "https://hunter.dev/problems/order-refused",
      title: "x",
      status: 422,
      detail: "market ... is not an executable SPOT market (reason: market_not_executable_spot): ...",
    });
    expect(marketNotSpot).toMatch(/SPOT executável/);

    const shortRefused = manualOrderProblemMessage({
      type: "https://hunter.dev/problems/order-refused",
      title: "x",
      status: 422,
      detail: "direction 'short' is refused on SPOT (reason: short_not_supported_spot): ...",
    });
    expect(shortRefused).toMatch(/short/i);
  });

  it("falls back to a status-based sentence for an unrecognized type, never showing the raw slug", () => {
    const message = manualOrderProblemMessage({ type: "https://hunter.dev/problems/something-new", title: "x", status: 422 });
    expect(message).not.toContain("something-new");
    expect(message.length).toBeGreaterThan(0);
  });

  it("maps 403 to the role sentence regardless of type", () => {
    const message = manualOrderProblemMessage({ type: "https://hunter.dev/problems/forbidden", title: "x", status: 403 });
    expect(message).toMatch(/trader/i);
  });
});
