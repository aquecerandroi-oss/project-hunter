/**
 * "Aprovar (REAL)" (T4.17): the double-confirmed sibling of `approve-sheet.test.tsx`
 * -- step (a) the four parameters (still editable, prefilled from `suggested`),
 * step (b) typing the exact SOL size back before the red button unlocks.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LiveExecutor } from "@/lib/api/meme-live-types";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

const { approveProposalActionMock } = vi.hoisted(() => ({ approveProposalActionMock: vi.fn() }));

vi.mock("@/lib/api/meme-desk-actions", () => ({
  approveProposalAction: approveProposalActionMock,
}));

afterEach(() => {
  cleanup();
  approveProposalActionMock.mockReset();
});

import { ApproveRealSheet } from "@/components/meme-desk/approve-real-sheet";

const ROW: MemeDeskRow = {
  id: "0199-proposal",
  mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
  origin: "rules",
  status: "proposed",
  proposed_at: "2026-09-12T11:59:30Z",
  expires_at: "2026-09-12T12:01:30Z",
  features_end_time: null,
  quote: { observed_at: "2026-09-12T11:59:00Z", source: "solana_rpc", mcap_sol: "9.14", curve_progress_pct: null, price_sol_per_token: null, size_sol: "0.02", fee_pct: "1.75", fee_sol: "0.00035", cost_sol: "0.02", tokens: "21000000", reason: null },
  reasons: ["progress_gate"],
  suggested: { size_sol: "0.02", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null },
  decision: null,
  decided_by: null,
  decided_at: null,
  refusal: null,
  token: { mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump", name: "bum bum", symbol: "BAM", creator: null, created_at: null, mayhem_enabled: null, mayhem_state: null, completed_at: null, migrated_at: null },
  rule_set: { id: "rs-1", name: "operator", version: "1", kind: "operator", max_sol_per_bet: "0.5" },
  bet: null,
};

const EXECUTOR: LiveExecutor = {
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
  policy: { profile: "meme_live_v0", wallet_max_sol: "0.5", max_sol_per_trade: "0.02", daily_loss_cap_sol: "0.1", max_open_positions: 2, rug_cooldown_s: 3600 },
  orders_by_state: {},
  positions_open: 0,
  blocked_exits: {},
  last_signature: null,
  last_refusal: null,
  day_start_sol_equity: null,
  equity_sol: null,
  daily_loss_sol: null,
  auto_close_on_emergency: false,
  last_entries_tick_at: null,
  last_exits_tick_at: null,
};

function renderSheet() {
  const onApproved = vi.fn();
  render(<ApproveRealSheet orgId="org-1" row={ROW} executor={EXECUTOR} onOpenChange={vi.fn()} onApproved={onApproved} />);
  return { onApproved };
}

function continueToConfirm() {
  fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
}

describe("ApproveRealSheet: the two confirmation steps", () => {
  it("step (a): pre-fills the four parameters and shows the rule set's cap", () => {
    renderSheet();
    expect(screen.getByLabelText("Tamanho (SOL)")).toHaveValue("0.02");
    expect(screen.getByLabelText("Alvo (×)")).toHaveValue("2");
    expect(screen.queryByText(/Isto assina uma transação real/)).not.toBeInTheDocument();
  });

  it("refuses an invalid target inline, never leaving step (a)", () => {
    renderSheet();
    fireEvent.change(screen.getByLabelText("Alvo (×)"), { target: { value: "1" } });
    continueToConfirm();
    expect(screen.getByText("O alvo deve ser maior que 1×.")).toBeInTheDocument();
    expect(screen.queryByText(/Isto assina uma transação real/)).not.toBeInTheDocument();
  });

  it("step (b): shows the ticker, the mint, the caps and the mainnet warning", () => {
    renderSheet();
    continueToConfirm();
    expect(screen.getByText(/bum bum \(BAM\)/)).toBeInTheDocument();
    expect(screen.getByText(/Isto assina uma transação real na mainnet\./)).toBeInTheDocument();
    expect(screen.getByText(/teto por compra: 0\.0200 SOL/)).toBeInTheDocument();
  });

  it("the red button stays disabled until the typed size numerically matches (tolerating a trailing zero)", () => {
    renderSheet();
    continueToConfirm();
    const submit = screen.getByRole("button", { name: "Assinar e enviar (REAL)" });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.03" } });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.020" } });
    expect(submit).toBeEnabled();
  });

  it("Voltar returns to step (a) without losing the edited values", () => {
    renderSheet();
    fireEvent.change(screen.getByLabelText("Tamanho (SOL)"), { target: { value: "0.03" } });
    continueToConfirm();
    fireEvent.click(screen.getByRole("button", { name: "Voltar" }));
    expect(screen.getByLabelText("Tamanho (SOL)")).toHaveValue("0.03");
  });

  it("submits mode: 'live' with one Idempotency-Key reused on retry, only once the typed size matches", async () => {
    approveProposalActionMock
      .mockResolvedValueOnce({ ok: false, problem: { type: "https://hunter.dev/problems/unexpected-response", title: "x", status: 502 } })
      .mockResolvedValueOnce({ ok: true, data: { row: { ...ROW, status: "approved" } } });
    const { onApproved } = renderSheet();

    continueToConfirm();
    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.02" } });
    fireEvent.click(screen.getByRole("button", { name: "Assinar e enviar (REAL)" }));
    await waitFor(() => expect(approveProposalActionMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Assinar e enviar (REAL)" }));
    await waitFor(() => expect(approveProposalActionMock).toHaveBeenCalledTimes(2));

    const [orgId, proposalId, firstKey, body] = approveProposalActionMock.mock.calls[0] as [string, string, string, { mode: string; size_sol: string }];
    const [, , secondKey] = approveProposalActionMock.mock.calls[1] as [string, string, string];
    expect(orgId).toBe("org-1");
    expect(proposalId).toBe(ROW.id);
    expect(body.mode).toBe("live");
    expect(secondKey).toBe(firstKey);
    expect(onApproved).toHaveBeenCalledTimes(1);
  });

  it("shows the brief's named REAL error (meme_live_disabled) in Portuguese", async () => {
    approveProposalActionMock.mockResolvedValueOnce({
      ok: false,
      problem: { type: "https://hunter.dev/problems/meme-desk-refused", title: "Unprocessable Entity", status: 422, detail: "mode 'live' needs ENABLE_MEME_LIVE_TRADING on the API (reason: meme_live_disabled)" },
    });
    renderSheet();
    continueToConfirm();
    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.02" } });
    fireEvent.click(screen.getByRole("button", { name: "Assinar e enviar (REAL)" }));
    expect(await screen.findByText("dinheiro real desligado na API (ENABLE_MEME_LIVE_TRADING)")).toBeInTheDocument();
  });

  it("an unrecognized refusal is still shown, named, never silent", async () => {
    approveProposalActionMock.mockResolvedValueOnce({
      ok: false,
      problem: { type: "https://hunter.dev/problems/meme-desk-refused", title: "x", status: 422, detail: "(reason: something_brand_new)" },
    });
    renderSheet();
    continueToConfirm();
    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.02" } });
    fireEvent.click(screen.getByRole("button", { name: "Assinar e enviar (REAL)" }));
    expect(await screen.findByText("recusa não prevista: something_brand_new")).toBeInTheDocument();
  });
});
