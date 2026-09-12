/**
 * The approval sheet (contract §Tela): pre-filled from `suggested`,
 * editable, validated before any request, one `Idempotency-Key` per
 * opening reused across retries of the same submission.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

const { approveProposalActionMock } = vi.hoisted(() => ({ approveProposalActionMock: vi.fn() }));

vi.mock("@/lib/api/meme-desk-actions", () => ({
  approveProposalAction: approveProposalActionMock,
}));

afterEach(() => {
  cleanup();
  approveProposalActionMock.mockReset();
});

import { ApproveSheet } from "@/components/meme-desk/approve-sheet";

const ROW: MemeDeskRow = {
  id: "0199-proposal",
  mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
  origin: "rules",
  status: "proposed",
  proposed_at: "2026-09-12T11:59:30Z",
  expires_at: "2026-09-12T12:01:30Z",
  features_end_time: null,
  quote: { observed_at: "2026-09-12T11:59:00Z", source: "solana_rpc", mcap_sol: "9.14", curve_progress_pct: null, price_sol_per_token: null, size_sol: "0.2", fee_pct: "1.75", fee_sol: "0.0035", cost_sol: "0.2", tokens: "21000000", reason: null },
  reasons: ["progress_gate"],
  suggested: { size_sol: "0.2", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null },
  decision: null,
  decided_by: null,
  decided_at: null,
  refusal: null,
  token: { mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump", name: "bum bum", symbol: "bam bum", creator: null, created_at: null, mayhem_enabled: null, mayhem_state: null, completed_at: null, migrated_at: null },
  rule_set: { id: "rs-1", name: "operator", version: "1", kind: "operator", max_sol_per_bet: "0.5" },
  bet: null,
};

function renderSheet() {
  const onApproved = vi.fn();
  render(<ApproveSheet orgId="org-1" row={ROW} onOpenChange={vi.fn()} onApproved={onApproved} />);
  return { onApproved };
}

describe("ApproveSheet", () => {
  it("pre-fills the four parameters from suggested", () => {
    renderSheet();
    expect(screen.getByLabelText("Tamanho (SOL)")).toHaveValue("0.2");
    expect(screen.getByLabelText("Alvo (×)")).toHaveValue("2");
    expect(screen.getByLabelText("Trailing (%)")).toHaveValue("30");
    expect(screen.getByLabelText("Espera máx (s)")).toHaveValue("900");
    expect(screen.getByText(/teto por aposta do conjunto: 0\.5000 SOL/)).toBeInTheDocument();
  });

  it("refuses an invalid target inline and never calls the action", async () => {
    renderSheet();
    fireEvent.change(screen.getByLabelText("Alvo (×)"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Aprovar compra (papel)" }));
    expect(await screen.findByText("O alvo deve ser maior que 1×.")).toBeInTheDocument();
    expect(approveProposalActionMock).not.toHaveBeenCalled();
  });

  it("submits the edited values with one Idempotency-Key, reused on retry", async () => {
    approveProposalActionMock
      .mockResolvedValueOnce({ ok: false, problem: { type: "https://hunter.dev/problems/unexpected-response", title: "x", status: 502 } })
      .mockResolvedValueOnce({ ok: true, data: { row: { ...ROW, status: "approved" } } });
    const { onApproved } = renderSheet();

    fireEvent.change(screen.getByLabelText("Tamanho (SOL)"), { target: { value: "0.3" } });
    fireEvent.click(screen.getByRole("button", { name: "Aprovar compra (papel)" }));
    await waitFor(() => expect(approveProposalActionMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/formato esperado/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Aprovar compra (papel)" }));
    await waitFor(() => expect(approveProposalActionMock).toHaveBeenCalledTimes(2));

    const [orgId, proposalId, firstKey, body] = approveProposalActionMock.mock.calls[0] as [string, string, string, { size_sol: string; max_hold_s: number }];
    const [, , secondKey] = approveProposalActionMock.mock.calls[1] as [string, string, string];
    expect(orgId).toBe("org-1");
    expect(proposalId).toBe(ROW.id);
    expect(body.size_sol).toBe("0.3");
    expect(body.max_hold_s).toBe(900);
    expect(secondKey).toBe(firstKey);
    expect(onApproved).toHaveBeenCalledTimes(1);
  });

  it("shows the API's named refusal in Portuguese", async () => {
    approveProposalActionMock.mockResolvedValueOnce({
      ok: false,
      problem: { type: "https://hunter.dev/problems/meme-desk-refused", title: "Unprocessable Entity", status: 422, detail: "size_sol 0.6 exceeds the rule set's max_sol_per_bet 0.5 (reason: exceeds_max_sol_per_bet)" },
    });
    renderSheet();
    fireEvent.change(screen.getByLabelText("Tamanho (SOL)"), { target: { value: "0.6" } });
    fireEvent.click(screen.getByRole("button", { name: "Aprovar compra (papel)" }));
    expect(await screen.findByText(/teto por aposta do conjunto de regras/)).toBeInTheDocument();
  });
});
