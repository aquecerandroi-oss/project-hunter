import { describe, expect, it } from "vitest";

import { buildLiveOutcomeIndex } from "@/components/meme-live/live-index";
import {
  executorStatusLabel,
  killSwitchBadgeVariant,
  killSwitchStateLabel,
  liveMarkSourceLabel,
  liveOrderStatusLabel,
  livePositionStatusLabel,
  realActionProblemMessage,
} from "@/components/meme-live/labels";
import { gatesLines, killSwitchSourceLines, policyLines, truncateAddress } from "@/components/meme-live/live-format";
import { executorRefusalLabel, markReasonLabel } from "@/components/meme-live/refusal-labels";
import {
  EXECUTOR_STATUSES,
  LIVE_ORDER_STATUSES,
  LIVE_POSITION_STATUSES,
  executorPanelState,
  realActionsAvailable,
} from "@/lib/api/meme-live-types";
import type { LiveExecutor, LiveOrder, LivePosition, MemeLive } from "@/lib/api/meme-live-types";

function executor(overrides: Partial<LiveExecutor> = {}): LiveExecutor {
  return {
    status: "alive",
    heartbeat_key: "hb:meme:executor",
    heartbeat_ts: "2026-09-12T18:00:00Z",
    executor_ts: "2026-09-12T18:00:00Z",
    error: null,
    live_enabled: true,
    cluster: "mainnet-beta",
    wallet_pubkey: "9eoCKjVtEzehnnJSv9yYEwSSkYPANrxUZRq7U4HWpvzN",
    wallet_sol_balance: "1.5",
    wallet_read_at: "2026-09-12T18:00:00Z",
    kill_switch: "ACTIVE",
    kill_switch_latched: false,
    kill_switch_latch_reason: null,
    kill_switch_sources: { system: "ACTIVE", redis: "", file: "", wallet: "ACTIVE" },
    gates: null,
    policy: null,
    orders_by_state: {},
    positions_open: 0,
    blocked_exits: {},
    last_signature: null,
    last_refusal: null,
    day_start_sol_equity: null,
    equity_sol: null,
    daily_loss_sol: null,
    auto_close_on_emergency: false,
    last_entries_tick_at: "2026-09-12T18:00:00Z",
    last_exits_tick_at: "2026-09-12T18:00:00Z",
    ...overrides,
  };
}

describe("meme-live labels are exhaustive and never leak a raw enum", () => {
  it("every executor status has a label distinct from the raw value", () => {
    for (const status of EXECUTOR_STATUSES) {
      expect(executorStatusLabel(status)).not.toBe(status);
    }
    expect(executorStatusLabel("something_new")).toBe("estado não previsto");
  });

  it("kill switch states: known four, the empty 'not configured' source, and an unrecognized value shown as-is", () => {
    expect(killSwitchStateLabel("ACTIVE")).toBe("ATIVO");
    expect(killSwitchStateLabel("WARNING")).toBe("AVISO");
    expect(killSwitchStateLabel("TRADING_DISABLED")).toBe("BLOQUEADO");
    expect(killSwitchStateLabel("EMERGENCY")).toBe("EMERGÊNCIA");
    expect(killSwitchStateLabel("")).toBe("não configurada");
    expect(killSwitchStateLabel("WEIRD")).toBe("WEIRD");
    expect(killSwitchBadgeVariant("WARNING")).toBe("warning");
    expect(killSwitchBadgeVariant("EMERGENCY")).toBe("negative");
    expect(killSwitchBadgeVariant("TRADING_DISABLED")).toBe("negative");
    expect(killSwitchBadgeVariant("ACTIVE")).toBe("default");
  });

  it("every live order status has a label", () => {
    for (const status of LIVE_ORDER_STATUSES) {
      expect(liveOrderStatusLabel(status)).not.toBe(status);
    }
    expect(liveOrderStatusLabel("something_new")).toBe("estado não previsto");
  });

  it("every live position status has a label", () => {
    for (const status of LIVE_POSITION_STATUSES) {
      expect(livePositionStatusLabel(status)).not.toBe(status);
    }
    expect(livePositionStatusLabel("something_new")).toBe("estado não previsto");
  });

  it("mark source: known three, null is silence, unrecognized is still shown", () => {
    expect(liveMarkSourceLabel("solana_rpc")).toContain("cadeia");
    expect(liveMarkSourceLabel("curve_snapshot")).toContain("curva");
    expect(liveMarkSourceLabel("tape")).toContain("fita");
    expect(liveMarkSourceLabel(null)).toBeNull();
    expect(liveMarkSourceLabel("weird")).toBe("marcada por weird");
  });
});

