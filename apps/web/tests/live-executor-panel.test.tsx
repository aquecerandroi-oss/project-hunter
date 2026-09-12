/**
 * "Executor real" (T4.17 deliverable 1): the three honest states -- ausente,
 * desligado, ligado -- each naming what is actually true, never a placeholder.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// `SectionUnavailable` (the "falha ao carregar" state) calls `useRouter()` for its retry button.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import { LiveExecutorPanel } from "@/components/meme-live/live-executor-panel";
import type { LiveExecutor, MemeLive } from "@/lib/api/meme-live-types";

afterEach(cleanup);

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
    gates: { live: true, engineering: "2026-09-01", evidence: "2026-09-01", owner: "2026-09-01", signed_by: "Everton", valid_until: "2026-12-01T00:00:00Z" },
    policy: { profile: "meme_live_v0", wallet_max_sol: "0.5", max_sol_per_trade: "0.02", daily_loss_cap_sol: "0.1", max_open_positions: 2, rug_cooldown_s: 3600 },
    orders_by_state: { confirmed: 3, refused: 1 },
    positions_open: 1,
    blocked_exits: {},
    last_signature: null,
    last_refusal: null,
    day_start_sol_equity: "1.0",
    equity_sol: "0.95",
    daily_loss_sol: "0.05",
    auto_close_on_emergency: false,
    last_entries_tick_at: "2026-09-12T18:00:00Z",
    last_exits_tick_at: "2026-09-12T18:00:00Z",
    ...overrides,
  };
}

function live(overrides: Partial<MemeLive> = {}): MemeLive {
  return { label: "REAL", server_now: "2026-09-12T18:00:00Z", api_live_enabled: true, executor: executor(), positions: [], orders: [], ...overrides };
}

describe("LiveExecutorPanel: three states, each its own honest sentence", () => {
  it("falha ao carregar: an honest section-unavailable, never a broken page", () => {
    render(<LiveExecutorPanel live={null} loadReason="falha de rede" nowMs={0} />);
    expect(screen.getByText(/falha de rede/)).toBeInTheDocument();
  });

  it("ausente: the executor never proved it is up", () => {
    render(<LiveExecutorPanel live={live({ executor: executor({ status: "never" }) })} loadReason={null} nowMs={0} />);
    expect(screen.getByText("O perfil meme-live não está no ar.")).toBeInTheDocument();
    expect(screen.queryByText(/Tetos \(policy\)/)).not.toBeInTheDocument();
  });

  it("desligado: alive, but the executor's own flag is off", () => {
    render(<LiveExecutorPanel live={live({ executor: executor({ status: "alive", live_enabled: false }) })} loadReason={null} nowMs={0} />);
    expect(screen.getByText(/dinheiro real está desligado nele/)).toBeInTheDocument();
    expect(screen.queryByText(/Tetos \(policy\)/)).not.toBeInTheDocument();
  });

  it("ligado: wallet, tetos, portões, corta-circuito, perda do dia and blocked exits, every field named", () => {
    render(<LiveExecutorPanel live={live()} loadReason={null} nowMs={new Date("2026-09-12T18:00:05Z").getTime()} />);
    expect(screen.getByText(/9eoCK…WpvzN/)).toBeInTheDocument();
    expect(screen.getByText(/Tetos \(policy\)/)).toBeInTheDocument();
    expect(screen.getByText(/Portões A e B verdes, assinado por Everton/)).toBeInTheDocument();
    expect(screen.getByText("ATIVO")).toBeInTheDocument();
    expect(screen.getByText(/Perda do dia/)).toBeInTheDocument();
    expect(screen.getByText(/posições abertas: 1/)).toBeInTheDocument();
  });

  it("shows the API's own flag being off as its own warning, separate from the executor's state", () => {
    render(<LiveExecutorPanel live={live({ api_live_enabled: false })} loadReason={null} nowMs={0} />);
    expect(screen.getByText(/A API está com o dinheiro real desligado/)).toBeInTheDocument();
  });

  it("names a blocked exit by its refusal, never a bare code", () => {
    render(<LiveExecutorPanel live={live({ executor: executor({ blocked_exits: { "position-1": "pumpswap_sell_not_implemented" } }) })} loadReason={null} nowMs={0} />);
    expect(screen.getByText(/venda no PumpSwap ainda não existe/)).toBeInTheDocument();
  });
});
