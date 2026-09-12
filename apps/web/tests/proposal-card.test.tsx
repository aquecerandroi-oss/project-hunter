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

/**
 * T4.19/T4.20: `manual_plan` -- the loop's own Portuguese text ("Comprar 0,05
 * SOL de X até HH:MM:SS. Vender até HH:MM — antes disso se…") that Everton
 * follows by hand in the terminal. Shown whole, in an attention block, with
 * the countdown the plan's "até" refers to and a one-tap copy of the mint;
 * without it the card is exactly what it was.
 */
const PLAN = "Comprar 0,05 SOL de BAM até 09:03:00 (proposta expira). Vender até 09:33 (30 min) — antes disso se triplicar (3×), se cair pela metade (−50 %), se o dev vender, ou se a linha de suporte quebrar.";

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

describe("ProposalCard: 'Plano para executar à mão' (manual_plan)", () => {
  it("shows nothing about a plan when the proposal carries none (older loop or research set)", () => {
    renderCard();
    expect(screen.queryByText("Plano para executar à mão")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copiar mint" })).not.toBeInTheDocument();
  });

  it("shows the whole plan, the countdown to the expiry and the copy button when the loop wrote one", () => {
    renderCard({ row: { ...ROW, manual_plan: PLAN } });
    const block = screen.getByRole("region", { name: "Plano para executar à mão" });
    expect(block).toHaveTextContent(PLAN);
    // 12:05:00Z against 12:00:00Z -- the same countdown the header shows.
    expect(block).toHaveTextContent("expira em 5 min 0 s");
    expect(screen.getByRole("button", { name: "Copiar mint" })).toBeEnabled();
  });

  it("copies the mint to the clipboard and says so", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    stubClipboard(writeText);
    renderCard({ row: { ...ROW, manual_plan: PLAN } });
    fireEvent.click(screen.getByRole("button", { name: "Copiar mint" }));
    expect(writeText).toHaveBeenCalledWith(ROW.mint);
    expect(await screen.findByRole("button", { name: "Mint copiado" })).toBeInTheDocument();
  });

  it("says honestly when the browser refuses the clipboard, and keeps the mint readable to select", async () => {
    stubClipboard(vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error("denied")));
    renderCard({ row: { ...ROW, manual_plan: PLAN } });
    fireEvent.click(screen.getByRole("button", { name: "Copiar mint" }));
    expect(await screen.findByText("não foi possível copiar — selecione o mint")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Plano para executar à mão" })).toHaveTextContent(ROW.mint);
  });
});