describe("realActionProblemMessage: the brief's exact vocabulary, with a named fallback", () => {
  const base = { title: "x", status: 422 };

  it("meme_live_disabled names the API's own flag", () => {
    const message = realActionProblemMessage({ ...base, type: "https://hunter.dev/problems/meme-desk-refused", detail: "mode 'live' needs ENABLE_MEME_LIVE_TRADING on the API (reason: meme_live_disabled)" });
    expect(message).toBe("dinheiro real desligado na API (ENABLE_MEME_LIVE_TRADING)");
  });

  it("exceeds_max_sol_per_bet, rule_set_inactive and expired are each their own sentence", () => {
    expect(realActionProblemMessage({ ...base, type: "x", detail: "(reason: exceeds_max_sol_per_bet)" })).toContain("teto por aposta");
    expect(realActionProblemMessage({ ...base, type: "x", detail: "(reason: rule_set_inactive)" })).toContain("não está mais ativo");
    expect(realActionProblemMessage({ ...base, type: "x", detail: "(reason: expired)" })).toContain("prazo desta proposta venceu");
  });

  it("an unrecognized reason falls back to the literal, named sentence the brief asks for", () => {
    expect(realActionProblemMessage({ ...base, type: "x", detail: "(reason: totally_unheard_of)" })).toBe("recusa não prevista: totally_unheard_of");
  });

  it("falls back by status/type slug when there is no named reason at all", () => {
    expect(realActionProblemMessage({ status: 403, title: "x", type: "https://hunter.dev/problems/insufficient-role" })).toContain("Trader");
    expect(realActionProblemMessage({ status: 404, title: "x", type: "https://hunter.dev/problems/meme-live-position-not-found" })).toContain("Posição real não encontrada");
    expect(realActionProblemMessage({ status: 500, title: "x", type: "https://hunter.dev/problems/whatever" })).toContain("indisponível");
  });
});

describe("executorRefusalLabel: the RISK_ENGINE_MEME.md §4 vocabulary, exhaustive with a named fallback", () => {
  it("translates a representative check name from each family", () => {
    expect(executorRefusalLabel("meme_live_disabled")).toContain("ENABLE_MEME_LIVE_TRADING");
    expect(executorRefusalLabel("bundled_share_unmeasurable")).toContain("bundle");
    expect(executorRefusalLabel("wallet_over_max_sol")).toContain("teto");
    expect(executorRefusalLabel("daily_loss_cap_reached")).toContain("perda diária");
    expect(executorRefusalLabel("pumpswap_sell_not_implemented")).toContain("PumpSwap");
    expect(executorRefusalLabel("reservation_expired")).toContain("5 s");
    expect(executorRefusalLabel("small_test_scope_exhausted")).toContain("esgotado");
  });

  it("never returns the bare code -- an unrecognized one is still prefixed", () => {
    expect(executorRefusalLabel("never_seen_before")).toBe("recusa: never_seen_before");
    expect(executorRefusalLabel(null)).toBeNull();
    expect(executorRefusalLabel(undefined)).toBeNull();
  });

  it("dynamic-suffix refusals keep the motivo, not just the prefix", () => {
    expect(executorRefusalLabel("rpc_unreachable:TimeoutError")).toBe("RPC inalcançável (TimeoutError)");
    expect(executorRefusalLabel("fill_decode_failed:ValueError")).toContain("ValueError");
    expect(executorRefusalLabel("simulation_failed:AccountNotFound")).toContain("AccountNotFound");
  });

  it("markReasonLabel covers the executor's own mark-absence reasons", () => {
    expect(markReasonLabel("curve_complete")).toContain("curva concluída");
    expect(markReasonLabel("curve_not_found")).toContain("não encontrada");
    expect(markReasonLabel("rpc_unreachable:OSError")).toContain("OSError");
    expect(markReasonLabel(null)).toBeNull();
  });
});

