/**
 * "Aprovar (REAL)" on the proposal card (T4.17): off by default, and only
 * ever enabled when the executor is `ligado` -- `realAvailable` is the
 * card's own name for `lib/api/meme-live-types.ts`'s `realActionsAvailable`.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProposalCard } from "@/components/meme-desk/proposal-card";
import type { MemeDeskRow } from "@/lib/api/meme-desk-types";

afterEach(cleanup);

const ROW: MemeDeskRow = {
  id: "0199-proposal",
  mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
  origin: "rules",
  status: "proposed",
  proposed_at: "2026-09-12T11:59:30Z",
  expires_at: "2026-09-12T12:05:00Z",
  features_end_time: null,
  quote: { observed_at: null, source: null, mcap_sol: null, curve_progress_pct: null, price_sol_per_token: null, size_sol: null, fee_pct: null, fee_sol: null, cost_sol: null, tokens: null, reason: "no_snapshot_yet" },
  reasons: [],
  suggested: { size_sol: "0.02", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null },
  decision: null,
  decided_by: null,
  decided_at: null,
  refusal: null,
  token: null,
  rule_set: null,
  bet: null,
};

const NOW_MS = new Date("2026-09-12T12:00:00Z").getTime();

function renderCard(props: Partial<Parameters<typeof ProposalCard>[0]> = {}) {
  return render(
    <ProposalCard
      orgSlug="ever"
      row={ROW}
      nowMs={NOW_MS}
      canOperate={true}
      busy={false}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      realAvailable={false}
      onApproveReal={vi.fn()}
      {...props}
    />,
  );
}

describe("ProposalCard: 'Aprovar (REAL)' gated by the executor's own state", () => {
  it("is disabled and names the reason when the executor is not ligado", () => {
    renderCard({ realAvailable: false });
    const button = screen.getByRole("button", { name: "Aprovar (REAL)" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "O executor real não está ligado — veja o painel Executor real.");
  });

  it("is disabled without the Trader role even when the executor is ligado", () => {
    renderCard({ realAvailable: true, canOperate: false });
    const button = screen.getByRole("button", { name: "Aprovar (REAL)" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Requer o papel Trader ou superior nesta organização.");
  });

  it("is enabled and calls onApproveReal only when the executor is ligado and the role is ok", () => {
    const onApproveReal = vi.fn();
    renderCard({ realAvailable: true, canOperate: true, onApproveReal });
    const button = screen.getByRole("button", { name: "Aprovar (REAL)" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(onApproveReal).toHaveBeenCalledTimes(1);
  });

  it("the ordinary paper 'Aprovar' is unaffected by realAvailable", () => {
    renderCard({ realAvailable: false, canOperate: true });
    expect(screen.getByRole("button", { name: "Aprovar" })).toBeEnabled();
  });
});