describe("policyLines / gatesLines / killSwitchSourceLines: honest reads of a dict[str, Any], never a fabricated number", () => {
  it("policyLines lists only the fields present, formatted with the right unit", () => {
    const lines = policyLines({ profile: "meme_live_v0", wallet_max_sol: "0.5", max_sol_per_trade: "0.02", daily_loss_cap_sol: "0.1", max_open_positions: 2, rug_cooldown_s: 3600 });
    expect(lines.some((l) => l.includes("meme_live_v0"))).toBe(true);
    expect(lines.some((l) => l.includes("0.0200 SOL") || l.includes("0.02"))).toBe(true);
    expect(lines.some((l) => l.includes("até 2"))).toBe(true);
    expect(lines.some((l) => l.includes("3600 s"))).toBe(true);
  });

  it("policyLines never fabricates: null/absent policy says so", () => {
    expect(policyLines(null)).toEqual(["tetos: sem leitura do executor"]);
    expect(policyLines({})).toEqual(["tetos: nenhum campo reconhecido na leitura do executor"]);
  });

  it("gatesLines: sem leitura, vermelho, teste pequeno com decisão, e verde completo", () => {
    expect(gatesLines(null)).toEqual(["portões: sem leitura do executor"]);
    expect(gatesLines({ live: false })).toEqual(["Portões A/B vermelhos — sem autorização para operar com dinheiro real"]);
    const smallTest = gatesLines({
      live: true,
      small_test: { authorized_by: "Everton", max_sol_per_trade: "0.02", max_total_sol: "0.5", max_trades: 10, expires_at: "2026-09-20T00:00:00Z", decision_note: "obsidian/06-DECISIONS/2026-09-12-teste.md" },
    });
    expect(smallTest[0]).toContain("Everton");
    expect(smallTest.some((l) => l.includes("obsidian"))).toBe(true);
    const full = gatesLines({ live: true, signed_by: "Everton", valid_until: "2026-12-01T00:00:00Z" });
    expect(full[0]).toContain("Everton");
  });

  it("killSwitchSourceLines: the four sources always present, empty string is a fact not a state", () => {
    const lines = killSwitchSourceLines({ system: "ACTIVE", redis: "", file: "", wallet: "TRADING_DISABLED" });
    expect(lines).toHaveLength(4);
    expect(lines.find((l) => l.key === "redis")?.value).toBe("");
    expect(lines.find((l) => l.key === "wallet")?.value).toBe("TRADING_DISABLED");
  });

  it("truncateAddress shortens a pubkey the same 5+5 way as a mint", () => {
    expect(truncateAddress("9eoCKjVtEzehnnJSv9yYEwSSkYPANrxUZRq7U4HWpvzN")).toBe("9eoCK…WpvzN");
    expect(truncateAddress("short")).toBe("short");
  });
});

describe("executorPanelState / realActionsAvailable: the three states the brief names", () => {
  it("ausente: any non-alive status", () => {
    expect(executorPanelState(executor({ status: "never" }))).toBe("ausente");
    expect(executorPanelState(executor({ status: "stalled" }))).toBe("ausente");
    expect(executorPanelState(executor({ status: "redis_unavailable" }))).toBe("ausente");
  });

  it("desligado: alive but the executor's own flag is off", () => {
    expect(executorPanelState(executor({ status: "alive", live_enabled: false }))).toBe("desligado");
  });

  it("ligado: alive and the executor's own flag is on", () => {
    expect(executorPanelState(executor({ status: "alive", live_enabled: true }))).toBe("ligado");
  });

  it("realActionsAvailable requires both the executor's flag AND the API's own copy", () => {
    const live = (apiLiveEnabled: boolean, execOverrides: Partial<LiveExecutor>): MemeLive => ({
      label: "REAL",
      server_now: "2026-09-12T18:00:00Z",
      api_live_enabled: apiLiveEnabled,
      executor: executor(execOverrides),
      positions: [],
      orders: [],
    });
    expect(realActionsAvailable(live(true, { status: "alive", live_enabled: true }))).toBe(true);
    expect(realActionsAvailable(live(false, { status: "alive", live_enabled: true }))).toBe(false);
    expect(realActionsAvailable(live(true, { status: "alive", live_enabled: false }))).toBe(false);
    expect(realActionsAvailable(live(true, { status: "never", live_enabled: true }))).toBe(false);
  });
});

describe("buildLiveOutcomeIndex: pairs a proposal with its real order/position (T4.17 deliverable 4)", () => {
  function order(overrides: Partial<LiveOrder> = {}): LiveOrder {
    return {
      id: "order-1",
      proposal_id: "proposal-1",
      mint: "mint1",
      side: "buy",
      client_order_id: "meme:proposal-1",
      attempt: 1,
      status: "refused",
      reason: "wallet_over_max_sol",
      tx_signature: null,
      admission_approved: false,
      first_refusal: "wallet_over_max_sol",
      binding_constraint: null,
      sol_final: null,
      fill: null,
      received_at: "2026-09-12T18:00:00Z",
      submitted_at: null,
      settled_at: null,
      ...overrides,
    };
  }

  function position(overrides: Partial<LivePosition> = {}): LivePosition {
    return {
      id: "position-1",
      proposal_id: "proposal-2",
      mint: "mint2",
      status: "open",
      entry_at: "2026-09-12T18:00:00Z",
      tokens: 1000,
      sol_spent: "0.02",
      initial_risk_sol: "0.02",
      params: {},
      mark_sol: null,
      mark_at: null,
      mark_source: null,
      mark_reason: null,
      high_water_sol: null,
      exit_intent: null,
      sell_requested_at: null,
      sell_requested_by: null,
      exit_at: null,
      exit: null,
      sol_received: null,
      pnl_sol: null,
      r_multiple: null,
      migrated: false,
      can_sell_now: true,
      ...overrides,
    };
  }

  it("returns an empty index for null/absent live data", () => {
    expect(buildLiveOutcomeIndex(null).size).toBe(0);
    expect(buildLiveOutcomeIndex(undefined).size).toBe(0);
  });

  it("a refused order with no position still gets an entry, keyed by proposal_id", () => {
    const index = buildLiveOutcomeIndex({ label: "x", server_now: "2026-09-12T18:00:00Z", api_live_enabled: true, executor: executor(), positions: [], orders: [order()] });
    const entry = index.get("proposal-1");
    expect(entry?.position).toBeNull();
    expect(entry?.order?.status).toBe("refused");
  });

  it("a confirmed position wins over an older order for the same proposal", () => {
    const index = buildLiveOutcomeIndex({
      label: "x",
      server_now: "2026-09-12T18:00:00Z",
      api_live_enabled: true,
      executor: executor(),
      positions: [position({ proposal_id: "proposal-3" })],
      orders: [order({ id: "o1", proposal_id: "proposal-3", received_at: "2026-09-12T17:00:00Z" })],
    });
    const entry = index.get("proposal-3");
    expect(entry?.position?.id).toBe("position-1");
    expect(entry?.order?.id).toBe("o1");
  });

  it("the newest order is kept when a proposal has more than one attempt", () => {
    const index = buildLiveOutcomeIndex({
      label: "x",
      server_now: "2026-09-12T18:00:00Z",
      api_live_enabled: true,
      executor: executor(),
      positions: [],
      orders: [order({ id: "old", received_at: "2026-09-12T17:00:00Z" }), order({ id: "new", received_at: "2026-09-12T17:05:00Z" })],
    });
    expect(index.get("proposal-1")?.order?.id).toBe("new");
  });
});
